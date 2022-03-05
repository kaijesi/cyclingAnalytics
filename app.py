import os
import operator
import requests

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    # Find current user's stock portfolio
    portfolio = db.execute("SELECT symbol, amount_owned FROM ownedstock WHERE owner = :runninguser", runninguser=session.get("user_id"))
    # For each stock the user owns
    # Keep track of total sum
    stocks_balance = 0
    for record in portfolio:
        # Find out the current value of one share of this symbol
        record["current_price"] = lookup(record["symbol"])["price"]
        record["current_total_value"] = float(record["current_price"]) * float(record["amount_owned"])
        record["symbol"] = record["symbol"].upper()
        stocks_balance += record["current_total_value"]
    # Find user's current cash balance
    if not(db.execute("SELECT cash FROM users WHERE id = :runninguser", runninguser=session.get("user_id"))):
        return redirect("/")
    cash = db.execute("SELECT cash FROM users WHERE id = :runninguser", runninguser=session.get("user_id"))[0]
    cash_balance = round(cash["cash"], 2)
    total = float(cash_balance + stocks_balance)
    return render_template("index.html", portfolio=portfolio, cash=cash_balance, stocks=stocks_balance, total = total)

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    # If get request, show buy page
    if request.method == "GET":
        return render_template("buy.html")
    # If post request, place order
    # Verify input
    # Check if either input field is empty
    if not (request.form.get("symbol") and request.form.get("shares")):
        return apology("Please provide both a stock symbol and an amount you want to purchase")
    # Check if shares input is integer
    if not request.form.get("shares").isdigit():
        return apology("Please provide a whole number of shares")
    # If both filled out, store in variables
    symbol = request.form.get("symbol")
    amount = int(request.form.get("shares"))
    # Check for valid amount (>0)
    if amount < 1:
        return apology("Please provide an amount >0 of shares you want to purchase")
    # Check if stock symbol exists
    stockinfo = lookup(symbol)
    if not stockinfo:
        return apology("Symbol not found")
    # If it does, check if the user can afford this
    buyer = db.execute("SELECT cash FROM users WHERE id = :runninguser LIMIT 1", runninguser=session.get("user_id"))[0]
    current_price = stockinfo.get("price")
    if amount * current_price > buyer.get("cash"):
        return apology("You can't afford this many shares. Price: {} vs Your Cash: {}".format(round(amount * current_price, 2), round(buyer.get("cash"), 2)))
    # If user can afford this, log a transaction with timestamp
    # Find out current time in UTC seconds
    current_time = int(datetime.utcnow().timestamp())
    db.execute("INSERT INTO transactions (owner, symbol, amount, value_at_transaction, purchase, timestamp_unixsec) VALUES (:runninguser, :symbol, :amount, :value_at_transaction, 1, :current_time)", runninguser=session.get("user_id"), symbol=symbol, amount=amount, value_at_transaction=current_price, current_time=current_time)
    # Deduct total purchase value from user record
    new_cash = buyer.get("cash") - amount * current_price
    db.execute("UPDATE users SET cash = :new_cash WHERE id = :runninguser", new_cash=new_cash, runninguser=session.get("user_id"))
    # Also update or create their ownership record for this symbol
    # Find out if they already have an ownership record for this symbol
    ownedstock = db.execute("SELECT id, owner, symbol, amount_owned FROM ownedstock WHERE owner = :runninguser AND symbol = :symbol", runninguser=session.get("user_id"), symbol=symbol.upper())
    # Add the newly ordered shares to the existing ones if they already own stock
    if ownedstock:
        ownedrecord = ownedstock[0]
        # Find out previously owned amount, add new order to this
        new_owned = ownedrecord.get("amount_owned") + amount
        # Update database
        db.execute("UPDATE ownedstock SET amount_owned = :new_owned WHERE id = :ownedrecord_id", new_owned=new_owned, ownedrecord_id=ownedrecord.get("id"))
    # If they don't own stock for this symbol yet, add new ownership record
    else:
        db.execute("INSERT INTO ownedstock (owner, symbol, amount_owned) VALUES (:runninguser, :symbol, :amount)", runninguser=session.get("user_id"), symbol=symbol.upper(), amount=amount)
    # Return to index if action was made from index page
    if request.form.get("submit_button") == "index_edit":
        return redirect("/")
    # Else show transaction summary
    return render_template("transaction_summary.html", type="purchase", amount=amount, price=current_price, total=amount*current_price, symbol=symbol.upper(), company=stockinfo.get("name"), cash=new_cash)


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    # Get transaction history for running user
    transaction_history = db.execute("SELECT symbol, amount, value_at_transaction, purchase, total_transaction_value, timestamp_unixsec FROM transactions WHERE owner = :runninguser", runninguser=session.get("user_id"))
    if not transaction_history:
        return apology("You have not bought/sold any shares yet")
    # Order list by transaction date
    transaction_history.sort(key=operator.itemgetter("timestamp_unixsec"), reverse=True)
    # Transform values in transaction history into html-friendly format
    for transaction in transaction_history:
        transaction["symbol"] = transaction.get("symbol").upper()
        if transaction.get("purchase") == 1:
            transaction["purchase"] = "Purchase"
        else:
            transaction["purchase"] = "Sale"
        transaction["timestamp_unixsec"] = datetime.utcfromtimestamp(transaction.get("timestamp_unixsec")).strftime("%Y-%m-%d %H:%M:%S")
    return render_template("history.html", transactions=transaction_history)

@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    # If get request, show quotation page
    if request.method == "GET":
        return render_template("quote.html")
    # If post request, look up current price of stock
    # Check for empty stock symbol
    if not request.form.get("symbol"):
        return apology("Please provide a ticker symbol")
    # If not empty, check for price
    quote = lookup(request.form.get("symbol"))
    # Check if symbol exists
    if not quote:
        return apology("Symbol not found")
    # If it does, return quote
    return render_template("quoted.html", company=quote.get("name"), price=quote.get("price"))


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    # If get request, show registration page
    if request.method == "GET":
        return render_template("register.html")
    # If post request, register the user
    # Check if username, password and confirmation fields are filled out
    if not (request.form.get("username") and request.form.get("password") and request.form.get("confirmation")):
        return apology("Please provide a username and password")
    # Store input
    username = request.form.get("username")
    password = request.form.get("password")
    confirmation = request.form.get("confirmation")
    # Check if passwords match
    if password != confirmation:
        return apology("Passwords don't match")
    # Check if username already exists
    usernamecheck = db.execute("SELECT * FROM users WHERE username = ?", username)
    if len(usernamecheck) > 0:
        return apology("Username already exists")
    # If no return until now, register the user
    # Generate password hash
    hashedpw = generate_password_hash(password)
    db.execute("INSERT INTO users (username, hash) VALUES (:username, :hashedpw)", username=username, hashedpw=hashedpw)
    return redirect("/")





@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    # If get request, show sell page
    if request.method == "GET":
        # Find out which stocks the person owns
        allstock = db.execute("SELECT symbol FROM ownedstock WHERE owner = :runninguser", runninguser=session.get("user_id"))
        return render_template("sell.html", stocks=allstock)
    # If post request, place order
    # Verify input
    # Check if either input field is empty
    if not (request.form.get("symbol") and request.form.get("shares")):
        return apology("Please provide both a stock symbol and an amount you want to sell")
    # Check if shares input is integer
    if not request.form.get("shares").isdigit():
        return apology("Please provide a whole number of shares")
    # If both filled out, store in variables
    symbol = request.form.get("symbol")
    amount = int(request.form.get("shares"))
    # Check for valid amount (>0)
    if amount < 1:
        return apology("Please provide an amount >0 of shares you want to sell")
    # Check if stock symbol exists
    stockinfo = lookup(symbol)
    if not stockinfo:
        return apology("Symbol not found")
    # If it does, check if the user owns any of this stock
    ownedstock = db.execute("SELECT id, symbol, amount_owned FROM ownedstock WHERE owner = :runninguser AND symbol = :symbol", runninguser=session.get("user_id"), symbol=symbol)
    if not ownedstock:
        return apology("You do not own any shares of this company")
    # If they own shares, check if they have enough for this purchase
    ownedrecord = ownedstock[0]
    if ownedrecord.get("amount_owned") < amount:
        return apology("You do not own enough shares of this company to complete the sale")
    # If they can perform sale, log a transaction with timestamp
    current_time = int(datetime.utcnow().timestamp())
    current_price = stockinfo.get("price")
    db.execute("INSERT INTO transactions (owner, symbol, amount, value_at_transaction, purchase, timestamp_unixsec) VALUES (:runninguser, :symbol, :amount, :value_at_transaction, 0, :current_time)", runninguser=session.get("user_id"), symbol=symbol, amount=amount, value_at_transaction=current_price, current_time=current_time)
    # Add total purchase value to user record
    seller = db.execute("SELECT cash FROM users WHERE id = :runninguser LIMIT 1", runninguser=session.get("user_id"))[0]
    new_cash = float(seller.get("cash")) + amount * current_price
    db.execute("UPDATE users SET cash = :new_cash WHERE id = :runninguser", new_cash=new_cash, runninguser=session.get("user_id"))
    # Also update their ownership record for this symbol
    # Delete if sold amount is total owned
    owned_amount = int(ownedrecord.get("amount_owned"))
    if owned_amount == amount:
        db.execute("DELETE FROM ownedstock WHERE id = :ownedrecord_id", ownedrecord_id=ownedrecord.get("id"))
    # Update if sold amount less than total owned
    if owned_amount > amount:
        new_amount = owned_amount - amount
        db.execute("UPDATE ownedstock SET amount_owned = :new_amount WHERE id = :ownedrecord_id", ownedrecord_id=ownedrecord.get("id"), new_amount=new_amount)
    # Return to index if action was made from index page
    if request.form.get("submit_button") == "index_edit":
        return redirect("/")
    # Else show transaction summary
    return render_template("transaction_summary.html", type="sale", amount=amount, price=current_price, total=amount*current_price, symbol=symbol.upper(), company=stockinfo.get("name"), cash=new_cash)

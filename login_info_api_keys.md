API token from IEX: pk_c60b278ddbf34a5aa1dbf16758f040b1
Login for your test user: kai, abc

CREATE TABLE IF NOT EXISTS 'ownedstock' ('id' INTEGER PRIMARY KEY NOT NULL, 'owner' INTEGER, 'symbol' TEXT, 'number_of_shares' INTEGER);
CREATE TABLE IF NOT EXISTS 'transactions' ('id' INTEGER PRIMARY KEY NOT NULL, 'symbol' INTEGER, 'number_of_shares' INTEGER, 'price_at_transaction' NUMERIC, 'timestamp' DATETIME);
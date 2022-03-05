import requests
import sys
import json

token = 'hF8c3mQTZuuh2rUidyR4vOSWjVcjdJlb'
response = requests.get('https://www.cyclinganalytics.com/api/me/rides', headers={'Authorization': 'Bearer ' + token})
print(response.text)
newvalue = json.loads(response.text)
print(newvalue)


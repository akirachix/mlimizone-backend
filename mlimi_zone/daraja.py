import requests
from django.conf import settings
import base64
from datetime import datetime
from requests.auth import HTTPBasicAuth

class DarajaClient:
    def __init__(self):
        config = getattr(settings, 'DARJA_CONFIG', {})
        self.consumer_key = config.get('CONSUMER_KEY')
        self.consumer_secret = config.get('CONSUMER_SECRET')
        self.business_shortcode = config.get('BUSINESS_SHORT_CODE')
        self.passkey = config.get('PASSKEY')
        self.callback_url = config.get('CALLBACK_URL')
        self.base_url = 'https://sandbox.safaricom.co.ke'
        self.access_token = None

    def get_access_token(self):
        auth_url = f"{self.base_url}/oauth/v1/generate?grant_type=client_credentials"
        response = requests.get(auth_url, auth=HTTPBasicAuth(self.consumer_key, self.consumer_secret))
        if response.status_code == 200:
            self.access_token = response.json().get('access_token')
            return self.access_token
        else:
            raise Exception(f"Failed to get access token: {response.text}")

    def stk_push(self, phone_number, amount, account_reference="MlimiZone", transaction_desc="Payment for crops"):
        if not self.access_token:
            self.get_access_token()

        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        password_str = self.business_shortcode + self.passkey + timestamp
        password = base64.b64encode(password_str.encode('utf-8')).decode('utf-8')

        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json',
        }
        payload = {
            "BusinessShortCode": self.business_shortcode,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": amount,
            "PartyA": phone_number,
            "PartyB": self.business_shortcode,
            "PhoneNumber": phone_number,
            "CallBackURL": self.callback_url,
            "AccountReference": account_reference,
            "TransactionDesc": transaction_desc,
        }
        stk_url = f"{self.base_url}/mpesa/stkpush/v1/processrequest"
        response = requests.post(stk_url, json=payload, headers=headers)
        if response.status_code == 200:
            return response.json()
        else:
            return {"error": response.text}

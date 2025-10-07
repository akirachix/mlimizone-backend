import os
import requests
from datetime import datetime
from base64 import b64encode
import logging

logger = logging.getLogger(__name__)

class DarajaClient:
    def __init__(self):
        self.consumer_key = os.getenv('DARJA_CONSUMER_KEY')
        self.consumer_secret = os.getenv('DARJA_CONSUMER_SECRET')
        self.business_shortcode = os.getenv('DARJA_SHORTCODE')
        self.passkey = os.getenv('DARJA_PASSKEY')
        self.callback_url = "https://mydomain.com/path"
        self.callback_url = self.callback_url.strip()
        sandbox_mode = os.getenv('SANDBOX_MODE', 'True').lower() == 'true'
        self.base_url = 'https://sandbox.safaricom.co.ke' if sandbox_mode else 'https://api.safaricom.co.ke'
        self.access_token = None

        missing = []
        for name, value in [
            ('DARJA_CONSUMER_KEY', self.consumer_key),
            ('DARJA_CONSUMER_SECRET', self.consumer_secret),
            ('DARJA_SHORTCODE', self.passkey),
        ]:
            if not value:
                missing.append(name)
                logger.error(f"Missing environment variable: {name}")

        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

        logger.info(f"DarajaClient initialized with HARDCODED callback URL: {repr(self.callback_url)}")

    def get_access_token(self):
        url = f"{self.base_url}/oauth/v1/generate?grant_type=client_credentials"
        auth = b64encode(f"{self.consumer_key}:{self.consumer_secret}".encode()).decode()
        headers = {'Authorization': f'Basic {auth}'}
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            token = response.json().get('access_token')
            if not token:
                raise ValueError("No access token in response")
            self.access_token = token
            logger.info("Access token acquired.")
            return token
        except Exception as e:
            error_text = getattr(response, 'text', str(e))
            logger.error(f"Failed to get access token: {error_text}")
            raise ValueError(f"Access token error: {error_text}")

    def stk_push(self, phone_number, amount, account_reference="MlimiZone", transaction_desc="Payment for crops"):
        if not isinstance(phone_number, str) or not phone_number.startswith('254') or len(phone_number) != 12:
            return {'error': 'Invalid phone number. Must be 254XXXXXXXXX'}

        try:
            amount = int(float(amount))
            if amount <= 0:
                raise ValueError("Amount must be positive")
        except (ValueError, TypeError):
            return {'error': 'Amount must be a positive number'}

        if not self.callback_url.startswith('https://'):
            return {'error': 'CallBackURL must be HTTPS'}

        if not self.access_token:
            try:
                self.get_access_token()
            except Exception as e:
                return {'error': f"Authentication failed: {str(e)}"}

        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        password = b64encode(f"{self.business_shortcode}{self.passkey}{timestamp}".encode()).decode()
        logger.info(f"Sending STK Push with CallBackURL: {repr(self.callback_url)}")

        payload = {
            "BusinessShortCode": self.business_shortcode,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": str(amount),
            "PartyA": phone_number,
            "PartyB": self.business_shortcode,
            "PhoneNumber": phone_number,
            "CallBackURL": self.callback_url,
            "AccountReference": account_reference,
            "TransactionDesc": transaction_desc
        }

        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }

        url = f"{self.base_url}/mpesa/stkpush/v1/processrequest"
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            response.raise_for_status()
            result = response.json()
            logger.info(f"STK Push successful: {result}")
            return result
        except requests.exceptions.HTTPError as e:
            error_text = getattr(e.response, 'text', 'No response')
            logger.error(f"STK Push failed: {error_text}")
            return {'error': f"HTTP error: {error_text}"}
        except Exception as e:
            logger.error(f"Network error: {str(e)}")
            return {'error': f"Network error: {str(e)}"}
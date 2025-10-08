import json
import requests
import os, sys
from dotenv import load_dotenv
import base64

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mlimizone.settings')

load_dotenv()
USERNAME_SMS =os.getenv("USERNAME_SMS")
PASSWORD= os.getenv("PASSWORD")
SOURCE = os.getenv("SOURCE")


def send_sms(destination, message):
    url = "https://api.smsleopard.com/v1/sms/send"
    credentials = f"{USERNAME_SMS}:{PASSWORD}"
    base64_credentials = base64.b64encode(credentials.encode()).decode()
    headers = {
    "Authorization": f'Basic {base64_credentials}',
    "Content-Type": "application/json"
}
    payload = {
        "source": SOURCE,
        "multi": False,
        "message": message,
        "destination": [
            {
                "number": destination
            }
        ]
    }

    response = requests.post(url, data=json.dumps(payload), headers=headers)
    if response.status_code == 200:
        print(response.text)
        print("SMS sent successfully")
        return response.json()
    else:
        print(response.text)
        print("Waiting to send SMS")
        return {"status_code": response.status_code, "message": response.text}
    
if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python helpers.py <phone_number> <message>")
    else:
        phone_number = sys.argv[1]
        message = sys.argv[2]
        send_sms(phone_number, message)
    

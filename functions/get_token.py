import sys
from google.oauth2 import service_account
import google.auth.transport.requests

try:
    creds = service_account.Credentials.from_service_account_file(
        'serviceAccountKey.json',
        scopes=['https://www.googleapis.com/auth/cloud-platform', 'https://www.googleapis.com/auth/firebase']
    )
    auth_req = google.auth.transport.requests.Request()
    creds.refresh(auth_req)
    print(creds.token)
except Exception as e:
    print(f"Error: {e}", file=sys.stderr)

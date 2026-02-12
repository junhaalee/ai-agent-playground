"""
로컬에서 OAuth 토큰을 발급받는 스크립트.

사용법:
  pip install google-auth google-auth-oauthlib
  python generate_token.py

"""

import os
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
CLIENT_SECRET_FILE = os.path.join("resources", "client_secret.json")
TOKEN_FILE = os.path.join("resources", "token.json")

flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
creds = flow.run_local_server(port=8080, access_type="offline", prompt="consent")

with open(TOKEN_FILE, "w") as f:
    f.write(creds.to_json())

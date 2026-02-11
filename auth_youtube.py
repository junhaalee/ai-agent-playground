"""
Run this script ONCE to authenticate your YouTube account.
After successful auth, youtube_token.json is saved and the web app can upload without issues.

Usage:
    python3 auth_youtube.py
"""
import os
from google_auth_oauthlib.flow import InstalledAppFlow

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CLIENT_SECRETS_FILE = os.path.join(BASE_DIR, "client_secret.json")
TOKEN_FILE = os.path.join(BASE_DIR, "youtube_token.json")
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def main():
    if not os.path.exists(CLIENT_SECRETS_FILE):
        print(f"[오류] {CLIENT_SECRETS_FILE} 파일이 없습니다.")
        print()
        print("Google Cloud Console에서 OAuth 2.0 클라이언트 ID를 생성하고")
        print("다운로드한 JSON 파일을 client_secret.json 으로 저장해주세요.")
        return

    if os.path.exists(TOKEN_FILE):
        print(f"[정보] {TOKEN_FILE} 이미 존재합니다.")
        answer = input("다시 인증하시겠습니까? (y/N): ").strip().lower()
        if answer != "y":
            print("취소되었습니다.")
            return

    print("브라우저가 열립니다. Google 계정으로 로그인해주세요...")
    print()

    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
    creds = flow.run_local_server(port=8090)

    with open(TOKEN_FILE, "w") as f:
        f.write(creds.to_json())

    print()
    print(f"인증 완료! 토큰이 저장되었습니다: {TOKEN_FILE}")
    print("이제 웹에서 유튜브 업로드 기능을 사용할 수 있습니다.")


if __name__ == "__main__":
    main()

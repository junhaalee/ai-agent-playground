import os
import time
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from util.WatchdogUtil import start_watching

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
CLIENT_SECRET_FILE = "client_secret.json"
TOKEN_FILE = "token.json"
WATCH_DIR = os.environ.get("WATCH_DIR", "/app/videos")

# OAuth2 인증
#
# [client_secret.json] - Google Cloud Console에서 발급받은 앱 식별 정보 (앱당 1개, 변경 없음)
# [token.json]         - 사용자 인증 후 발급되는 토큰 파일
#   ├─ access_token    - YouTube API 호출에 사용 (유효기간: 1시간)
#   └─ refresh_token   - access_token 만료 시 자동 갱신에 사용 (반영구적, 6개월 미사용 시 만료)
#
# 인증 흐름:
#   1. token.json 존재 → access_token 유효하면 그대로 사용
#   2. access_token 만료 → refresh_token으로 자동 갱신
#   3. refresh_token도 없거나 만료 → 브라우저에서 재인증 (최초 실행 시)
def get_authenticated_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        from google.oauth2.credentials import Credentials
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
            creds = flow.run_local_server(port=8080, access_type="offline", prompt="consent")
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    return build("youtube", "v3", credentials=creds)

def upload_video(youtube, file_path, title, description, tags, category_id="22", privacy="private"):
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": category_id,
        },
        "status": {
            # TODO : privacyStatus는 추후 수정 필요. privacy는 테스트를 위한 설정
            "privacyStatus": privacy,  # "public", "unlisted", "private"
        },
    }

    media = MediaFileUpload(file_path, chunksize=-1, resumable=True)

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = request.execute()
    print(f"업로드 완료: [{title}] https://www.youtube.com/watch?v={response['id']}")
    return response

def wait_for_file_ready(file_path, interval=2, stable_count=3):
    """파일 크기가 변하지 않을 때까지 대기"""
    count = 0
    prev_size = -1
    while count < stable_count:
        size = os.path.getsize(file_path)
        if size > 0 and size == prev_size:
            count += 1
        else:
            count = 0
        prev_size = size
        time.sleep(interval)
    print(f"파일 준비 완료: {file_path} ({prev_size} bytes)")

def handle_new_video(file_path):
    wait_for_file_ready(file_path)
    youtube = get_authenticated_service()
    title = os.path.splitext(os.path.basename(file_path))[0]

    # TODO : 영상 관련 메타 데이터 입력 해줘야 함
    upload_video(
        youtube,
        file_path=file_path,
        title=title,
        description="",
        tags=[""],
        privacy="private",
    )

if __name__ == "__main__":
    start_watching(WATCH_DIR, handle_new_video)

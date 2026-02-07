import os
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
CLIENT_SECRET_FILE = "client_secret.json"
TOKEN_FILE = "token.json"

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

if __name__ == "__main__":
    youtube = get_authenticated_service()
    upload_video(
        youtube,
        file_path="/Users/user/Downloads/output.mp4",
        title="테스트 영상",
        description="API로 업로드한 테스트 영상입니다.",
        tags=["테스트", "API"],
        privacy="private",
    )

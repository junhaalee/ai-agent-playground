import os
import logging
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

import config

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
CLIENT_SECRETS_FILE = os.path.join(config.BASE_DIR, "client_secret.json")
TOKEN_FILE = os.path.join(config.BASE_DIR, "youtube_token.json")


def _get_authenticated_service():
    """Authenticate and return a YouTube API service object."""
    creds = None

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(TOKEN_FILE, "w") as f:
                f.write(creds.to_json())
        else:
            raise RuntimeError(
                "YouTube 인증이 필요합니다. 터미널에서 먼저 실행해주세요:\n"
                "  python3 auth_youtube.py"
            )

    return build("youtube", "v3", credentials=creds)


def upload_video(video_path, title, description=""):
    """
    Upload a video to YouTube as a Short.
    Returns dict with video_id and url.
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"영상 파일을 찾을 수 없습니다: {video_path}")

    youtube = _get_authenticated_service()

    body = {
        "snippet": {
            "title": title,
            "description": description or f"{title} #Shorts",
            "tags": ["Shorts", "뉴스", "정치", "시사"],
            "categoryId": "25",  # News & Politics
        },
        "status": {
            "privacyStatus": "private",  # Start as private for safety
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(
        video_path,
        mimetype="video/mp4",
        resumable=True,
        chunksize=1024 * 1024,
    )

    request = youtube.videos().insert(
        part=",".join(body.keys()),
        body=body,
        media_body=media,
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            logger.info(f"Upload progress: {int(status.progress() * 100)}%")

    video_id = response["id"]
    video_url = f"https://www.youtube.com/shorts/{video_id}"

    logger.info(f"Upload complete: {video_url}")

    return {
        "video_id": video_id,
        "url": video_url,
    }

import os
from dotenv import load_dotenv

load_dotenv()

NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Video dimensions (YouTube Shorts = 9:16)
SHORTS_WIDTH = 1080
SHORTS_HEIGHT = 1920

# Directories
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
TEMP_DIR = os.path.join(BASE_DIR, "temp")

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

# Speed multiplier mapping
SPEED_MAP = {
    "slow": 0.8,
    "normal": 1.0,
    "fast": 1.2,
    "very-fast": 1.5,
}

# 기사 1개당 할당 시간 (초)
SECONDS_PER_ARTICLE = 5

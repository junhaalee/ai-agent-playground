import os
import logging
import requests
from PIL import Image
from io import BytesIO

import config

logger = logging.getLogger(__name__)

NAVER_IMAGE_API = "https://openapi.naver.com/v1/search/image"


def fetch_images(keyword, count, temp_dir):
    """네이버 이미지 검색 API로 키워드 관련 이미지를 다운로드한다.

    Args:
        keyword: 검색 키워드
        count: 필요한 이미지 수
        temp_dir: 저장 디렉토리

    Returns:
        이미지 파일 경로 리스트 (1080x1920 리사이즈 완료)
    """
    os.makedirs(temp_dir, exist_ok=True)

    headers = {
        "X-Naver-Client-Id": config.NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": config.NAVER_CLIENT_SECRET,
    }

    # 여유분 포함하여 요청 (다운로드 실패 대비)
    params = {
        "query": keyword,
        "display": min(count * 2, 100),
        "sort": "sim",
    }

    image_urls = []
    try:
        resp = requests.get(NAVER_IMAGE_API, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        for item in data.get("items", []):
            url = item.get("link", "")
            if url:
                image_urls.append(url)
    except requests.RequestException as e:
        logger.error(f"[이미지검색] API 실패 ({keyword}): {e}")

    logger.info(f"[이미지검색] '{keyword}' → {len(image_urls)}개 URL 수집")

    # 이미지 다운로드 + 리사이즈
    image_paths = []
    for i, url in enumerate(image_urls):
        if len(image_paths) >= count:
            break

        output_path = os.path.join(temp_dir, f"bg_{keyword}_{i}.png")
        if _download_and_resize(url, output_path):
            image_paths.append(output_path)

    logger.info(f"[이미지검색] '{keyword}' → {len(image_paths)}장 다운로드 완료")
    return image_paths


def _download_and_resize(url, output_path):
    """이미지를 다운로드하고 1080x1920으로 크롭/리사이즈한다."""
    try:
        resp = requests.get(url, timeout=8, headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": url,
        })
        resp.raise_for_status()

        img = Image.open(BytesIO(resp.content)).convert("RGB")

        # 9:16 비율로 중앙 크롭 후 리사이즈
        target_w, target_h = config.SHORTS_WIDTH, config.SHORTS_HEIGHT
        target_ratio = target_w / target_h  # 0.5625

        img_w, img_h = img.size
        img_ratio = img_w / img_h

        if img_ratio > target_ratio:
            # 이미지가 더 넓음 → 좌우 크롭
            new_w = int(img_h * target_ratio)
            left = (img_w - new_w) // 2
            img = img.crop((left, 0, left + new_w, img_h))
        else:
            # 이미지가 더 높음 → 상하 크롭
            new_h = int(img_w / target_ratio)
            top = (img_h - new_h) // 2
            img = img.crop((0, top, img_w, top + new_h))

        img = img.resize((target_w, target_h), Image.LANCZOS)
        img.save(output_path, "PNG")
        return True

    except Exception as e:
        logger.debug(f"[이미지다운] 실패 ({url[:60]}...): {e}")
        return False

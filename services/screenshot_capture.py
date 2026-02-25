import os
import logging
from PIL import Image, ImageDraw, ImageFont, ImageFilter

import config

logger = logging.getLogger(__name__)

# Font candidates (나눔고딕 Bold 최우선)
_FONT_CANDIDATES = [
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fonts", "GmarketSansTTFBold.ttf"),
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fonts", "NanumGothicBold.ttf"),
    "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
]


def _get_font(size=32):
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _wrap_text(draw, text, font, max_width):
    """텍스트를 max_width에 맞춰 줄바꿈."""
    lines = []
    current_line = ""
    for char in text:
        test = current_line + char
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current_line = test
        else:
            if current_line:
                lines.append(current_line)
            current_line = char
    if current_line:
        lines.append(current_line)
    return lines or [text]


def _generate_gradient_bg():
    """이미지가 없을 때 사용할 기본 그라데이션 배경."""
    W, H = config.SHORTS_WIDTH, config.SHORTS_HEIGHT
    img = Image.new("RGB", (W, H), (18, 18, 35))
    draw = ImageDraw.Draw(img)
    for y in range(H):
        ratio = y / H
        r = int(18 + (30 - 18) * ratio)
        g = int(18 + (25 - 18) * ratio)
        b = int(35 + (60 - 35) * ratio)
        draw.line([(0, y), (W, y)], fill=(r, g, b))
    return img


def overlay_news_info(bg_image_path, article, output_path, keyword=None):
    """배경 이미지 위에 어두운 오버레이 + 뉴스 정보를 합성한다.

    Args:
        bg_image_path: 배경 이미지 경로 (None이면 그라데이션 사용)
        article: 기사 dict (title, source, link)
        output_path: 출력 경로
        keyword: 키워드 태그 (optional)
    """
    W, H = config.SHORTS_WIDTH, config.SHORTS_HEIGHT
    title = article.get("title", "뉴스")
    source = article.get("source", "")

    # 출처 도메인 추출
    try:
        from urllib.parse import urlparse
        domain = urlparse(source or article.get("link", "")).netloc.replace("www.", "")
    except Exception:
        domain = ""

    # 배경 이미지 로드
    if bg_image_path and os.path.exists(bg_image_path):
        bg = Image.open(bg_image_path).convert("RGB")
        bg = bg.resize((W, H), Image.LANCZOS)
    else:
        bg = _generate_gradient_bg()

    # RGBA로 변환하여 오버레이 합성
    img = bg.convert("RGBA")

    # 어두운 반투명 오버레이 (상단 영역 — 제목이 읽히도록)
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # 상단 그라데이션 오버레이 (위에서 아래로 점점 투명)
    for y in range(H // 2):
        alpha = int(180 * (1 - y / (H // 2)))
        draw.line([(0, y), (W, y)], fill=(0, 0, 0, alpha))

    # 상단 장식 라인
    draw.rectangle([(0, 0), (W, 6)], fill=(67, 97, 238, 255))

    # 키워드 태그
    y_cursor = 200
    if keyword:
        font_tag = _get_font(30)
        tag_text = f"# {keyword}"
        bbox = draw.textbbox((0, 0), tag_text, font=font_tag)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        tag_pad_h, tag_pad_v = 20, 10
        tag_x = (W - tw) // 2 - tag_pad_h
        draw.rounded_rectangle(
            [(tag_x, y_cursor), (tag_x + tw + tag_pad_h * 2, y_cursor + th + tag_pad_v * 2)],
            radius=20,
            fill=(67, 97, 238, 230),
        )
        draw.text((tag_x + tag_pad_h, y_cursor + tag_pad_v), tag_text,
                  fill=(255, 255, 255, 255), font=font_tag)
        y_cursor += th + tag_pad_v * 2 + 40

    # 제목 (큰 글씨)
    font_title = _get_font(46)
    max_title_w = W - 120
    title_lines = _wrap_text(draw, title, font_title, max_title_w)
    title_lines = title_lines[:4]

    title_line_h = 64
    for line in title_lines:
        bbox = draw.textbbox((0, 0), line, font=font_title)
        tw = bbox[2] - bbox[0]
        x = (W - tw) // 2
        # 텍스트 그림자
        draw.text((x + 2, y_cursor + 2), line, fill=(0, 0, 0, 180), font=font_title)
        draw.text((x, y_cursor), line, fill=(255, 255, 255, 255), font=font_title)
        y_cursor += title_line_h

    # 출처
    if domain:
        font_meta = _get_font(24)
        y_cursor += 20
        bbox = draw.textbbox((0, 0), domain, font=font_meta)
        tw = bbox[2] - bbox[0]
        draw.text(((W - tw) // 2 + 1, y_cursor + 1), domain,
                  fill=(0, 0, 0, 150), font=font_meta)
        draw.text(((W - tw) // 2, y_cursor), domain,
                  fill=(200, 200, 220, 255), font=font_meta)

    result = Image.alpha_composite(img, overlay).convert("RGB")
    result.save(output_path, "PNG")


def generate_frames_for_article(bg_images, article, temp_dir, article_idx, keyword=None):
    """기사 하나에 대해 배경 이미지별 프레임을 생성한다.

    Args:
        bg_images: 배경 이미지 경로 리스트
        article: 기사 dict
        temp_dir: 임시 디렉토리
        article_idx: 기사 인덱스
        keyword: 키워드 태그

    Returns:
        뉴스 정보가 오버레이된 프레임 이미지 경로 리스트
    """
    os.makedirs(temp_dir, exist_ok=True)
    frame_paths = []

    if not bg_images:
        # 배경 이미지 없으면 그라데이션 1장
        output_path = os.path.join(temp_dir, f"card_{article_idx}_0.png")
        overlay_news_info(None, article, output_path, keyword=keyword)
        frame_paths.append(output_path)
        return frame_paths

    for i, bg_path in enumerate(bg_images):
        output_path = os.path.join(temp_dir, f"card_{article_idx}_{i}.png")
        overlay_news_info(bg_path, article, output_path, keyword=keyword)
        frame_paths.append(output_path)

    return frame_paths

import os
import logging
from PIL import Image, ImageDraw, ImageFont

import config

logger = logging.getLogger(__name__)

# 자막 위치 (1920 높이 기준)
POSITION_MAP = {
    "top": 1100,
    "middle": 1350,
    "bottom": 1600,
}

# Font candidates
_FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
]


def _get_font(size=40):
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


def render_subtitle_on_image(image_path, text, position, output_path):
    """뉴스 카드 이미지 위에 자막 한 줄을 렌더링한다.

    한 줄이 길면 자동 줄바꿈하되, 기본적으로 한 문장 = 한 프레임.
    """
    if not text or not text.strip():
        img = Image.open(image_path)
        img.save(output_path, "PNG")
        return

    img = Image.open(image_path).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    font = _get_font(44)
    y_center = POSITION_MAP.get(position, POSITION_MAP["bottom"])

    max_width = config.SHORTS_WIDTH - 100
    lines = _wrap_text(draw, text.strip(), font, max_width)

    line_height = 60
    total_height = len(lines) * line_height
    padding_v = 20
    padding_h = 30

    # 배경 박스 크기 계산
    max_line_w = 0
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        lw = bbox[2] - bbox[0]
        if lw > max_line_w:
            max_line_w = lw

    box_top = y_center - total_height // 2 - padding_v
    box_bottom = y_center + total_height // 2 + padding_v
    box_left = (config.SHORTS_WIDTH - max_line_w) // 2 - padding_h
    box_right = (config.SHORTS_WIDTH + max_line_w) // 2 + padding_h

    draw.rounded_rectangle(
        [(box_left, box_top), (box_right, box_bottom)],
        radius=14,
        fill=(0, 0, 0, 190),
    )

    # 텍스트 그리기
    y = y_center - total_height // 2
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        tw = bbox[2] - bbox[0]
        x = (config.SHORTS_WIDTH - tw) // 2
        draw.text((x, y), line, fill=(255, 255, 255, 255), font=font)
        y += line_height

    result = Image.alpha_composite(img, overlay).convert("RGB")
    result.save(output_path, "PNG")

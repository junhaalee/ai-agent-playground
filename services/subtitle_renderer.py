import os
import logging
from PIL import Image, ImageDraw, ImageFont

import config

logger = logging.getLogger(__name__)

# Subtitle Y positions for 1920-height frame
POSITION_MAP = {
    "top": 200,
    "middle": 860,
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


def render_subtitle_on_image(image_path, text, position, output_path):
    """
    Render subtitle text onto a copy of the image with a semi-transparent background.
    position: "top", "middle", or "bottom"
    """
    if not text or not text.strip():
        # No subtitle to render, just copy the image
        img = Image.open(image_path)
        img.save(output_path, "PNG")
        return

    img = Image.open(image_path).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    font = _get_font(42)
    y_center = POSITION_MAP.get(position, POSITION_MAP["bottom"])

    # Word-wrap text to fit within image width with padding
    max_width = config.SHORTS_WIDTH - 80  # 40px padding each side
    lines = _wrap_text(draw, text, font, max_width)

    # Calculate total text block height
    line_height = 56
    total_height = len(lines) * line_height
    padding_v = 16
    padding_h = 24

    # Draw background box
    box_top = y_center - total_height // 2 - padding_v
    box_bottom = y_center + total_height // 2 + padding_v

    # Find max line width for box
    max_line_w = 0
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        lw = bbox[2] - bbox[0]
        if lw > max_line_w:
            max_line_w = lw

    box_left = (config.SHORTS_WIDTH - max_line_w) // 2 - padding_h
    box_right = (config.SHORTS_WIDTH + max_line_w) // 2 + padding_h

    draw.rounded_rectangle(
        [(box_left, box_top), (box_right, box_bottom)],
        radius=12,
        fill=(0, 0, 0, 180),
    )

    # Draw text lines
    y = y_center - total_height // 2
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        tw = bbox[2] - bbox[0]
        x = (config.SHORTS_WIDTH - tw) // 2
        draw.text((x, y), line, fill=(255, 255, 255, 255), font=font)
        y += line_height

    result = Image.alpha_composite(img, overlay).convert("RGB")
    result.save(output_path, "PNG")


def _wrap_text(draw, text, font, max_width):
    """Break text into lines that fit within max_width."""
    words = text.split()
    lines = []
    current_line = ""

    for word in words:
        test_line = f"{current_line} {word}".strip() if current_line else word
        bbox = draw.textbbox((0, 0), test_line, font=font)
        tw = bbox[2] - bbox[0]
        if tw <= max_width:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line)
            # If a single word is too long, break by characters
            bbox = draw.textbbox((0, 0), word, font=font)
            if bbox[2] - bbox[0] > max_width:
                for i in range(0, len(word), 10):
                    lines.append(word[i:i + 10])
                current_line = ""
            else:
                current_line = word

    if current_line:
        lines.append(current_line)

    return lines if lines else [text]

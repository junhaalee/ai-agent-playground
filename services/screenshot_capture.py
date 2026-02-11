import os
import logging
from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright

import config

logger = logging.getLogger(__name__)

# Try to find a Korean font
_FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
]

def _get_font(size=32):
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _generate_fallback_image(title, source, output_path):
    """Generate a dark placeholder image when screenshot fails."""
    img = Image.new("RGB", (config.SHORTS_WIDTH, config.SHORTS_HEIGHT), color=(30, 30, 50))
    draw = ImageDraw.Draw(img)
    font_title = _get_font(44)
    font_source = _get_font(28)

    # Word-wrap title
    max_chars_per_line = 18
    lines = []
    for i in range(0, len(title), max_chars_per_line):
        lines.append(title[i:i + max_chars_per_line])

    y = config.SHORTS_HEIGHT // 2 - len(lines) * 30
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font_title)
        tw = bbox[2] - bbox[0]
        x = (config.SHORTS_WIDTH - tw) // 2
        draw.text((x, y), line, fill=(255, 255, 255), font=font_title)
        y += 60

    # Source attribution
    if source:
        source_text = f"- {source} -"
        bbox = draw.textbbox((0, 0), source_text, font=font_source)
        tw = bbox[2] - bbox[0]
        draw.text(((config.SHORTS_WIDTH - tw) // 2, y + 40), source_text,
                  fill=(180, 180, 180), font=font_source)

    img.save(output_path, "PNG")


def _add_source_bar(image_path, source_text, output_path):
    """Add a semi-transparent source attribution bar at the bottom."""
    img = Image.open(image_path).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    bar_height = 60
    bar_y = img.height - bar_height
    draw.rectangle([(0, bar_y), (img.width, img.height)], fill=(0, 0, 0, 160))

    font = _get_font(24)
    if source_text:
        bbox = draw.textbbox((0, 0), source_text, font=font)
        tw = bbox[2] - bbox[0]
        draw.text(((img.width - tw) // 2, bar_y + 18), source_text,
                  fill=(255, 255, 255, 230), font=font)

    result = Image.alpha_composite(img, overlay).convert("RGB")
    result.save(output_path, "PNG")


def capture_articles_sync(articles, temp_dir):
    """
    Capture screenshots of article URLs.
    Returns list of image file paths (1080x1920).
    """
    os.makedirs(temp_dir, exist_ok=True)
    image_paths = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": config.SHORTS_WIDTH, "height": config.SHORTS_HEIGHT},
            device_scale_factor=1,
        )

        for i, article in enumerate(articles):
            output_path = os.path.join(temp_dir, f"screenshot_{i}.png")
            url = article.get("link") or article.get("source", "")
            title = article.get("title", f"기사 {i + 1}")
            source = article.get("source", "")

            # Extract domain name for attribution
            try:
                from urllib.parse import urlparse
                domain = urlparse(source or url).netloc.replace("www.", "")
            except Exception:
                domain = ""

            if not url:
                _generate_fallback_image(title, domain, output_path)
                image_paths.append(output_path)
                continue

            try:
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=15000)
                page.wait_for_timeout(2000)

                raw_path = os.path.join(temp_dir, f"raw_{i}.png")
                page.screenshot(path=raw_path, full_page=False)
                page.close()

                # Crop/resize to exact Shorts dimensions
                img = Image.open(raw_path)
                img = img.resize((config.SHORTS_WIDTH, config.SHORTS_HEIGHT), Image.LANCZOS)
                img.save(output_path, "PNG")

                # Add source bar
                _add_source_bar(output_path, domain, output_path)

                # Clean up raw
                os.remove(raw_path)

            except Exception as e:
                logger.warning(f"Screenshot failed for {url}: {e}")
                _generate_fallback_image(title, domain, output_path)

            image_paths.append(output_path)

        browser.close()

    return image_paths

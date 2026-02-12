import os
from datetime import datetime, timezone, timedelta

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ── 인덱스 페이지 설정 (URL 목록을 가져올 페이지) ──
INDEX_URL = "https://m.sports.naver.com/wfootball/index"
INDEX_WAIT_SELECTOR = ".Home_title_area__Fxfwm"
INDEX_LINK_SELECTOR = ".Home_title_area__Fxfwm a.Home_link_title__W6Auj"

# ── 기사 페이지 설정 (개별 기사에서 추출할 셀렉터) ──
ARTICLE_TITLE_SELECTOR = "h2.ArticleHead_article_title__qh8GV"
ARTICLE_BODY_SELECTOR = "._article_body"
ARTICLE_BODY_EXCLUDE_SELECTOR = ".img_desc"
ARTICLE_IMAGE_SELECTOR = "img"
ARTICLE_IMAGE_DOMAIN = "imgnews.pstatic.net"


class NaverNewsCrawler:
    """기사 URL 수집 및 개별 기사에서 title, text, image 목록을 추출"""

    @staticmethod
    def _create_driver() -> webdriver.Chrome:
        """Headless Chrome 드라이버를 생성한다."""
        opts = Options()
        opts.add_argument("--headless")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-gpu")
        opts.add_argument("user-agent=Mozilla/5.0")

        chrome_bin = os.environ.get("CHROME_BIN", "/usr/bin/chromium")
        chromedriver_path = os.environ.get("CHROMEDRIVER_PATH", "/usr/bin/chromedriver")

        if os.path.isfile(chrome_bin):
            opts.binary_location = chrome_bin
        if os.path.isfile(chromedriver_path):
            return webdriver.Chrome(service=Service(chromedriver_path), options=opts)
        return webdriver.Chrome(options=opts)

    def fetch_article_urls(self) -> list[str]:
        """인덱스 페이지에서 기사 URL 목록을 가져온다."""
        driver = self._create_driver()
        try:
            driver.get(INDEX_URL)
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, INDEX_WAIT_SELECTOR))
            )
            elements = driver.find_elements(By.CSS_SELECTOR, INDEX_LINK_SELECTOR)
            urls = []
            for el in elements:
                href = el.get_attribute("href")
                if href:
                    urls.append(href)
            return urls[:3]
        finally:
            driver.quit()

    def crawl(self, url: str) -> dict:
        """기사 URL을 받아 dict return"""
        html = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10).text
        soup = BeautifulSoup(html, "html.parser")

        title = self._parse_title(soup)
        body = soup.select_one(ARTICLE_BODY_SELECTOR)
        if body:
            for desc in body.select(ARTICLE_BODY_EXCLUDE_SELECTOR):
                desc.decompose()
            text = body.get_text("\n", strip=True)
        else:
            text = ""
        images = self._parse_images(body)

        kst = datetime.now(timezone(timedelta(hours=9)))
        prefix = kst.strftime("%Y%m%d%H")
        article_id = prefix + "_" + "_".join(url.rstrip("/").split("/")[-2:])
        return {"article_id": article_id, "image": images, "title": title, "text": text}

    def _parse_title(self, soup: BeautifulSoup) -> str:
        el = soup.select_one(ARTICLE_TITLE_SELECTOR)
        if el:
            return el.get_text(strip=True)
        og = soup.find("meta", property="og:title")
        if og and og.get("content"):
            return og["content"]
        return ""

    def _parse_images(self, body) -> list[str]:
        if not body:
            return []
        images = []
        for img in body.select(ARTICLE_IMAGE_SELECTOR):
            src = img.get("data-src") or img.get("src")
            if src and ARTICLE_IMAGE_DOMAIN in src:
                images.append(src)
        return images

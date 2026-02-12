import json
import os
import sys

import requests

from crawler import NaverNewsCrawler

N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "http://n8n:5678/webhook/news-crawler")


def send_to_webhook(data: dict) -> None:
    """n8n webhook으로 크롤링 결과를 POST 전송한다."""
    try:
        resp = requests.post(N8N_WEBHOOK_URL, json=data, timeout=10)
        print(f"[Webhook] {resp.status_code} → {N8N_WEBHOOK_URL}")
    except requests.RequestException as e:
        print(f"[Webhook] 전송 실패: {e}")


def main():
    crawler = NaverNewsCrawler()
    urls = crawler.fetch_article_urls()

    for url in urls:
        try:
            data = crawler.crawl(url)
        except Exception as e:
            print(f"[Error] 크롤링 실패: {e} / url : {url}")
            continue


        # Webhook 전송
        send_to_webhook(data)

if __name__ == "__main__":
    main()

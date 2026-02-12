import os
import time
from datetime import datetime

import requests
from croniter import croniter

from crawler import NaverNewsCrawler

N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL")
CRON_SCHEDULE = os.getenv("CRON_SCHEDULE")


def send_to_webhook(data: dict) -> None:
    """n8n webhook으로 크롤링 결과를 POST 전송."""
    try:
        resp = requests.post(N8N_WEBHOOK_URL, json=data, timeout=10)
        print(f"[Webhook] {resp.status_code} → {N8N_WEBHOOK_URL}")
    except requests.RequestException as e:
        print(f"[Webhook] 전송 실패: {e}")


def run_crawl():
    crawler = NaverNewsCrawler()
    urls = crawler.fetch_article_urls()
    print(f"[Fetch] 기사 {len(urls)}개 URL 수집")

    for url in urls:
        try:
            data = crawler.crawl(url)
        except Exception as e:
            print(f"[Error] 크롤링 실패: {e} / url : {url}")
            continue

        send_to_webhook(data)


if __name__ == "__main__":
    print(f"[Scheduler] cron: {CRON_SCHEDULE}")
    run_crawl()

    cron = croniter(CRON_SCHEDULE, datetime.now())
    while True:
        next_run = cron.get_next(datetime)
        wait_seconds = (next_run - datetime.now()).total_seconds()
        print(f"[Scheduler] 다음 실행: {next_run} ({wait_seconds:.0f}초 후)")
        time.sleep(max(wait_seconds, 0))
        run_crawl()

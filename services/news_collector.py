import requests
from datetime import datetime, timedelta
from html import unescape
import re
import config

NAVER_NEWS_API = "https://openapi.naver.com/v1/search/news.json"

QUERIES = ["정치", "국회", "대통령", "여당", "야당"]


def _clean_html(text):
    text = re.sub(r"<.*?>", "", text)
    return unescape(text).strip()


def _is_within_days(pub_date_str, days=7):
    try:
        pub_date = datetime.strptime(pub_date_str, "%a, %d %b %Y %H:%M:%S %z")
        cutoff = datetime.now(pub_date.tzinfo) - timedelta(days=days)
        return pub_date >= cutoff
    except (ValueError, TypeError):
        return True


def collect_news():
    headers = {
        "X-Naver-Client-Id": config.NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": config.NAVER_CLIENT_SECRET,
    }

    seen_titles = set()
    articles = []

    for query in QUERIES:
        params = {
            "query": query,
            "display": 100,
            "sort": "date",
        }

        try:
            resp = requests.get(NAVER_NEWS_API, headers=headers, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException:
            continue

        for item in data.get("items", []):
            if not _is_within_days(item.get("pubDate")):
                continue

            title = _clean_html(item.get("title", ""))
            if title in seen_titles:
                continue
            seen_titles.add(title)

            articles.append({
                "title": title,
                "description": _clean_html(item.get("description", "")),
                "source": item.get("originallink", ""),
                "link": item.get("link", ""),
                "pub_date": item.get("pubDate", ""),
            })

    return articles

import requests
from datetime import datetime, timedelta
from html import unescape
import re
import json
import logging
import config

logger = logging.getLogger(__name__)

NAVER_NEWS_API = "https://openapi.naver.com/v1/search/news.json"

FALLBACK_QUERIES = ["정치", "국회", "대통령", "여당", "야당"]


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


def _parse_traffic(traffic_str):
    """트래픽 문자열 '1000+' → 정수 1000 으로 변환."""
    try:
        return int(re.sub(r"[^0-9]", "", str(traffic_str)))
    except (ValueError, TypeError):
        return 0


def _get_trending_keywords():
    """trendspyg로 Google Trends KR 실시간 트렌딩 키워드를 가져온다.
    트래픽 높은 순으로 정렬된 (keyword, traffic, headlines) 리스트를 반환."""
    try:
        from trendspyg import download_google_trends_rss
        results = download_google_trends_rss(geo="KR", include_images=False, include_articles=True, max_articles_per_trend=2)
        if isinstance(results, list) and len(results) > 0:
            items = []
            for item in results:
                if not item.get("trend"):
                    continue
                headlines = [
                    a.get("headline", "")
                    for a in item.get("news_articles", [])
                    if a.get("headline")
                ]
                items.append((
                    item["trend"],
                    _parse_traffic(item.get("traffic", "0")),
                    headlines,
                ))
            items.sort(key=lambda x: x[1], reverse=True)
            if items:
                logger.info(f"[트렌딩] {len(items)}개 수집: {[f'{k}({t}+)' for k, t, _ in items]}")
                return items
        logger.warning("[트렌딩] 빈 결과 반환됨")
    except Exception as e:
        logger.error(f"[트렌딩] 수집 실패: {e}")
    return []


def _filter_political_keywords(keywords, count=3):
    """Gemini API로 키워드 목록에서 정치 관련 키워드만 필터링한다."""
    try:
        import google.generativeai as genai

        genai.configure(api_key=config.GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-2.5-flash-lite")

        prompt = (
            "다음은 한국 실시간 트렌딩 키워드 목록입니다:\n"
            f"{json.dumps(keywords, ensure_ascii=False)}\n\n"
            f"이 중에서 한국 정치와 관련된 키워드를 최대 {count}개 골라주세요.\n"
            "정치, 국회, 대통령, 정당, 선거, 법안, 외교, 국방 등 정치와 직접 관련된 것만 선택하세요.\n"
            "정치 관련 키워드가 없으면 빈 리스트를 반환하세요.\n"
            "반드시 JSON 배열 형식으로만 응답하세요. 예: [\"키워드1\", \"키워드2\"]\n"
            "다른 설명 없이 JSON 배열만 출력하세요."
        )

        response = model.generate_content(prompt)
        text = response.text.strip()

        # JSON 파싱 — ```json ... ``` 감싸진 경우도 처리
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)

        result = json.loads(text)
        if isinstance(result, list) and len(result) > 0:
            filtered = result[:count]
            logger.info(f"[Gemini] 정치 키워드 선별: {filtered}")
            return filtered
        logger.warning(f"[Gemini] 정치 키워드 없음 (응답: {text})")
    except Exception as e:
        logger.error(f"[Gemini] 필터링 실패: {e}")
    return []


def _get_trending_political_keywords():
    """트렌딩 키워드에서 정치 관련 키워드를 선별하고, 부족하면 핫 키워드로 채운다."""
    TARGET_COUNT = 3
    trending_items = _get_trending_keywords()  # [(keyword, traffic), ...]

    if not trending_items:
        logger.warning("[Fallback] 트렌딩 키워드 수집 실패 → 기본 키워드 사용")
        return [], FALLBACK_QUERIES, FALLBACK_QUERIES, [], True

    keyword_names = [k for k, _ in trending_items]
    political = _filter_political_keywords(keyword_names)

    # 3개 미만이면 트래픽 높은 순으로 나머지 채우기
    hot_filled = []
    if len(political) < TARGET_COUNT:
        political_set = set(political)
        hot_candidates = [k for k, _ in trending_items if k not in political_set]
        fill_count = TARGET_COUNT - len(political)
        hot_filled = hot_candidates[:fill_count]
        logger.info(f"[키워드 보충] 정치 {len(political)}개 + 핫 트렌딩 {len(hot_filled)}개: {hot_filled}")

    queries = political + hot_filled
    return keyword_names, queries, political, hot_filled, False


def collect_news():
    headers = {
        "X-Naver-Client-Id": config.NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": config.NAVER_CLIENT_SECRET,
    }

    trending, queries, political, hot_filled, is_fallback = _get_trending_political_keywords()

    seen_titles = set()
    articles = []

    for query in queries:
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

    keyword_log = {
        "trending_keywords": trending,
        "political_keywords": political,
        "hot_keywords": hot_filled,
        "is_fallback": is_fallback,
    }

    return articles, keyword_log

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


def _tag_political_keywords(trending_items):
    """Gemini API로 각 키워드가 정치 관련인지 여부를 태깅한다.
    trending_items: [(keyword, traffic, headlines), ...] 형태.
    반환: 정치 키워드 set"""
    try:
        import google.generativeai as genai

        genai.configure(api_key=config.GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-2.5-flash-lite")

        keyword_info = []
        for keyword, traffic, headlines in trending_items:
            entry = {"키워드": keyword}
            if headlines:
                entry["관련기사"] = headlines
            keyword_info.append(entry)

        prompt = (
            "다음은 한국 실시간 트렌딩 키워드와 관련 기사 헤드라인입니다:\n"
            f"{json.dumps(keyword_info, ensure_ascii=False)}\n\n"
            "각 키워드가 한국 정치와 관련이 있는지 판별해주세요.\n"
            "정치인, 국회, 대통령, 정당, 선거, 법안, 외교, 국방, 지방자치단체장 등 정치와 관련된 것을 선택하세요.\n"
            "인물 이름인 경우 관련 기사 헤드라인을 참고하여 정치인인지 판단하세요.\n"
            "정치 관련 키워드만 JSON 배열로 반환하세요. 정치 관련 키워드가 없으면 빈 리스트를 반환하세요.\n"
            "반드시 JSON 배열 형식으로만 응답하세요. 예: [\"키워드1\", \"키워드2\"]\n"
            "다른 설명 없이 JSON 배열만 출력하세요."
        )

        response = model.generate_content(prompt)
        text = response.text.strip()

        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)

        result = json.loads(text)
        if isinstance(result, list):
            political_set = set(result)
            logger.info(f"[Gemini] 정치 키워드 태깅: {result}")
            return political_set
        logger.warning(f"[Gemini] 정치 키워드 태깅 실패 (응답: {text})")
    except Exception as e:
        logger.error(f"[Gemini] 태깅 실패: {e}")
    return set()


def get_trending_keywords():
    """트렌딩 키워드를 수집하고 정치 여부를 태깅하여 반환한다.
    반환: [{ keyword, traffic, is_political }, ...]"""
    trending_items = _get_trending_keywords()

    if not trending_items:
        logger.warning("[Fallback] 트렌딩 키워드 수집 실패 → 기본 키워드 사용")
        return [
            {"keyword": q, "traffic": 0, "is_political": True}
            for q in FALLBACK_QUERIES
        ], True

    political_set = _tag_political_keywords(trending_items)

    result = []
    for keyword, traffic, _headlines in trending_items:
        result.append({
            "keyword": keyword,
            "traffic": traffic,
            "is_political": keyword in political_set,
        })

    logger.info(f"[트렌딩] {len(result)}개 키워드 (정치 {len(political_set)}개)")
    return result, False


def search_news(selected_keywords):
    """선택된 키워드로 네이버 뉴스 API를 호출하여 기사를 수집한다.
    selected_keywords: ["키워드1", "키워드2", ...] 형태.
    반환: articles 리스트"""
    headers = {
        "X-Naver-Client-Id": config.NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": config.NAVER_CLIENT_SECRET,
    }

    seen_titles = set()
    articles = []

    for query in selected_keywords:
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

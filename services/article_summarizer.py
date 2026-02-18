import json
import re
import logging
import config

logger = logging.getLogger(__name__)


def summarize_article(article):
    """Gemini로 기사를 3~4문장으로 요약한다. 각 문장이 자막 한 줄이 된다.
    반환: 문장 리스트 (예: ["첫 번째 문장.", "두 번째 문장.", ...])
    """
    title = article.get("title", "")
    description = article.get("description", "")

    try:
        import google.generativeai as genai

        genai.configure(api_key=config.GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-2.5-flash-lite")

        prompt = (
            "다음 뉴스 기사를 YouTube Shorts 자막용으로 요약해주세요.\n\n"
            f"제목: {title}\n"
            f"내용: {description}\n\n"
            "규칙:\n"
            "- 3~4개의 짧은 문장으로 요약\n"
            "- 각 문장은 15~25자 이내 (한 줄에 읽기 좋은 길이)\n"
            "- 뉴스 앵커가 읽는 듯한 간결한 문체\n"
            "- 핵심 사실 위주로 요약\n"
            '- 반드시 JSON 배열로만 응답. 예: ["첫 번째 문장.", "두 번째 문장."]\n'
            "- 다른 설명 없이 JSON 배열만 출력"
        )

        response = model.generate_content(prompt)
        text = response.text.strip()

        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)

        result = json.loads(text)
        if isinstance(result, list) and len(result) > 0:
            logger.info(f"[요약] '{title[:20]}...' → {len(result)}문장")
            return result

    except Exception as e:
        logger.error(f"[요약] 실패: {e}")

    # Fallback: 제목을 그대로 사용
    logger.warning(f"[요약] fallback → 제목 사용: {title}")
    return [title]


def summarize_articles(articles):
    """여러 기사를 순서대로 요약. 반환: [[문장, ...], [문장, ...], ...]"""
    return [summarize_article(a) for a in articles]

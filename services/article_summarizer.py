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
        model = genai.GenerativeModel("gemini-2.5-flash")

        prompt = (
            "뉴스 기사를 TV 뉴스 앵커가 보도하는 말투로 요약해주세요.\n"
            "모든 문장은 반드시 '~습니다' 또는 '~했습니다'로 끝나야 합니다.\n\n"
            "=== 예시 ===\n"
            "입력 제목: 윤석열 대통령 탄핵소추안 국회 본회의 통과\n"
            "입력 내용: 국회는 오늘 본회의에서 윤석열 대통령 탄핵소추안을 찬성 204표로 가결했다.\n"
            '출력: ["국회가 윤석열 대통령 탄핵소추안을 가결했습니다.", "찬성 204표로 본회의를 통과했습니다.", "헌법재판소의 최종 심판이 남아있습니다."]\n\n'
            "=== 실제 기사 ===\n"
            f"제목: {title}\n"
            f"내용: {description}\n\n"
            "규칙:\n"
            "- 3~4개의 짧은 문장으로 요약\n"
            "- 각 문장은 20~40자 이내\n"
            "- 모든 문장을 반드시 '~습니다'로 끝내세요\n"
            "- JSON 배열로만 응답하세요"
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


def summarize_issue(articles, num_sentences=4):
    """여러 기사를 종합하여 기승전결 흐름의 하나의 요약을 만든다.
    반환: 문장 리스트 (예: ["첫 번째 문장.", "두 번째 문장.", ...])
    """
    articles_text = ""
    for i, article in enumerate(articles):
        articles_text += f"기사{i+1} 제목: {article.get('title', '')}\n"
        articles_text += f"기사{i+1} 내용: {article.get('description', '')}\n\n"

    try:
        import google.generativeai as genai

        genai.configure(api_key=config.GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-2.5-flash")

        prompt = (
            "다음 뉴스 기사들을 종합하여 TV 뉴스 앵커가 보도하는 하나의 리포트로 만들어주세요.\n\n"
            f"{articles_text}"
            "=== 예시 출력 ===\n"
            '["오늘 국회에서 중대한 결정이 내려졌습니다.", '
            '"윤석열 대통령 탄핵소추안이 찬성 204표로 가결됐습니다.", '
            '"이에 따라 대통령의 직무가 즉시 정지됐습니다.", '
            '"헌법재판소의 최종 판결이 주목됩니다."]\n\n'
            "규칙:\n"
            f"- 정확히 {num_sentences}개의 문장으로 요약\n"
            "- 기승전결 흐름으로 구성하세요 (도입 → 전개 → 핵심 → 전망/마무리)\n"
            "- 여러 기사의 핵심을 하나의 이야기로 엮으세요 (같은 내용 반복 금지)\n"
            "- 각 문장은 20~40자 이내\n"
            "- 모든 문장을 반드시 '~습니다'로 끝내세요\n"
            "- JSON 배열로만 응답하세요"
        )

        response = model.generate_content(prompt)
        text = response.text.strip()

        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)

        result = json.loads(text)
        if isinstance(result, list) and len(result) > 0:
            logger.info(f"[이슈요약] {len(articles)}개 기사 → {len(result)}문장 통합 요약")
            return result

    except Exception as e:
        logger.error(f"[이슈요약] 실패: {e}")

    # Fallback: 첫 번째 기사 단독 요약
    logger.warning("[이슈요약] fallback → 첫 기사 단독 요약")
    return summarize_article(articles[0])

import re
from collections import Counter

STOP_WORDS = {
    "에서", "으로", "에서는", "것으로", "대해", "위해", "통해",
    "하는", "있는", "라며", "이라고", "했다", "밝혔다", "전했다",
    "말했다", "됐다", "있다", "없다", "한다", "대한", "관련",
    "이번", "지난", "오늘", "내일", "어제", "올해", "뉴스",
    "속보", "종합", "단독", "포토", "영상", "한국", "정치",
    "기자", "보도", "사진", "제공", "연합뉴스", "헤럴드",
}


def _extract_keywords(text):
    words = re.findall(r"[가-힣]{2,}", text)
    return set(w for w in words if w not in STOP_WORDS)


def _similarity(kw_a, kw_b):
    if not kw_a or not kw_b:
        return 0.0
    return len(kw_a & kw_b) / len(kw_a | kw_b)


def analyze_issues(articles):
    if not articles:
        return []

    # Step 1: Extract keywords for each article
    article_keywords = []
    for article in articles:
        text = article["title"] + " " + article["description"]
        kws = _extract_keywords(text)
        article_keywords.append(kws)

    # Step 2: Cluster articles by keyword similarity
    SIMILARITY_THRESHOLD = 0.15
    clusters = []

    for i, article in enumerate(articles):
        kws = article_keywords[i]
        best_cluster = None
        best_score = 0.0

        for cluster in clusters:
            scores = [_similarity(kws, ckw) for _, ckw in cluster]
            avg = sum(scores) / len(scores)
            if avg > best_score:
                best_score = avg
                best_cluster = cluster

        if best_score >= SIMILARITY_THRESHOLD and best_cluster is not None:
            best_cluster.append((article, kws))
        else:
            clusters.append([(article, kws)])

    # Step 3: Rank by article count (most discussed first)
    clusters.sort(key=lambda c: len(c), reverse=True)

    # Step 4: Build top 3 topics
    topics = []
    for cluster in clusters[:3]:
        cluster_articles = [a for a, _ in cluster]
        cluster_keywords = [kw for _, kws in cluster for kw in kws]

        kw_counts = Counter(cluster_keywords).most_common(3)
        title = " ".join(kw for kw, _ in kw_counts)

        sorted_by_len = sorted(cluster_articles, key=lambda a: len(a["title"]))
        summary = sorted_by_len[0]["title"]
        if len(summary) > 50:
            summary = summary[:50] + "..."

        articles_info = [
            {
                "title": a["title"],
                "link": a.get("link", ""),
                "source": a.get("source", ""),
                "description": a.get("description", ""),
            }
            for a in cluster_articles
        ]

        topics.append({
            "title": title,
            "summary": summary,
            "article_count": len(cluster_articles),
            "articles": articles_info,
        })

    return topics

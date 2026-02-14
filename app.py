import logging
from flask import Flask, render_template, jsonify, request
from services.news_collector import collect_news
from services.issue_analyzer import analyze_issues
from services.video_creator import generate_shorts, get_job_status
from services.youtube_uploader import upload_video

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")

app = Flask(__name__)

# Cache issues between fetch and generate calls
_cached_issues = []


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/fetch-issues", methods=["POST"])
def fetch_issues():
    global _cached_issues
    try:
        articles, keyword_log = collect_news()
        if not articles:
            return jsonify({"error": "뉴스를 가져오지 못했습니다. API 키를 확인해주세요."}), 500

        issues = analyze_issues(articles)
        _cached_issues = issues
        return jsonify({
            "issues": issues,
            "article_count": len(articles),
            "keyword_log": keyword_log,
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/generate-shorts", methods=["POST"])
def api_generate_shorts():
    try:
        data = request.get_json()
        selected_indices = data.get("selected_indices", [])
        options = data.get("options", {})

        if not selected_indices:
            return jsonify({"error": "이슈를 선택해주세요."}), 400

        if not _cached_issues:
            return jsonify({"error": "먼저 화제를 가져와주세요."}), 400

        selected = [_cached_issues[i] for i in selected_indices if i < len(_cached_issues)]
        if not selected:
            return jsonify({"error": "유효한 이슈가 없습니다."}), 400

        job_id = generate_shorts(selected, options)
        return jsonify({"job_id": job_id})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/generation-status/<job_id>")
def api_generation_status(job_id):
    job = get_job_status(job_id)
    if not job:
        return jsonify({"error": "작업을 찾을 수 없습니다."}), 404
    return jsonify(job)


@app.route("/api/upload-youtube", methods=["POST"])
def api_upload_youtube():
    try:
        data = request.get_json()
        job_id = data.get("job_id")
        title = data.get("title", "")
        description = data.get("description", "")

        if not job_id:
            return jsonify({"error": "job_id가 필요합니다."}), 400

        job = get_job_status(job_id)
        if not job or job["status"] != "completed":
            return jsonify({"error": "완료된 영상이 없습니다."}), 400

        video_path = job.get("video_path")
        if not video_path:
            return jsonify({"error": "영상 파일을 찾을 수 없습니다."}), 400

        if not title:
            title = "뉴스 쇼츠"

        result = upload_video(video_path, title, description)
        return jsonify(result)

    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True, port=8080)

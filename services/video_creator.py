import os
import uuid
import shutil
import logging
import subprocess
import threading
from datetime import datetime

import config
from services.article_summarizer import summarize_articles
from services.image_fetcher import fetch_images
from services.screenshot_capture import generate_frames_for_article
from services.tts_generator import generate_narration_sync
from services.subtitle_renderer import render_subtitle_on_image

logger = logging.getLogger(__name__)

# 배경 이미지 교체 간격 (초)
BG_CHANGE_INTERVAL = 3.0

# In-memory job tracking
_jobs = {}


def get_job_status(job_id):
    """Return job progress dict or None."""
    return _jobs.get(job_id)


def generate_shorts(selected_issues, options):
    """Start video generation in a background thread. Returns job_id immediately."""
    job_id = str(uuid.uuid4())[:8]
    _jobs[job_id] = {
        "status": "running",
        "progress": 0,
        "message": "준비 중...",
        "video_path": None,
        "error": None,
    }

    thread = threading.Thread(
        target=_pipeline,
        args=(job_id, selected_issues, options),
        daemon=True,
    )
    thread.start()
    return job_id


def _update(job_id, progress, message):
    if job_id in _jobs:
        _jobs[job_id]["progress"] = progress
        _jobs[job_id]["message"] = message
    logger.info(f"[{job_id}] {progress}% - {message}")


def _pipeline(job_id, selected_issues, options):
    """Main video generation pipeline."""
    duration_range = options.get("duration", "20-30")
    subtitle_pos = options.get("subtitle_pos", "bottom")
    speed_key = options.get("speed", "normal")
    speed = config.SPEED_MAP.get(speed_key, 1.0)

    num_articles = config.DURATION_ARTICLE_MAP.get(duration_range, 2)

    # 영상 예상 길이 (초) — 중간값 사용
    dur_parts = duration_range.split("-")
    estimated_duration = (int(dur_parts[0]) + int(dur_parts[1])) / 2

    # Collect articles from selected issues
    all_articles = []
    for issue in selected_issues:
        for a in issue.get("articles", []):
            all_articles.append(a)
            if len(all_articles) >= num_articles:
                break
        if len(all_articles) >= num_articles:
            break

    if not all_articles:
        _jobs[job_id]["status"] = "error"
        _jobs[job_id]["error"] = "선택한 이슈에 기사가 없습니다."
        return

    job_dir = os.path.join(config.TEMP_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)

    try:
        # Step 0: Generate suggested title
        suggested_title = _generate_title(selected_issues)
        _jobs[job_id]["suggested_title"] = suggested_title

        # Step 1: Summarize articles (0-10%)
        _update(job_id, 5, "기사 요약 중...")
        summaries = summarize_articles(all_articles)
        _update(job_id, 10, f"기사 {len(summaries)}개 요약 완료")

        # Step 2: TTS narration (10-25%)
        _update(job_id, 12, "음성 나레이션 생성 중...")
        audio_paths, subtitle_segments = generate_narration_sync(summaries, job_dir)
        _update(job_id, 25, "나레이션 생성 완료")

        # Step 3: Fetch images for each article (25-45%)
        _update(job_id, 28, "관련 이미지 검색 중...")
        # 기사당 필요 이미지 수 = 오디오 길이 / 3초
        all_bg_frames = []
        for i, article in enumerate(all_articles):
            audio_dur = _get_audio_duration(audio_paths[i]) if i < len(audio_paths) else estimated_duration
            images_needed = max(int(audio_dur / BG_CHANGE_INTERVAL) + 1, 2)

            keyword = article.get("title", "뉴스")[:10]
            bg_images = fetch_images(keyword, images_needed, os.path.join(job_dir, f"images_{i}"))

            # 배경 이미지에 뉴스 정보 오버레이
            card_frames = generate_frames_for_article(
                bg_images, article, job_dir, article_idx=i, keyword=keyword
            )
            all_bg_frames.append(card_frames)
            _update(job_id, 28 + int(17 * (i + 1) / len(all_articles)),
                    f"이미지 검색 {i + 1}/{len(all_articles)}...")
        _update(job_id, 45, "이미지 준비 완료")

        # Step 4: Generate timed frames (45-65%)
        _update(job_id, 48, "자막 프레임 생성 중...")
        frame_data = _build_timed_frames(
            all_bg_frames, subtitle_segments, audio_paths, subtitle_pos, job_dir
        )
        _update(job_id, 65, f"프레임 {len(frame_data)}개 생성 완료")

        # Step 5: Assemble video (65-85%)
        _update(job_id, 68, "영상 조립 중...")
        merged_audio = _merge_audio(audio_paths, job_dir)
        raw_video = _assemble_video(frame_data, merged_audio, job_dir)
        _update(job_id, 85, "영상 조립 완료")

        # Step 6: Speed adjustment (85-95%)
        if speed != 1.0:
            _update(job_id, 88, f"속도 조절 중 ({speed}x)...")
            final_video = _apply_speed(raw_video, speed, job_dir)
        else:
            final_video = raw_video
        _update(job_id, 95, "마무리 중...")

        # Step 7: Move to output
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(config.OUTPUT_DIR, f"shorts_{timestamp}.mp4")
        shutil.move(final_video, output_path)

        _jobs[job_id]["status"] = "completed"
        _jobs[job_id]["progress"] = 100
        _jobs[job_id]["message"] = "완료!"
        _jobs[job_id]["video_path"] = output_path

    except Exception as e:
        logger.exception(f"Pipeline failed for job {job_id}")
        _jobs[job_id]["status"] = "error"
        _jobs[job_id]["error"] = str(e)
    finally:
        try:
            shutil.rmtree(job_dir, ignore_errors=True)
        except Exception:
            pass


def _generate_title(selected_issues):
    """선택된 이슈들을 관통하는 쇼츠 영상 제목을 Gemini로 생성한다."""
    issue_titles = [issue.get("title", "") for issue in selected_issues if issue.get("title")]
    if not issue_titles:
        return "오늘의 정치 뉴스"

    try:
        import google.generativeai as genai

        genai.configure(api_key=config.GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-2.5-flash-lite")

        prompt = (
            "다음 뉴스 이슈들을 관통하는 YouTube Shorts 영상 제목을 1개만 만들어줘.\n\n"
            f"이슈들:\n" + "\n".join(f"- {t}" for t in issue_titles) + "\n\n"
            "규칙:\n"
            "- 30자 이내의 짧고 임팩트 있는 제목\n"
            "- 클릭을 유도하되 낚시성은 아닌 제목\n"
            "- 이모지 1~2개 포함 가능\n"
            "- 제목 텍스트만 출력 (따옴표, 설명 없이)"
        )

        response = model.generate_content(prompt)
        title = response.text.strip().strip('"').strip("'")
        if title:
            logger.info(f"[제목생성] {title}")
            return title
    except Exception as e:
        logger.error(f"[제목생성] 실패: {e}")

    # Fallback: 첫 번째 이슈 제목 사용
    return issue_titles[0][:30]


def _build_timed_frames(all_bg_frames, subtitle_segments, audio_paths, subtitle_pos, job_dir):
    """배경 이미지 3초 교체 + 자막 TTS 타이밍을 병합하여 프레임 생성.

    Returns: [(frame_path, duration_sec), ...]
    """
    all_frame_data = []
    frame_idx = 0

    for article_i, card_frames in enumerate(all_bg_frames):
        segments = subtitle_segments[article_i] if article_i < len(subtitle_segments) else []
        audio_dur = _get_audio_duration(audio_paths[article_i]) if article_i < len(audio_paths) else 10.0

        # 변경점(change points) 수집
        change_points = set()
        change_points.add(0.0)
        change_points.add(audio_dur)

        # 배경 교체 시점
        t = 0.0
        while t < audio_dur:
            change_points.add(t)
            t += BG_CHANGE_INTERVAL

        # 자막 교체 시점
        for seg in segments:
            change_points.add(seg.get("start", 0))
            change_points.add(seg.get("end", 0))

        change_points = sorted(change_points)

        # 각 구간별 프레임 생성
        for cp_i in range(len(change_points) - 1):
            t_start = change_points[cp_i]
            t_end = change_points[cp_i + 1]
            duration = t_end - t_start

            if duration < 0.05:
                continue

            # 현재 배경 이미지 결정
            bg_idx = int(t_start / BG_CHANGE_INTERVAL) % len(card_frames)
            bg_frame = card_frames[bg_idx]

            # 현재 자막 텍스트 결정
            subtitle_text = ""
            for seg in segments:
                seg_start = seg.get("start", 0)
                seg_end = seg.get("end", 0)
                if seg_start <= t_start < seg_end:
                    subtitle_text = seg.get("text", "")
                    break

            # 프레임 렌더링
            frame_path = os.path.join(job_dir, f"frame_{frame_idx}.png")
            render_subtitle_on_image(bg_frame, subtitle_text, subtitle_pos, frame_path)
            all_frame_data.append((frame_path, duration))
            frame_idx += 1

    return all_frame_data


def _get_audio_duration(audio_path):
    """Get duration of audio file in seconds using ffprobe."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
            capture_output=True, text=True, timeout=10,
        )
        return float(result.stdout.strip())
    except Exception:
        return 10.0


def _merge_audio(audio_paths, job_dir):
    """Merge multiple audio files into one."""
    if len(audio_paths) == 1:
        return audio_paths[0]

    list_file = os.path.join(job_dir, "audio_list.txt")
    with open(list_file, "w") as f:
        for path in audio_paths:
            f.write(f"file '{path}'\n")

    merged = os.path.join(job_dir, "merged_audio.mp3")
    result = subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_file,
         "-c", "copy", merged],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"오디오 병합 실패: {result.stderr[:200]}")
    return merged


def _assemble_video(frame_data, audio_path, job_dir):
    """프레임별 duration으로 영상 조립."""
    concat_file = os.path.join(job_dir, "concat.txt")
    with open(concat_file, "w") as f:
        for frame_path, duration in frame_data:
            f.write(f"file '{frame_path}'\n")
            f.write(f"duration {duration:.3f}\n")
        if frame_data:
            f.write(f"file '{frame_data[-1][0]}'\n")

    output = os.path.join(job_dir, "assembled.mp4")
    result = subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_file,
         "-i", audio_path,
         "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-vf", f"scale={config.SHORTS_WIDTH}:{config.SHORTS_HEIGHT}",
         "-shortest", output],
        capture_output=True, text=True, timeout=180,
    )

    if not os.path.exists(output):
        logger.error(f"ffmpeg stderr: {result.stderr}")
        raise RuntimeError(f"영상 조립 실패: {result.stderr[:200]}")
    return output


def _apply_speed(video_path, speed, job_dir):
    """Apply speed adjustment."""
    output = os.path.join(job_dir, "speed_adjusted.mp4")
    atempo = max(0.5, min(2.0, speed))
    setpts = 1.0 / speed

    subprocess.run(
        ["ffmpeg", "-y", "-i", video_path,
         "-filter_complex",
         f"[0:v]setpts={setpts}*PTS[v];[0:a]atempo={atempo}[a]",
         "-map", "[v]", "-map", "[a]",
         "-c:v", "libx264", "-pix_fmt", "yuv420p",
         output],
        capture_output=True, timeout=120,
    )

    if not os.path.exists(output):
        logger.warning("Speed adjustment failed, using original")
        return video_path
    return output

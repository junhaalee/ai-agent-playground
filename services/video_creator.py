import os
import uuid
import shutil
import logging
import subprocess
import threading
from datetime import datetime

import config
from services.screenshot_capture import capture_articles_sync
from services.tts_generator import generate_narration_sync
from services.subtitle_renderer import render_subtitle_on_image

logger = logging.getLogger(__name__)

# In-memory job tracking
_jobs = {}


def get_job_status(job_id):
    """Return job progress dict or None."""
    return _jobs.get(job_id)


def generate_shorts(selected_issues, options):
    """
    Start video generation in a background thread.
    Returns job_id immediately.
    """
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
    """Main video generation pipeline running in background thread."""
    duration = options.get("duration", "20-30")
    subtitle_pos = options.get("subtitle_pos", "bottom")
    speed_key = options.get("speed", "normal")
    speed = config.SPEED_MAP.get(speed_key, 1.0)

    # Determine how many articles to use
    num_articles = config.DURATION_ARTICLE_MAP.get(duration, 2)

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

    # Create job temp directory
    job_dir = os.path.join(config.TEMP_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)

    try:
        # Step 1: Screenshots (0-20%)
        _update(job_id, 5, "기사 스크린샷 캡처 중...")
        image_paths = capture_articles_sync(all_articles, job_dir)
        _update(job_id, 20, f"스크린샷 {len(image_paths)}장 완료")

        # Step 2: TTS narration (20-40%)
        _update(job_id, 25, "음성 나레이션 생성 중...")
        audio_paths, subtitle_segments = generate_narration_sync(all_articles, job_dir)
        _update(job_id, 40, "나레이션 생성 완료")

        # Step 3: Render subtitles onto images (40-60%)
        _update(job_id, 45, "자막 렌더링 중...")
        subtitled_paths = _render_all_subtitles(
            image_paths, subtitle_segments, subtitle_pos, job_dir
        )
        _update(job_id, 60, "자막 렌더링 완료")

        # Step 4: Assemble video with ffmpeg (60-80%)
        _update(job_id, 65, "영상 조립 중...")
        merged_audio = _merge_audio(audio_paths, job_dir)
        raw_video = _assemble_video(subtitled_paths, merged_audio, audio_paths, job_dir)
        _update(job_id, 80, "영상 조립 완료")

        # Step 5: Apply speed adjustment (80-95%)
        if speed != 1.0:
            _update(job_id, 85, f"속도 조절 중 ({speed}x)...")
            final_video = _apply_speed(raw_video, speed, job_dir)
        else:
            final_video = raw_video
        _update(job_id, 95, "마무리 중...")

        # Step 6: Move to output (95-100%)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"shorts_{timestamp}.mp4"
        output_path = os.path.join(config.OUTPUT_DIR, output_filename)
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
        # Clean up temp dir
        try:
            shutil.rmtree(job_dir, ignore_errors=True)
        except Exception:
            pass


def _render_all_subtitles(image_paths, subtitle_segments, position, job_dir):
    """For each image, render the first subtitle segment onto it."""
    subtitled = []
    for i, img_path in enumerate(image_paths):
        segments = subtitle_segments[i] if i < len(subtitle_segments) else []
        # Combine all subtitle text for this article into one overlay
        combined_text = " ".join(seg["text"] for seg in segments) if segments else ""

        out_path = os.path.join(job_dir, f"subtitled_{i}.png")
        render_subtitle_on_image(img_path, combined_text, position, out_path)
        subtitled.append(out_path)

    return subtitled


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
        return 10.0  # default fallback


def _merge_audio(audio_paths, job_dir):
    """Merge multiple audio files into one using ffmpeg concat."""
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
        logger.error(f"Audio merge failed: {result.stderr}")
        raise RuntimeError(f"오디오 병합 실패: {result.stderr[:200]}")
    return merged


def _assemble_video(image_paths, audio_path, individual_audios, job_dir):
    """
    Create video by showing each image for the duration of its corresponding audio,
    then combining with the merged audio track.
    """
    # Build concat file with per-image durations
    concat_file = os.path.join(job_dir, "concat.txt")
    with open(concat_file, "w") as f:
        for i, img_path in enumerate(image_paths):
            if i < len(individual_audios):
                dur = _get_audio_duration(individual_audios[i])
            else:
                dur = 10.0
            f.write(f"file '{img_path}'\n")
            f.write(f"duration {dur}\n")
        # ffmpeg concat demuxer needs the last image repeated without duration
        if image_paths:
            f.write(f"file '{image_paths[-1]}'\n")

    output = os.path.join(job_dir, "assembled.mp4")
    result = subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_file,
         "-i", audio_path,
         "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-vf", f"scale={config.SHORTS_WIDTH}:{config.SHORTS_HEIGHT}",
         "-shortest", output],
        capture_output=True, text=True, timeout=120,
    )

    if not os.path.exists(output):
        logger.error(f"ffmpeg assembly stderr: {result.stderr}")
        raise RuntimeError(f"영상 조립 실패: {result.stderr[:200]}")

    return output


def _apply_speed(video_path, speed, job_dir):
    """Apply speed adjustment to video and audio."""
    output = os.path.join(job_dir, "speed_adjusted.mp4")

    # atempo filter only supports 0.5-2.0 range
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

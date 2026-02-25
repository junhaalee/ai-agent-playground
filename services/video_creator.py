import os
import uuid
import shutil
import logging
import subprocess
import threading
import random
from datetime import datetime

import config
from services.article_summarizer import summarize_issue
from services.image_fetcher import fetch_images
from services.screenshot_capture import generate_frames_for_article
from services.tts_generator import generate_narration_sync
from services.subtitle_renderer import render_subtitle_on_image

logger = logging.getLogger(__name__)

# 배경 이미지 교체 간격 (초)
BG_CHANGE_INTERVAL = 3.0

# BGM 설정
BGM_DIR = os.path.join(config.BASE_DIR, "bgm")
BGM_VOLUME = 0.15  # 나레이션 대비 BGM 볼륨 (0.0~1.0)

# 로봇 앵커 설정
ROBOT_IMG_PATH = os.path.join(config.BASE_DIR, "assets", "robot_anchor.png")
ROBOT_HEIGHT = 280
INTRO_TEXT = "오늘의 뉴스입니다."
SLIDE_FRAMES = 8
SLIDE_DURATION = 0.8
OUTRO_DURATION = 0.8

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
    bgm_key = options.get("bgm", "none")

    # 영상 예상 길이 (초) — 중간값 사용
    dur_parts = duration_range.split("-")
    estimated_duration = (int(dur_parts[0]) + int(dur_parts[1])) / 2

    # 5초당 기사 1개
    num_articles = max(int(estimated_duration / config.SECONDS_PER_ARTICLE), 1)

    # Collect articles from selected issues
    all_articles = []
    issue_keyword = selected_issues[0].get("title", "뉴스") if selected_issues else "뉴스"
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

        # Step 1: 전체 기사를 하나의 기승전결 요약으로 생성 (0-10%)
        _update(job_id, 5, "기사 요약 중...")
        num_sentences = max(int(estimated_duration / 2), 5)
        summary = summarize_issue(all_articles, num_sentences)
        _update(job_id, 10, f"기사 {len(all_articles)}개 → {len(summary)}문장 통합 요약 완료")

        # Step 2: TTS narration — 통합 요약 1개 (10-25%)
        _update(job_id, 12, "음성 나레이션 생성 중...")
        audio_paths, subtitle_segments = generate_narration_sync([summary], job_dir)
        _update(job_id, 25, "나레이션 생성 완료")

        # Step 3: 기사별 이미지 검색 (다양성 확보) → 프레임 통합 (25-45%)
        _update(job_id, 28, "관련 이미지 검색 중...")
        audio_dur = _get_audio_duration(audio_paths[0]) if audio_paths else estimated_duration
        total_images = max(int(audio_dur / BG_CHANGE_INTERVAL) + 1, 2)
        images_per_article = max(total_images // len(all_articles) + 1, 1)

        all_card_frames = []
        for i, article in enumerate(all_articles):
            keyword = article.get("title", "") or issue_keyword
            bg_images = fetch_images(keyword, images_per_article, os.path.join(job_dir, f"images_{i}"))

            card_frames = generate_frames_for_article(
                bg_images, article, job_dir, article_idx=i, keyword=issue_keyword
            )
            all_card_frames.extend(card_frames)
            _update(job_id, 28 + int(17 * (i + 1) / len(all_articles)),
                    f"이미지 검색 {i + 1}/{len(all_articles)}...")
        _update(job_id, 45, "이미지 준비 완료")

        # Step 4: Generate timed frames (45-65%)
        _update(job_id, 48, "자막 프레임 생성 중...")
        frame_data = _build_timed_frames(
            [all_card_frames], subtitle_segments, audio_paths, subtitle_pos, job_dir
        )
        _update(job_id, 55, f"프레임 {len(frame_data)}개 생성 완료")

        # Step 5: Robot anchor overlay (비활성화 — 코드 유지)
        # first_card = all_card_frames[0] if all_card_frames else None
        # frame_data, final_audio = _add_robot_anchor(
        #     frame_data, audio_paths[0], first_card, subtitle_pos, job_dir
        # )
        final_audio = _merge_audio(audio_paths, job_dir)

        # Step 5.5: BGM 믹싱
        bgm_path = _select_bgm(bgm_key)
        if bgm_path:
            _update(job_id, 68, "배경음악 합성 중...")
            narr_dur = _get_audio_duration(final_audio)
            mixed_audio = os.path.join(job_dir, "mixed_with_bgm.mp3")
            final_audio = _mix_bgm(final_audio, bgm_path, mixed_audio, narr_dur)

        # Step 6: Assemble video (70-85%)
        _update(job_id, 72, "영상 조립 중...")
        raw_video = _assemble_video(frame_data, final_audio, job_dir)
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

        suggested_desc = _generate_description(all_articles)

        _jobs[job_id]["status"] = "completed"
        _jobs[job_id]["progress"] = 100
        _jobs[job_id]["message"] = "완료!"
        _jobs[job_id]["video_path"] = output_path
        _jobs[job_id]["suggested_description"] = suggested_desc

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
        model = genai.GenerativeModel("gemini-2.5-flash")

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


def _generate_description(all_articles):
    """기사들을 종합하여 영상 설명(한글 + 영어 번역)을 생성한다."""
    articles_text = ""
    for i, article in enumerate(all_articles):
        articles_text += f"기사{i+1}: {article.get('title', '')}\n"
        articles_text += f"내용: {article.get('description', '')}\n\n"

    try:
        import google.generativeai as genai

        genai.configure(api_key=config.GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-2.5-flash")

        prompt = (
            "다음 뉴스 기사들을 종합하여 YouTube Shorts 영상 설명을 작성해주세요.\n\n"
            f"{articles_text}"
            "규칙:\n"
            "- 먼저 한국어로 5~10줄의 상세한 요약을 작성하세요\n"
            "- 뉴스 보도 구어체로 작성 (~했습니다, ~밝혔습니다)\n"
            "- 핵심 사실, 배경, 영향, 전망을 포함하세요\n"
            "- 한국어 요약이 끝나면 빈 줄 2개를 넣고 영어 번역을 작성하세요\n"
            "- 영어 번역도 5~10줄로 작성하세요\n"
            "- 다른 설명이나 제목 없이 본문만 출력하세요"
        )

        response = model.generate_content(prompt)
        desc = response.text.strip()
        if desc:
            logger.info(f"[영상설명] 생성 완료 ({len(desc)}자)")
            return desc
    except Exception as e:
        logger.error(f"[영상설명] 실패: {e}")

    return ""


def _load_robot_img():
    from PIL import Image
    if not os.path.exists(ROBOT_IMG_PATH):
        logger.warning("[로봇앵커] 이미지 없음: %s", ROBOT_IMG_PATH)
        return None
    img = Image.open(ROBOT_IMG_PATH).convert("RGBA")
    ratio = ROBOT_HEIGHT / img.height
    new_w = int(img.width * ratio)
    return img.resize((new_w, ROBOT_HEIGHT), Image.LANCZOS)


def _overlay_robot_on_frame(bg_path, robot_img, x, y, output_path):
    from PIL import Image
    bg = Image.open(bg_path).convert("RGBA")
    layer = Image.new("RGBA", bg.size, (0, 0, 0, 0))
    layer.paste(robot_img, (int(x), int(y)), robot_img)
    result = Image.alpha_composite(bg, layer)
    result.convert("RGB").save(output_path, "PNG")


def _add_robot_anchor(frame_data, main_audio, first_card, subtitle_pos, job_dir):
    """로봇 앵커 등장(인트로) → 본문 오버레이 → 퇴장(아웃트로)."""
    robot_img = _load_robot_img()
    if robot_img is None:
        return frame_data, main_audio

    robot_w, robot_h = robot_img.size
    target_x = 30
    target_y = 1520 - robot_h - 10

    # --- Intro TTS ---
    intro_dir = os.path.join(job_dir, "intro")
    os.makedirs(intro_dir, exist_ok=True)
    intro_audio_paths, _ = generate_narration_sync([[INTRO_TEXT]], intro_dir)
    intro_audio = intro_audio_paths[0]
    intro_dur = _get_audio_duration(intro_audio)

    slide_dur = min(SLIDE_DURATION, intro_dur * 0.4)
    hold_dur = max(intro_dur - slide_dur, 0.3)

    bg = first_card or frame_data[0][0]

    # --- Intro: slide-in + hold ---
    intro_frames = []
    for i in range(SLIDE_FRAMES):
        t = (i + 1) / SLIDE_FRAMES
        ease = 1 - (1 - t) ** 3
        x = -robot_w + (target_x + robot_w) * ease

        fp = os.path.join(job_dir, f"intro_s{i}.png")
        _overlay_robot_on_frame(bg, robot_img, x, target_y, fp)
        fp_sub = os.path.join(job_dir, f"intro_s{i}_sub.png")
        render_subtitle_on_image(fp, INTRO_TEXT, subtitle_pos, fp_sub)
        intro_frames.append((fp_sub, slide_dur / SLIDE_FRAMES))

    hold_fp = os.path.join(job_dir, "intro_hold.png")
    _overlay_robot_on_frame(bg, robot_img, target_x, target_y, hold_fp)
    hold_sub = os.path.join(job_dir, "intro_hold_sub.png")
    render_subtitle_on_image(hold_fp, INTRO_TEXT, subtitle_pos, hold_sub)
    intro_frames.append((hold_sub, hold_dur))

    # --- Main: static robot overlay ---
    main_frames = []
    for i, (fp, dur) in enumerate(frame_data):
        out = os.path.join(job_dir, f"mr_{i}.png")
        _overlay_robot_on_frame(fp, robot_img, target_x, target_y, out)
        main_frames.append((out, dur))

    # --- Outro: slide-out ---
    last_bg = frame_data[-1][0] if frame_data else bg
    outro_frames = []
    for i in range(SLIDE_FRAMES):
        t = (i + 1) / SLIDE_FRAMES
        ease = t ** 3
        x = target_x - (target_x + robot_w) * ease

        fp = os.path.join(job_dir, f"outro_{i}.png")
        _overlay_robot_on_frame(last_bg, robot_img, x, target_y, fp)
        outro_frames.append((fp, OUTRO_DURATION / SLIDE_FRAMES))

    # --- Silence for outro ---
    silence = os.path.join(job_dir, "silence.mp3")
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
        "-t", str(OUTRO_DURATION), "-c:a", "libmp3lame", "-q:a", "9", silence
    ], capture_output=True, timeout=10)

    # --- Merge audio: intro + main + silence ---
    full_audio = os.path.join(job_dir, "full_audio.mp3")
    audio_list = os.path.join(job_dir, "full_audio_list.txt")
    with open(audio_list, "w") as f:
        f.write(f"file '{intro_audio}'\n")
        f.write(f"file '{main_audio}'\n")
        f.write(f"file '{silence}'\n")
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", audio_list, "-c", "copy", full_audio
    ], capture_output=True, timeout=60)

    logger.info(f"[로봇앵커] 인트로 {len(intro_frames)}프레임 + 본문 {len(main_frames)}프레임 + 아웃트로 {len(outro_frames)}프레임")
    return intro_frames + main_frames + outro_frames, full_audio


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


def _select_bgm(bgm_key):
    """BGM 폴더에서 랜덤으로 1개 선택. 없으면 None."""
    if not bgm_key or bgm_key == "none":
        return None
    bgm_folder = os.path.join(BGM_DIR, bgm_key)
    if not os.path.isdir(bgm_folder):
        logger.warning(f"[BGM] 폴더 없음: {bgm_folder}")
        return None
    files = [f for f in os.listdir(bgm_folder) if f.endswith((".mp3", ".wav", ".m4a"))]
    if not files:
        logger.warning(f"[BGM] 음원 없음: {bgm_folder}")
        return None
    selected = random.choice(files)
    logger.info(f"[BGM] 선택: {selected}")
    return os.path.join(bgm_folder, selected)


def _mix_bgm(narration_path, bgm_path, output_path, narration_duration):
    """나레이션에 BGM을 낮은 볼륨으로 믹싱."""
    result = subprocess.run(
        ["ffmpeg", "-y",
         "-i", narration_path,
         "-stream_loop", "-1", "-i", bgm_path,
         "-filter_complex",
         f"[1:a]volume={BGM_VOLUME},afade=t=out:st={narration_duration - 2}:d=2[bgm];"
         f"[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=2[out]",
         "-map", "[out]", "-c:a", "libmp3lame", "-q:a", "2",
         output_path],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        logger.error(f"[BGM] 믹싱 실패: {result.stderr[:200]}")
        return narration_path
    logger.info(f"[BGM] 믹싱 완료")
    return output_path


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

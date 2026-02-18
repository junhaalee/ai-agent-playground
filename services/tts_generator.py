import os
import asyncio
import logging
import edge_tts

logger = logging.getLogger(__name__)

VOICE = "ko-KR-InJoonNeural"
# edge-tts timing uses 100-nanosecond units (1 tick = 100ns)
_TICKS_PER_SEC = 10_000_000


async def _generate_single(text, audio_path):
    """Generate TTS audio and extract subtitle timing from SentenceBoundary."""
    communicate = edge_tts.Communicate(text, VOICE)
    segments = []

    with open(audio_path, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "SentenceBoundary":
                offset = chunk.get("offset", 0)
                duration = chunk.get("duration", 0)
                start_sec = offset / _TICKS_PER_SEC
                end_sec = (offset + duration) / _TICKS_PER_SEC
                segments.append({
                    "text": chunk.get("text", ""),
                    "start": start_sec,
                    "end": end_sec,
                })

    # Verify audio was actually written
    if os.path.getsize(audio_path) == 0:
        raise RuntimeError("TTS produced empty audio")

    return segments


def generate_narration_sync(summary_sentences_list, temp_dir):
    """요약된 문장 리스트를 받아 기사별 TTS 생성.

    Args:
        summary_sentences_list: [[문장1, 문장2, ...], [문장1, ...], ...]
            각 기사의 요약 문장 리스트
        temp_dir: 임시 파일 디렉토리

    Returns:
        (audio_paths, all_subtitle_segments)
        audio_paths: list of MP3 file paths
        all_subtitle_segments: list of list of {text, start, end}
    """
    os.makedirs(temp_dir, exist_ok=True)
    audio_paths = []
    all_segments = []

    loop = asyncio.new_event_loop()

    for i, sentences in enumerate(summary_sentences_list):
        # 문장들을 하나의 나레이션 텍스트로 합침
        text = " ".join(sentences)
        audio_path = os.path.join(temp_dir, f"narration_{i}.mp3")

        try:
            segments = loop.run_until_complete(_generate_single(text, audio_path))
            audio_paths.append(audio_path)
            all_segments.append(segments)
            logger.info(f"TTS generated for article {i}: {len(segments)} subtitle segments")
        except Exception as e:
            logger.error(f"TTS failed for article {i}: {e}")
            raise RuntimeError(f"음성 생성 실패 (기사 {i + 1}): {e}")

    loop.close()
    return audio_paths, all_segments

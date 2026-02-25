import os
import base64
import logging
from elevenlabs import ElevenLabs
import config

logger = logging.getLogger(__name__)

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = ElevenLabs(api_key=config.ELEVENLABS_API_KEY)
    return _client


def _generate_single(text, audio_path):
    """ElevenLabs TTS로 음성 생성 + 글자별 타임스탬프로 문장 싱크 계산."""
    client = _get_client()

    result = client.text_to_speech.convert_with_timestamps(
        voice_id=config.ELEVENLABS_VOICE_ID,
        text=text,
        model_id="eleven_multilingual_v2",
        output_format="mp3_44100_128",
    )

    # 오디오 저장
    audio_bytes = base64.b64decode(result.audio_base_64)
    with open(audio_path, "wb") as f:
        f.write(audio_bytes)

    if os.path.getsize(audio_path) == 0:
        raise RuntimeError("TTS produced empty audio")

    # 글자별 타임스탬프에서 문장별 타이밍 추출
    alignment = result.alignment
    chars = alignment.characters
    starts = alignment.character_start_times_seconds
    ends = alignment.character_end_times_seconds

    segments = []
    sentence_start = 0

    for i, char in enumerate(chars):
        if char in ".!?" and i > 0:
            # 문장 끝 발견 → 세그먼트 생성
            sentence_text = "".join(chars[sentence_start:i + 1]).strip()
            if sentence_text:
                segments.append({
                    "text": sentence_text,
                    "start": starts[sentence_start],
                    "end": ends[i],
                })
            sentence_start = i + 1
            # 공백 건너뛰기
            while sentence_start < len(chars) and chars[sentence_start] == " ":
                sentence_start += 1

    # 마지막 문장 (마침표 없이 끝난 경우)
    if sentence_start < len(chars):
        remaining = "".join(chars[sentence_start:]).strip()
        if remaining:
            segments.append({
                "text": remaining,
                "start": starts[sentence_start],
                "end": ends[-1],
            })

    if not segments:
        segments = [{"text": text, "start": 0.0, "end": ends[-1] if ends else 5.0}]

    logger.info(f"[TTS] 타임스탬프 기반 {len(segments)}개 세그먼트 생성")
    for seg in segments:
        logger.debug(f"  [{seg['start']:.2f}-{seg['end']:.2f}] {seg['text']}")

    return segments


def generate_narration_sync(summary_sentences_list, temp_dir):
    """요약된 문장 리스트를 받아 TTS 생성.

    Args:
        summary_sentences_list: [[문장1, 문장2, ...], [문장1, ...], ...]
        temp_dir: 임시 파일 디렉토리

    Returns:
        (audio_paths, all_subtitle_segments)
    """
    os.makedirs(temp_dir, exist_ok=True)
    audio_paths = []
    all_segments = []

    for i, sentences in enumerate(summary_sentences_list):
        text = " ".join(sentences)
        audio_path = os.path.join(temp_dir, f"narration_{i}.mp3")

        try:
            segments = _generate_single(text, audio_path)
            audio_paths.append(audio_path)
            all_segments.append(segments)
            logger.info(f"TTS generated for article {i}: {len(segments)} subtitle segments")
        except Exception as e:
            logger.error(f"TTS failed for article {i}: {e}")
            raise RuntimeError(f"음성 생성 실패 (기사 {i + 1}): {e}")

    return audio_paths, all_segments

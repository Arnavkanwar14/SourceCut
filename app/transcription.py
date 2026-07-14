from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from .media import extract_audio


@lru_cache(maxsize=1)
def model():
    from faster_whisper import WhisperModel

    # ponytail: CPU int8 is intentionally fixed for this machine; add selectable models only after the core flow needs it.
    return WhisperModel("tiny.en", device="cpu", compute_type="int8")


def transcribe_media(source: Path) -> list[dict]:
    audio = extract_audio(source)
    try:
        segments, _ = model().transcribe(str(audio), word_timestamps=True, vad_filter=True)
        return [
            {
                "start": round(segment.start, 2),
                "end": round(segment.end, 2),
                "text": segment.text.strip(),
                "words": [
                    {"start": round(word.start, 2), "end": round(word.end, 2), "text": word.word.strip()}
                    for word in (segment.words or [])
                ],
            }
            for segment in segments
            if segment.text.strip()
        ]
    finally:
        audio.unlink(missing_ok=True)

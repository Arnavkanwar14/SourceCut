from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any


NARRATION_LOGIC_VERSION = "beat-sync-v1"
MIN_BEAT_WORDS = 3
MAX_BEAT_WORDS = 24
MAX_TTS_SPEED = 1.10
CROSSFADE_SECONDS = 0.06
MAX_POSTROLL_SECONDS = 2.0


@dataclass(frozen=True)
class NarrationBeat:
    source_id: str
    desired_start: float
    text: str

    @property
    def word_count(self) -> int:
        return len(re.findall(r"\b[\w'-]+\b", self.text))


def with_terminal_punctuation(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if text and text[-1] not in ".!?":
        text += "."
    return text


def sentence_units(text: str) -> list[str]:
    normalized = with_terminal_punctuation(text)
    return [with_terminal_punctuation(unit) for unit in re.split(r"(?<=[.!?])\s+", normalized) if unit.strip()]


def source_narration_beats(segments: list[Any], clip_start: float, clip_end: float) -> list[NarrationBeat]:
    """Use each source sentence once, in source order, at its own source-time slot."""
    beats: list[NarrationBeat] = []
    seen: set[str] = set()
    for segment in segments:
        start = max(clip_start, float(segment["start"]))
        end = min(clip_end, float(segment["end"]))
        if end <= start:
            continue
        sentences = sentence_units(str(segment["text"]))
        for index, text in enumerate(sentences, 1):
            identity = text.casefold()
            if not text or identity in seen:
                continue
            seen.add(identity)
            desired_start = start + (end - start) * (index - 1) / max(1, len(sentences))
            beats.append(NarrationBeat(f"segment-{segment['id']}-{index}", desired_start - clip_start, text))
    return beats


def target_window(beats: list[NarrationBeat], index: int, clip_duration: float) -> float:
    next_start = beats[index + 1].desired_start if index + 1 < len(beats) else clip_duration
    return max(0.35, next_start - beats[index].desired_start)


def speed_for_window(measured_duration: float, available_seconds: float) -> float:
    if measured_duration <= 0 or available_seconds <= 0:
        return 1.0
    return min(MAX_TTS_SPEED, max(1.0, measured_duration / available_seconds))


def schedule_beats(beats: list[NarrationBeat], durations: list[float]) -> list[dict[str, object]]:
    """Delay overruns without cutting words, then naturally re-sync at the next gap."""
    cursor = 0.0
    scheduled: list[dict[str, object]] = []
    for beat, duration in zip(beats, durations):
        start = max(beat.desired_start, cursor - CROSSFADE_SECONDS)
        cursor = start + duration
        scheduled.append({**asdict(beat), "duration": round(duration, 3), "start": round(start, 3)})
    return scheduled

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from .review import Candidate, Evidence, TranscriptSegment, review_claim


class ModelCandidate(BaseModel):
    title: str
    draft: str
    evidence: Evidence


class ModelCandidateSet(BaseModel):
    candidates: list[ModelCandidate]


SYSTEM_PROMPT = """You select short-form marketing content candidates from a transcript.
Return exactly three candidates. Each candidate needs a concise title and an 8 to 18 word, source-grounded draft ending in terminal punctuation,
and one evidence object using exact transcript segment IDs, an exact quote, and timestamp bounds.
Do not invent facts, outcomes, or source quotes. Preserve qualifiers such as pilot scope and up to.
"""


def configured_model() -> str | None:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass
    if os.getenv("SOURCECUT_LIVE_ANALYSIS") != "1":
        return None
    if not os.getenv("OPENAI_API_KEY"):
        return None
    return os.getenv("OPENAI_MODEL", "gpt-5.6")


def transcript_prompt(segments: list[TranscriptSegment]) -> str:
    rows = [f"{segment.id} | {segment.start:.2f}-{segment.end:.2f} | {segment.text}" for segment in segments]
    return "Transcript:\n" + "\n".join(rows)


def generate_candidates(
    segments: list[TranscriptSegment],
    *,
    api_key: str | None = None,
    model: str | None = None,
    client_factory: Callable[..., Any] | None = None,
) -> list[Candidate] | None:
    selected_model = model or configured_model()
    selected_key = api_key or os.getenv("OPENAI_API_KEY")
    if not segments or not selected_model or not selected_key:
        return None
    try:
        if client_factory is None:
            from openai import OpenAI

            client_factory = OpenAI
        client = client_factory(api_key=selected_key)
        response = client.responses.parse(
            model=selected_model,
            input=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": transcript_prompt(segments)},
            ],
            text_format=ModelCandidateSet,
        )
        parsed = response.output_parsed
        if not parsed:
            return None
        return [
            Candidate(
                title=item.title,
                draft=item.draft,
                claim=review_claim(item.draft, item.evidence, segments),
            )
            for item in parsed.candidates[:3]
        ]
    except Exception:
        return None

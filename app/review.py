from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel


Status = Literal["supported", "unsupported", "needs_review"]


class TranscriptSegment(BaseModel):
    id: str
    start: float
    end: float
    text: str


class Evidence(BaseModel):
    segment_ids: list[str]
    quote: str
    start: float
    end: float


class ClaimReview(BaseModel):
    text: str
    status: Status
    reason: str
    rewrite: str
    evidence: Evidence | None


class Candidate(BaseModel):
    title: str
    draft: str
    claim: ClaimReview


def normalized(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9% ]", " ", text.lower())).strip()


def review_claim(text: str, evidence: Evidence | None, segments: list[TranscriptSegment]) -> ClaimReview:
    if not evidence:
        return ClaimReview(text=text, status="needs_review", reason="No transcript evidence was supplied.", rewrite=text, evidence=None)
    sources = {segment.id: segment for segment in segments}
    cited = [sources.get(segment_id) for segment_id in evidence.segment_ids]
    if not cited or any(segment is None for segment in cited):
        return ClaimReview(text=text, status="needs_review", reason="The cited transcript segment is missing.", rewrite=text, evidence=evidence)
    source_text = " ".join(segment.text for segment in cited if segment)
    source_start = min(segment.start for segment in cited if segment)
    source_end = max(segment.end for segment in cited if segment)
    if normalized(evidence.quote) not in normalized(source_text):
        return ClaimReview(text=text, status="needs_review", reason="The displayed quote does not match the cited transcript.", rewrite=text, evidence=evidence)
    if evidence.start < source_start or evidence.end > source_end:
        return ClaimReview(text=text, status="needs_review", reason="The evidence timestamp falls outside the cited transcript.", rewrite=text, evidence=evidence)
    claim_words = set(normalized(text).split()) - {"a", "an", "the", "and", "in", "to", "of", "by", "for", "with"}
    quote_words = set(normalized(source_text).split())
    if claim_words and not claim_words.intersection(quote_words):
        return ClaimReview(text=text, status="needs_review", reason="The claim is not grounded in the cited wording.", rewrite=text, evidence=evidence)
    claim_text = normalized(text)
    quote_text = normalized(source_text)
    if re.search(r"\b(all|every|always|guarantee[sd]?)\b", claim_text) and not re.search(r"\b(all|every|always|guarantee[sd]?)\b", quote_text):
        return ClaimReview(text=text, status="unsupported", reason="The draft makes an absolute claim not present in the source.", rewrite=evidence.quote, evidence=evidence)
    if re.search(r"\d|percent|%", claim_text) and (("up to" in quote_text and "up to" not in claim_text) or ("pilot" in quote_text and "pilot" not in claim_text)):
        return ClaimReview(text=text, status="unsupported", reason="The draft drops a source qualifier from a numerical claim.", rewrite=evidence.quote, evidence=evidence)
    return ClaimReview(text=text, status="supported", reason="The claim preserves the cited transcript wording.", rewrite=text, evidence=evidence)


def local_candidates(segments: list[TranscriptSegment]) -> list[Candidate]:
    if not segments:
        return []
    metric = next((segment for segment in segments if re.search(r"\d|percent|%", segment.text.lower())), segments[0])
    workflow = next(
        (
            segment for segment in segments
            if re.search(r"\b(bring|together|workflow|skills)\b", segment.text.lower())
        ),
        next((segment for segment in segments if "review" in segment.text.lower()), segments[min(1, len(segments) - 1)]),
    )
    outcome = segments[min(2, len(segments) - 1)]

    def evidence(segment: TranscriptSegment) -> Evidence:
        return Evidence(segment_ids=[segment.id], quote=segment.text, start=segment.start, end=segment.end)

    number = re.search(r"(?:up to )?\d+(?:\.\d+)?(?:\s*(?:percent|%))?", metric.text.lower())
    risky = f"Teams reduce handoff time by {number.group(0).replace('up to ', '')}." if number else "Teams get faster results."
    return [
        Candidate(title="Pilot result, with context", draft=metric.text, claim=review_claim(metric.text, evidence(metric), segments)),
        Candidate(title="Risky performance promise", draft=risky, claim=review_claim(risky, evidence(metric), segments)),
        Candidate(title="Workflow proof", draft=workflow.text, claim=review_claim(workflow.text, evidence(workflow), segments)),
    ]

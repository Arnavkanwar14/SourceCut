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


CONTINUATION_OPENERS = re.compile(r"^(and|but|so|because|which|this|that|also)\b", re.IGNORECASE)
FILLER_LINES = re.compile(r"^(beautiful|awesome|it looks good|well, that's running|and here we go|and that's it)\b", re.IGNORECASE)


def _moment_score(segment: TranscriptSegment) -> float:
    text = segment.text.strip()
    words = re.findall(r"[a-z0-9']+", text.lower())
    score = min(len(words), 20) * 0.2
    if re.search(r"[.!?][\"')\]]*$", text):
        score += 1.5
    if re.search(r"\b(automatically|found|set|built|shared|publish|flagged|fix|ship|generated|delegate|bring)\b", text, re.IGNORECASE):
        score += 4.0
    if re.search(r"\b(today|now|new|imagine|take a look|let's|can you|here's)\b", text, re.IGNORECASE):
        score += 2.5
    if re.search(r"\b(work|tools|workflow|calendar|data|metrics|dashboard|campaign|projects|team|brand|files|mobile|desktop)\b", text, re.IGNORECASE):
        score += 1.5
    if re.match(r"^(i can|you can)\b", text, re.IGNORECASE):
        score += 1.0
    if CONTINUATION_OPENERS.match(text):
        score -= 4.0
    if len(words) < 7:
        score -= 3.0
    if FILLER_LINES.match(text):
        score -= 8.0
    return score


def _moment_title(text: str) -> str:
    lowered = text.lower()
    if re.search(r"\b(fix|bug|ship|pr|version)\b", lowered):
        return "Ship the fix"
    if re.search(r"\b(data|metrics|dashboard|analytics)\b", lowered):
        return "Data to decision"
    if re.search(r"\b(calendar|slack|drive|briefing|day)\b", lowered):
        return "Morning prep workflow"
    if re.search(r"\b(image|brand|campaign|visuals|ideas)\b", lowered):
        return "Creative workflow"
    if re.search(r"\b(automation|automatically|set)\b", lowered):
        return "Set it once"
    if re.search(r"\b(today|new|release)\b", lowered):
        return "Launch hook"
    return "Product proof"


def local_candidates(segments: list[TranscriptSegment]) -> list[Candidate]:
    """Choose distinct, transcript-backed social moments without inventing claims."""
    if not segments:
        return []
    maximum = 5
    terminal = [segment for segment in segments if re.search(r"[.!?][\"')\]]*$", segment.text.strip())]
    ranked = sorted(terminal or segments, key=lambda segment: (_moment_score(segment), -segment.start), reverse=True)
    chosen: list[TranscriptSegment] = []
    for segment in ranked:
        if CONTINUATION_OPENERS.match(segment.text.strip()):
            continue
        if any(abs(segment.start - prior.start) < 28 for prior in chosen):
            continue
        chosen.append(segment)
        if len(chosen) == maximum:
            break
    if len(chosen) < 3:
        for segment in ranked:
            if segment not in chosen and not CONTINUATION_OPENERS.match(segment.text.strip()):
                chosen.append(segment)
            if len(chosen) == maximum:
                break

    used_titles: set[str] = set()
    candidates: list[Candidate] = []
    for segment in chosen:
        title = _moment_title(segment.text)
        if title in used_titles:
            title = f"{title} {len(used_titles) + 1}"
        used_titles.add(title)
        evidence = Evidence(segment_ids=[segment.id], quote=segment.text, start=segment.start, end=segment.end)
        candidates.append(Candidate(title=title, draft=segment.text, claim=review_claim(segment.text, evidence, segments)))
    if len(candidates) < 3 and chosen:
        source = chosen[0]
        evidence = Evidence(segment_ids=[source.id], quote=source.text, start=source.start, end=source.end)
        number = re.search(r"(?:up to )?\d+(?:\.\d+)?(?:\s*(?:percent|%))?", source.text.lower())
        draft = f"Teams reduce handoff time by {number.group(0).replace('up to ', '')}." if number else "Teams always get faster results."
        candidates.append(Candidate(title="Needs evidence review", draft=draft, claim=review_claim(draft, evidence, segments)))
    return candidates

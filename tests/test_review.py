import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.llm import ModelCandidate, ModelCandidateSet, SYSTEM_PROMPT, generate_candidates
from app.production import clean_clip_window
from app.review import Evidence, TranscriptSegment, local_candidates, review_claim


FIXTURE = Path(__file__).parent / "fixtures" / "evidence_cases.json"


def test_evidence_cases_match_expected_statuses() -> None:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    segments = [TranscriptSegment.model_validate(segment) for segment in data["segments"]]
    for case in data["cases"]:
        evidence = Evidence.model_validate(case["evidence"]) if case["evidence"] else None
        assert review_claim(case["claim"], evidence, segments).status == case["expected"], case["claim"]


def test_model_drafts_have_a_minimum_and_maximum_word_budget() -> None:
    assert "8 to 18 word" in SYSTEM_PROMPT
    assert "terminal punctuation" in SYSTEM_PROMPT


def test_evidence_requires_complete_structure() -> None:
    with pytest.raises(ValidationError):
        Evidence.model_validate({"segment_ids": ["s1"], "quote": "missing timestamps"})


def test_model_candidates_are_rechecked_against_transcript() -> None:
    segments = [TranscriptSegment(id="s1", start=18.0, end=24.0, text="In a pilot, teams reduced handoff time by up to 40 percent.")]

    class FakeResponses:
        def parse(self, **_: object) -> object:
            candidate = ModelCandidate(
                title="Risky promise",
                draft="Every team reduced handoff time by 40 percent.",
                evidence=Evidence(segment_ids=["s1"], quote=segments[0].text, start=18.0, end=24.0),
            )
            return type("Response", (), {"output_parsed": ModelCandidateSet(candidates=[candidate])})()

    class FakeClient:
        responses = FakeResponses()

    candidates = generate_candidates(segments, api_key="test-key", model="gpt-5.6", client_factory=lambda **_: FakeClient())
    assert candidates
    assert candidates[0].claim.status == "unsupported"


def test_auto_clip_window_finishes_the_spoken_thought() -> None:
    segments = [
        TranscriptSegment(id="s1", start=1.0, end=3.0, text="A thought begins"),
        TranscriptSegment(id="s2", start=3.0, end=5.0, text="and ends here."),
        TranscriptSegment(id="s3", start=6.0, end=11.0, text="A second complete thought follows."),
    ]
    start, end = clean_clip_window(segments, "s2", 30.0)
    assert start == pytest.approx(1.0)
    assert end == pytest.approx(11.0)


def test_auto_clip_window_never_runs_into_the_next_spoken_segment() -> None:
    segments = [
        TranscriptSegment(id="s1", start=150.31, end=150.45, text="Beautiful."),
        TranscriptSegment(id="s2", start=150.63, end=152.43, text="Ready for our launch review meeting today."),
        TranscriptSegment(id="s3", start=157.34, end=160.22, text="Let's switch gears to data science."),
        TranscriptSegment(id="s4", start=162.42, end=167.76, text="The metrics are in different places."),
        TranscriptSegment(id="s5", start=168.24, end=170.50, text="And I used ChatGPT to bring them together."),
    ]
    start, end = clean_clip_window(segments, "s5", 30.0)
    assert start == pytest.approx(162.42)
    assert end == pytest.approx(170.50)


def test_local_candidates_choose_distinct_source_backed_product_moments() -> None:
    segments = [
        TranscriptSegment(id="s1", start=1, end=4, text="Today, we are releasing a new product workflow."),
        TranscriptSegment(id="s2", start=6, end=9, text="And it connects your tools in one place."),
        TranscriptSegment(id="s3", start=40, end=45, text="ChatGPT automatically brought the metrics together in one dashboard."),
        TranscriptSegment(id="s4", start=80, end=85, text="Publish the fix so the team can ship a new version of the app."),
    ]
    candidates = local_candidates(segments)
    assert [candidate.claim.evidence.segment_ids for candidate in candidates] == [["s4"], ["s3"], ["s1"]]
    assert all(candidate.claim.status == "supported" for candidate in candidates)

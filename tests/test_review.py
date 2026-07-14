import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.llm import ModelCandidate, ModelCandidateSet, generate_candidates
from app.review import Evidence, TranscriptSegment, review_claim


FIXTURE = Path(__file__).parent / "fixtures" / "evidence_cases.json"


def test_evidence_cases_match_expected_statuses() -> None:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    segments = [TranscriptSegment.model_validate(segment) for segment in data["segments"]]
    for case in data["cases"]:
        evidence = Evidence.model_validate(case["evidence"]) if case["evidence"] else None
        assert review_claim(case["claim"], evidence, segments).status == case["expected"], case["claim"]


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

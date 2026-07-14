import json
from pathlib import Path

import pytest
from pydantic import ValidationError

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

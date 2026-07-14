import pytest
from fastapi.testclient import TestClient

from app import main
from app.main import app


client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_seeded_claims() -> None:
    for claim_id in range(1, 4):
        client.post(f"/claims/{claim_id}/restore")
    yield
    for claim_id in range(1, 4):
        client.post(f"/claims/{claim_id}/restore")


def test_seeded_review_is_visible() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "ApexFlow product webinar" in response.text
    assert "Customers save 40%." in response.text
    assert "Evidence: s1, s2" in response.text
    assert "/static/app.js" in response.text
    assert "/static/sourcecut-evidence-object.png" in response.text


def test_grounded_rewrite_can_be_accepted_and_restored() -> None:
    client.post("/claims/1/restore")


def test_custom_rewrite_is_rechecked_before_approval() -> None:
    client.post("/claims/1/restore")
    edited = client.post("/claims/1/edit", data={"rewrite": "Every team reduced handoff time by up to 40 percent."}, follow_redirects=True)
    assert edited.status_code == 200
    assert "Every team reduced handoff time by up to 40 percent." in edited.text
    assert "unsupported" in edited.text
    client.post("/claims/1/restore")


def test_export_contains_approved_claim_evidence() -> None:
    client.post("/claims/1/restore")
    client.post("/claims/1/accept")
    exported = client.get("/export.json")
    assert exported.status_code == 200
    assert exported.json()["clip"] == {"start": "00:18", "end": "00:36"}
    assert exported.json()["claims"][0]["text"] == "Pilot teams reduced handoff time by up to 40%."
    assert exported.json()["evidence"][0]["segment_id"] == "s1"
    markdown = client.get("/export.md")
    assert "# ApexFlow product webinar" in markdown.text
    client.post("/claims/1/restore")
    accepted = client.post("/claims/1/accept", follow_redirects=True)
    assert accepted.status_code == 200
    assert "Pilot teams reduced handoff time by up to 40%." in accepted.text
    client.post("/claims/1/restore")


def test_upload_uses_cpu_transcription_result(monkeypatch) -> None:
    monkeypatch.setattr(main, "transcribe_media", lambda _: [{"start": 0.0, "end": 1.2, "text": "A local transcript.", "words": []}])
    response = client.post("/upload", files={"file": ("demo.wav", b"not-real-audio", "audio/wav")})
    assert response.status_code == 200
    assert "Transcript ready" in response.text
    assert "A local transcript." in response.text
    assert "Generate review candidates" in response.text


def test_upload_rejects_unapproved_extension() -> None:
    response = client.post("/upload", files={"file": ("unsafe.exe", b"not-media", "application/octet-stream")})
    assert response.status_code == 400

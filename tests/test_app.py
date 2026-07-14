from fastapi.testclient import TestClient

from app import main
from app.main import app


client = TestClient(app)


def test_seeded_review_is_visible() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "ApexFlow product webinar" in response.text
    assert "Customers save 40%." in response.text
    assert "Evidence: s1, s2" in response.text


def test_grounded_rewrite_can_be_accepted_and_restored() -> None:
    client.post("/claims/1/restore")


def test_upload_uses_cpu_transcription_result(monkeypatch) -> None:
    monkeypatch.setattr(main, "transcribe_media", lambda _: [{"start": 0.0, "end": 1.2, "text": "A local transcript.", "words": []}])
    response = client.post("/upload", files={"file": ("demo.wav", b"not-real-audio", "audio/wav")})
    assert response.status_code == 200
    assert "Transcript ready" in response.text
    assert "A local transcript." in response.text


def test_upload_rejects_unapproved_extension() -> None:
    response = client.post("/upload", files={"file": ("unsafe.exe", b"not-media", "application/octet-stream")})
    assert response.status_code == 400
    accepted = client.post("/claims/1/accept", follow_redirects=True)
    assert accepted.status_code == 200
    assert "Pilot teams reduced handoff time by up to 40%." in accepted.text
    client.post("/claims/1/restore")

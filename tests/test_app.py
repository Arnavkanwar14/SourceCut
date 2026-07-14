from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import main, production
from app.main import app


client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_seeded_claims() -> None:
    for claim_id in range(1, 4):
        client.post(f"/claims/{claim_id}/restore")
    yield
    for claim_id in range(1, 4):
        client.post(f"/claims/{claim_id}/restore")


def test_dashboard_explains_the_product_and_links_seed_review() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "Turn recordings into evidence-backed social clips." in response.text
    assert "ApexFlow product webinar" in response.text
    assert "/review" in response.text


def test_seeded_review_is_visible() -> None:
    response = client.get("/review")
    assert response.status_code == 200
    assert "Customers save 40%." in response.text
    assert "Evidence: s1, s2" in response.text
    assert "/static/app.js" in response.text
    assert "/static/sourcecut-spiral-reel-cut-object.png" in response.text
    assert "/static/sourcecut-seed-demo.mp4" in response.text


def test_grounded_rewrite_can_be_accepted_and_restored() -> None:
    accepted = client.post("/claims/1/accept", follow_redirects=True)
    assert accepted.status_code == 200
    assert "Pilot teams reduced handoff time by up to 40%." in accepted.text
    client.post("/claims/1/restore")


def test_custom_rewrite_is_rechecked_before_approval() -> None:
    edited = client.post("/claims/1/edit", data={"rewrite": "Every team reduced handoff time by up to 40 percent."}, follow_redirects=True)
    assert edited.status_code == 200
    assert "Every team reduced handoff time by up to 40 percent." in edited.text
    assert "unsupported" in edited.text


def test_export_contains_approved_claim_evidence() -> None:
    client.post("/claims/1/accept")
    exported = client.get("/export.json")
    assert exported.status_code == 200
    assert exported.json()["clip"] == {"start": "00:18", "end": "00:36"}
    assert exported.json()["claims"][0]["text"] == "Pilot teams reduced handoff time by up to 40%."
    assert exported.json()["evidence"][0]["segment_id"] == "s1"
    assert "# ApexFlow product webinar" in client.get("/export.md").text


def test_create_form_has_production_controls() -> None:
    response = client.get("/upload")
    assert response.status_code == 200
    for value in ("Up to 500 MB", "Shorts / Reels / TikTok", "Clip count", "Manual clips", "Plan quiet-gap trims", "AI voiceover", "Add proof cards"):
        assert value in response.text
    assert "Build the edit brief first." in response.text
    assert "data-source-file" in response.text
    assert "data-audio-mode" in response.text


def test_example_project_opens_with_player_and_proposals() -> None:
    response = client.post("/examples/production", follow_redirects=True)
    assert response.status_code == 200
    assert "SourceCut production example" in response.text
    assert "sourcecut-production-example.mp4" not in response.text
    assert "Review before render." in response.text
    assert "Source evidence" in response.text
    assert "selected for render" in response.text
    assert "Rebuild clip picks" in response.text


def test_project_can_be_deleted_from_library(tmp_path: Path) -> None:
    source = tmp_path / "delete-me.mp4"
    source.write_bytes(b"video")
    project_id = production.create_project("Delete test project", source, production.settings_from_form({}))
    deleted = client.post(f"/projects/{project_id}/delete", follow_redirects=True)
    assert deleted.status_code == 200
    assert "Delete test project" not in deleted.text
    assert client.get(f"/projects/{project_id}").status_code == 404
    assert source.exists()


def test_upload_creates_project_and_serves_source(monkeypatch) -> None:
    monkeypatch.setattr(main, "start_analysis", lambda _: 0)
    response = client.post("/upload", files={"file": ("desk-demo.mp4", b"not-real-video", "video/mp4")}, follow_redirects=False)
    assert response.status_code == 303
    project_url = response.headers["location"]
    project_id = int(project_url.rsplit("/", 1)[-1])
    workspace = client.get(project_url)
    assert workspace.status_code == 200
    assert "Review before render." in workspace.text
    source = client.get(f"/projects/{project_id}/source")
    assert source.status_code == 200
    assert source.content == b"not-real-video"


def test_analysis_creates_evidence_backed_proposals(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "original.mp4"
    source.write_bytes(b"video")
    settings = production.settings_from_form({})
    project_id = production.create_project("Original demo", source, settings)
    monkeypatch.setattr(production, "transcribe_media", lambda _: [
        {"start": 18.0, "end": 24.0, "text": "In a pilot, teams reduced handoff time by up to 40 percent."},
        {"start": 30.0, "end": 35.0, "text": "Teams used a review queue before publishing."},
    ])
    job_id = production.make_job(project_id, "analysis", "Queued")
    production.run_analysis(project_id, job_id)
    clips = production.get_clips(project_id)
    assert clips
    assert any(clip["claim_status"] == "supported" for clip in clips)
    unsupported = next(clip for clip in clips if clip["claim_status"] == "unsupported")
    blocked = client.post(f"/projects/{project_id}/clips/{unsupported['id']}/select", data={"selected": "true"})
    assert blocked.status_code == 422
    status = client.get(f"/projects/{project_id}/status")
    assert status.json()["job"]["status"] == "done"


def test_project_export_only_includes_selected_clips(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "original.mp4"
    source.write_bytes(b"video")
    project_id = production.create_project("Export demo", source, production.settings_from_form({}))
    monkeypatch.setattr(production, "transcribe_media", lambda _: [{"start": 2.0, "end": 8.0, "text": "Teams use a review queue before publishing."}])
    job_id = production.make_job(project_id, "analysis", "Queued")
    production.run_analysis(project_id, job_id)
    clip = production.get_clips(project_id)[0]
    assert production.set_selected(project_id, clip["id"], True)
    exported = client.get(f"/projects/{project_id}/export.json")
    assert exported.status_code == 200
    assert exported.json()["clips"][0]["evidence"]["quote"]


def test_failed_render_does_not_stop_other_selected_clips(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "original.mp4"
    source.write_bytes(b"video")
    project_id = production.create_project("Render isolation", source, production.settings_from_form({}))
    with production.closing(production.db()) as connection:
        for title in ("First", "Second"):
            connection.execute(
                "INSERT INTO clip_proposals (project_id, title, start, end, hook, caption, evidence_quote, claim_status, reason, selected) VALUES (?, ?, 0, 1, ?, ?, ?, 'supported', ?, 1)",
                (project_id, title, title, title, title, "Direct source wording."),
            )
        connection.commit()
    outcomes = iter([(False, "first render failed", ""), (True, "C:/temporary-second.mp4", "")])
    monkeypatch.setattr(production, "_render_one", lambda *_: next(outcomes))
    job_id = production.make_job(project_id, "render", "Queued")
    production.run_render(project_id, job_id)
    clips = production.get_clips(project_id)
    assert [clip["render_status"] for clip in clips] == ["failed", "ready"]


def test_upload_rejects_unapproved_extension() -> None:
    response = client.post("/upload", files={"file": ("unsafe.exe", b"not-media", "application/octet-stream")})
    assert response.status_code == 400


def test_upload_size_error_stays_in_create_screen(monkeypatch) -> None:
    monkeypatch.setattr(main, "save_upload", lambda *_: (_ for _ in ()).throw(HTTPException(status_code=400, detail="Files must be 500 MB or smaller.")))
    response = client.post("/upload", files={"file": ("large.mp4", b"source", "video/mp4")})
    assert response.status_code == 400
    assert "Files must be 500 MB or smaller." in response.text
    assert "Build production project" in response.text

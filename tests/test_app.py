from pathlib import Path
from zipfile import ZipFile

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import main, production
from app.main import app
from app.review import Candidate, Evidence, TranscriptSegment, review_claim


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
    assert "AI drafts your clips." in response.text
    assert "unsupported claim through." in response.text
    assert "ApexFlow product webinar" in response.text
    assert "/review" in response.text
    assert response.headers["content-security-policy"].startswith("default-src 'self'")
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert '/static/sourcecut-film-spiral-clip-object.png' in response.text


def test_cross_site_posts_cannot_change_local_workspace_state() -> None:
    blocked = client.post("/claims/1/accept", headers={"Origin": "https://untrusted.example"})
    assert blocked.status_code == 403
    assert client.get("/export.json").json()["claims"] == []

    allowed = client.post("/claims/1/accept", headers={"Origin": "http://testserver"}, follow_redirects=False)
    assert allowed.status_code == 303


def test_seeded_review_is_visible() -> None:
    response = client.get("/review")
    assert response.status_code == 200
    assert "Customers save 40%." in response.text
    assert "Evidence: s1, s2" in response.text
    assert "/static/app.js" in response.text
    assert "/static/sourcecut-film-spiral-clip-object.png" in response.text
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
    for value in ("Up to 500 MB", "Shorts / Reels / TikTok", "Clip count", "Manual clips", "Plan quiet-gap trims", "Kokoro voiceover", "Add proof cards"):
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
    assert "Local deterministic fallback" in response.text
    assert "Rendered production files" in response.text
    assert "/outputs/" in response.text
    assert "12 labelled cases. No live runner." in response.text
    assert "Drops the pilot scope and the up-to qualifier." in response.text


def test_judge_demo_deep_links_to_the_qualifier_drop_case() -> None:
    response = client.post("/examples/production", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].endswith("#scorecase-2")


def test_gpt_proposals_are_persisted_but_still_evidence_gated(monkeypatch, tmp_path: Path) -> None:
    segments = [TranscriptSegment(id="segment-1", start=1, end=5, text="In a pilot, teams reduced handoff time by up to 40 percent.")]
    evidence = Evidence(segment_ids=["segment-1"], quote=segments[0].text, start=1, end=5)
    risky = "Every team reduced handoff time by 40 percent."
    candidate = Candidate(title="Risky promise", draft=risky, claim=review_claim(risky, evidence, segments))
    monkeypatch.setattr(production, "generate_candidates", lambda _: [candidate])
    source = tmp_path / "model-demo.mp4"
    source.write_bytes(b"video")
    project_id = production.create_project("Model demo", source, production.settings_from_form({}))
    production._insert_proposals(project_id, segments, production.settings_from_form({}))

    project = production.get_project(project_id)
    clip = production.get_clips(project_id)[0]
    assert project["proposal_provider"] == "GPT-5.6 proposals, evidence verified locally"
    assert clip["claim_status"] == "unsupported"
    assert not production.set_selected(project_id, clip["id"], True)


def test_local_fallback_and_manual_ranges_are_labelled(monkeypatch, tmp_path: Path) -> None:
    segments = [TranscriptSegment(id="segment-1", start=1, end=5, text="Teams review product claims before publishing.")]
    monkeypatch.setattr(production, "generate_candidates", lambda _: None)
    source = tmp_path / "fallback-demo.mp4"
    source.write_bytes(b"video")
    project_id = production.create_project("Fallback demo", source, production.settings_from_form({}))
    production._insert_proposals(project_id, segments, production.settings_from_form({}))
    assert production.get_project(project_id)["proposal_provider"] == "Local deterministic fallback"

    manual = production.settings_from_form({"manual_clips": "00:01-00:04"})
    production._insert_proposals(project_id, segments, manual)
    assert production.get_project(project_id)["proposal_provider"] == "Manual source ranges, evidence review required"
    assert production.get_clips(project_id)[0]["claim_status"] == "needs_review"


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
    monkeypatch.setattr(production, "inspect_media", lambda _: 22.0)
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
    assert status.json()["job"]["progress"] == 100
    assert status.json()["job"]["started_at"]
    assert status.json()["job"]["finished_at"]
    fragments = client.get(f"/projects/{project_id}/workspace-fragments")
    assert fragments.status_code == 200
    assert "data-selection-form" in fragments.json()["clip_cards"]


def test_project_export_only_includes_selected_clips(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "original.mp4"
    source.write_bytes(b"video")
    project_id = production.create_project("Export demo", source, production.settings_from_form({}))
    monkeypatch.setattr(production, "inspect_media", lambda _: 8.0)
    monkeypatch.setattr(production, "transcribe_media", lambda _: [{"start": 2.0, "end": 8.0, "text": "Teams use a review queue before publishing."}])
    job_id = production.make_job(project_id, "analysis", "Queued")
    production.run_analysis(project_id, job_id)
    clip = production.get_clips(project_id)[0]
    assert production.set_selected(project_id, clip["id"], True)
    exported = client.get(f"/projects/{project_id}/export.json")
    assert exported.status_code == 200
    assert exported.json()["clips"][0]["evidence"]["quote"]


def test_finished_project_has_handoff_exports_and_truthful_audio(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    rendered = tmp_path / "finished.mp4"
    source.write_bytes(b"source")
    rendered.write_bytes(b"finished video")
    settings = production.settings_from_form({"audio_mode": "voiceover", "voice": "af_sarah"})
    project_id = production.create_project("Handoff demo", source, settings)
    with production.closing(production.db()) as connection:
        connection.execute("INSERT INTO project_segments (project_id, start, end, text) VALUES (?, 1, 4, ?)", (project_id, "Evidence quote."))
        segment_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
        connection.execute(
            "INSERT INTO clip_proposals (project_id, title, start, end, hook, caption, evidence_segment_id, evidence_quote, claim_status, reason, selected, render_status, output_path) VALUES (?, ?, 1, 4, ?, ?, ?, ?, 'supported', ?, 1, 'ready', ?)",
            (project_id, "Publishable moment", "Useful hook", "Copy-ready caption", segment_id, "Evidence quote.", "Direct source wording.", str(rendered)),
        )
        connection.commit()
    exported = client.get(f"/projects/{project_id}/export.json")
    assert exported.json()["render_settings"]["audio"] == "Kokoro local voiceover - Sarah"
    assert "Evidence quote." in client.get(f"/projects/{project_id}/export.md").text
    handoff = client.get(f"/projects/{project_id}/handoff")
    assert "Download ZIP" in handoff.text
    archive = client.get(f"/projects/{project_id}/handoff.zip")
    archive_path = tmp_path / "handoff.zip"
    archive_path.write_bytes(archive.content)
    with ZipFile(archive_path) as bundle:
        assert {"evidence-package.json", "evidence-package.md", "videos/finished.mp4"}.issubset(bundle.namelist())


def test_clip_selection_returns_json_without_reloading_workspace(tmp_path: Path) -> None:
    source = tmp_path / "selection-demo.mp4"
    source.write_bytes(b"video")
    project_id = production.create_project("Selection demo", source, production.settings_from_form({}))
    with production.closing(production.db()) as connection:
        cursor = connection.execute(
            "INSERT INTO clip_proposals (project_id, title, start, end, hook, caption, evidence_quote, claim_status, reason) VALUES (?, ?, 0, 1, ?, ?, ?, 'supported', ?)",
            (project_id, "Moment", "Moment", "Moment", "Moment", "Direct source wording."),
        )
        connection.commit()
    response = client.post(
        f"/projects/{project_id}/clips/{cursor.lastrowid}/select",
        data={"selected": "true"},
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 200
    assert response.json() == {"clip_id": cursor.lastrowid, "selected": True, "selected_count": 1, "clip_count": 1}


def test_workspace_client_uses_in_place_updates_and_reduced_motion() -> None:
    root = Path(__file__).parent.parent
    script = (root / "static" / "app.js").read_text(encoding="utf-8")
    styles = (root / "static" / "style.css").read_text(encoding="utf-8")
    assert "window.location.reload" not in script
    assert "sourcecut:job-started" in script
    assert "const asyncAction" in script
    assert "const essential" in script
    assert "will-reveal" in styles
    assert "prefers-reduced-motion" in styles


def test_render_starts_without_reloading_workspace(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "render-demo.mp4"
    source.write_bytes(b"video")
    project_id = production.create_project("Render demo", source, production.settings_from_form({}))
    with production.closing(production.db()) as connection:
        connection.execute(
            "INSERT INTO clip_proposals (project_id, title, start, end, hook, caption, evidence_quote, claim_status, reason, selected) VALUES (?, ?, 0, 1, ?, ?, ?, 'supported', ?, 1)",
            (project_id, "Moment", "Hook", "Caption", "Exact source quote.", "Direct source wording."),
        )
        connection.commit()
    monkeypatch.setattr(main, "start_render", lambda project_id: production.make_job(project_id, "render", "Queued"))
    response = client.post(f"/projects/{project_id}/render", headers={"Accept": "application/json"})
    assert response.status_code == 202
    assert response.json()["action"] == "render_started"
    assert response.json()["job"]["status"] == "queued"


def test_duplicate_upload_reopens_existing_project(monkeypatch) -> None:
    monkeypatch.setattr(main, "start_analysis", lambda _: 0)
    first = client.post("/upload", files={"file": ("same.mp4", b"one-source", "video/mp4")}, follow_redirects=False)
    second = client.post("/upload", files={"file": ("same.mp4", b"one-source", "video/mp4")}, follow_redirects=False)
    assert first.status_code == second.status_code == 303
    assert first.headers["location"] == second.headers["location"]


def test_interrupted_job_is_marked_retryable(tmp_path: Path) -> None:
    source = tmp_path / "interrupted.mp4"
    source.write_bytes(b"video")
    project_id = production.create_project("Interrupted", source, production.settings_from_form({}))
    job_id = production.make_job(project_id, "render", "Queued")
    production.update_job(job_id, "running", "Render selected clips", "Working", 30)
    assert production.recover_interrupted_jobs() >= 1
    job = production.latest_job(project_id)
    assert job["status"] == "failed"
    assert job["stage"] == "Interrupted"
    assert "Retry" in job["detail"]


def test_cached_render_reuses_verified_output(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    output = tmp_path / "cached.mp4"
    source.write_bytes(b"source")
    output.write_bytes(b"cached")
    project_id = production.create_project("Cached render", source, production.settings_from_form({}))
    with production.closing(production.db()) as connection:
        connection.execute(
            "INSERT INTO clip_proposals (project_id, title, start, end, hook, caption, evidence_quote, claim_status, reason, selected, render_status, output_path) VALUES (?, ?, 0, 1, ?, ?, ?, 'supported', ?, 1, 'ready', ?)",
            (project_id, "Cached", "Hook", "Caption", "Quote", "Evidence", str(output)),
        )
        connection.commit()
    monkeypatch.setattr(production, "_render_one", lambda *_: (_ for _ in ()).throw(AssertionError("cache should be reused")))
    job_id = production.make_job(project_id, "render", "Queued")
    production.run_render(project_id, job_id)
    assert production.latest_job(project_id)["status"] == "done"


def test_voiceover_uses_kokoro_voices_and_never_falls_back_to_source_audio(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "voiceover-demo.mp4"
    source.write_bytes(b"video")
    settings = production.settings_from_form({"audio_mode": "voiceover", "voice": "en-US-AvaMultilingualNeural", "captions": "none"})
    assert settings["voice"] == "af_sarah"
    project_id = production.create_project("Voiceover demo", source, settings)
    with production.closing(production.db()) as connection:
        connection.execute(
            "INSERT INTO clip_proposals (project_id, title, start, end, hook, caption, evidence_quote, claim_status, reason, selected) VALUES (?, ?, 0, 1, ?, ?, ?, 'supported', ?, 1)",
            (project_id, "Moment", "Hook", "Caption", "Exact supported source quote.", "Direct source wording."),
        )
        connection.commit()
    monkeypatch.setattr(production, "_synthesize_kokoro_voice", lambda *_: (_ for _ in ()).throw(RuntimeError("voice engine unavailable")))
    ok, detail, warning = production._render_one(production.get_project(project_id), production.get_clips(project_id)[0], settings)
    assert not ok
    assert "Local Kokoro voiceover failed" in detail
    assert warning == ""


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

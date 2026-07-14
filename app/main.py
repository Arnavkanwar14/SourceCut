from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from html import escape
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from .export import build_package, markdown
from .media import save_upload
from .production import (
    PLATFORMS,
    create_example_project,
    create_project,
    delete_project,
    get_clips,
    get_project,
    get_segments,
    init_db as init_production_db,
    latest_job,
    list_projects,
    output_path,
    refine_project_cuts,
    set_selected,
    settings_from_form,
    start_analysis,
    start_render,
)
from .review import Evidence, TranscriptSegment, review_claim


ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "sourcecut.db"
TRANSCRIPT = [
    ("s1", "00:18", "In a 12-customer pilot, teams reduced handoff time by up to 40 percent."),
    ("s2", "00:32", "The pilot was small, so we are not claiming this result for every customer yet."),
    ("s3", "01:04", "Participants used the review queue to check product claims before publishing."),
    ("s4", "01:42", "One pilot team cut its weekly approval meeting from 90 minutes to 45 minutes."),
]
SEED_CLAIMS = [
    ("Customers save 40%.", "unsupported", "The source says 'up to 40 percent' in a 12-customer pilot, not a result for all customers.", "Pilot teams reduced handoff time by up to 40%.", "s1,s2"),
    ("Teams can review product claims before publishing.", "supported", "The source directly describes the review queue workflow.", "Teams used a review queue to check product claims before publishing.", "s3"),
    ("Approval meetings are cut in half.", "needs_review", "One pilot team reported this result; the source does not establish it as a general outcome.", "One pilot team cut its weekly approval meeting from 90 to 45 minutes.", "s4"),
]
SEED_SEGMENTS = [
    TranscriptSegment(id="s1", start=18.0, end=24.0, text=TRANSCRIPT[0][2]),
    TranscriptSegment(id="s2", start=32.0, end=36.0, text=TRANSCRIPT[1][2]),
    TranscriptSegment(id="s3", start=64.0, end=68.0, text=TRANSCRIPT[2][2]),
    TranscriptSegment(id="s4", start=102.0, end=108.0, text=TRANSCRIPT[3][2]),
]
SEED_SEGMENT_BY_ID = {segment.id: segment for segment in SEED_SEGMENTS}


app = FastAPI(title="SourceCut")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


def db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    with closing(db()) as connection:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS claims (
            id INTEGER PRIMARY KEY, draft TEXT NOT NULL, status TEXT NOT NULL,
            reason TEXT NOT NULL, rewrite TEXT NOT NULL, evidence_ids TEXT NOT NULL,
            approved INTEGER NOT NULL DEFAULT 0)"""
        )
        if not connection.execute("SELECT 1 FROM claims LIMIT 1").fetchone():
            connection.executemany(
                "INSERT INTO claims (draft, status, reason, rewrite, evidence_ids) VALUES (?, ?, ?, ?, ?)",
                SEED_CLAIMS,
            )
        connection.commit()
    init_production_db()


@app.on_event("startup")
def startup() -> None:
    init_db()


def get_claims() -> list[sqlite3.Row]:
    init_db()
    with closing(db()) as connection:
        return connection.execute("SELECT * FROM claims ORDER BY id").fetchall()


def get_claim(claim_id: int) -> sqlite3.Row:
    init_db()
    with closing(db()) as connection:
        claim = connection.execute("SELECT * FROM claims WHERE id = ?", (claim_id,)).fetchone()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    return claim


def review_seeded_rewrite(claim: sqlite3.Row, rewrite: str):
    segment_id = claim["evidence_ids"].split(",")[0]
    segment = SEED_SEGMENT_BY_ID[segment_id]
    evidence = Evidence(segment_ids=[segment.id], quote=segment.text, start=segment.start, end=segment.end)
    return review_claim(rewrite, evidence, SEED_SEGMENTS)


def document(title: str, context: str, action_href: str, action_label: str, status: str, content: str) -> str:
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{escape(title)} | SourceCut</title><link rel="stylesheet" href="/static/style.css"><script defer src="/static/app.js"></script></head><body>
    <header class="topbar" data-reveal><a class="brand" href="/" aria-label="SourceCut dashboard">SOURCECUT</a><span class="product-context">{escape(context)}</span><nav aria-label="Primary navigation"><a href="/">Projects</a><a href="/upload">Create</a><a href="/#outputs">Outputs</a></nav><a class="nav-action" href="{action_href}">{escape(action_label)}</a><b class="mode-chip">{escape(status)}</b></header>
    <main>{content}</main><footer data-reveal>SourceCut evaluates support in the shown source transcript. It does not certify real-world, legal, or compliance truth.</footer></body></html>'''


def evidence_object() -> str:
    return '''<div class="object-stage" aria-hidden="true"><span class="object-orbit orbit-one"></span><span class="object-orbit orbit-two"></span><img src="/static/sourcecut-evidence-object.png" alt=""></div>'''


def project_header(eyebrow: str, title: str, detail: str, stat: str = "", stat_label: str = "") -> str:
    progress = f'''<div class="progress" data-reveal><strong>{escape(stat)}</strong><span>{escape(stat_label)}</span></div>''' if stat else ""
    return f'''<section class="project-hero" data-reveal><div class="hero-copy"><p class="eyebrow">{escape(eyebrow)}</p><h1>{escape(title)}</h1><p class="hero-detail">{detail}</p>{progress}</div>{evidence_object()}</section>'''


def format_time(seconds: float) -> str:
    minutes, remainder = divmod(max(0, int(seconds)), 60)
    return f"{minutes:02d}:{remainder:02d}"


def claim_html(claim: sqlite3.Row) -> str:
    status = "approved" if claim["approved"] else claim["status"]
    text = claim["rewrite"] if claim["approved"] else claim["draft"]
    evidence = claim["evidence_ids"].replace(",", ", ")
    action = (
        f'<form method="post" action="/claims/{claim["id"]}/restore" data-action-form><button class="secondary">Restore draft</button></form>'
        if claim["approved"]
        else f'<form method="post" action="/claims/{claim["id"]}/accept" data-action-form><button>{"Approve rewrite" if claim["rewrite"] != claim["draft"] else "Mark approved"}</button></form>'
    )
    proposal = f'<p class="proposed-rewrite"><span>PROPOSED REWRITE</span>{escape(claim["rewrite"])}</p>' if not claim["approved"] and claim["rewrite"] != claim["draft"] else ""
    editor = "" if claim["approved"] else f'''<details class="claim-editor"><summary>Edit rewrite</summary><form method="post" action="/claims/{claim["id"]}/edit" data-action-form><label for="rewrite-{claim["id"]}">Rewrite grounded in the linked evidence</label><textarea id="rewrite-{claim["id"]}" name="rewrite" rows="3" required>{escape(claim["rewrite"])}</textarea><button class="secondary">Save and recheck</button></form></details>'''
    return f'''<article class="claim {status}" data-reveal><div class="claim-top"><span class="status">{escape(status.replace("_", " "))}</span><a href="#evidence-{claim["evidence_ids"].split(",")[0]}" data-evidence-link>Evidence: {escape(evidence)}</a></div><p class="claim-copy">{escape(text)}</p>{proposal}<p class="reason">{escape(claim["reason"])}</p><div class="claim-actions">{action}{editor}</div></article>'''


def evidence_panel(transcript: str, note: str = "Statuses reflect support in this transcript, not real-world verification.") -> str:
    return f'''<aside class="evidence-panel" data-reveal><p class="eyebrow">SOURCE EVIDENCE</p><h2>Transcript</h2><p class="note">{escape(note)}</p><ol>{transcript}</ol></aside>'''


def review_band(cards: str, title: str, intro: str, count: str) -> str:
    return f'''<section class="review-band" data-reveal><div class="review-heading"><div><p class="eyebrow">DRAFT REVIEW</p><h2>{escape(title)}</h2></div><span>{escape(count)}</span></div><p class="review-intro">{escape(intro)}</p><div class="claims">{cards}</div></section>'''


def export_controls(approved: int) -> str:
    if not approved:
        return ""
    return f'''<section class="export-band" data-reveal><div><p class="eyebrow">APPROVED PACKAGE</p><h2>{approved} claim{"s" if approved != 1 else ""} ready to hand off.</h2></div><div class="export-actions"><a class="review-link" href="/export.md">Markdown</a><a class="review-link secondary-link" href="/export.json">JSON</a></div></section>'''


def seed_review_page() -> str:
    claims = get_claims()
    transcript = "".join(f'<li id="evidence-{segment_id}"><time>{time}</time><span>{escape(text)}</span></li>' for segment_id, time, text in TRANSCRIPT)
    cards = "".join(claim_html(claim) for claim in claims)
    grounded = sum(claim["approved"] for claim in claims)
    header = project_header("SEED REVIEW", "ApexFlow product webinar", "A ready-to-review fictional project. Fix the risky claim, inspect its source evidence, then export the approved package.", f"{grounded}/3", "claims grounded")
    angles = '''<aside class="angle-rail" data-reveal><p class="eyebrow">CONTENT ANGLES</p><button class="angle active" type="button" aria-pressed="true"><strong>Proof beats promises</strong><span>LinkedIn post · selected</span></button><button class="angle" type="button" aria-pressed="false"><strong>Approval queue workflow</strong><span>Short video · ready</span></button><button class="angle" type="button" aria-pressed="false"><strong>Meeting time pilot</strong><span>Newsletter · needs review</span></button></aside>'''
    review = review_band(cards, "Proof beats promises", "A faster review queue helps content teams move from a raw webinar to publishable content without losing the evidence behind each claim.", "3 claims")
    preview = '''<section class="seed-preview" data-reveal><div><p class="eyebrow">ORIGINAL DEMO SOURCE</p><h2>See the evidence on the source timeline.</h2><p class="note">This original fictional recording displays the same source statements used by the seed review at their linked timestamps.</p></div><video controls preload="metadata"><source src="/static/sourcecut-seed-demo.mp4" type="video/mp4">Your browser cannot play this demo source.</video></section>'''
    return document("Seed review", "Evidence-backed review", "/upload", "Create project", "Demo mode", f'''{header}{preview}<section class="review-layout">{angles}{review}{evidence_panel(transcript)}</section>{export_controls(grounded)}''')


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    init_db()
    projects = list_projects()
    project_cards = "".join(
        f'''<article class="project-card" data-reveal><div class="project-card-top"><span class="status">{escape(row["status"])}</span><span>{int(row["output_count"] or 0)} outputs</span></div><h2>{escape(row["name"])}</h2><p>{escape(PLATFORMS.get(json.loads(row["settings_json"])["platform"], PLATFORMS["vertical"])["label"])} · {int(row["clip_count"])} proposals</p><div class="project-card-actions"><a class="review-link" href="/projects/{row["id"]}">Open production desk</a><form method="post" action="/projects/{row["id"]}/delete" data-delete-form><button class="delete-button" aria-label="Delete {escape(row["name"])}">Delete</button></form></div></article>'''
        for row in projects
    ) or '<p class="empty-state">No uploaded projects yet. Start with a local recording or open the seeded review below.</p>'
    seed = '''<article class="project-card seed-card" data-reveal><div class="project-card-top"><span class="status">seeded demo</span><span>no key needed</span></div><h2>ApexFlow product webinar</h2><p>See an unsupported marketing claim become a timestamp-backed rewrite.</p><a class="review-link" href="/review">Open evidence review</a></article>'''
    example = '''<article class="project-card example-card" data-reveal><div class="project-card-top"><span class="status">example video</span><span>22 seconds</span></div><h2>SourceCut production example</h2><p>Open a prepared player, transcript, clip proposals, and render-ready source.</p><div class="example-actions"><a href="/static/sourcecut-production-example.mp4" download>Download MP4</a><form method="post" action="/examples/production"><button>Load project</button></form></div></article>'''
    header = project_header("WORK & PRODUCTIVITY", "Turn recordings into evidence-backed social clips.", "SourceCut helps marketing teams choose moments, preserve the source behind every claim, and produce reviewable videos without losing context.", "3 steps", "source · review · render")
    content = f'''{header}<section class="dashboard-intro" data-reveal><div><p class="eyebrow">PRODUCTION DESK</p><h2>From source to a confident handoff.</h2></div><ol><li><strong>1</strong><span>Upload a recording and choose its social edit preset.</span></li><li><strong>2</strong><span>Review proposed clips against the source transcript.</span></li><li><strong>3</strong><span>Render selected clips and export their evidence package.</span></li></ol><a class="nav-action" href="/upload">Create a project</a></section><section class="project-library" data-reveal><div class="section-heading"><div><p class="eyebrow">PROJECTS</p><h2>Production library</h2></div><a href="/upload">New project</a></div><div class="project-grid">{seed}{example}{project_cards}</div></section><section id="outputs" class="dashboard-note" data-reveal><p class="eyebrow">WHAT MAKES IT DIFFERENT</p><p>Every selected clip carries its original timestamp and supporting transcript quote. SourceCut can accelerate production, but it never turns a weak claim into an approved one.</p></section>'''
    return document("Projects", "Evidence-backed production", "/upload", "Create project", "Local mode", content)


def production_options() -> str:
    return '''<section class="create-form" data-reveal><div class="create-copy"><p class="eyebrow">CREATE PROJECT</p><h2>Choose the edit before the machine starts.</h2><p class="note">SourceCut stores your source locally, transcribes it on CPU, proposes grounded moments, then renders only the clips you select.</p><p class="workflow-note">Upload → Transcribe → Review proposals → Render selected clips</p></div><form method="post" action="/upload" enctype="multipart/form-data" data-production-form><div class="file-drop"><label for="media-file">Source recording</label><input id="media-file" type="file" name="file" accept=".mp4,.mp3,.wav" required><span data-file-name>Up to 500 MB. MP4 produces playable source and rendered clips. MP3/WAV remains a transcript review source.</span></div><div class="settings-grid"><label>Platform<select name="platform"><option value="vertical">Shorts / Reels / TikTok · 9:16</option><option value="linkedin">LinkedIn · 16:9</option><option value="square">Instagram feed · 1:1</option></select></label><label>Clip count<select name="clip_count"><option value="1">1 clip</option><option value="2">2 clips</option><option value="3" selected>3 clips</option><option value="4">4 clips</option><option value="5">5 clips</option></select></label><label>Target length<select name="duration"><option value="30">30 seconds</option><option value="45" selected>45 seconds</option><option value="60">60 seconds</option></select></label><label>Captions<select name="captions"><option value="bold" selected>Bold</option><option value="minimal">Minimal</option><option value="none">No captions</option></select></label><label>Framing<select name="framing"><option value="center" selected>Preserve full frame</option><option value="balanced">Balanced frame</option></select></label><label>Audio<select name="audio_mode"><option value="source" selected>Original source audio</option><option value="voiceover">AI voiceover (free)</option></select></label><label>Voice<select name="voice"><option value="en-US-AndrewMultilingualNeural">Andrew · energetic</option><option value="en-US-AvaMultilingualNeural">Ava · clear</option></select></label><label class="toggle-field"><input type="checkbox" name="proof_cards"><span>Add proof cards</span></label><label class="toggle-field"><input type="checkbox" name="trim_silence"><span>Plan quiet-gap trims</span></label></div><label>Find moments about <input type="text" name="focus" maxlength="160" placeholder="For example: pricing, onboarding, customer proof"></label><label>Manual clips (optional) <input type="text" name="manual_clips" maxlength="240" placeholder="12:30-13:10, 45:02-45:50"></label><button class="go" type="submit">Build production project</button><p class="form-message" aria-live="polite"></p></form></section>'''


@app.get("/upload", response_class=HTMLResponse)
def upload_form(message: str = "") -> str:
    header = project_header("LOCAL PRODUCTION", "Turn a source recording into a clip desk.", "Choose a platform preset, then SourceCut will produce timestamped, evidence-linked clip proposals for your review.")
    example = '''<section class="example-callout" data-reveal><div><p class="eyebrow">NO FILE READY?</p><h2>Use the original SourceCut example.</h2><p>Download the short MP4, or open it as a prepared production project with transcript evidence and selectable clips.</p></div><div class="example-actions"><a class="review-link secondary-link" href="/static/sourcecut-production-example.mp4" download>Download example MP4</a><form method="post" action="/examples/production"><button>Load example project</button></form></div></section>'''
    return document("Create project", "Local production", "/", "View projects", "CPU mode", header + production_options() + example + message)


@app.post("/examples/production")
def load_production_example() -> RedirectResponse:
    try:
        project_id = create_example_project()
    except FileNotFoundError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
    return RedirectResponse(f"/projects/{project_id}", status_code=303)


@app.post("/upload")
async def upload_media(
    file: UploadFile = File(...), platform: str = Form("vertical"), clip_count: str = Form("3"), duration: str = Form("45"),
    captions: str = Form("bold"), framing: str = Form("center"), audio_mode: str = Form("source"), voice: str = Form("en-US-AndrewMultilingualNeural"), proof_cards: str | None = Form(None), trim_silence: str | None = Form(None), focus: str = Form(""), manual_clips: str = Form(""),
) -> Response:
    init_db()
    try:
        path = await save_upload(file, ROOT / "data" / "uploads")
    except HTTPException as error:
        message = f'<p class="error" role="alert">{escape(str(error.detail))}</p>'
        return HTMLResponse(upload_form(message), status_code=error.status_code)
    settings = settings_from_form({"platform": platform, "clip_count": clip_count, "duration": duration, "captions": captions, "framing": framing, "audio_mode": audio_mode, "voice": voice, "proof_cards": proof_cards or "", "trim_silence": trim_silence or "", "focus": focus, "manual_clips": manual_clips})
    project_id = create_project(file.filename or path.name, path, settings)
    start_analysis(project_id)
    return RedirectResponse(f"/projects/{project_id}", status_code=303)


def workspace(project: sqlite3.Row) -> str:
    settings = json.loads(project["settings_json"])
    segments = get_segments(project["id"])
    clips = get_clips(project["id"])
    job = latest_job(project["id"])
    status = project["status"]
    processing = status in {"queued", "processing", "rendering"}
    source_kind = project["media_type"]
    if source_kind == "mp4":
        player = f'''<video class="source-player" controls preload="metadata" data-source-player><source src="/projects/{project["id"]}/source" type="video/mp4">Your browser cannot play this source video.</video>'''
    elif source_kind in {"mp3", "wav"}:
        player = f'''<audio class="source-audio" controls preload="metadata" data-source-player><source src="/projects/{project["id"]}/source">Your browser cannot play this source audio.</audio>'''
    else:
        player = '<p class="empty-state">This source cannot be previewed in the browser.</p>'
    transcript = "".join(f'<li id="segment-{row["id"]}" data-source-time="{row["start"]}"><button type="button" data-seek="{row["start"]}"><time>{format_time(row["start"])}</time><span>{escape(row["text"])}</span></button></li>' for row in segments) or '<li>No speech detected yet.</li>'
    clip_cards = "".join(clip_card(project["id"], clip) for clip in clips) or '<p class="empty-state">Clip proposals will appear after transcription finishes.</p>'
    selected = sum(bool(clip["selected"]) for clip in clips)
    outputs = "".join(output_card(project["id"], clip) for clip in clips if clip["render_status"] == "ready") or '<p class="empty-state">Approved rendered clips will appear here.</p>'
    job_detail = escape(job["detail"] if job else "Waiting for the next production action.")
    header = project_header("PROJECT WORKSPACE", project["name"], f'''<span class="project-meta">{escape(PLATFORMS[settings["platform"]]["label"])} · {settings["duration"]} seconds · {settings["clip_count"]} requested clips</span>''', f"{selected}/{len(clips)}", "clips selected")
    progress = f'''<section class="job-panel" data-job-status="/projects/{project["id"]}/status" data-reveal><div><p class="eyebrow">LOCAL JOB</p><h2>{escape(job["stage"] if job else "Ready")}</h2><p data-job-detail>{job_detail}</p></div><span class="status" data-job-state>{escape(job["status"] if job else status)}</span></section>''' if processing else ""
    render_action = f'''<div class="proposal-actions"><form method="post" action="/projects/{project["id"]}/refine-cuts" data-action-form><button class="secondary" {'disabled' if processing else ''}>Improve clip cuts</button></form><form method="post" action="/projects/{project["id"]}/render" data-action-form><button {'disabled' if not selected or processing else ''}>Render {selected} selected clip{'s' if selected != 1 else ''}</button></form></div>'''
    desk = f'''{progress}<section class="production-workspace" data-reveal><aside class="source-column"><p class="eyebrow">SOURCE</p>{player}<p class="source-note">SourceCut preserves the full frame and keeps every rendered clip aligned to complete transcript thoughts.</p></aside><section class="proposal-column"><div class="section-heading"><div><p class="eyebrow">CLIP PROPOSALS</p><h2>Review before render.</h2></div>{render_action}</div><div class="clip-proposals">{clip_cards}</div></section><aside class="transcript-column"><p class="eyebrow">TRANSCRIPT</p><ol>{transcript}</ol></aside></section><section id="outputs" class="outputs-library" data-reveal><div class="section-heading"><div><p class="eyebrow">OUTPUTS</p><h2>Rendered production files</h2></div><a href="/projects/{project["id"]}/export.json">Export package</a></div><div class="output-grid">{outputs}</div></section>'''
    return document(project["name"], "Production workspace", "/upload", "New project", status, header + desk)


def clip_card(project_id: int, clip: sqlite3.Row) -> str:
    is_safe = clip["claim_status"] == "supported"
    selected = bool(clip["selected"])
    status_text = "selected" if selected else clip["claim_status"].replace("_", " ")
    selection = f'''<form method="post" action="/projects/{project_id}/clips/{clip["id"]}/select" data-action-form><input type="hidden" name="selected" value="{str(not selected).lower()}"><button class="{'secondary' if selected else ''}" {'disabled' if not is_safe else ''}>{'Remove from render' if selected else ('Select for render' if is_safe else 'Fix evidence first')}</button></form>'''
    error = f'<p class="error compact">{escape(clip["error"])}</p>' if clip["error"] else ""
    return f'''<article class="clip-proposal {'chosen' if selected else ''} {escape(clip["claim_status"])}"><div class="clip-head"><span class="status">{escape(status_text)}</span><span>{format_time(clip["start"])}–{format_time(clip["end"])}</span></div><h3>{escape(clip["title"])}</h3><p class="clip-hook">{escape(clip["hook"])}</p><p class="clip-caption"><span>CAPTION</span>{escape(clip["caption"])}</p><a href="#segment-{clip["evidence_segment_id"]}" data-evidence-link data-seek="{clip["start"]}">Source evidence</a><p class="reason">{escape(clip["reason"])}</p><div class="clip-actions">{selection}<span class="render-state">{escape(clip["render_status"])}</span></div>{error}</article>'''


def output_card(project_id: int, clip: sqlite3.Row) -> str:
    return f'''<article class="output-card"><video controls preload="metadata"><source src="/projects/{project_id}/outputs/{clip["id"]}" type="video/mp4"></video><div><span class="status">ready</span><h3>{escape(clip["title"])}</h3><p>{format_time(clip["start"])}–{format_time(clip["end"])}</p><a class="review-link" href="/projects/{project_id}/outputs/{clip["id"]}" download>Download MP4</a></div></article>'''


@app.get("/projects/{project_id}", response_class=HTMLResponse)
def project_workspace(project_id: int) -> str:
    init_db()
    project = get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return workspace(project)


@app.get("/projects/{project_id}/source")
def project_source(project_id: int) -> FileResponse:
    project = get_project(project_id)
    source = Path(project["source_path"]) if project else None
    if not source or not source.is_file():
        raise HTTPException(status_code=404, detail="Source media not found")
    return FileResponse(source, filename=project["name"])


@app.get("/projects/{project_id}/status")
def project_status(project_id: int) -> JSONResponse:
    project = get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    job = latest_job(project_id)
    clips = get_clips(project_id)
    return JSONResponse({"project_status": project["status"], "job": dict(job) if job else None, "selected": sum(bool(clip["selected"]) for clip in clips), "outputs": sum(clip["render_status"] == "ready" for clip in clips)})


@app.post("/projects/{project_id}/clips/{clip_id}/select")
def select_clip(project_id: int, clip_id: int, selected: bool = Form(...)) -> RedirectResponse:
    if not set_selected(project_id, clip_id, selected):
        raise HTTPException(status_code=422, detail="Only source-supported clips can be selected for rendering.")
    return RedirectResponse(f"/projects/{project_id}", status_code=303)


@app.post("/projects/{project_id}/delete")
def remove_project(project_id: int) -> RedirectResponse:
    try:
        removed = delete_project(project_id)
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if not removed:
        raise HTTPException(status_code=404, detail="Project not found")
    return RedirectResponse("/", status_code=303)


@app.post("/projects/{project_id}/refine-cuts")
def refine_cuts(project_id: int) -> RedirectResponse:
    if not refine_project_cuts(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return RedirectResponse(f"/projects/{project_id}", status_code=303)


@app.post("/projects/{project_id}/render")
def render_project(project_id: int) -> RedirectResponse:
    project = get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not any(clip["selected"] for clip in get_clips(project_id)):
        raise HTTPException(status_code=422, detail="Select a source-grounded clip before rendering.")
    start_render(project_id)
    return RedirectResponse(f"/projects/{project_id}", status_code=303)


@app.get("/projects/{project_id}/outputs/{clip_id}")
def project_output(project_id: int, clip_id: int) -> FileResponse:
    path = output_path(project_id, clip_id)
    if not path:
        raise HTTPException(status_code=404, detail="Rendered output not found")
    return FileResponse(path, media_type="video/mp4", filename=path.name)


@app.get("/projects/{project_id}/export.json")
def project_export(project_id: int) -> JSONResponse:
    project = get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    segments = {row["id"]: row for row in get_segments(project_id)}
    clips = [clip for clip in get_clips(project_id) if clip["selected"]]
    package = {
        "project": project["name"],
        "status": project["status"],
        "clips": [
            {
                "title": clip["title"], "source_range": {"start": format_time(clip["start"]), "end": format_time(clip["end"])},
                "hook": clip["hook"], "caption": clip["caption"], "claim_status": clip["claim_status"],
                "evidence": {"quote": clip["evidence_quote"], "segment_id": clip["evidence_segment_id"], "text": segments[clip["evidence_segment_id"]]["text"] if clip["evidence_segment_id"] in segments else ""},
                "render_status": clip["render_status"],
            }
            for clip in clips
        ],
    }
    return JSONResponse(package, headers={"Content-Disposition": f'attachment; filename="sourcecut-project-{project_id}.json"'})


@app.get("/review", response_class=HTMLResponse)
def seed_review() -> str:
    return seed_review_page()


@app.post("/claims/{claim_id}/accept")
def accept(claim_id: int) -> RedirectResponse:
    claim = get_claim(claim_id)
    review = review_seeded_rewrite(claim, claim["rewrite"])
    with closing(db()) as connection:
        connection.execute("UPDATE claims SET status = ?, reason = ?, approved = ? WHERE id = ?", (review.status, review.reason, int(review.status == "supported"), claim_id))
        connection.commit()
    return RedirectResponse("/review", status_code=303)


@app.post("/claims/{claim_id}/restore")
def restore(claim_id: int) -> RedirectResponse:
    if claim_id < 1 or claim_id > len(SEED_CLAIMS):
        raise HTTPException(status_code=404, detail="Claim not found")
    draft, status, reason, rewrite, evidence_ids = SEED_CLAIMS[claim_id - 1]
    with closing(db()) as connection:
        connection.execute("UPDATE claims SET draft = ?, status = ?, reason = ?, rewrite = ?, evidence_ids = ?, approved = 0 WHERE id = ?", (draft, status, reason, rewrite, evidence_ids, claim_id))
        connection.commit()
    return RedirectResponse("/review", status_code=303)


@app.post("/claims/{claim_id}/edit")
def edit_rewrite(claim_id: int, rewrite: str = Form(...)) -> RedirectResponse:
    text = rewrite.strip()
    if not text:
        raise HTTPException(status_code=422, detail="Rewrite cannot be empty")
    claim = get_claim(claim_id)
    review = review_seeded_rewrite(claim, text)
    with closing(db()) as connection:
        connection.execute("UPDATE claims SET rewrite = ?, status = ?, reason = ?, approved = 0 WHERE id = ?", (text, review.status, review.reason, claim_id))
        connection.commit()
    return RedirectResponse("/review", status_code=303)


@app.get("/export.json")
def export_json() -> JSONResponse:
    return JSONResponse(build_package(get_claims(), SEED_SEGMENT_BY_ID), headers={"Content-Disposition": 'attachment; filename="sourcecut-approved-package.json"'})


@app.get("/export.md")
def export_markdown() -> PlainTextResponse:
    return PlainTextResponse(markdown(build_package(get_claims(), SEED_SEGMENT_BY_ID)), media_type="text/markdown", headers={"Content-Disposition": 'attachment; filename="sourcecut-approved-package.md"'})

from __future__ import annotations

import sqlite3
from contextlib import closing
from html import escape
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .media import remove_media, save_upload
from .export import build_package, markdown
from .review import Evidence, TranscriptSegment, local_candidates, review_claim
from .transcription import transcribe_media


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
        connection.execute("""CREATE TABLE IF NOT EXISTS claims (
            id INTEGER PRIMARY KEY, draft TEXT NOT NULL, status TEXT NOT NULL,
            reason TEXT NOT NULL, rewrite TEXT NOT NULL, evidence_ids TEXT NOT NULL,
            approved INTEGER NOT NULL DEFAULT 0)""")
        connection.execute("""CREATE TABLE IF NOT EXISTS uploads (
            id INTEGER PRIMARY KEY, original_name TEXT NOT NULL, path TEXT NOT NULL)""")
        connection.execute("""CREATE TABLE IF NOT EXISTS transcript_segments (
            id INTEGER PRIMARY KEY, upload_id INTEGER NOT NULL, start REAL NOT NULL,
            end REAL NOT NULL, text TEXT NOT NULL)""")
        if not connection.execute("SELECT 1 FROM claims LIMIT 1").fetchone():
            connection.executemany(
                "INSERT INTO claims (draft, status, reason, rewrite, evidence_ids) VALUES (?, ?, ?, ?, ?)",
                SEED_CLAIMS,
            )
        connection.commit()


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
    <header class="topbar" data-reveal><a class="brand" href="/" aria-label="SourceCut home">SOURCECUT</a><span class="product-context">{escape(context)}</span><nav aria-label="Primary navigation"><a href="/">Review</a><a href="/upload">Upload</a></nav><a class="nav-action" href="{action_href}">{escape(action_label)}</a><b class="mode-chip">{escape(status)}</b></header>
    <main>{content}</main><footer data-reveal>SourceCut demo data is fictional. No account or API key is required for the seeded review.</footer></body></html>'''


def evidence_object() -> str:
    return '''<div class="object-stage" aria-hidden="true"><span class="object-orbit orbit-one"></span><span class="object-orbit orbit-two"></span><img src="/static/sourcecut-evidence-object.png" alt=""></div>'''


def project_header(eyebrow: str, title: str, detail: str, stat: str = "", stat_label: str = "") -> str:
    progress = f'''<div class="progress" data-reveal><strong>{escape(stat)}</strong><span>{escape(stat_label)}</span></div>''' if stat else ""
    return f'''<section class="project-hero" data-reveal><div class="hero-copy"><p class="eyebrow">{escape(eyebrow)}</p><h1>{escape(title)}</h1><p class="hero-detail">{detail}</p>{progress}</div>{evidence_object()}</section>'''


def claim_html(claim: sqlite3.Row) -> str:
    status = "approved" if claim["approved"] else claim["status"]
    text = claim["rewrite"] if claim["approved"] else claim["draft"]
    evidence = claim["evidence_ids"].replace(",", ", ")
    action = (
        f'<form method="post" action="/claims/{claim["id"]}/restore" data-action-form><button class="secondary">Restore draft</button></form>'
        if claim["approved"]
        else f'<form method="post" action="/claims/{claim["id"]}/accept" data-action-form><button>{"Approve rewrite" if claim["rewrite"] != claim["draft"] else "Mark approved"}</button></form>'
    )
    proposal = (
        f'<p class="proposed-rewrite"><span>PROPOSED REWRITE</span>{escape(claim["rewrite"])}</p>'
        if not claim["approved"] and claim["rewrite"] != claim["draft"]
        else ""
    )
    editor = "" if claim["approved"] else f'''<details class="claim-editor"><summary>Edit rewrite</summary><form method="post" action="/claims/{claim["id"]}/edit" data-action-form><label for="rewrite-{claim["id"]}">Rewrite grounded in the linked evidence</label><textarea id="rewrite-{claim["id"]}" name="rewrite" rows="3" required>{escape(claim["rewrite"])}</textarea><button class="secondary">Save and recheck</button></form></details>'''
    return f'''<article class="claim {status}" data-reveal>
      <div class="claim-top"><span class="status">{escape(status.replace("_", " "))}</span><a href="#evidence-{claim["evidence_ids"].split(",")[0]}" data-evidence-link>Evidence: {escape(evidence)}</a></div>
      <p class="claim-copy">{escape(text)}</p>{proposal}<p class="reason">{escape(claim["reason"])}</p><div class="claim-actions">{action}{editor}</div></article>'''


def evidence_panel(transcript: str, note: str = "Statuses reflect support in this transcript, not real-world verification.") -> str:
    return f'''<aside class="evidence-panel" data-reveal><p class="eyebrow">SOURCE EVIDENCE</p><h2>Transcript</h2><p class="note">{escape(note)}</p><ol>{transcript}</ol></aside>'''


def review_band(cards: str, title: str, intro: str, count: str) -> str:
    return f'''<section class="review-band" data-reveal><div class="review-heading"><div><p class="eyebrow">DRAFT REVIEW</p><h2>{escape(title)}</h2></div><span>{escape(count)}</span></div><p class="review-intro">{escape(intro)}</p><div class="claims">{cards}</div></section>'''


def export_controls(approved: int) -> str:
    if not approved:
        return ""
    return f'''<section class="export-band" data-reveal><div><p class="eyebrow">APPROVED PACKAGE</p><h2>{approved} claim{"s" if approved != 1 else ""} ready to hand off.</h2></div><div class="export-actions"><a class="review-link" href="/export.md">Markdown</a><a class="review-link secondary-link" href="/export.json">JSON</a></div></section>'''


def page() -> str:
    claims = get_claims()
    transcript = "".join(
        f'<li id="evidence-{segment_id}"><time>{time}</time><span>{escape(text)}</span></li>'
        for segment_id, time, text in TRANSCRIPT
    )
    cards = "".join(claim_html(claim) for claim in claims)
    grounded = sum(claim["approved"] for claim in claims)
    header = project_header(
        "WORK & PRODUCTIVITY",
        "ApexFlow product webinar",
        "Original fictional demo &middot; 03:12 &middot; 3 draft angles",
        f"{grounded}/3",
        "claims grounded",
    )
    angles = '''<aside class="angle-rail" data-reveal><p class="eyebrow">CONTENT ANGLES</p><button class="angle active" type="button" aria-pressed="true"><strong>Proof beats promises</strong><span>LinkedIn post &middot; selected</span></button><button class="angle" type="button" aria-pressed="false"><strong>Approval queue workflow</strong><span>Short video &middot; ready</span></button><button class="angle" type="button" aria-pressed="false"><strong>Meeting time pilot</strong><span>Newsletter &middot; needs review</span></button></aside>'''
    review = review_band(
        cards,
        "Proof beats promises",
        "A faster review queue helps content teams move from raw webinar to publishable post without losing the evidence behind each claim.",
        "3 claims",
    )
    content = f'''{header}<section class="review-layout">{angles}{review}{evidence_panel(transcript)}</section>{export_controls(grounded)}'''
    return document("SourceCut", "Evidence-backed content review", "/upload", "Upload media", "Demo mode", content)


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return page()


def upload_page(message: str = "") -> str:
    header = project_header(
        "LOCAL TRANSCRIPTION",
        "Transcribe a local recording",
        "MP3, MP4, or WAV. Files stay in this local runtime directory and are not committed.",
    )
    content = f'''{header}<section class="upload-surface" data-reveal><div><p class="eyebrow">UPLOAD RECORDING</p><h2>Bring the source into review.</h2><p class="note">SourceCut runs local CPU transcription and returns timestamped segments for the review workflow.</p></div><form class="upload-form" method="post" action="/upload" enctype="multipart/form-data" data-action-form><label for="media-file">Select local media</label><input id="media-file" type="file" name="file" accept=".mp3,.mp4,.wav" required><button>Transcribe locally</button></form></section>{message}'''
    return document("Upload", "Local transcription", "/", "Review demo", "CPU mode", content)


@app.get("/upload", response_class=HTMLResponse)
def upload_form() -> str:
    return upload_page()


@app.post("/upload", response_class=HTMLResponse)
async def upload_media(file: UploadFile = File(...)) -> str:
    path = await save_upload(file, ROOT / "data" / "uploads")
    try:
        segments = transcribe_media(path)
    except Exception as error:
        remove_media(path)
        return HTMLResponse(upload_page(f'<p class="error" role="alert">Transcription failed: {escape(str(error))}</p>'), status_code=422)
    with closing(db()) as connection:
        cursor = connection.execute("INSERT INTO uploads (original_name, path) VALUES (?, ?)", (file.filename or path.name, str(path)))
        connection.executemany(
            "INSERT INTO transcript_segments (upload_id, start, end, text) VALUES (?, ?, ?, ?)",
            [(cursor.lastrowid, segment["start"], segment["end"], segment["text"]) for segment in segments],
        )
        connection.commit()
    rows = "".join(f'<li><time>{segment["start"]:05.2f}</time><span>{escape(segment["text"])}</span></li>' for segment in segments) or "<li>No speech was detected.</li>"
    review_link = f'<p><a class="review-link" href="/uploads/{cursor.lastrowid}/review">Generate review candidates</a></p>' if segments else ""
    result = f'''<section class="transcript-result" data-reveal><p class="eyebrow">TRANSCRIPT READY</p><h2>Transcript ready</h2><p>{len(segments)} timestamped segments from {escape(file.filename or path.name)}.</p><ol>{rows}</ol>{review_link}</section>'''
    return HTMLResponse(upload_page(result))


def load_segments(upload_id: int) -> tuple[str, list[TranscriptSegment]]:
    with closing(db()) as connection:
        upload = connection.execute("SELECT original_name FROM uploads WHERE id = ?", (upload_id,)).fetchone()
        rows = connection.execute("SELECT id, start, end, text FROM transcript_segments WHERE upload_id = ? ORDER BY id", (upload_id,)).fetchall()
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    return upload["original_name"], [
        TranscriptSegment(id=f"segment-{row['id']}", start=row["start"], end=row["end"], text=row["text"])
        for row in rows
    ]


@app.get("/uploads/{upload_id}/review", response_class=HTMLResponse)
def review_upload(upload_id: int) -> str:
    name, segments = load_segments(upload_id)
    candidates = local_candidates(segments)
    if not candidates:
        return HTMLResponse(upload_page('<p class="error" role="alert">No speech was detected, so there is nothing to review yet.</p>'), status_code=422)
    cards = "".join(
        f'''<article class="claim {candidate.claim.status}" data-reveal><div class="claim-top"><span class="status">{candidate.claim.status.replace('_', ' ')}</span><a href="#evidence-{candidate.claim.evidence.segment_ids[0]}" data-evidence-link>Evidence</a></div><h2>{escape(candidate.title)}</h2><p class="claim-copy">{escape(candidate.draft)}</p><p class="reason">{escape(candidate.claim.reason)}</p><p><strong>Grounded rewrite:</strong> {escape(candidate.claim.rewrite)}</p></article>'''
        for candidate in candidates
    )
    transcript = "".join(
        f'<li id="evidence-{segment.id}"><time>{segment.start:05.2f}</time><span>{escape(segment.text)}</span></li>'
        for segment in segments
    )
    header = project_header(
        "CONTENT CANDIDATES",
        name,
        "Deterministic local analysis. Statuses are support in the shown transcript, not real-world verification.",
    )
    review = review_band(cards, "Candidate review", "Inspect the evidence, keep the nuance, then take the publishable line forward.", f"{len(candidates)} candidates")
    content = f'''{header}<section class="review-layout upload-review">{review}{evidence_panel(transcript, "Exact source segments used to review these candidates.")}</section>'''
    return document("Review candidates", "Local candidate review", "/upload", "Upload another", "Local analysis", content)


@app.post("/claims/{claim_id}/accept")
def accept(claim_id: int) -> RedirectResponse:
    claim = get_claim(claim_id)
    review = review_seeded_rewrite(claim, claim["rewrite"])
    with closing(db()) as connection:
        connection.execute(
            "UPDATE claims SET status = ?, reason = ?, approved = ? WHERE id = ?",
            (review.status, review.reason, int(review.status == "supported"), claim_id),
        )
        connection.commit()
    return RedirectResponse("/", status_code=303)


@app.post("/claims/{claim_id}/restore")
def restore(claim_id: int) -> RedirectResponse:
    if claim_id < 1 or claim_id > len(SEED_CLAIMS):
        raise HTTPException(status_code=404, detail="Claim not found")
    draft, status, reason, rewrite, evidence_ids = SEED_CLAIMS[claim_id - 1]
    with closing(db()) as connection:
        connection.execute(
            "UPDATE claims SET draft = ?, status = ?, reason = ?, rewrite = ?, evidence_ids = ?, approved = 0 WHERE id = ?",
            (draft, status, reason, rewrite, evidence_ids, claim_id),
        )
        connection.commit()
    return RedirectResponse("/", status_code=303)


@app.post("/claims/{claim_id}/edit")
def edit_rewrite(claim_id: int, rewrite: str = Form(...)) -> RedirectResponse:
    text = rewrite.strip()
    if not text:
        raise HTTPException(status_code=422, detail="Rewrite cannot be empty")
    claim = get_claim(claim_id)
    review = review_seeded_rewrite(claim, text)
    with closing(db()) as connection:
        connection.execute(
            "UPDATE claims SET rewrite = ?, status = ?, reason = ?, approved = 0 WHERE id = ?",
            (text, review.status, review.reason, claim_id),
        )
        connection.commit()
    return RedirectResponse("/", status_code=303)


@app.get("/export.json")
def export_json() -> JSONResponse:
    return JSONResponse(
        build_package(get_claims(), SEED_SEGMENT_BY_ID),
        headers={"Content-Disposition": 'attachment; filename="sourcecut-approved-package.json"'},
    )


@app.get("/export.md")
def export_markdown() -> PlainTextResponse:
    package = build_package(get_claims(), SEED_SEGMENT_BY_ID)
    return PlainTextResponse(
        markdown(package),
        media_type="text/markdown",
        headers={"Content-Disposition": 'attachment; filename="sourcecut-approved-package.md"'},
    )

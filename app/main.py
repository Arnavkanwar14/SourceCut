from __future__ import annotations

import sqlite3
from contextlib import closing
from html import escape
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .media import remove_media, save_upload
from .review import TranscriptSegment, local_candidates
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


def claim_html(claim: sqlite3.Row) -> str:
    status = "approved" if claim["approved"] else claim["status"]
    text = claim["rewrite"] if claim["approved"] else claim["draft"]
    evidence = claim["evidence_ids"].replace(",", ", ")
    action = (
        f'<form method="post" action="/claims/{claim["id"]}/restore"><button class="secondary">Restore draft</button></form>'
        if claim["approved"]
        else f'<form method="post" action="/claims/{claim["id"]}/accept"><button>Accept grounded rewrite</button></form>'
    )
    return f'''<article class="claim {status}">
      <div class="claim-top"><span class="status">{escape(status.replace("_", " "))}</span><a href="#evidence-{claim["evidence_ids"].split(",")[0]}">Evidence: {escape(evidence)}</a></div>
      <p class="claim-copy">{escape(text)}</p><p class="reason">{escape(claim["reason"])}</p>{action}</article>'''


def page() -> str:
    claims = get_claims()
    transcript = "".join(
        f'<li id="evidence-{segment_id}"><time>{time}</time><span>{escape(text)}</span></li>'
        for segment_id, time, text in TRANSCRIPT
    )
    cards = "".join(claim_html(claim) for claim in claims)
    grounded = sum(claim["approved"] for claim in claims)
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>SourceCut</title><link rel="stylesheet" href="/static/style.css"></head><body>
    <header><strong>SourceCut</strong><span>Evidence-backed content review</span><a href="/upload">Upload media</a><b>Demo mode</b></header>
    <main><section class="project"><div><p class="eyebrow">WORK &amp; PRODUCTIVITY</p><h1>ApexFlow product webinar</h1><p>Original fictional demo · 03:12 · 3 draft angles</p></div><div class="progress"><strong>{grounded}/3</strong><span>claims grounded</span></div></section>
    <section class="workspace"><aside class="angles"><p class="eyebrow">CONTENT ANGLES</p><div class="angle active"><strong>Proof beats promises</strong><span>LinkedIn post · selected</span></div><div class="angle"><strong>Approval queue workflow</strong><span>Short video · ready</span></div><div class="angle"><strong>Meeting time pilot</strong><span>Newsletter · needs review</span></div></aside>
    <section class="review"><div class="title"><div><p class="eyebrow">DRAFT REVIEW</p><h2>Proof beats promises</h2></div><span>3 claims</span></div><p class="intro">A faster review queue can help content teams move from raw webinar to publishable post without losing the evidence behind each claim.</p>{cards}</section>
    <aside class="evidence"><p class="eyebrow">SOURCE EVIDENCE</p><h2>Transcript</h2><p class="note">Statuses reflect support in this transcript, not real-world verification.</p><ol>{transcript}</ol></aside></section></main>
    <footer>SourceCut demo data is fictional. No API key, upload, or account is required.</footer></body></html>'''


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return page()


def upload_page(message: str = "") -> str:
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Upload | SourceCut</title><link rel="stylesheet" href="/static/style.css"></head><body>
    <header><strong>SourceCut</strong><span>Local transcription</span><a href="/">Review demo</a><b>CPU mode</b></header>
    <main class="upload-main"><p class="eyebrow">STAGE 1</p><h1>Transcribe a local recording</h1><p class="note">MP3, MP4, or WAV. Files stay in this local SourceCut runtime directory and are not committed.</p><form class="upload-form" method="post" action="/upload" enctype="multipart/form-data" onsubmit="this.querySelector('button').textContent='Transcribing locally...';this.querySelector('button').disabled=true"><input type="file" name="file" accept=".mp3,.mp4,.wav" required><button>Transcribe locally</button></form>{message}</main></body></html>'''


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
        return HTMLResponse(upload_page(f'<p class="error">Transcription failed: {escape(str(error))}</p>'), status_code=422)
    with closing(db()) as connection:
        cursor = connection.execute("INSERT INTO uploads (original_name, path) VALUES (?, ?)", (file.filename or path.name, str(path)))
        connection.executemany(
            "INSERT INTO transcript_segments (upload_id, start, end, text) VALUES (?, ?, ?, ?)",
            [(cursor.lastrowid, segment["start"], segment["end"], segment["text"]) for segment in segments],
        )
        connection.commit()
    rows = "".join(f'<li><time>{segment["start"]:05.2f}</time><span>{escape(segment["text"])}</span></li>' for segment in segments) or "<li>No speech was detected.</li>"
    review_link = f'<p><a class="review-link" href="/uploads/{cursor.lastrowid}/review">Generate review candidates</a></p>' if segments else ""
    return HTMLResponse(upload_page(f'<section class="transcript-result"><h2>Transcript ready</h2><p>{len(segments)} timestamped segments from {escape(file.filename or path.name)}.</p><ol>{rows}</ol>{review_link}</section>'))


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
        return HTMLResponse(upload_page('<p class="error">No speech was detected, so there is nothing to review yet.</p>'), status_code=422)
    cards = "".join(
        f'''<article class="claim {candidate.claim.status}"><div class="claim-top"><span class="status">{candidate.claim.status.replace('_', ' ')}</span><a href="#evidence-{candidate.claim.evidence.segment_ids[0]}">Evidence</a></div><h2>{escape(candidate.title)}</h2><p class="claim-copy">{escape(candidate.draft)}</p><p class="reason">{escape(candidate.claim.reason)}</p><p><strong>Grounded rewrite:</strong> {escape(candidate.claim.rewrite)}</p></article>'''
        for candidate in candidates
    )
    transcript = "".join(
        f'<li id="evidence-{segment.id}"><time>{segment.start:05.2f}</time><span>{escape(segment.text)}</span></li>'
        for segment in segments
    )
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Review | SourceCut</title><link rel="stylesheet" href="/static/style.css"></head><body>
    <header><strong>SourceCut</strong><span>Local candidate review</span><a href="/upload">Upload another recording</a><b>Local analysis</b></header>
    <main><section class="project"><div><p class="eyebrow">CONTENT CANDIDATES</p><h1>{escape(name)}</h1><p>Deterministic local analysis. Statuses are support in the shown transcript, not real-world verification.</p></div></section><section class="review-grid"><section>{cards}</section><aside class="evidence"><p class="eyebrow">SOURCE EVIDENCE</p><h2>Transcript</h2><ol>{transcript}</ol></aside></section></main></body></html>'''


def update_claim(claim_id: int, approved: int) -> RedirectResponse:
    with closing(db()) as connection:
        updated = connection.execute("UPDATE claims SET approved = ? WHERE id = ?", (approved, claim_id)).rowcount
        connection.commit()
    if not updated:
        raise HTTPException(status_code=404, detail="Claim not found")
    return RedirectResponse("/", status_code=303)


@app.post("/claims/{claim_id}/accept")
def accept(claim_id: int) -> RedirectResponse:
    return update_claim(claim_id, 1)


@app.post("/claims/{claim_id}/restore")
def restore(claim_id: int) -> RedirectResponse:
    return update_claim(claim_id, 0)

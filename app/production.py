from __future__ import annotations

import json
import re
import shutil
import sqlite3
import subprocess
import threading
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from .media import ffmpeg_exe, inspect_media, media_fingerprint
from .review import TranscriptSegment, local_candidates
from .transcription import transcribe_media


ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "sourcecut.db"
OUTPUT_DIR = ROOT / "data" / "outputs"
KOKORO_DIR = ROOT / "data" / "models" / "kokoro"
KOKORO_MODEL = KOKORO_DIR / "kokoro-v1.0.int8.onnx"
KOKORO_VOICES = KOKORO_DIR / "voices-v1.0.bin"
EXAMPLE_SOURCE = ROOT / "static" / "sourcecut-production-example.mp4"
WORKER_LOCK = threading.Lock()
KOKORO_ENGINE: object | None = None
PLATFORMS = {
    "vertical": {"label": "Shorts / Reels / TikTok", "size": (1080, 1920), "limit": 60},
    "linkedin": {"label": "LinkedIn", "size": (1920, 1080), "limit": 60},
    "square": {"label": "Instagram feed", "size": (1080, 1080), "limit": 60},
}
EXAMPLE_SEGMENTS = [
    (0.0, 5.0, "In a pilot, teams reduced handoff time by up to 40 percent."),
    (6.0, 11.0, "The pilot was small, so we are not claiming this result for every customer yet."),
    (12.0, 17.0, "Participants used the review queue to check product claims before publishing."),
    (18.0, 21.0, "One pilot team cut its weekly approval meeting from 90 minutes to 45 minutes."),
]


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def format_duration(seconds: float) -> str:
    minutes, remainder = divmod(max(0, int(round(seconds))), 60)
    return f"{minutes}:{remainder:02d}"


def db() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    with closing(db()) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                source_path TEXT NOT NULL,
                media_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'queued',
                settings_json TEXT NOT NULL,
                error TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS project_segments (
                id INTEGER PRIMARY KEY,
                project_id INTEGER NOT NULL,
                start REAL NOT NULL,
                end REAL NOT NULL,
                text TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS clip_proposals (
                id INTEGER PRIMARY KEY,
                project_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                start REAL NOT NULL,
                end REAL NOT NULL,
                hook TEXT NOT NULL,
                caption TEXT NOT NULL,
                evidence_segment_id INTEGER,
                evidence_quote TEXT NOT NULL,
                claim_status TEXT NOT NULL,
                reason TEXT NOT NULL,
                selected INTEGER NOT NULL DEFAULT 0,
                render_status TEXT NOT NULL DEFAULT 'draft',
                output_path TEXT NOT NULL DEFAULT '',
                error TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS production_jobs (
                id INTEGER PRIMARY KEY,
                project_id INTEGER NOT NULL,
                kind TEXT NOT NULL,
                status TEXT NOT NULL,
                stage TEXT NOT NULL,
                detail TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(production_jobs)")}
        for name, definition in (
            ("progress", "INTEGER NOT NULL DEFAULT 0"),
            ("started_at", "TEXT NOT NULL DEFAULT ''"),
            ("finished_at", "TEXT NOT NULL DEFAULT ''"),
        ):
            if name not in columns:
                connection.execute(f"ALTER TABLE production_jobs ADD COLUMN {name} {definition}")
        connection.execute(
            """
            UPDATE production_jobs
            SET progress = CASE WHEN status IN ('done', 'failed') THEN 100 ELSE progress END,
                started_at = CASE WHEN started_at = '' AND status IN ('running', 'done', 'failed') THEN created_at ELSE started_at END,
                finished_at = CASE WHEN finished_at = '' AND status IN ('done', 'failed') THEN updated_at ELSE finished_at END
            """
        )
        project_columns = {row["name"] for row in connection.execute("PRAGMA table_info(projects)")}
        if "source_fingerprint" not in project_columns:
            connection.execute("ALTER TABLE projects ADD COLUMN source_fingerprint TEXT NOT NULL DEFAULT ''")
        connection.commit()


def settings_from_form(values: dict[str, str]) -> dict[str, object]:
    platform = values.get("platform", "vertical")
    if platform not in PLATFORMS:
        platform = "vertical"
    try:
        clip_count = min(max(int(values.get("clip_count", "3")), 1), 5)
    except ValueError:
        clip_count = 3
    try:
        duration = int(values.get("duration", "45"))
    except ValueError:
        duration = 45
    duration = min(max(duration, 15), int(PLATFORMS[platform]["limit"]))
    return {
        "platform": platform,
        "clip_count": clip_count,
        "duration": duration,
        "focus": values.get("focus", "").strip()[:160],
        "manual_clips": values.get("manual_clips", "").strip()[:240],
        "captions": values.get("captions", "bold") if values.get("captions") in {"bold", "minimal", "none"} else "bold",
        "framing": values.get("framing", "center") if values.get("framing") in {"center", "balanced"} else "center",
        "trim_silence": values.get("trim_silence") == "on",
        "audio_mode": "voiceover" if values.get("audio_mode") == "voiceover" else "source",
        "voice": _kokoro_voice(values.get("voice", "am_adam")),
        "proof_cards": values.get("proof_cards") == "on",
    }


def _kokoro_voice(voice: object) -> str:
    legacy_voices = {
        "en-US-AndrewMultilingualNeural": "am_adam",
        "en-US-AvaMultilingualNeural": "af_sarah",
    }
    value = legacy_voices.get(str(voice), str(voice))
    return value if value in {"am_adam", "af_sarah"} else "am_adam"


def create_project(name: str, source_path: Path, settings: dict[str, object], source_hash: str | None = None) -> int:
    init_db()
    media_type = source_path.suffix.lower().lstrip(".")
    source_hash = source_hash if source_hash is not None else media_fingerprint(source_path)
    with closing(db()) as connection:
        cursor = connection.execute(
            "INSERT INTO projects (name, source_path, media_type, settings_json, source_fingerprint, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (name or source_path.name, str(source_path), media_type, json.dumps(settings), source_hash, now()),
        )
        connection.commit()
        return int(cursor.lastrowid)


def create_example_project() -> int:
    if not EXAMPLE_SOURCE.is_file():
        raise FileNotFoundError("The SourceCut example video is missing.")
    existing = find_project_by_fingerprint(media_fingerprint(EXAMPLE_SOURCE))
    if existing:
        return int(existing["id"])
    settings = settings_from_form({"platform": "vertical", "clip_count": "3", "duration": "30", "captions": "bold", "proof_cards": "on"})
    project_id = create_project("SourceCut production example", EXAMPLE_SOURCE, settings)
    with closing(db()) as connection:
        connection.execute("UPDATE projects SET status = 'ready' WHERE id = ?", (project_id,))
        connection.executemany(
            "INSERT INTO project_segments (project_id, start, end, text) VALUES (?, ?, ?, ?)",
            [(project_id, start, end, text) for start, end, text in EXAMPLE_SEGMENTS],
        )
        connection.commit()
    segments = [
        TranscriptSegment(id=f"segment-{row['id']}", start=row["start"], end=row["end"], text=row["text"])
        for row in get_segments(project_id)
    ]
    _insert_proposals(project_id, segments, settings)
    return project_id


def get_project(project_id: int) -> sqlite3.Row | None:
    init_db()
    with closing(db()) as connection:
        return connection.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()


def find_project_by_fingerprint(source_hash: str) -> sqlite3.Row | None:
    if not source_hash:
        return None
    init_db()
    with closing(db()) as connection:
        return connection.execute(
            "SELECT * FROM projects WHERE source_fingerprint = ? ORDER BY id DESC LIMIT 1", (source_hash,)
        ).fetchone()


def list_projects() -> list[sqlite3.Row]:
    init_db()
    with closing(db()) as connection:
        return connection.execute(
            """SELECT projects.*, COUNT(DISTINCT clip_proposals.id) AS clip_count,
                      SUM(CASE WHEN clip_proposals.render_status = 'ready' THEN 1 ELSE 0 END) AS output_count
               FROM projects LEFT JOIN clip_proposals ON clip_proposals.project_id = projects.id
               GROUP BY projects.id ORDER BY projects.id DESC"""
        ).fetchall()


def get_segments(project_id: int) -> list[sqlite3.Row]:
    with closing(db()) as connection:
        return connection.execute("SELECT * FROM project_segments WHERE project_id = ? ORDER BY start", (project_id,)).fetchall()


def get_clips(project_id: int) -> list[sqlite3.Row]:
    with closing(db()) as connection:
        return connection.execute("SELECT * FROM clip_proposals WHERE project_id = ? ORDER BY id", (project_id,)).fetchall()


def latest_job(project_id: int) -> sqlite3.Row | None:
    with closing(db()) as connection:
        return connection.execute("SELECT * FROM production_jobs WHERE project_id = ? ORDER BY id DESC LIMIT 1", (project_id,)).fetchone()


def make_job(project_id: int, kind: str, stage: str) -> int:
    stamp = now()
    with closing(db()) as connection:
        cursor = connection.execute(
            "INSERT INTO production_jobs (project_id, kind, status, stage, progress, created_at, updated_at) VALUES (?, ?, 'queued', ?, 0, ?, ?)",
            (project_id, kind, stage, stamp, stamp),
        )
        connection.commit()
        return int(cursor.lastrowid)


def update_job(job_id: int, status: str, stage: str, detail: str = "", progress: int | None = None) -> None:
    stamp = now()
    fields = ["status = ?", "stage = ?", "detail = ?", "updated_at = ?"]
    values: list[object] = [status, stage, detail, stamp]
    if progress is not None:
        fields.append("progress = ?")
        values.append(max(0, min(100, int(progress))))
    if status == "running":
        fields.append("started_at = CASE WHEN started_at = '' THEN ? ELSE started_at END")
        values.append(stamp)
    if status in {"done", "failed"}:
        fields.append("finished_at = ?")
        values.append(stamp)
    values.append(job_id)
    with closing(db()) as connection:
        connection.execute(
            f"UPDATE production_jobs SET {', '.join(fields)} WHERE id = ?",
            values,
        )
        connection.commit()


def job_queue_position(job_id: int) -> int:
    with closing(db()) as connection:
        row = connection.execute(
            "SELECT COUNT(*) AS position FROM production_jobs WHERE status = 'queued' AND id <= ?", (job_id,)
        ).fetchone()
    return int(row["position"] or 0)


def recover_interrupted_jobs() -> int:
    stamp = now()
    with closing(db()) as connection:
        cursor = connection.execute(
            """
            UPDATE production_jobs
            SET status = 'failed', stage = 'Interrupted',
                detail = 'The local server restarted before this job finished. Retry the selected clips.',
                progress = 100, updated_at = ?, finished_at = ?
            WHERE status IN ('queued', 'running')
            """,
            (stamp, stamp),
        )
        connection.execute("UPDATE projects SET status = 'failed' WHERE status IN ('queued', 'processing', 'rendering')")
        connection.commit()
    return int(cursor.rowcount)


def parse_manual_ranges(value: str) -> list[tuple[float, float]]:
    ranges: list[tuple[float, float]] = []
    for part in value.split(","):
        match = re.fullmatch(r"\s*(?:(\d+):)?(\d{1,2})\s*-\s*(?:(\d+):)?(\d{1,2})\s*", part)
        if not match:
            continue
        start = int(match.group(1) or 0) * 60 + int(match.group(2))
        end = int(match.group(3) or 0) * 60 + int(match.group(4))
        if end > start:
            ranges.append((float(start), float(end)))
    return ranges[:5]


def _insert_proposals(project_id: int, segments: list[TranscriptSegment], settings: dict[str, object]) -> None:
    candidates = local_candidates(segments)
    manual = parse_manual_ranges(str(settings["manual_clips"]))
    planned: list[tuple[str, float, float, str, str, int | None, str, str, str]] = []
    if manual:
        for index, (start, end) in enumerate(manual, 1):
            evidence = next((segment for segment in segments if segment.start <= end and segment.end >= start), None)
            if not evidence:
                continue
            planned.append((
                f"Manual clip {index}", start, end, evidence.text, evidence.text,
                int(evidence.id.removeprefix("segment-")), evidence.text, "needs_review",
                "Manual range retained; review the linked source before rendering.",
            ))
    else:
        for candidate in candidates[:int(settings["clip_count"])]:
            evidence = candidate.claim.evidence
            if not evidence:
                continue
            source = next((segment for segment in segments if segment.id == evidence.segment_ids[0]), None)
            if not source:
                continue
            start, end = clean_clip_window(segments, source.id, float(settings["duration"]))
            planned.append((
                candidate.title, start, end, candidate.draft, candidate.claim.rewrite,
                int(source.id.removeprefix("segment-")), evidence.quote, candidate.claim.status,
                candidate.claim.reason,
            ))
    with closing(db()) as connection:
        connection.execute("DELETE FROM clip_proposals WHERE project_id = ?", (project_id,))
        connection.executemany(
            """INSERT INTO clip_proposals
               (project_id, title, start, end, hook, caption, evidence_segment_id, evidence_quote, claim_status, reason)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [(project_id, *proposal) for proposal in planned],
        )
        connection.commit()


def clean_clip_window(segments: list[TranscriptSegment], source_id: str, requested: float) -> tuple[float, float]:
    """Keep auto-selected clips on complete transcript thoughts, not arbitrary offsets."""
    anchor = next((index for index, segment in enumerate(segments) if segment.id == source_id), None)
    if anchor is None:
        return 0.0, min(requested, 15.0)
    first = anchor
    while first > 0 and not re.search(r"[.!?][\"')\]]*$", segments[first - 1].text.strip()):
        first -= 1
    if first > 0 and re.match(r"^(and|but|so|because|which|this|that|also)\b", segments[first].text.strip(), re.IGNORECASE):
        first -= 1
        while first > 0 and not re.search(r"[.!?][\"')\]]*$", segments[first - 1].text.strip()):
            first -= 1
    last = anchor
    minimum = min(max(10.0, requested * 0.35), 18.0)
    while last < len(segments) - 1:
        duration = segments[last].end - segments[first].start
        closes_thought = bool(re.search(r"[.!?][\"')\]]*$", segments[last].text.strip()))
        if duration >= minimum and closes_thought:
            break
        next_duration = segments[last + 1].end - segments[first].start
        if next_duration > requested and closes_thought:
            break
        last += 1
    # Do not add generic lead-in/out padding: a later transcript segment can
    # begin within it, making the rendered clip cut a new sentence in half.
    return segments[first].start, segments[last].end


def refine_project_cuts(project_id: int) -> bool:
    project = get_project(project_id)
    if not project:
        return False
    settings = json.loads(project["settings_json"])
    segments = [
        TranscriptSegment(id=f"segment-{row['id']}", start=row["start"], end=row["end"], text=row["text"])
        for row in get_segments(project_id)
    ]
    clips = get_clips(project_id)
    selected_count = sum(1 for clip in clips if clip["selected"])
    for clip in clips:
        old_output = Path(clip["output_path"]) if clip["output_path"] else None
        if old_output and old_output.exists() and old_output.resolve().is_relative_to(OUTPUT_DIR.resolve()):
            old_output.unlink(missing_ok=True)
            old_output.with_suffix(".srt").unlink(missing_ok=True)
            old_output.with_suffix(".voice.mp3").unlink(missing_ok=True)
            old_output.with_suffix(".voice.wav").unlink(missing_ok=True)
    _insert_proposals(project_id, segments, settings)
    if selected_count:
        with closing(db()) as connection:
            connection.execute(
                "UPDATE clip_proposals SET selected = 1 WHERE id IN (SELECT id FROM clip_proposals WHERE project_id = ? AND claim_status = 'supported' ORDER BY id LIMIT ?)",
                (project_id, selected_count),
            )
            connection.commit()
    return True


def run_analysis(project_id: int, job_id: int) -> None:
    try:
        with WORKER_LOCK:
            update_job(job_id, "running", "Inspect media", "Preparing the local source.", 5)
            project = get_project(project_id)
            if not project:
                return
            duration = inspect_media(Path(project["source_path"]))
            with closing(db()) as connection:
                connection.execute("UPDATE projects SET status = 'processing', error = '' WHERE id = ?", (project_id,))
                connection.commit()
            update_job(job_id, "running", "Transcribe", f"Verified a {format_duration(duration)} source. Creating timestamped segments on CPU.", 20)
            raw_segments = transcribe_media(Path(project["source_path"]))
            with closing(db()) as connection:
                connection.execute("DELETE FROM project_segments WHERE project_id = ?", (project_id,))
                connection.executemany(
                    "INSERT INTO project_segments (project_id, start, end, text) VALUES (?, ?, ?, ?)",
                    [(project_id, segment["start"], segment["end"], segment["text"]) for segment in raw_segments],
                )
                connection.commit()
            update_job(job_id, "running", "Find moments", "Building source-grounded clip proposals.", 75)
            segments = [
                TranscriptSegment(id=f"segment-{row['id']}", start=row["start"], end=row["end"], text=row["text"])
                for row in get_segments(project_id)
            ]
            _insert_proposals(project_id, segments, json.loads(project["settings_json"]))
            with closing(db()) as connection:
                connection.execute("UPDATE projects SET status = 'ready' WHERE id = ?", (project_id,))
                connection.commit()
            update_job(job_id, "done", "Review proposals", "Select the clips you want SourceCut to render.", 100)
    except Exception as error:
        with closing(db()) as connection:
            connection.execute("UPDATE projects SET status = 'failed', error = ? WHERE id = ?", (str(error)[-700:], project_id))
            connection.commit()
        update_job(job_id, "failed", "Analysis failed", str(error)[-700:], 100)


def start_analysis(project_id: int) -> int:
    job_id = make_job(project_id, "analysis", "Queued")
    threading.Thread(target=run_analysis, args=(project_id, job_id), daemon=True).start()
    return job_id


def set_selected(project_id: int, clip_id: int, selected: bool) -> bool:
    statement = "UPDATE clip_proposals SET selected = ? WHERE id = ? AND project_id = ?"
    arguments: tuple[object, ...] = (int(selected), clip_id, project_id)
    if selected:
        statement += " AND claim_status = 'supported'"
    with closing(db()) as connection:
        cursor = connection.execute(statement, arguments)
        connection.commit()
        return cursor.rowcount == 1


def render_filter(platform: str, framing: str) -> str:
    if platform == "vertical":
        return (
            "split[background][foreground];"
            "[background]scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920,boxblur=20:2[background];"
            "[foreground]scale=1080:1920:force_original_aspect_ratio=decrease[foreground];"
            "[background][foreground]overlay=(W-w)/2:(H-h)/2"
        )
    if platform == "square":
        return "scale=1080:1080:force_original_aspect_ratio=increase,crop=1080:1080"
    if framing == "balanced":
        return "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2"
    return "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080"


def srt_timestamp(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    seconds, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def write_timed_subtitles(project_id: int, clip: sqlite3.Row, destination: Path) -> None:
    start = float(clip["start"])
    end = float(clip["end"])
    cues: list[str] = []
    for index, segment in enumerate(get_segments(project_id), 1):
        cue_start = max(start, float(segment["start"]))
        cue_end = min(end, float(segment["end"]))
        if cue_end <= cue_start:
            continue
        text = str(segment["text"]).replace("-->", "->").replace("\n", " ")
        cues.append(f"{index}\n{srt_timestamp(cue_start - start)} --> {srt_timestamp(cue_end - start)}\n{text}\n")
    if not cues:
        cues.append(f"1\n00:00:00,000 --> {srt_timestamp(end - start)}\n{clip['caption']}\n")
    destination.write_text("\n".join(cues), encoding="utf-8")


def _kokoro_engine():
    global KOKORO_ENGINE
    if KOKORO_ENGINE is None:
        if not KOKORO_MODEL.is_file() or not KOKORO_VOICES.is_file():
            raise RuntimeError("The local Kokoro model is missing. Install SourceCut's local voice model before rendering.")
        from kokoro_onnx import Kokoro

        KOKORO_ENGINE = Kokoro(str(KOKORO_MODEL), str(KOKORO_VOICES))
    return KOKORO_ENGINE


def _synthesize_kokoro_voice(clip: sqlite3.Row, voice_file: Path, voice: object) -> None:
    import soundfile as soundfile

    text = str(clip["evidence_quote"] or clip["caption"]).replace("\n", " ").strip()
    if not text:
        raise RuntimeError("This clip has no source text to narrate.")
    samples, sample_rate = _kokoro_engine().create(text, voice=_kokoro_voice(voice), speed=1.0, lang="en-us")
    soundfile.write(voice_file, samples, sample_rate)
    if not voice_file.is_file() or voice_file.stat().st_size == 0:
        raise RuntimeError("Kokoro did not create an audio file.")


def _render_one(project: sqlite3.Row, clip: sqlite3.Row, settings: dict[str, object]) -> tuple[bool, str, str]:
    source = Path(project["source_path"])
    if source.suffix.lower() != ".mp4":
        return False, "Rendering requires an MP4 source. This source remains available for transcript review.", ""
    destination = OUTPUT_DIR / str(project["id"]) / f"sourcecut-clip-{clip['id']}.mp4"
    destination.parent.mkdir(parents=True, exist_ok=True)
    captions = destination.with_suffix(".srt")
    duration = max(0.2, float(clip["end"]) - float(clip["start"]))
    filter_chain = render_filter(str(settings["platform"]), str(settings["framing"]))
    if settings["captions"] != "none":
        write_timed_subtitles(int(project["id"]), clip, captions)
        subtitle_file = str(captions).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
        font_size = "8" if settings["captions"] == "bold" else "6"
        style = f"FontName=Arial,FontSize={font_size},PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=1,Alignment=2,MarginV=20"
        filter_chain = f"{filter_chain},subtitles=filename='{subtitle_file}':force_style='{style}'"
    if settings.get("proof_cards"):
        filter_chain += ",drawbox=x=40:y=40:w=440:h=105:color=black@0.9:t=fill:enable='between(t,0.4,2.7)',drawtext=text='SOURCE EVIDENCE':fontcolor=white:fontsize=28:x=66:y=78:enable='between(t,0.4,2.7)'"
    extra_inputs: list[str] = []
    audio_map = "0:a:0?"
    audio_filters: list[str] = []
    if settings.get("audio_mode") == "voiceover":
        voice_file = destination.with_suffix(".voice.wav")
        try:
            _synthesize_kokoro_voice(clip, voice_file, settings.get("voice"))
            extra_inputs = ["-i", str(voice_file)]
            audio_map = "1:a:0"
            audio_filters = ["-af", f"apad=pad_dur={duration}"]
        except Exception as error:
            return False, f"Local Kokoro voiceover failed: {str(error)[-500:]}", ""
    command = [
        ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", "-ss", str(clip["start"]),
        "-i", str(source), *extra_inputs, "-t", str(duration), "-map", "0:v:0?", "-map", audio_map,
        "-vf", filter_chain,
        "-c:v", "libx264", "-c:a", "aac", *audio_filters, "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(destination),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode or not destination.exists() or destination.stat().st_size == 0:
        destination.unlink(missing_ok=True)
        return False, result.stderr[-700:] or "FFmpeg could not render this clip.", ""
    probe = subprocess.run([ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-i", str(destination), "-f", "null", "-"], capture_output=True, text=True)
    if probe.returncode:
        destination.unlink(missing_ok=True)
        return False, "The rendered file could not be validated.", ""
    return True, str(destination), ""


def run_render(project_id: int, job_id: int, clip_ids: set[int] | None = None) -> None:
    try:
        with WORKER_LOCK:
            project = get_project(project_id)
            if not project:
                return
            settings = json.loads(project["settings_json"])
            clips = [clip for clip in get_clips(project_id) if clip["selected"] and (clip_ids is None or clip["id"] in clip_ids)]
            if not clips:
                update_job(job_id, "failed", "Nothing selected", "Choose one or more clip proposals before rendering.")
                return
            with closing(db()) as connection:
                connection.execute("UPDATE projects SET status = 'rendering' WHERE id = ?", (project_id,))
                connection.commit()
            for index, clip in enumerate(clips, 1):
                progress = 10 + int((index - 1) / len(clips) * 80)
                update_job(job_id, "running", "Render selected clips", f"Rendering {index} of {len(clips)}.", progress)
                if output_path(project_id, int(clip["id"])):
                    update_job(job_id, "running", "Reuse verified render", f"Reusing cached output {index} of {len(clips)}.", progress)
                    continue
                with closing(db()) as connection:
                    connection.execute("UPDATE clip_proposals SET render_status = 'rendering', error = '' WHERE id = ?", (clip["id"],))
                    connection.commit()
                ok, value, warning = _render_one(project, clip, settings)
                with closing(db()) as connection:
                    connection.execute(
                        "UPDATE clip_proposals SET render_status = ?, output_path = ?, error = ? WHERE id = ?",
                        ("ready" if ok else "failed", value if ok else "", warning if ok else value, clip["id"]),
                    )
                    connection.commit()
            with closing(db()) as connection:
                connection.execute("UPDATE projects SET status = 'ready' WHERE id = ?", (project_id,))
                connection.commit()
            update_job(job_id, "done", "Outputs ready", "Finished clips are ready in this project.", 100)
    except Exception as error:
        update_job(job_id, "failed", "Render failed", str(error)[-700:], 100)


def start_render(project_id: int, clip_ids: set[int] | None = None) -> int:
    job_id = make_job(project_id, "render", "Queued")
    threading.Thread(target=run_render, args=(project_id, job_id, clip_ids), daemon=True).start()
    return job_id


def output_path(project_id: int, clip_id: int) -> Path | None:
    with closing(db()) as connection:
        row = connection.execute(
            "SELECT output_path FROM clip_proposals WHERE id = ? AND project_id = ? AND render_status = 'ready'",
            (clip_id, project_id),
        ).fetchone()
    path = Path(row["output_path"]) if row and row["output_path"] else None
    return path if path and path.is_file() else None


def delete_project(project_id: int) -> bool:
    project = get_project(project_id)
    if not project:
        return False
    job = latest_job(project_id)
    if job and job["status"] in {"queued", "running"}:
        raise RuntimeError("Wait for the active local job before deleting this project.")
    source = Path(project["source_path"])
    uploads = (ROOT / "data" / "uploads").resolve()
    with closing(db()) as connection:
        connection.execute("DELETE FROM project_segments WHERE project_id = ?", (project_id,))
        connection.execute("DELETE FROM clip_proposals WHERE project_id = ?", (project_id,))
        connection.execute("DELETE FROM production_jobs WHERE project_id = ?", (project_id,))
        connection.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        connection.commit()
    try:
        managed_source = source.resolve().is_relative_to(uploads)
    except OSError:
        managed_source = False
    if managed_source:
        source.unlink(missing_ok=True)
        source.with_suffix(".16k.wav").unlink(missing_ok=True)
    project_outputs = OUTPUT_DIR / str(project_id)
    if project_outputs.exists() and project_outputs.resolve().is_relative_to(OUTPUT_DIR.resolve()):
        shutil.rmtree(project_outputs)
    return True

"""Run SourceCut's short original MP4 through the local CPU production path."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import production


SOURCE = ROOT / "static" / "sourcecut-production-example.mp4"


def main() -> None:
    if not SOURCE.is_file():
        raise SystemExit(f"Benchmark source is missing: {SOURCE}")
    settings = production.settings_from_form({"clip_count": "1", "duration": "15", "captions": "none"})
    project_id = production.create_project("Temporary CPU benchmark", SOURCE, settings)
    timings: dict[str, float] = {}
    try:
        started = perf_counter()
        duration = production.inspect_media(SOURCE)
        timings["inspect_seconds"] = round(perf_counter() - started, 3)
        started = perf_counter()
        live_segments = production.transcribe_media(SOURCE)
        timings["transcription_seconds"] = round(perf_counter() - started, 3)
        timings["transcription_segments"] = len(live_segments)
        # The original visual benchmark has an accompanying deterministic
        # transcript so it stays renderable even when a local ASR model hears
        # no speech in this short fixture.
        with production.closing(production.db()) as connection:
            connection.execute("UPDATE projects SET status = 'ready' WHERE id = ?", (project_id,))
            connection.executemany(
                "INSERT INTO project_segments (project_id, start, end, text) VALUES (?, ?, ?, ?)",
                [(project_id, start, end, text) for start, end, text in production.EXAMPLE_SEGMENTS],
            )
            connection.commit()
        segments = [
            production.TranscriptSegment(id=f"segment-{row['id']}", start=row["start"], end=row["end"], text=row["text"])
            for row in production.get_segments(project_id)
        ]
        started = perf_counter()
        production._insert_proposals(project_id, segments, settings)
        timings["proposal_seconds"] = round(perf_counter() - started, 3)
        clip = next((item for item in production.get_clips(project_id) if item["claim_status"] == "supported"), None)
        if not clip:
            raise RuntimeError("The benchmark source did not produce a supported proposal.")
        production.set_selected(project_id, int(clip["id"]), True)
        started = perf_counter()
        render_job = production.make_job(project_id, "render", "Queued")
        production.run_render(project_id, render_job)
        timings["render_seconds"] = round(perf_counter() - started, 3)
        output = production.output_path(project_id, int(clip["id"]))
        if not output:
            raise RuntimeError("The benchmark render was not FFmpeg-validated.")
        print(json.dumps({"source": SOURCE.name, "source_seconds": round(duration, 3), "output_bytes": output.stat().st_size, **timings}, indent=2))
    finally:
        production.delete_project(project_id)


if __name__ == "__main__":
    main()

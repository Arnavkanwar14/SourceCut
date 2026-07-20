from __future__ import annotations

import json
from pathlib import Path

from app import narration, production


def test_source_narration_beats_are_unique_chronological_and_punctuated() -> None:
    segments = [
        {"id": 1, "start": 0, "end": 2, "text": "First proof lands. Second proof follows"},
        {"id": 2, "start": 5, "end": 7, "text": "Final proof closes."},
    ]

    beats = narration.source_narration_beats(segments, 0, 7)

    assert [beat.text for beat in beats] == ["First proof lands.", "Second proof follows.", "Final proof closes."]
    assert [beat.desired_start for beat in beats] == [0, 1, 5]
    assert len({beat.text.casefold() for beat in beats}) == len(beats)
    assert all(beat.text[-1] in ".!?" for beat in beats)


def test_beat_schedule_shifts_an_overrun_and_resyncs_at_a_gap() -> None:
    beats = [
        narration.NarrationBeat("one", 0, "Opening proof."),
        narration.NarrationBeat("two", 1, "Middle proof."),
        narration.NarrationBeat("three", 5, "Final proof."),
    ]

    schedule = narration.schedule_beats(beats, [1.5, 1.0, 0.5])

    assert schedule[1]["start"] == 1.44
    assert schedule[2]["start"] == 5
    assert narration.speed_for_window(3, 1) == narration.MAX_TTS_SPEED


def test_voiceover_writes_a_measured_timing_manifest(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    project_id = production.create_project("Narration timing", source, production.settings_from_form({"audio_mode": "voiceover"}))
    with production.closing(production.db()) as connection:
        connection.executemany(
            "INSERT INTO project_segments (project_id, start, end, text) VALUES (?, ?, ?, ?)",
            [
                (project_id, 0, 1, "Opening proof lands."),
                (project_id, 1, 2, "Middle proof lands."),
                (project_id, 5, 6, "Final proof lands."),
            ],
        )
        cursor = connection.execute(
            "INSERT INTO clip_proposals (project_id, title, start, end, hook, caption, evidence_quote, claim_status, reason) VALUES (?, ?, 0, 7, ?, ?, ?, 'supported', ?)",
            (project_id, "Moment", "Hook", "Caption", "Opening proof lands.", "Direct source wording."),
        )
        connection.commit()
    clip = production.get_clips(project_id)[0]
    voice_file = tmp_path / "voice.wav"
    captured: dict[str, object] = {}

    def fake_synthesis(_: str, path: Path, __: object, speed: float = 1.0) -> float:
        path.write_bytes(b"beat")
        return 1.6 / speed

    def fake_mix(files: list[Path], schedule: list[dict[str, object]], destination: Path, duration: float) -> None:
        captured["files"] = files
        captured["schedule"] = schedule
        captured["duration"] = duration
        destination.write_bytes(b"mixed")

    monkeypatch.setattr(production, "_synthesize_kokoro_beat", fake_synthesis)
    monkeypatch.setattr(production, "_mix_voiceover_beats", fake_mix)
    production.build_voiceover_track(production.get_project(project_id), clip, voice_file, "am_adam", 7)

    timing = json.loads(production.voice_timing_path(voice_file).read_text(encoding="utf-8"))
    assert timing["logic_version"] == narration.NARRATION_LOGIC_VERSION
    assert timing["word_budget"] == {"min": narration.MIN_BEAT_WORDS, "max": narration.MAX_BEAT_WORDS}
    assert len(timing["beats"]) == 3
    assert timing["beats"][0]["speed"] == narration.MAX_TTS_SPEED
    assert timing["beats"][-1]["start"] == 5
    assert len(captured["files"]) == 3

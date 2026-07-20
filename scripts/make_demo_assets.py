from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.main import TRANSCRIPT
from app.media import ffmpeg_exe
from app.production import EXAMPLE_SEGMENTS, _synthesize_kokoro_beat
from app.transcription import transcribe_media


STATIC = ROOT / "static"
IMAGE = STATIC / "sourcecut-evidence-object.png"
VOICE = "am_adam"
MAX_ASSET_TTS_SPEED = 2.0


def timestamp(value: float) -> str:
    milliseconds = round(value * 1000)
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    seconds, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def normalized(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def synthesize_slot(text: str, destination: Path, slot_seconds: float) -> float:
    speed = 1.0
    duration = _synthesize_kokoro_beat(text, destination, VOICE, speed)
    while duration > slot_seconds and speed < MAX_ASSET_TTS_SPEED:
        speed = min(MAX_ASSET_TTS_SPEED, speed * duration / slot_seconds * 1.02)
        duration = _synthesize_kokoro_beat(text, destination, VOICE, speed)
    if duration > slot_seconds:
        raise RuntimeError(f"Narration overruns its {slot_seconds:.2f}s source slot: {text}")
    return duration


def write_subtitles(lines: list[tuple[float, str, float]], destination: Path) -> None:
    cues = [f"{index}\n{timestamp(start)} --> {timestamp(start + duration)}\n{text}\n" for index, (start, text, duration) in enumerate(lines, 1)]
    destination.write_text("\n".join(cues), encoding="utf-8")


def render_asset(output: Path, lines: list[tuple[float, str]], duration: float, size: tuple[int, int], temp: Path) -> None:
    rendered_lines: list[tuple[float, str, float]] = []
    wavs: list[Path] = []
    for index, (start, text) in enumerate(lines):
        next_start = lines[index + 1][0] if index + 1 < len(lines) else duration
        wav = temp / f"line-{index + 1:02d}.wav"
        spoken_duration = synthesize_slot(text, wav, next_start - start)
        rendered_lines.append((start, text, spoken_duration))
        wavs.append(wav)

    subtitles = temp / f"{output.stem}.srt"
    write_subtitles(rendered_lines, subtitles)
    width, height = size
    subtitle_path = str(subtitles).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
    # libass scales SRT captions from its default canvas, so large point sizes fill the frame.
    font_size = 10
    video_filter = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=0xe5e5e5,"
        f"subtitles=filename='{subtitle_path}':force_style='FontName=Arial,FontSize={font_size},PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00000000,BorderStyle=1,Outline=2,Alignment=2,MarginV=48'"
    )
    inputs = ["-loop", "1", "-framerate", "24", "-i", str(IMAGE)]
    for wav in wavs:
        inputs.extend(["-i", str(wav)])
    audio_filters: list[str] = []
    labels: list[str] = []
    for index, (start, _, _) in enumerate(rendered_lines, 1):
        label = f"a{index}"
        audio_filters.append(f"[{index}:a]adelay={round(start * 1000)}:all=1[{label}]")
        labels.append(f"[{label}]")
    audio_filters.append(f"{''.join(labels)}amix=inputs={len(labels)}:duration=longest,apad,atrim=duration={duration:.3f}[audio]")
    command = [
        ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", *inputs,
        "-filter_complex", ";".join(audio_filters), "-map", "0:v:0", "-map", "[audio]",
        "-vf", video_filter, "-t", str(duration), "-c:v", "libx264", "-c:a", "aac", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr[-1000:] or f"Could not render {output.name}")


def verify_streams(path: Path) -> None:
    result = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", str(path), "-f", "null", "-"], capture_output=True, text=True)
    metadata = result.stderr.split("Stream mapping:", 1)[0]
    if result.returncode or metadata.count("Video:") != 1 or metadata.count("Audio:") != 1:
        raise RuntimeError(f"{path.name} must contain exactly one video stream and one audio stream.")


def verify_transcript(path: Path, expected: list[tuple[float, float, str]]) -> None:
    actual = transcribe_media(path)
    for start, end, text in expected:
        expected_words = normalized(text).split()
        match = next((segment for segment in actual if abs(float(segment["start"]) - start) <= 1.5 and sum(word in normalized(segment["text"]) for word in expected_words) >= max(3, len(expected_words) - 2)), None)
        if not match:
            raise RuntimeError(f"Whisper could not verify the expected source line at {start:.2f}s: {text}")
        if float(match["end"]) < min(end, start + 1):
            raise RuntimeError(f"Whisper timing ended too early for the source line at {start:.2f}s")


def main() -> None:
    if not IMAGE.is_file():
        raise FileNotFoundError("The original SourceCut evidence object is missing.")
    seed_lines = [(int(clock.split(":")[0]) * 60 + int(clock.split(":")[1]), text) for _, clock, text in TRANSCRIPT]
    production_lines = [(start, text) for start, _, text in EXAMPLE_SEGMENTS]
    judge_lines = [(0.0, EXAMPLE_SEGMENTS[0][2])]
    with tempfile.TemporaryDirectory(prefix="sourcecut-demo-assets-") as directory:
        temp = Path(directory)
        render_asset(STATIC / "sourcecut-seed-demo.mp4", seed_lines, 110.0, (1280, 720), temp)
        render_asset(STATIC / "sourcecut-production-example.mp4", production_lines, 22.0, (1280, 720), temp)
        render_asset(STATIC / "sourcecut-judge-output.mp4", judge_lines, 5.0, (1080, 1920), temp)
    for name in ("sourcecut-seed-demo.mp4", "sourcecut-production-example.mp4", "sourcecut-judge-output.mp4"):
        verify_streams(STATIC / name)
    verify_transcript(STATIC / "sourcecut-production-example.mp4", EXAMPLE_SEGMENTS)
    print("Rendered and verified SourceCut demo assets.")


if __name__ == "__main__":
    main()

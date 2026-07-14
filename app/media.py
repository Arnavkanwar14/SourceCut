from __future__ import annotations

import re
import shutil
import subprocess
import uuid
from pathlib import Path

import imageio_ffmpeg
from fastapi import HTTPException, UploadFile


ALLOWED_SUFFIXES = {".mp3", ".mp4", ".wav"}
MAX_UPLOAD_BYTES = 500 * 1024 * 1024


def ffmpeg_exe() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()


def inspect_media(source: Path) -> float:
    """Return the source duration after asking the bundled FFmpeg to read it."""
    result = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", str(source)], capture_output=True, text=True)
    match = re.search(r"Duration:\s*(\d+):(\d{2}):(\d{2}(?:\.\d+)?)", result.stderr)
    if not match:
        raise RuntimeError("SourceCut could not inspect this media file. Choose a playable MP4, MP3, or WAV source.")
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


async def save_upload(upload: UploadFile, upload_dir: Path) -> Path:
    suffix = Path(upload.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=400, detail="Use an MP3, MP4, or WAV file.")
    upload_dir.mkdir(parents=True, exist_ok=True)
    path = upload_dir / f"{uuid.uuid4().hex}{suffix}"
    size = 0
    with path.open("wb") as destination:
        while chunk := await upload.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                destination.close()
                path.unlink(missing_ok=True)
                raise HTTPException(status_code=400, detail="Files must be 500 MB or smaller.")
            destination.write(chunk)
    if not size:
        path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    return path


def extract_audio(source: Path) -> Path:
    output = source.with_suffix(".16k.wav")
    result = subprocess.run(
        [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(source), "-vn", "-ac", "1", "-ar", "16000", str(output)],
        capture_output=True,
        text=True,
    )
    if result.returncode:
        output.unlink(missing_ok=True)
        raise RuntimeError(result.stderr[-1000:] or "FFmpeg could not read this media file.")
    return output


def remove_media(path: Path) -> None:
    path.unlink(missing_ok=True)
    path.with_suffix(".16k.wav").unlink(missing_ok=True)
    if path.parent.exists() and not any(path.parent.iterdir()):
        shutil.rmtree(path.parent)

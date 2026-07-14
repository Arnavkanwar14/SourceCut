from __future__ import annotations

import shutil
import subprocess
import uuid
from pathlib import Path

import imageio_ffmpeg
from fastapi import HTTPException, UploadFile


ALLOWED_SUFFIXES = {".mp3", ".mp4", ".wav"}
MAX_UPLOAD_BYTES = 25 * 1024 * 1024


def ffmpeg_exe() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()


async def save_upload(upload: UploadFile, upload_dir: Path) -> Path:
    suffix = Path(upload.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=400, detail="Use an MP3, MP4, or WAV file.")
    body = await upload.read(MAX_UPLOAD_BYTES + 1)
    if len(body) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="Files must be 25 MB or smaller.")
    if not body:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    upload_dir.mkdir(parents=True, exist_ok=True)
    path = upload_dir / f"{uuid.uuid4().hex}{suffix}"
    path.write_bytes(body)
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

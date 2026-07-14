# Third-Party Notices

SourceCut uses the following direct Python dependencies. Their source and license terms remain with their respective maintainers; include their notices when redistributing a packaged build.

| Dependency | Purpose | License |
| --- | --- | --- |
| FastAPI | Web framework | MIT |
| Uvicorn | Local ASGI server | BSD-3-Clause |
| HTTPX | Test client transport | BSD-3-Clause |
| pytest | Test runner | MIT |
| python-multipart | Multipart upload parsing | Apache-2.0 |
| imageio-ffmpeg | Bundled FFmpeg executable resolution | BSD-2-Clause |
| faster-whisper | Optional local CPU transcription | MIT |

The optional transcription stack brings transitive dependencies. Their licenses are distributed with their installed packages and must be reviewed before any standalone binary distribution. SourceCut does not redistribute third-party media or model weights in this repository.

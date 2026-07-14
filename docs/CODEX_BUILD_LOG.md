# Codex Build Log

## Project decision

SourceCut is a Work & Productivity review copilot for marketing teams. The team deliberately chose evidence review over a general video editor so the demo can show an inspectable decision: an unsupported marketing claim becomes a timestamp-backed rewrite.

## Codex-assisted implementation

| Stage | Codex contribution | Human decision and verification |
| --- | --- | --- |
| Foundation | Built FastAPI, SQLite seed state, tests, and a no-key review page. | Keep the judge flow deterministic and local. |
| Transcript path | Added bundled-FFmpeg media handling and CPU `faster-whisper` transcription. | Use CPU `int8`; do not depend on broken CUDA. |
| Evidence engine | Implemented structured transcript evidence validation and 12 labelled evaluation cases. | A positive status must validate IDs, exact quote, and timestamps mechanically. |
| Reviewer workflow | Added rewrite approval, custom-edit rechecking, and Markdown/JSON export. | Export only approved rewrites with their source evidence. |
| UI | Applied the supplied editorial reference with original SourceCut branding and a generated original evidence object. | Do not reuse Dayos assets, text, logos, or font files. |

## Runtime model status

The project was built in Codex during Build Week. The submitted seed flow is deterministic and does not call an external model. GPT-5.6 runtime inference is intentionally not represented as complete until an API key and credits are configured.

## Required submission evidence

- Build Week `/feedback` session ID: `TBD before submission`.
- Dated SourceCut commits: available in Git history.
- Verification: `pytest` passes the seed workflow and evidence evaluation suite.

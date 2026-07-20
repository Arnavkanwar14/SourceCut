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
| Production desk | Built persistent projects, source playback, transcript seeking, evidence-linked clip proposals, local job polling, source-cut rendering, output playback, and exports. | Borrow flow ideas from Shortsmaker/OpenMontage without copying their code, media, or branding; only supported claims can enter the render queue. |

## Runtime model status

The project was built in Codex during Build Week. The submitted Judge Demo is deterministic and does not call an external model. GPT-5.6 structured transcript analysis is available for uploaded projects only when a local key and explicit feature flag are configured; all returned candidates are revalidated locally and provenance is shown in the workspace and handoff.

## Required submission evidence

- Build Week `/feedback` session ID: `019f5c94-f927-7441-bc28-439e89b247cd`.
- Dated SourceCut commits: available in Git history.
- Verification: `pytest` passes the seed workflow and evidence evaluation suite.

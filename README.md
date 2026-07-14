# SourceCut

SourceCut is an evidence-backed content review copilot for marketing teams. It turns a long-form source into a reviewable content package, but does not label a claim as safe until its cited transcript IDs, exact quote, and timestamps validate mechanically.

The default experience is a no-key seeded production dashboard. It opens on a fictional project, explains the upload-to-output workflow, and links to an intentionally risky claim that a reviewer can correct against its transcript evidence.

## Run the judge demo

Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_demo.ps1
```

The script uses port `8000`, installs dependencies into `.venv` only when needed, and prints the local URL. If that port is already occupied, stop the existing process or explicitly choose one port with `-Port 8010`; the script will never silently switch ports. No account, API key, media file, or model download is required for the seeded review.

For a manual setup:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Then open `http://127.0.0.1:8000`.

## Judge flow

1. Open the seeded `ApexFlow product webinar` review.
2. Open the evidence link for `Customers save 40%.` and inspect the source qualifier: a 12-customer pilot achieved up to 40 percent.
3. Approve the grounded rewrite, or open `Edit rewrite` and save a custom sentence. SourceCut rechecks every saved edit before it can become approved.
4. Use the Markdown or JSON export controls after approval. The package contains only approved rewrites and their evidence timestamps.

## Production workflow

`Create project` accepts local MP4, MP3, and WAV sources. MP4 is the full production path: SourceCut stores the recording locally, transcribes it on CPU, creates evidence-backed proposals, then renders only supported clips selected by the reviewer. MP3/WAV remain useful for transcript and production-brief review, but cannot produce a visual MP4 output.

The Create screen provides curated controls for platform, clip count, duration, captions, framing, source audio or optional AI voiceover, original proof-card overlays, focus, and manual ranges. The renderer supports vertical, square, and landscape source cuts with local FFmpeg. It validates each output before it appears in the project library.

Quiet-gap trimming is shown as a non-destructive edit plan in this release so the original evidence timestamps stay exact. Voiceover is opt-in, uses the free `edge-tts` package when installed, and requires internet access; if it is unavailable, SourceCut renders with the original audio and records a visible warning.

## Optional GPT-5.6 analysis

The seed demo never calls a paid API. To enable structured GPT-5.6 candidate generation for uploaded transcripts only, set these values in a local `.env` file:

```text
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-5.6
SOURCECUT_LIVE_ANALYSIS=1
```

SourceCut requests structured output through the Responses API, then reruns every model-proposed claim through the local transcript validator. If the key is missing, disabled, or a model request fails, the upload review falls back to deterministic local candidates.

## What the checker guarantees

- A claim with missing segment IDs, a mismatched quote, or timestamps outside the source remains `needs_review`.
- Numerical claims that remove `pilot` or `up to` qualifiers are `unsupported`.
- Absolute language not present in the cited source is `unsupported`.
- An edit is never marked approved without passing the same deterministic check.

The checker evaluates support in the shown transcript. It is not a legal, factual, or compliance certification.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest
```

The suite includes the 12 labelled evidence cases in `tests/fixtures/evidence_cases.json`, seeded reviewer approval/restore actions, unsafe custom rewrite rejection, upload handling, and exports.

## Build Week collaboration

SourceCut was built in Codex during OpenAI Build Week. Codex helped implement the FastAPI workflow, local transcription integration, deterministic evidence validation, reviewer UI, original product visual, tests, and submission documentation. Human decisions set the product scope, seed scenario, review policy, and visual direction.

The application stays usable without keys while Build Week credits are unavailable. GPT-5.6 is an optional, explicitly enabled upload-analysis provider; the seeded judge flow stays deterministic and key-free.

Before submitting, add the required Build Week `/feedback` session ID here: `TBD`.

## Submission notes

- Category: Work & Productivity.
- Seeded demo: free, local, and no-sign-in.
- Product, transcript, UI asset, and demo scenario: original or created specifically for SourceCut. See `ASSET_NOTES.md`.
- Direct dependency notices: `THIRD_PARTY_NOTICES.md`.
- Demo narration: `docs/demo-script.md`.
- Submission checklist: `docs/submission-checklist.md`.

## License

SourceCut is released under the [MIT License](LICENSE).

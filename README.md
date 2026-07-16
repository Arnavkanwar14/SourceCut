# SourceCut

AI drafts your clips. SourceCut is the gate that won't let an unsupported claim through. It is an evidence-backed content review copilot for marketing teams that does not label a claim as safe until its cited transcript IDs, exact quote, and timestamps validate mechanically.

The default experience is a no-key seeded production dashboard. It opens on a fictional project, explains the upload-to-output workflow, and links to an intentionally risky claim that a reviewer can correct against its transcript evidence.

## Why It Matters

A marketer clips a webinar and turns “in a 12-customer pilot, teams reduced handoff time by up to 40 percent” into “Customers save 40%.” The pilot scope and qualifier disappear, and the usual backstop is a human rewatching the source. SourceCut catches that loss before publish by keeping the claim attached to its source wording and time range. This is the kind of substantiation risk where objective advertising claims need a reasonable basis before they are disseminated; SourceCut is not legal advice or a substitute for final compliance review. [FTC advertising substantiation policy](https://www.ftc.gov/legal-library/browse/ftc-policy-statement-regarding-advertising-substantiation)

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

## Judge Quickstart

Run the command above, then choose **Open Judge Demo** on the dashboard. It opens an original source recording with transcript evidence, reviewable proposals, one finished vertical clip, and its marketer handoff package. This path is fully local and requires no API key, model download, account, or upload.

## Security model

SourceCut is a single-user local workspace and its demo command binds to `127.0.0.1` only. State-changing browser requests reject cross-site origins, and the app sends local-only content, framing, MIME-sniffing, and referrer protections. Do not expose this instance on a LAN or public host: it has no accounts, authentication, or per-user project ownership.

## Judge flow

1. Open the seeded `ApexFlow product webinar` review.
2. Open the evidence link for `Customers save 40%.` and inspect the source qualifier: a 12-customer pilot achieved up to 40 percent.
3. Approve the grounded rewrite, or open `Edit rewrite` and save a custom sentence. SourceCut rechecks every saved edit before it can become approved.
4. Use the Markdown or JSON export controls after approval. The package contains only approved rewrites and their evidence timestamps.

## Production workflow

`Create project` accepts local MP4, MP3, and WAV sources up to 500 MB. The browser shows the selected source duration and a local CPU estimate before upload; SourceCut then verifies the media with bundled FFmpeg before transcription. MP4 is the full production path: SourceCut stores the recording locally, transcribes it on CPU, creates evidence-backed proposals, then renders only supported clips selected by the reviewer. MP3/WAV remain useful for transcript and production-brief review, but cannot produce a visual MP4 output.

The Create screen provides curated controls for platform, clip count, duration, captions, framing, source audio or optional AI voiceover, original proof-card overlays, focus, and manual ranges. The renderer supports vertical, square, and landscape source cuts with local FFmpeg. It validates each output before it appears in the project library.

Quiet-gap trimming is shown as a non-destructive edit plan in this release so the original evidence timestamps stay exact. Voiceover is opt-in and runs locally through the quantized Kokoro ONNX model; it narrates the exact source evidence quote and never silently falls back to original audio. A failed local synthesis is reported on that clip instead.

## Marketer handoff

Finished projects have a dedicated handoff view with playable clips, hook, caption, source range, direct evidence link, explicit audio mode, render profile, individual downloads, and re-render controls. Download the ZIP to receive the ready selected MP4s plus matching JSON and Markdown evidence packages. Re-running a verified local output reuses the cached file; a server restart leaves interrupted work in a visible retryable state rather than reporting a false success.

Run the short original fixture benchmark with `\.venv\Scripts\python.exe .\scripts\benchmark.py`. Its latest measured local timing and ASR caveat are recorded in `docs/benchmark.md`.

## Optional GPT-5.6 analysis

The Judge Demo never calls a paid API. For uploaded projects, SourceCut can use GPT-5.6 to propose content moments only when explicitly enabled. Every proposal is then checked locally against transcript IDs, exact quoted wording, and timestamp bounds before it can be selected for render. If the model is disabled, unavailable, or produces no usable candidates, SourceCut visibly reports and uses its deterministic local fallback.

To enable the optional provider, set these values in a local `.env` file:

```text
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-5.6
SOURCECUT_LIVE_ANALYSIS=1
```

SourceCut requests structured output through the Responses API and records either `GPT-5.6 proposals, evidence verified locally` or `Local deterministic fallback` in the workspace and handoff. API keys remain local and are never rendered or exported.

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

The suite covers the labelled evidence cases in `tests/fixtures/evidence_cases.json`, seeded reviewer approval/restore actions, unsafe custom rewrite rejection, upload handling, exports, durable job progress, and workspace fragment updates.

## Build Week collaboration

SourceCut was built in Codex during OpenAI Build Week. Codex helped implement the FastAPI workflow, local transcription integration, GPT-5.6 proposal guardrails, deterministic evidence validation, reviewer UI, original product visual, tests, and submission documentation. Human decisions set the product scope, seed scenario, review policy, and visual direction.

The application stays usable without keys while Build Week credits are unavailable. GPT-5.6 is an optional, explicitly enabled upload-analysis provider; the seeded judge flow stays deterministic and key-free.

Before submitting, add the required Build Week `/feedback` session ID here: `TBD`.

## Submission notes

- Category: Work & Productivity.
- Judge Demo: free, local, and no-sign-in.
- Public repository: https://github.com/Arnavkanwar14/SourceCut
- Product, transcript, UI asset, and demo scenario: original or created specifically for SourceCut. See `ASSET_NOTES.md`.
- Direct dependency notices: `THIRD_PARTY_NOTICES.md`.
- Demo narration: `docs/demo-script.md`.
- Submission checklist: `docs/submission-checklist.md`.

## License

SourceCut is released under the [MIT License](LICENSE).

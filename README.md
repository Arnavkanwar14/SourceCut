# SourceCut

SourceCut is an evidence-backed content review copilot for marketing teams. It turns a long-form source into a reviewable content package, but does not label a claim as safe until its cited transcript IDs, exact quote, and timestamps validate mechanically.

The default experience is a no-key seeded demo. It opens on an intentionally risky claim, shows the supporting transcript, lets a reviewer edit or approve a grounded rewrite, and exports the approved package as Markdown or JSON.

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

The `Upload` page is an optional local transcription path for MP3, MP4, and WAV files. It uses CPU transcription and can download the small Whisper model on its first real upload. It is not needed for judging.

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

The runtime currently does not call GPT-5.6 or any paid model API. The application stays usable without keys while Build Week credits are unavailable. The planned OpenAI provider remains a future optional integration, not a claimed current feature.

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

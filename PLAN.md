# SourceCut Build Plan

## Handoff

**SourceCut** is a Work & Productivity project for marketing and agency teams. It turns a long-form recording into publishable social-content drafts, but its core value is a review surface that links each generated claim to a transcript timestamp and flags unsupported or risky wording. The project starts in this empty directory; `shortsmaker` is a read-only reference for its local transcription, timestamps, and FFmpeg patterns. The chosen approach is a standalone Python/FastAPI app with a simple server-rendered review interface, free-first transcription, and a provider adapter that uses Groq during development and GPT-5.6 after Build Week credits are available.

**Current status:** Stages 0 and 1 are complete and verified locally. The no-key seeded review page persists approval/revert actions; local MP3/MP4/WAV uploads normalize through the bundled FFmpeg binary and transcribe on CPU with persisted timestamped segments.

**Next step:** Stage 2, add structured candidate generation and mechanically validated transcript evidence while preserving the seeded no-key path.

## Product Definition

### User

A content marketer or agency reviewer who needs to turn a webinar, interview, or product recording into short-form posts, but must verify claims before they go public.

### Demo promise

"A marketer uploads an original fictional product webinar, receives three social-post drafts with clip windows, sees a claim such as ‘customers save 40%’ marked unsupported, and replaces it with a timestamp-backed, publishable version."

### Judge's 30-second aha

The first screen opens a preloaded candidate that says, "Customers save 40%." The reviewer clicks its red evidence status, sees that the source only supports "up to 40% in a 12-customer pilot," accepts the safer rewrite, and sees the post become approval-ready. This must work without upload, account, API key, or waiting for a model.

### MVP scope

- Ingest a local MP4 or WAV file.
- Produce a timestamped transcript.
- Generate three candidate content moments and a social-post draft for each.
- Split every draft into atomic claims and attach supporting transcript spans.
- Mark claims as `supported`, `needs_review`, or `unsupported`, with a reason.
- Let the reviewer accept an agent rewrite or edit/approve a claim.
- Show an exportable final content package: clip time range, hook, caption, post copy, and evidence links.
- Ship an evaluation fixture of at least 12 labelled claims so the evidence checker can be measured rather than merely demonstrated.

### Explicitly out of scope

- Login, multi-user collaboration, notifications, billing, publishing to social networks, legal compliance certification, and full video rendering/export.
- Downloading arbitrary YouTube URLs in the MVP.
- Claiming that the tool determines legal truth. It only evaluates support against the uploaded transcript and the selected review rules.
- Hiding uncertainty: a claim without adequate evidence must visibly remain `needs_review`, not be force-labelled safe.

## Approaches Considered

### Chosen: standalone FastAPI review app with a provider adapter

Use FastAPI, server-rendered HTML/CSS/JS, SQLite, local CPU transcription, and an LLM adapter. This is fastest to a stable, inspectable demo and keeps the evidence engine under our control. A provider adapter lets us build with Groq now and demonstrate GPT-5.6 once the Build Week credits arrive.

### Rejected: extend `shortsmaker`

It already has useful transcription and highlight patterns, but adding review workflow features would change an existing project and obscure the hackathon submission. We will copy only the minimal concepts or code that are compatible with its license and attribution requirements.

### Rejected: build a React video-editing product

It would consume the schedule in timeline UI and rendering. Judges need to see the review decision, evidence, and corrected content; a clear preview link/time range is enough for the MVP.

### Rejected: OpenMontage integration

OpenMontage is a broad production system and an unsuitable dependency for a one-week, tightly scoped submission. Its repository stays untouched.

## Architecture

```text
Local media upload
    -> normalize audio with imageio-ffmpeg binary
    -> faster-whisper CPU transcription
    -> transcript segments + words stored in SQLite/JSON
    -> LLM content planner creates candidate moments and drafts
    -> deterministic evidence matcher + LLM reviewer checks each atomic claim
    -> reviewer UI approves, rewrites, or edits
    -> export JSON/Markdown content package
```

### Evidence contract

An evidence result is not a model opinion. Every displayed `supported` or `unsupported` result must contain: the claim text, a status, one or more immutable transcript segment IDs, the exact quoted source text, start/end timestamps, and a short human-readable reason. The UI may display an LLM-selected candidate, but it may not display a positive status until the referenced transcript segments actually exist and the stored quote matches them. Missing or ambiguous evidence becomes `needs_review`.

### Provider policy

- Build the core functionality through Codex/GPT-5.6 during the Submission Period, retain the `/feedback` session ID where most work occurred, and preserve dated commits as evidence.
- `OPENAI_API_KEY` configured: use GPT-5.6 for content planning and claim review.
- Otherwise, `GROQ_API_KEY` configured: use the supported Groq model selected in `.env`.
- Otherwise: load a seeded deterministic demo analysis so the complete review flow remains runnable without any key.
- Keys only live in `.env`; `.env.example` lists variable names only.

## Stages

### Stage 0: Walking Skeleton

**Visible endpoint:** `http://127.0.0.1:8000` opens a SourceCut review page containing one seeded webinar, three draft content cards, and one unsupported claim correction.

1. **Goal:** Create the Python project, isolated `.venv`, FastAPI app, static assets, `.gitignore`, `.env.example`, and SQLite schema.
   **Where:** project root, `app/`, `static/`, `tests/`.
   **Verify:** `python -m uvicorn app.main:app --port 8000` then open the page and confirm the seeded content displays.
   **Fence:** Do not add accounts, uploads, external APIs, or video processing.

2. **Goal:** Create an original, fictional product-webinar demo recording/transcript plus a realistic content package with an unsupported claim and a safe rewrite.
   **Where:** `demo_data/`, `app/seed.py`.
   **Verify:** reset the local database and confirm the evidence panel jumps to the cited transcript span and the unsupported card shows its reason.
   **Fence:** Do not use third-party voices, music, trademarks, recordings, or copyrighted media; do not represent seeded analysis as live LLM output.

3. **Goal:** Add basic route and evidence-matching tests.
   **Where:** `tests/`.
   **Verify:** `python -m pytest` passes.
   **Fence:** Keep tests fixture-based; do not require a model key or network.

### Stage 1: Real Transcript Ingestion

**Visible endpoint:** a user can upload a local short recording and see its timestamped transcript in SourceCut.

1. **Goal:** Copy only the necessary media-normalization and CPU-transcription approach from `shortsmaker`, resolving FFmpeg through `imageio-ffmpeg` so it works on this Windows machine.
   **Where:** `app/media.py`, `app/transcription.py`.
   **Verify:** upload the original 1-3 minute demo MP4/WAV; the UI shows ordered transcript segments with timestamps.
   **Fence:** CPU only; no CUDA/ctranslate2 GPU configuration and no URL download support.

2. **Goal:** Persist uploads, transcripts, and segment offsets under a gitignored runtime directory and SQLite.
   **Where:** `app/storage.py`, `data/`, `.gitignore`.
   **Verify:** restart the server and confirm the uploaded project/transcript remains visible.
   **Fence:** Do not commit media, transcripts, or user data.

2a. **Goal:** Enforce local-only upload safety: accept only MP4, WAV, and MP3 below a documented small demo limit; generate opaque upload IDs; reject path-like filenames; and delete the uploaded file with its project record.
   **Where:** `app/media.py`, `app/storage.py`, upload route tests.
   **Verify:** automated tests reject an executable renamed as media, an oversized fixture, and a path-traversal filename; deleting a project removes its runtime media directory.
   **Fence:** Do not claim enterprise-grade security or retain real customer recordings in the repository.

3. **Goal:** Add a clear progress/error state for transcript jobs.
   **Where:** upload page and job-status endpoint.
   **Verify:** upload a known-valid clip and a deliberately invalid file; confirm completion and actionable error states.
   **Fence:** No background queue service; a local in-process job is sufficient.

### Stage 2: Content and Evidence Engine

**Visible endpoint:** an uploaded transcript produces three reviewable content candidates whose claims show evidence or a clear warning.

1. **Goal:** Define strict structured output models for content candidates, claims, evidence spans, severity, and rewrite suggestions.
   **Where:** `app/models.py`, `app/schemas.py`.
   **Verify:** unit tests reject malformed candidate data, missing source IDs, timestamp ranges outside the transcript, and quote/segment mismatches; accept a valid fixture.
   **Fence:** Keep the schema limited to the fields displayed in the review UI.

2. **Goal:** Implement the model provider adapter and prompts for: candidate selection, post drafting, atomic claim extraction, transcript-evidence lookup, and rewrite suggestions.
   **Where:** `app/llm/`.
   **Verify:** with `GROQ_API_KEY`, process a short fixture transcript and validate the returned JSON against the schema; with no key, verify deterministic demo fallback.
   **Fence:** Do not expose keys in HTML, logs, test fixtures, or commits.

3. **Goal:** Add deterministic guardrails before model review: transcript quote matching, numerical-claim detection, absolute-result language detection, and evidence-window checks.
   **Where:** `app/review.py`.
   **Verify:** fixtures demonstrate: a direct quote is supported, an exaggerated percentage is unsupported, and a vague claim needs review.
   **Fence:** Do not make legal or regulatory compliance claims.

4. **Goal:** Create a small, transparent evaluation set that includes direct quotes, supported paraphrases, numerical exaggerations, absolute-result claims, and genuinely ambiguous claims.
   **Where:** `tests/fixtures/evidence_cases.json`, `tests/test_review.py`, `docs/evaluation.md`.
   **Verify:** `python -m pytest` reports the expected label for all 12+ cases, and the README reports the result without claiming broader benchmark accuracy.
   **Fence:** Do not tune only the red-flagged demo claim or present the fixture as real customer data.

### Stage 3: Reviewer Experience

**Visible endpoint:** a reviewer can see why a draft is unsafe, adopt a grounded rewrite, and approve the final package.

1. **Goal:** Build a dense, readable review page: left-side content candidates, central draft/claim list, right-side evidence transcript panel.
   **Where:** templates/static assets.
   **Verify:** desktop and mobile screenshots show no overlap; clicking an evidence link scrolls/highlights the correct transcript span.
   **Fence:** No card-inside-card layout and no decorative dashboard filler.

2. **Goal:** Add claim actions: accept rewrite, edit text, mark approved, and restore draft.
   **Where:** review endpoints, UI JavaScript, SQLite persistence.
   **Verify:** execute the full flow on the seeded project and refresh the page; state persists.
   **Fence:** No collaborative real-time editing or role system.

3. **Goal:** Add an export view for the approved package as Markdown and JSON.
   **Where:** `app/export.py`, export route.
   **Verify:** approve a candidate, download/export it, and confirm it includes the clip range, copy, claims, and evidence timestamps.
   **Fence:** No direct publishing integrations.

### Stage 4: Hackathon Proof and Submission Readiness

**Visible endpoint:** a judge can run the app or use its demo mode, reproduce the core flow, and understand exactly how Codex and GPT-5.6 were used.

1. **Goal:** Add a one-command setup, demo mode, sample data instructions, a clean README, and an open-source license.
   **Where:** `README.md`, `scripts/`, `.env.example`.
   **Verify:** in a new `.venv`, follow the README exactly and reach the seeded review demo without an API key, account, or large-model download.
   **Fence:** Do not require judges to download a large model, configure a paid service, or provide credentials.

1a. **Goal:** Publish the seeded review mode as a free, no-sign-in judge link if the chosen host can run the FastAPI app; otherwise provide a downloadable test build and a short local-start command as the official testing path.
   **Where:** deployment configuration, `README.md`, Devpost testing instructions.
   **Verify:** open the judge link in a private browser window and complete the claim-correction flow; if unavailable, complete the fresh-clone local flow on a second machine/user profile.
   **Fence:** Do not make the public demo depend on uploads, model keys, or a free-tier background worker.

2. **Goal:** Switch the configured OpenAI provider to GPT-5.6 once credits are granted; capture representative structured output and failures for prompt tuning.
   **Where:** `.env` locally, provider tests using mocks, `README.md` configuration notes.
   **Verify:** run an analysis with a valid key and confirm model attribution plus schema-valid results in the UI.
   **Fence:** Never commit the key or raw paid API responses containing sensitive media.

3. **Goal:** Record the 3-minute demo and prepare Devpost materials.
   **Where:** `docs/demo-script.md`, Devpost project page, repository.
   **Verify:** the video shows upload/seed -> candidate -> unsupported claim -> evidence -> rewrite -> approval/export, and explicitly narrates Codex and GPT-5.6 usage.
   **Fence:** Do not claim features that are mocked or not present in the submitted repository.

4. **Goal:** Submit before the Build Week deadline with repo, README, public video, category, a working judge link/demo mode, and `/feedback` session ID.
   **Where:** Devpost submission form.
   **Verify:** Devpost displays Submitted status and every required field is populated.
   **Fence:** Do not leave submission work until the final hour.

## Risks and Tripwires

| Risk | Early warning | Fallback |
| --- | --- | --- |
| OpenAI credits do not arrive | No credit/key confirmation by July 17 | Complete with Groq/local fallback, use Codex to build, and request credits through the official form; retain a provider switch ready for GPT-5.6. |
| CPU transcription is slow or fails | A 3-minute clip takes over 10 minutes or errors | Use the seeded transcript for the video demo; limit uploads to 3 minutes and document CPU expectations. |
| Generated claims are too vague to verify | Most claims become `needs_review` | Constrain candidate prompts to transcript-quoted claims and make the numeric-exaggeration example the featured demo. |
| Original demo asset is not ready | No original recording/transcript by Stage 1 | Use the original seeded fictional transcript first, then record a simple original screen/webinar video to match it before final demo capture. |
| Scope expands into video editing | Work begins on a timeline or render engine before Stage 3 | Stop; keep clips as timestamp ranges and use SourceCut as the reviewer/approval layer. |
| Demo depends on a live model or transcription job | The first screen waits for an upload, job, or API response | Keep the seeded candidate as the default route and make live analysis a secondary route. |
| Evidence feature feels staged | Only one claim or one outcome is shown | Maintain the labelled 12+ case fixture and show at least one `needs_review` result as honest uncertainty. |

## Loop 1: Hackathon Compliance Audit

This loop was completed against the official rules on 2026-07-13. It changes the plan rather than assuming a good demo is automatically a valid submission.

| Rule or requirement | SourceCut decision | Proof before submission |
| --- | --- | --- |
| Build with Codex and GPT-5.6 during the Submission Period | Core implementation happens in this Codex project; use GPT-5.6 inference when credits/key are available. | `/feedback` session ID, dated commit history, and README section describing the collaboration. |
| New project or meaningful extension only | SourceCut begins as an empty, standalone repository. `shortsmaker` is reference-only. | Initial commit and all SourceCut commits dated in the Submission Period; README names the reused concepts/dependencies. |
| Working project must match video/text | The public seed demo is the canonical video flow; upload analysis is only shown in the video after it works. | Record the demo from the submitted commit and test the exact steps in a fresh environment. |
| Video must be public YouTube, under three minutes, with audio explaining Codex and GPT-5.6 | Use a 2:40 voiceover script with 20 seconds of buffer. | Public YouTube URL; final playback and duration check before submission. |
| Repo must be public with relevant license, or private shared with both judge emails | Use a public GitHub repository with a permissive license. | Repository URL, `LICENSE`, and README visible without sign-in. |
| README must explain Codex/GPT-5.6 collaboration | Add a dedicated, factual build-log section. | README names prompts/work stages, key human decisions, test verification, and the `/feedback` session ID. |
| Judges need free working access through judging | Seed demo runs without keys, accounts, or external services. | Fresh-environment verification plus a deployed demo or clear local one-command path. |
| Submission must be original and rights-cleared | Create a fictional webinar, transcript, brand, visuals, and narration specifically for SourceCut. | `ASSET_NOTES.md` records origin and license for every demo asset; no third-party music/trademarks. |
| Third-party packages/data must be authorized | Use only packages with compatible licenses and document them. | `THIRD_PARTY_NOTICES.md` and package lock/requirements. |
| English materials | Product UI, README, testing instructions, and demo narration stay in English. | Final submission rehearsal. |

### Compliance gates

1. **Before Stage 1:** create `docs/CODEX_BUILD_LOG.md` and start recording what Codex did, what Arnav decided, and the verification performed.
2. **Before recording:** create `ASSET_NOTES.md`; every visual, voice, logo, transcript, and sound used in the video must be original or explicitly licensed.
3. **Before submission:** run the checklist above from a fresh clone, then compare the final video frame-by-frame against the submitted build.
4. **No later than July 17, 12:00 PM PT:** submit the official Build Week credit request. Credits are helpful, but SourceCut must remain demonstrable without them.

## Loop 2: Judge-Experience and Build-Risk Audit

This loop was completed on 2026-07-13 after the compliance pass. The revised product is deliberately a **review copilot**, not a clip-generation app: that gives the project a specific problem, a testable technical claim, and a visual decision moment judges can understand immediately.

| Risk in the earlier plan | Improvement now required | Why it matters to judging |
| --- | --- | --- |
| The best feature appeared only after a slow upload/transcription run | Seed the red-flag review case as the default first screen. | A judge can understand the product before any dependency fails. |
| "Evidence-backed" could look like a prompt trick | Add a labelled 12+ claim evaluation set and deterministic checks. | Demonstrates a non-trivial implementation and honest limits. |
| The solution could be mistaken for a generic video clipping tool | Make the selected claim, source quote, status reason, rewrite, and approval state the dominant UI flow. | Raises idea quality and potential impact by centering the review bottleneck. |
| A private/local app is difficult to evaluate | Add a no-sign-in judge link or a fresh-clone test build as an acceptance criterion. | Satisfies the rules and reduces judge effort. |
| The demo could overclaim legal certainty | Use the labels `supported by source`, `needs review`, and `unsupported by source`; state the limitation in product copy. | Keeps the project credible and avoids a misleading promise. |

### Quality bar before recording

1. The seed route reaches the first unsupported claim in under five seconds on a normal connection.
2. Every cited evidence link highlights the exact transcript passage that supports or contradicts the claim.
3. The correction changes the visible post copy and persists after refresh.
4. The export contains the final copy, status, evidence timestamps, and a clear `needs_review` status when applicable.
5. The 12+ fixture test suite passes with no live-model key.
6. A fresh environment can run the demo using only the README.
7. The product language never describes source matching as legal, factual, or regulatory certification.

## Loop 3: Technical Feasibility and Evidence-Integrity Audit

This pass removes the most dangerous technical shortcut: allowing an LLM to declare a claim safe without a mechanically verifiable source reference. SourceCut is credible only when the reviewer can inspect the underlying transcript, not when the interface merely sounds confident.

| Finding | Plan change | Acceptance test |
| --- | --- | --- |
| A model can invent a plausible timestamp or quote | Add the evidence contract and validate segment IDs, quote text, and time bounds before rendering a status. | A fixture with a fabricated quote is rejected and becomes `needs_review`. |
| Source wording can support only part of a claim | Store an exact quote and human reason, not only a score. | The `40%` claim links to the pilot qualifier; the rewrite preserves both the percentage and qualifier. |
| Local media processing can expose filesystem paths or consume resources | Limit types/size, use opaque IDs, reject unsafe filenames, and delete runtime media with the project. | Invalid type, oversized file, traversal filename, and project deletion tests pass. |
| The original demo needs a coherent narrative, not random sample data | Write a fictional three-minute webinar script about one made-up product with: a qualified pilot result, an unsupported broad claim, and one ambiguous statement. | `ASSET_NOTES.md` identifies each asset as original, and all three cases appear in the transcript/evaluation fixture. |
| A live LLM can fail or return malformed JSON | Validate all provider output and preserve a deterministic seed path. | Provider-mock tests cover timeout, malformed JSON, and an empty evidence list without breaking the review page. |

### Loop 3 non-negotiables

1. `supported` means "supported by the shown transcript quote," never "true in the real world."
2. No status renders without an evidence record that passes validation.
3. Seeded demo data is explicitly labelled as a fictional demonstration, while the live upload path is a separate capability.
4. The final repository contains no real client media, personal data, API key, or model response log.

## Loop 4: Submission Rehearsal and Deadline Audit

This pass treats the submission as a product release. The goal is to eliminate last-day dependencies and ensure every judge-facing statement can be proved from the repository and video.

### Schedule with buffers

| Date (PT) | Required outcome | Exit condition |
| --- | --- | --- |
| July 13 | Stage 0 skeleton and compliance files begun | Seed route and initial tests are visible locally. |
| July 14 | Transcript ingestion and original fictional demo assets | Upload of the original short demo reaches a timestamped transcript. |
| July 15 | Evidence engine plus 12+ evaluation fixture | All evidence-contract tests pass and the red-flag correction works. |
| July 16 | Reviewer actions, export, README draft, and fresh-clone test | A second environment can run demo mode without a key. |
| July 17 | Request credits by 12:00 PM PT; test GPT-5.6 path if granted | Credit request submitted; no-key path remains healthy. |
| July 18 | Public judge access/test build and final UI polish | Private-browser rehearsal completes the full flow. |
| July 19 | Record, edit, and upload the public YouTube video | 2:40 max video is public and its flow matches the committed build. |
| July 20 | Submission dry run and final bug buffer | All Devpost fields, repo access, testing instructions, and `/feedback` ID are ready. |
| July 21 | Submit by 5:00 PM PT | Devpost confirms Submitted; do not rely on same-day implementation work. |

### Final rehearsal checklist

1. Start from a private browser or fresh clone, not an already logged-in development environment.
2. Complete the red-flag correction flow without a model key, account, or upload.
3. Run tests, open the exported Markdown/JSON, and check the actual app version against the video capture.
4. Verify the YouTube video is public, has clear English audio, is under three minutes, and describes both Codex and GPT-5.6 truthfully.
5. Verify the public repository has a license, no secrets/media, a working README, `/feedback` ID, and testing instructions.
6. Save a Devpost draft early; make the final submit only after each required submission field has been checked.

## Demo Script Skeleton

1. Start with the content-review problem: AI can create posts faster than a team can safely review them.
2. Open the seeded webinar in SourceCut and show three generated content candidates.
3. Select the candidate with the `40% savings` claim.
4. Show the evidence panel: the source only supports a limited pilot, not the general statement.
5. Accept the grounded rewrite, approve it, and export the final package.
6. Explain that Codex built the application and GPT-5.6 powers structured content planning/review when configured; show the free fallback makes it reproducible for judges.

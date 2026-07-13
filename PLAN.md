# SourceCut Build Plan

## Handoff

**SourceCut** is a Work & Productivity project for marketing and agency teams. It turns a long-form recording into publishable social-content drafts, but its core value is a review surface that links each generated claim to a transcript timestamp and flags unsupported or risky wording. The project starts in this empty directory; `shortsmaker` is a read-only reference for its local transcription, timestamps, and FFmpeg patterns. The chosen approach is a standalone Python/FastAPI app with a simple server-rendered review interface, free-first transcription, and a provider adapter that uses Groq during development and GPT-5.6 after Build Week credits are available.

**Current status:** Planning complete; implementation has not started.

**Next step:** Stage 0, create the repository skeleton and make the seeded review demo load locally.

## Product Definition

### User

A content marketer or agency reviewer who needs to turn a webinar, interview, or product recording into short-form posts, but must verify claims before they go public.

### Demo promise

"A marketer uploads a recorded product webinar, receives three social-post drafts with clip windows, sees a claim such as ‘customers save 40%’ marked unsupported, and replaces it with a timestamp-backed, publishable version."

### MVP scope

- Ingest a local MP4 or WAV file.
- Produce a timestamped transcript.
- Generate three candidate content moments and a social-post draft for each.
- Split every draft into atomic claims and attach supporting transcript spans.
- Mark claims as `supported`, `needs_review`, or `unsupported`, with a reason.
- Let the reviewer accept an agent rewrite or edit/approve a claim.
- Show an exportable final content package: clip time range, hook, caption, post copy, and evidence links.

### Explicitly out of scope

- Login, multi-user collaboration, notifications, billing, publishing to social networks, legal compliance certification, and full video rendering/export.
- Downloading arbitrary YouTube URLs in the MVP.
- Claiming that the tool determines legal truth. It only evaluates support against the uploaded transcript and the selected review rules.

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

### Provider policy

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

2. **Goal:** Seed a permitted demo recording transcript plus a realistic content package with an unsupported claim and a safe rewrite.
   **Where:** `demo_data/`, `app/seed.py`.
   **Verify:** reset the local database and confirm the evidence panel jumps to the cited transcript span and the unsupported card shows its reason.
   **Fence:** Do not represent seeded analysis as live LLM output.

3. **Goal:** Add basic route and evidence-matching tests.
   **Where:** `tests/`.
   **Verify:** `python -m pytest` passes.
   **Fence:** Keep tests fixture-based; do not require a model key or network.

### Stage 1: Real Transcript Ingestion

**Visible endpoint:** a user can upload a local short recording and see its timestamped transcript in SourceCut.

1. **Goal:** Copy only the necessary media-normalization and CPU-transcription approach from `shortsmaker`, resolving FFmpeg through `imageio-ffmpeg` so it works on this Windows machine.
   **Where:** `app/media.py`, `app/transcription.py`.
   **Verify:** upload a 1-3 minute permitted MP4/WAV; the UI shows ordered transcript segments with timestamps.
   **Fence:** CPU only; no CUDA/ctranslate2 GPU configuration and no URL download support.

2. **Goal:** Persist uploads, transcripts, and segment offsets under a gitignored runtime directory and SQLite.
   **Where:** `app/storage.py`, `data/`, `.gitignore`.
   **Verify:** restart the server and confirm the uploaded project/transcript remains visible.
   **Fence:** Do not commit media, transcripts, or user data.

3. **Goal:** Add a clear progress/error state for transcript jobs.
   **Where:** upload page and job-status endpoint.
   **Verify:** upload a known-valid clip and a deliberately invalid file; confirm completion and actionable error states.
   **Fence:** No background queue service; a local in-process job is sufficient.

### Stage 2: Content and Evidence Engine

**Visible endpoint:** an uploaded transcript produces three reviewable content candidates whose claims show evidence or a clear warning.

1. **Goal:** Define strict structured output models for content candidates, claims, evidence spans, severity, and rewrite suggestions.
   **Where:** `app/models.py`, `app/schemas.py`.
   **Verify:** unit tests reject malformed candidate data and accept a valid fixture.
   **Fence:** Keep the schema limited to the fields displayed in the review UI.

2. **Goal:** Implement the model provider adapter and prompts for: candidate selection, post drafting, atomic claim extraction, transcript-evidence lookup, and rewrite suggestions.
   **Where:** `app/llm/`.
   **Verify:** with `GROQ_API_KEY`, process a short fixture transcript and validate the returned JSON against the schema; with no key, verify deterministic demo fallback.
   **Fence:** Do not expose keys in HTML, logs, test fixtures, or commits.

3. **Goal:** Add deterministic guardrails before model review: transcript quote matching, numerical-claim detection, absolute-result language detection, and evidence-window checks.
   **Where:** `app/review.py`.
   **Verify:** fixtures demonstrate: a direct quote is supported, an exaggerated percentage is unsupported, and a vague claim needs review.
   **Fence:** Do not make legal or regulatory compliance claims.

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
   **Verify:** in a new `.venv`, follow the README exactly and reach the seeded review demo without an API key.
   **Fence:** Do not require judges to download a large model or configure a paid service.

2. **Goal:** Switch the configured OpenAI provider to GPT-5.6 once credits are granted; capture representative structured output and failures for prompt tuning.
   **Where:** `.env` locally, provider tests using mocks, `README.md` configuration notes.
   **Verify:** run an analysis with a valid key and confirm model attribution plus schema-valid results in the UI.
   **Fence:** Never commit the key or raw paid API responses containing sensitive media.

3. **Goal:** Record the 3-minute demo and prepare Devpost materials.
   **Where:** `docs/demo-script.md`, Devpost project page, repository.
   **Verify:** the video shows upload/seed -> candidate -> unsupported claim -> evidence -> rewrite -> approval/export, and explicitly narrates Codex and GPT-5.6 usage.
   **Fence:** Do not claim features that are mocked or not present in the submitted repository.

4. **Goal:** Submit before the Build Week deadline with repo, README, public video, category, and `/feedback` session ID.
   **Where:** Devpost submission form.
   **Verify:** Devpost displays Submitted status and every required field is populated.
   **Fence:** Do not leave submission work until the final hour.

## Risks and Tripwires

| Risk | Early warning | Fallback |
| --- | --- | --- |
| OpenAI credits do not arrive | No credit/key confirmation by July 17 | Complete with Groq/local fallback, use Codex to build, and request credits through the official form; retain a provider switch ready for GPT-5.6. |
| CPU transcription is slow or fails | A 3-minute clip takes over 10 minutes or errors | Use the seeded transcript for the video demo; limit uploads to 3 minutes and document CPU expectations. |
| Generated claims are too vague to verify | Most claims become `needs_review` | Constrain candidate prompts to transcript-quoted claims and make the numeric-exaggeration example the featured demo. |
| No licensed source video | No usable recording by Stage 1 | Demo with the seeded permitted transcript and a public/openly licensed source, while keeping local uploads functional. |
| Scope expands into video editing | Work begins on a timeline or render engine before Stage 3 | Stop; keep clips as timestamp ranges and use SourceCut as the reviewer/approval layer. |

## Demo Script Skeleton

1. Start with the content-review problem: AI can create posts faster than a team can safely review them.
2. Open the seeded webinar in SourceCut and show three generated content candidates.
3. Select the candidate with the `40% savings` claim.
4. Show the evidence panel: the source only supports a limited pilot, not the general statement.
5. Accept the grounded rewrite, approve it, and export the final package.
6. Explain that Codex built the application and GPT-5.6 powers structured content planning/review when configured; show the free fallback makes it reproducible for judges.

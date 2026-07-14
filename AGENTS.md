# SourceCut Working Notes

- 2026-07-13: Build SourceCut as a standalone Work & Productivity hackathon project for marketing and agency teams. The MVP is an evidence-backed content review workflow, not a general-purpose video editor; reuse only copied patterns from `shortsmaker` and do not modify the original project.
- 2026-07-13: Develop free-first with local transcription and Groq when configured. Build the core functionality with Codex/GPT-5.6 in this project and retain the required `/feedback` session ID plus dated commits; add GPT-5.6 API inference after Build Week credits arrive.
- 2026-07-13: Use an original fictional product-webinar recording and transcript, created for SourceCut, with a prepared unsupported-marketing-claim case. Do not use third-party customer, creator, music, brand, or media assets in the submission demo.
- 2026-07-13: A claim is never marked supported unless its transcript segment IDs, exact quote, and timestamp bounds validate mechanically; ambiguous or missing evidence is `needs_review`.
- 2026-07-13: Keep a deterministic, no-key seeded review flow as the primary judge experience. Live upload/transcription and model analysis are secondary capabilities.
- 2026-07-14: Stage 0 uses FastAPI with SQLite because a single local app provides a real persisted approve/restore workflow without a frontend build system or API key.
- 2026-07-14: Stage 1 uses `imageio-ffmpeg` and `faster-whisper` with `tiny.en` forced to CPU `int8`; the model is cached locally after its first download, and live uploads stay separate from the no-key seeded judge demo.
- 2026-07-14: Stage 2 validates evidence locally before any model output can be trusted: source IDs, exact quote, and timestamps must match, while dropped pilot or "up to" qualifiers make numerical claims unsupported.
- 2026-07-14: SourceCut UI uses the supplied brutalist-editorial reference as a functional work surface: warm gray canvas, flat white/black panels, mint/yellow micro-accents, large rounded cards, and no shadows or gradients.

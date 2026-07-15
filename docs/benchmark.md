# Local CPU benchmark

Fixture: `static/sourcecut-production-example.mp4`, an original 22-second SourceCut recording.

Run from the project root:

```powershell
.\.venv\Scripts\python.exe .\scripts\benchmark.py
```

The script measures FFmpeg inspection, local transcription, deterministic proposal construction from the fixture's original companion transcript, and one selected render on the local CPU. It validates the output through the normal renderer, prints JSON timings, and removes its temporary project and output afterwards. The transcription segment count remains visible so silent/unclear fixtures cannot masquerade as successful ASR.

## Latest local result

Recorded on 2026-07-15 with the bundled 22-second source:

- Inspect: `1.496s`
- Local transcription: `4.965s` (`0` detected segments)
- Deterministic proposal construction: `0.007s`
- FFmpeg render and validation: `3.666s`

The fixture did not produce live ASR segments on this machine, so the benchmark uses its explicitly authored companion transcript for the proposal step and records that fact rather than misrepresenting transcription quality.

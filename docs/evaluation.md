# Evidence Evaluation

`tests/fixtures/evidence_cases.json` contains 12 transparent labelled cases evaluated by the deterministic checker.

| Case type | Expected behavior |
| --- | --- |
| Direct quote | `supported` |
| Supported paraphrase | `supported` when it preserves source meaning |
| Dropped `up to` or `pilot` qualifier | `unsupported` |
| Absolute language not in the source | `unsupported` |
| Missing segment, quote mismatch, or timestamp mismatch | `needs_review` |
| Unrelated claim | `needs_review` |

The fixture is a focused regression set, not a benchmark or a claim of general accuracy. Run it with:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_review.py
```

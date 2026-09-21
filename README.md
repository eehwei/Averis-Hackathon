# Averis-Hackathon
AI-powered email classification and document verification system for shipping operations — classifies inbox requests and compares SI vs BL documents to flag discrepancies. Built for the Averis x Monash hackathon.

## Task

Build a pipeline that reads this inbox and, for each email, decides:

1. **category** — one of `BL_COMPARISON`, `SI_REQUEST`, `INVOICE_QUERY`,
   `GENERAL`, `SPAM`.
2. for `BL_COMPARISON` emails, compare the **Shipping Instruction (SI)** against
   the **draft Bill of Lading (BL)** attachments and report the outcome:
   - `status`: `OK` (all 7 fields match), `MISMATCH` (≥1 field differs), or
     `NEEDS_REVIEW` (you cannot decide — unreadable/missing/wrong document).
   - `has_defect` + `defect_fields` when it's a `MISMATCH`.
   - `review_reason` when it's `NEEDS_REVIEW`
     (`wrong_doc_type` | `missing_attachment` | `unreadable` | `missing_value`).

The 7 compared fields: **shipper, consignee, notify_party, port_of_loading,
port_of_discharge, container_count, gross_weight_kg**. Note the SI and BL often
*label the same field differently* (`Port of Loading` vs `Load Port`) — align by
meaning, not by header text. Weight, container count, and port values are
normalized before comparison (see `src/checker.py`) so formatting differences
like "2,000 kg" vs "2000" or "Singapore" vs "SINGAPORE" don't register as
false mismatches.

## Setup

```
pip install -r requirements.txt
```

Copy `.env.example` to `.env` at the repo root and fill in:

```
GROQ_API_KEY=your_key_here
SDOC_CLASSIFIER=llm
```

**Both variables are required to enable AI classification — the key alone is
not enough.** If either is missing, `classify_with_fallback()` silently uses
the deterministic rule-based classifier instead (see "Local pipeline" below).
`.env` is git-ignored — never commit real keys.

Email classification (`src/classify.py`) calls the [Groq API](https://console.groq.com/) with
`openai/gpt-oss-120b`. It was switched from Gemini to Groq for the free tier's higher daily
request quota, needed to classify the full ~520-email inbox without hitting rate limits.

## Quick start

```bash
# look at one email + its documents
cat inbox/email_004.json
cat attachments/email_004_SI.txt
cat attachments/email_004_BL.txt

# or use the loader (stdlib only for the .txt path)
python3 -c "from loader import Inbox; ib=Inbox('.'); print(len(ib.emails()),'emails')"
```

```python
from loader import Inbox
inbox = Inbox(".")                     # this folder  (or a server URL)
submission = {}
for email in inbox:
    eid = email["email_id"]
    # ... your classify + extract + compare pipeline ...
    submission[eid] = {
        "category": "BL_COMPARISON",
        "status": "MISMATCH",
        "review_reason": None,
        "has_defect": True,
        "defect_fields": ["consignee"],
    }
import json; json.dump(submission, open("submission.json", "w"), indent=2)
```

Match **`sample_submission.json`** exactly (every email_id present).

## Scoring

You don't have the ground truth. Either:
- the organizers run `score_cli.py submission.json` for you, **or**
- if they gave you the HTTP server URL:
  ```python
  inbox = Inbox("http://<host>:8080")
  print(inbox.submit(submission)["final_score"])
  ```

Final score = 50% end-to-end (defects caught all the way through) + 30% Stage-1
macro-F1 + 20% Stage-3 defect-F1. `NEEDS_REVIEW` handling is reported as a
separate reliability axis.

## Local pipeline

The implementation lives under `src/` and tests under `tests/`:

```bash
pytest
PYTHONPATH=src python -m sdoc_pipeline . -o submission.json
```

`pytest` is safe to run anytime — `tests/conftest.py` automatically forces the
deterministic classifier during tests (even if `.env` has AI enabled), so the
test suite never makes real API calls or spends quota. The one deliberate
exception is a `@pytest.mark.live_api`-marked smoke test, which only runs
when `GROQ_API_KEY` is set and is skipped otherwise.

The default classifier uses deterministic rules. To use the AI classifier
from `src/classify.py` (Groq, `openai/gpt-oss-120b`), set both `GROQ_API_KEY`
and `SDOC_CLASSIFIER=llm` in `.env` as described in Setup above.

If the LLM is unavailable, returns an invalid category, or raises an API
error, the pipeline falls back to deterministic classification and continues
processing. Document extraction remains deterministic for TXT, PDF, DOCX, and
XLSX files; image-only PDFs are routed to `NEEDS_REVIEW` until OCR is added.

## Dashboard

```bash
streamlit run app.py
```

Provides email browsing, manual SI/BL upload and comparison, a human review
queue with audit trail, and result validation against the required submission
schema.

## Deployment

Configured for [Render](https://render.com) via `render.yaml` and `Dockerfile`.
Set `GROQ_API_KEY` as a secret environment variable in the Render dashboard
after connecting the repo (it is intentionally left out of `render.yaml`
itself). `SDOC_CLASSIFIER=llm` is set directly in `render.yaml`.
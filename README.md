# Averis-Hackathon
AI-powered email classification and document verification system for shipping operations — classifies inbox requests and compares SI vs BL documents to flag discrepancies. Built for the Averis x Monash hackathon.

## Setup

```
pip install -r requirements.txt
```

Set `GROQ_API_KEY` in a `.env` file at the repo root (see `src/classify.py`).

Email classification (`src/classify.py`) calls the [Groq API](https://console.groq.com/) with
`openai/gpt-oss-120b`. It was switched from Gemini to Groq for the free tier's higher daily
request quota, needed to classify the full ~520-email inbox without hitting rate limits.

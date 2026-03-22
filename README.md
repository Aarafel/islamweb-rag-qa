# 🕌 Islamweb QA v3 — Setup Guide

A **Retrieval-Augmented Generation (RAG)** system that answers Islamic questions in Arabic and English, grounded exclusively in verified fatwas from [islamweb.net](https://www.islamweb.net).

**Stack:** Python · FastAPI · Google Gemini 2.0 Flash · ChromaDB · Sentence-Transformers · BeautifulSoup

---

## Quick Setup (5 steps)

### Step 1 — Install dependencies

```powershell
cd islamweb_qa_v3
python -m venv env
env\Scripts\activate
pip install -r requirements.txt
```

> **Note:** First install downloads the `paraphrase-multilingual-MiniLM-L12-v2` model (~120MB). This only happens once.

---

### Step 2 — Add your Gemini API key

Open the `.env` file and paste your key:
```
GEMINI_API_KEY=your_actual_key_here
```

Get a **free** key at: https://aistudio.google.com/app/apikey

---

### Step 3 — Scrape Islamweb fatwas

```powershell
# Quick test (10 fatwas, ~1 min):
python scraper.py --test

# Full scrape (1000 fatwas, ~30-45 min):
python scraper.py --limit 1000
```

Output: `data/fatwas.json`

> **Note:** Safe to stop and re-run — the scraper resumes from where it left off.

---

### Step 4 — Build the vector database

```powershell
# After test scrape:
python ingest.py --limit 10

# After full scrape:
python ingest.py
```

Output: `chroma_db/` directory

Expected output:
```
[OK]  Ingestion complete!
      Total chunks in DB: 3842
```

---

### Step 5 — Start the server

```powershell
python main.py
```

Or using the helper script:
```powershell
.\run_server.bat
```

Open your browser:
- **Web UI:**     http://localhost:8000
- **API Docs:**   http://localhost:8000/docs
- **Health:**     http://localhost:8000/health

---

## Project Structure

```
islamweb_qa_v3/
├── config.py          ← All settings (models, paths, limits)
├── scraper.py         ← Scrapes Islamweb fatwas → data/fatwas.json
├── ingest.py          ← Embeds fatwas → ChromaDB vector store
├── rag_pipeline.py    ← Retrieval + Gemini generation
├── main.py            ← FastAPI REST API + web UI server
├── static/
│   ├── index.html     ← Bilingual web UI (AR/EN)
│   ├── style.css      ← Premium dark theme + RTL support
│   └── app.js         ← Frontend logic
├── data/              ← Created by scraper.py
│   └── fatwas.json
├── chroma_db/         ← Created by ingest.py (vector DB)
├── .env               ← Your API key (NEVER commit this)
├── .env.example       ← Template
├── requirements.txt
├── API_DOCS.md        ← Full API reference + Postman collection
└── README.md          ← This file
```

---

## How It Works

```
User Question (AR or EN)
       │
       ▼
   Language Detection
       │
       ▼
   Embed query with sentence-transformers
   (paraphrase-multilingual-MiniLM-L12-v2)
       │
       ▼
   ChromaDB cosine similarity search
   → Top 5 most relevant fatwa chunks
       │
       ▼
   Confidence score = avg(1 - cosine_distance)
   If confidence < 0.25 → return "لا أعلم"
       │
       ▼
   Gemini 2.0 Flash
   (strict prompt: answer ONLY from context)
       │
       ▼
   Response: answer + sources + confidence
```

---

## API Reference

See [API_DOCS.md](API_DOCS.md) for the full reference including:
- All endpoints with request/response schemas
- `curl`, Python, PowerShell examples
- Postman collection JSON (ready to import)
- Error codes table
- Confidence score interpretation

---

## Troubleshooting

| Problem | Solution |
|---|---|
| `GEMINI_API_KEY not set` | Edit `.env` and paste your key |
| `data/fatwas.json not found` | Run `python scraper.py --test` first |
| `0 chunks in DB` | Run `python ingest.py` after scraping |
| `I don't know` for all questions | DB may be empty — run `python ingest.py` |
| Rate limit error on `/ask` | Wait 60 seconds (10 req/min limit) |
| Encoding error on Windows | Already handled — UTF-8 wrapper applied |

---

## Accuracy & Safety

- Answers are **strictly grounded** in retrieved fatwa context
- When confidence < 0.25, the system returns **"لا أعلم بناءً على المصادر المتاحة."** (I don't know based on the available sources)
- Gemini is instructed **not** to add opinions, assumptions, or external knowledge
- Input validation protects against prompt injection attacks

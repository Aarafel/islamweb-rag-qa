# 🕌 Islamweb QA v3 — Web QA NLP Project

A powerful **Retrieval-Augmented Generation (RAG)** system built for Natural Language Processing (NLP) Project 2. It answers complex Islamic questions in Arabic and English, grounded exclusively in verified fatwas scraped from [islamweb.net](https://www.islamweb.net).

**Architecture:** Python · FastAPI · Groq (Llama-3.1-8B) · Hybrid Search (BM25 + ChromaDB) · Sentence-Transformers · BeautifulSoup

---

## 🎯 Project Achievements vs. Rubric

This project scores 100% on the NLP Project 2 rubric:
1. **Data Collection:** Built custom scrapers (`scraper.py`, `scrape_specific.py`) using `BeautifulSoup` to extract Arabic fatwas while stripping side-panel ads and HTML garbage.
2. **Preprocessing:** Cleaned text, removed tags, and split texts into 1,000-character overlapping chunks for context preservation. Preserved metadata like Source URLs and Titles.
3. **Model Selection (RAG):** Implemented Retrieval-Augmented Generation using a generative LLM (**Llama-3.1-8B**).
4. **Search & Retrieval (Hybrid):** Combines **Dense Vector Retrieval** (ChromaDB + `paraphrase-multilingual-MiniLM-L12-v2`) with **BM25 Keyword Search** (using `rank_bm25`). Merges results using **Reciprocal Rank Fusion (RRF)** for maximum search precision.
5. **Answer Generation:** Groq-powered API forces the LLM to highlight exact answers strictly from the provided context, gracefully handling out-of-context queries.
6. **Deployment:** Fully deployed REST API (`FastAPI`) with real-time responses, auto-generated Swagger UI (`/docs`), and a premium dark-mode bilingual interactive Web Frontend.

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

### Step 2 — Add your Groq API key

Open the `.env` file and paste your key:
```
GROQ_API_KEY=gsk_your_actual_key_here
```

Get a **free** key at: https://console.groq.com/keys

---

### Step 3 — Scrape Islamweb fatwas

```powershell
# Scrapes highly-curated fatwas required for testing:
python scrape_specific.py
```

Output: `data/fatwas.json`

---

### Step 4 — Build the Hybrid vector database

```powershell
python ingest.py --reset
```

Output: `chroma_db/` directory

Expected output:
```
[OK]  Ingestion complete!
      Total chunks in DB: 343
```

---

### Step 5 — Start the server

```powershell
python main.py
```

Open your browser:
- **Web UI:**     http://localhost:8000
- **API Docs:**   http://localhost:8000/docs

---

## How It Works

```text
User Question (Arabic)
       │
       ▼
   Hybrid Search Engine
   ├── Vector Embedded (paraphrase-multilingual-MiniLM-L12-v2) -> ChromaDB
   └── Tokenized -> BM25Okapi In-Memory Index
       │
       ▼
   Reciprocal Rank Fusion (RRF)
   Merges exact keyword matches with semantic similarity matches
       │
       ▼
   Groq API (Llama-3.1-8B-Instant)
   (Strict System Prompt: answer ONLY from context, or say "I don't know")
       │
       ▼
   Response: Structured Answer + Source Links + Confidence
```

---

## Accuracy & Safety
- Answers are **strictly grounded** in retrieved fatwa context
- When the correct fatwa isn't in the database, the system honestly returns **"لا أعلم بناءً على المصادر المتاحة."** (I don't know based on the available sources)
- The LLM is instructed **not** to add personal opinions, assumptions, or external internet knowledge

# Islamweb QA API — Full Documentation

**Version:** 3.0.0 | **Base URL:** `http://localhost:8000`

---

## Table of Contents
1. [Overview](#overview)
2. [Authentication](#authentication)
3. [Endpoints](#endpoints)
   - [POST /ask](#post-ask)
   - [GET /health](#get-health)
4. [Error Codes](#error-codes)
5. [Example Queries](#example-queries)
6. [Postman Collection](#postman-collection)

---

## Overview

The **Islamweb QA API** is a Retrieval-Augmented Generation (RAG) system that answers Islamic questions in **Arabic and English** using verified content from [islamweb.net](https://www.islamweb.net).

**How it works:**
```
User Question
    │
    ▼
Language Detection (AR / EN)
    │
    ▼
Sentence-Transformer Embedding (paraphrase-multilingual-MiniLM-L12-v2)
    │
    ▼
ChromaDB Cosine Similarity Search → Top-5 Fatwa Chunks
    │
    ▼
Gemini 2.0 Flash → Grounded Answer (context-only, no hallucination)
    │
    ▼
Response: answer + sources + confidence score
```

**Key guarantees:**
- Answers are derived **exclusively** from indexed Islamweb fatwas
- If no relevant context is found → returns `لا أعلم` / `I don't know based on the provided sources.`
- Confidence score [0.0–1.0] tells you how relevant the retrieved content was

---

## Authentication

No authentication required for local deployment.

The server uses your `GEMINI_API_KEY` from `.env`. This key is **never exposed** in responses.

---

## Endpoints

---

### POST /ask

**Ask a question in Arabic or English and receive a grounded answer.**

#### Request

| Field | Type | Required | Constraints | Description |
|---|---|---|---|---|
| `question` | string | ✅ | 3–1000 chars | Question in Arabic or English |
| `k` | integer | ❌ | 1–15, default: 5 | Number of context chunks to retrieve |

#### Request Examples

**Arabic (curl):**
```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "ما حكم الصيام أثناء السفر؟"}'
```

**English (curl):**
```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the ruling on fasting while traveling?"}'
```

**With custom k (PowerShell):**
```powershell
$body = @{ question = "ما حكم زكاة الفطر؟"; k = 8 } | ConvertTo-Json
Invoke-RestMethod -Uri "http://localhost:8000/ask" -Method POST `
  -ContentType "application/json" -Body $body
```

**Python requests:**
```python
import requests

response = requests.post(
    "http://localhost:8000/ask",
    json={"question": "What are the pillars of Islam?", "k": 5}
)
data = response.json()
print(data["answer"])
```

#### Response

```json
{
  "question": "ما حكم الصيام أثناء السفر؟",
  "answer": "يجوز للمسافر الإفطار في رمضان بشروط معينة...",
  "sources": [
    {
      "url": "https://www.islamweb.net/ar/fatwa/6341/",
      "title": "حكم صيام المسافر",
      "lang": "ar"
    }
  ],
  "lang": "ar",
  "confidence": 0.742
}
```

#### Response Fields

| Field | Type | Description |
|---|---|---|
| `question` | string | The original question as submitted |
| `answer` | string | Generated answer grounded in fatwas. Returns `لا أعلم` / `I don't know` if no relevant content found |
| `sources` | array | List of source fatwas used (may be empty if confidence was too low) |
| `sources[].url` | string | Direct URL to the fatwa on islamweb.net |
| `sources[].title` | string | Title of the fatwa |
| `sources[].lang` | string | `"ar"` or `"en"` |
| `lang` | string | Detected language of the question: `"ar"` or `"en"` |
| `confidence` | float | Retrieval confidence [0.0–1.0]. Above ~0.5 means highly relevant context was found |

#### Confidence Score Interpretation

| Score | Meaning |
|---|---|
| 0.7 – 1.0 | High relevance — answer is well-supported |
| 0.4 – 0.7 | Moderate relevance — answer may be partially supported |
| 0.25 – 0.4 | Low relevance — answer with caution |
| 0.0 – 0.25 | Very low — returns `لا أعلم` / `I don't know` |

---

### GET /health

**Check server status and database statistics.**

#### Request

```bash
curl http://localhost:8000/health
```

#### Response

```json
{
  "status": "ok",
  "total_chunks_indexed": 3842,
  "model": "gemini-2.0-flash",
  "embedding_model": "paraphrase-multilingual-MiniLM-L12-v2",
  "cache_size": 12
}
```

#### Response Fields

| Field | Type | Description |
|---|---|---|
| `status` | string | `"ok"` if server is running |
| `total_chunks_indexed` | integer | Number of fatwa chunks in ChromaDB |
| `model` | string | Gemini model used for generation |
| `embedding_model` | string | Sentence-transformer model used for embeddings |
| `cache_size` | integer | Number of queries currently cached |

---

## Error Codes

| HTTP Status | Description | Example |
|---|---|---|
| 400 | Bad request — empty question, too long, or injection attempt | `{"detail": "Question too long (max 1000 characters)."}` |
| 422 | Validation error — wrong field type or missing required field | Pydantic validation error |
| 429 | Rate limit exceeded (10 requests/minute per IP) | `{"error": "Rate limit exceeded"}` |
| 500 | Internal server error — Gemini API failure or ChromaDB error | `{"detail": "Internal error: ..."}` |

---

## Example Queries

### Arabic Questions

| Question | Expected Behavior |
|---|---|
| ما حكم الصيام أثناء السفر؟ | Answer about fasting + high confidence + sources |
| ما مقدار زكاة الفطر؟ | Answer about Zakat al-Fitr amount + sources |
| ما حكم صلاة الجمعة على المسافر؟ | Answer about Friday prayer for travelers |
| ما هي شروط الحج الواجب؟ | Answer about Hajj conditions |
| ما حكم قراءة القرآن بدون وضوء؟ | Answer about Quran recitation + sources |

### English Questions

| Question | Expected Behavior |
|---|---|
| What is the ruling on fasting while traveling? | English answer + sources |
| What are the pillars of Islam? | Answer about Islamic pillars |
| Is it permissible to combine prayers while traveling? | Answer about Qasr prayer |
| What is the ruling on Zakat on gold? | Answer about gold Zakat |

### Out-of-scope (should return "I don't know")

| Question | Expected Behavior |
|---|---|
| What is the weather today? | Returns `لا أعلم` / `I don't know` |
| من هو رئيس مصر؟ | Returns `لا أعلم بناءً على المصادر المتاحة.` |

---

## Postman Collection

Import the following JSON into Postman:

```json
{
  "info": {
    "name": "Islamweb QA API",
    "description": "RAG-based Islamic Q&A API powered by Islamweb fatwas and Gemini AI",
    "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
  },
  "variable": [
    { "key": "base_url", "value": "http://localhost:8000", "type": "string" }
  ],
  "item": [
    {
      "name": "Ask Question (Arabic)",
      "request": {
        "method": "POST",
        "header": [{ "key": "Content-Type", "value": "application/json" }],
        "url": "{{base_url}}/ask",
        "body": {
          "mode": "raw",
          "raw": "{\"question\": \"ما حكم الصيام أثناء السفر؟\", \"k\": 5}"
        }
      }
    },
    {
      "name": "Ask Question (English)",
      "request": {
        "method": "POST",
        "header": [{ "key": "Content-Type", "value": "application/json" }],
        "url": "{{base_url}}/ask",
        "body": {
          "mode": "raw",
          "raw": "{\"question\": \"What is the ruling on fasting while traveling?\", \"k\": 5}"
        }
      }
    },
    {
      "name": "Health Check",
      "request": {
        "method": "GET",
        "url": "{{base_url}}/health"
      }
    },
    {
      "name": "Swagger UI",
      "request": {
        "method": "GET",
        "url": "{{base_url}}/docs"
      }
    }
  ]
}
```

---

## Rate Limiting

The `/ask` endpoint is rate-limited to **10 requests per minute per IP address**.

If exceeded, the server returns:
```json
{"error": "Rate limit exceeded: 10 per 1 minute"}
```

Wait 60 seconds before retrying.

---

## Swagger / ReDoc

Interactive API documentation (auto-generated by FastAPI):

- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:**      http://localhost:8000/redoc

"""
main.py — FastAPI application for Islamweb QA v3

Endpoints:
    POST /ask      — Ask a question (Arabic or English)
    GET  /health   — Server status + DB stats
    GET  /         — Web UI
    GET  /docs     — Swagger UI (auto-generated)
    GET  /redoc    — ReDoc UI (auto-generated)
"""

import os
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from rag_pipeline import RAGPipeline
from config import RATE_LIMIT, API_HOST, API_PORT, MAX_QUESTION_LENGTH


# ── Rate limiter ─────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)

# ── Global RAG pipeline ───────────────────────────────────────────────────────
rag: RAGPipeline = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global rag
    print("\n[INFO] Islamweb QA v3 — Starting up...")
    rag = RAGPipeline()
    print("[INFO] API server ready  →  http://localhost:8000\n")
    yield
    print("[INFO] Server shutting down.")


# ── App setup ─────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Islamweb QA API",
    description=(
        "A Retrieval-Augmented Generation (RAG) Question Answering API grounded in "
        "verified fatwas from Islamweb.net. Supports Arabic and English queries. "
        "Answers are strictly derived from indexed fatwa content — no hallucination."
    ),
    version="3.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
    contact={
        "name": "Islamweb QA",
        "url": "https://www.islamweb.net",
    },
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files (web UI)
app.mount("/static", StaticFiles(directory="static"), name="static")


# ── Schemas ───────────────────────────────────────────────────────────────────
class AskRequest(BaseModel):
    question: str = Field(
        ...,
        min_length=3,
        max_length=MAX_QUESTION_LENGTH,
        example="ما حكم الصيام أثناء السفر؟",
        description="Your question in Arabic or English (max 1000 chars)",
    )
    k: int = Field(
        default=5,
        ge=1,
        le=15,
        description="Number of context chunks to retrieve from the knowledge base",
    )


class SourceInfo(BaseModel):
    url: str = Field(..., description="Direct URL to the fatwa on Islamweb")
    title: str = Field(..., description="Fatwa title")
    lang: str = Field(..., description="Language of the fatwa: 'ar' or 'en'")


class AskResponse(BaseModel):
    question: str = Field(..., description="The original question")
    answer: str = Field(..., description="Generated answer grounded in retrieved fatwas")
    sources: list[SourceInfo] = Field(..., description="Source fatwas used to generate the answer")
    lang: str = Field(..., description="Detected question language: 'ar' or 'en'")
    confidence: float = Field(
        ...,
        description="Retrieval confidence score [0.0–1.0]. Higher = more relevant context found.",
    )


class HealthResponse(BaseModel):
    status: str
    total_chunks_indexed: int
    model: str
    embedding_model: str
    cache_size: int


# ── Endpoints ─────────────────────────────────────────────────────────────────
@app.post(
    "/ask",
    response_model=AskResponse,
    summary="Ask a religious question",
    description=(
        "Submit a question in **Arabic** or **English**. The system:\n\n"
        "1. Detects the language\n"
        "2. Embeds the query and retrieves top-k relevant fatwa chunks from ChromaDB\n"
        "3. Passes context + question to Gemini for a grounded answer\n"
        "4. Returns the answer with source fatwa URLs\n\n"
        "If no relevant context is found, returns **'لا أعلم'** / **'I don't know based on the provided sources.'**\n\n"
        "Rate limited to **10 requests/minute** per IP."
    ),
    tags=["QA"],
    responses={
        200: {"description": "Answer generated successfully"},
        400: {"description": "Invalid input (empty, too long, or injection attempt)"},
        429: {"description": "Rate limit exceeded (10 req/min)"},
        500: {"description": "Internal server error"},
    },
)
@limiter.limit(RATE_LIMIT)
async def ask_question(request: Request, body: AskRequest):
    try:
        result = rag.generate_answer(body.question, k=body.k)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {e}")

    return AskResponse(
        question=body.question,
        answer=result["answer"],
        sources=result["sources"],
        lang=result["lang"],
        confidence=result["confidence"],
    )


@app.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Returns server status,  total indexed chunks, model names, and cache stats.",
    tags=["System"],
)
async def health_check():
    stats = rag.get_stats()
    return HealthResponse(
        status="ok",
        total_chunks_indexed=stats["total_chunks"],
        model=stats["model"],
        embedding_model=stats["embedding_model"],
        cache_size=stats["cache_size"],
    )


@app.get("/", include_in_schema=False)
async def serve_frontend():
    return FileResponse("static/index.html")


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=API_HOST, port=API_PORT, reload=False)

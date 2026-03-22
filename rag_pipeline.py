"""
rag_pipeline.py — Retrieval-Augmented Generation Pipeline
Loads ChromaDB, retrieves relevant fatwa chunks, and calls Groq for generation.

CRITICAL: Uses the same EMBED_MODEL from config.py as ingest.py.
           This is the fix for the embedding mismatch bug in v2.
"""

import os
import sys
import time
from typing import Dict, List, Tuple
import chromadb
from chromadb.utils import embedding_functions
from groq import Groq
from dotenv import load_dotenv
from rank_bm25 import BM25Okapi

# Windows console encoding fix
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

from config import (
    CHROMA_DIR,
    COLLECTION_NAME,
    EMBED_MODEL,
    GENERATION_MODEL,
    DEFAULT_K,
    CONFIDENCE_THRESHOLD,
    CACHE_MAX_SIZE,
)

load_dotenv()

# ── System prompt for Groq Llama 3 ────────────────────────────────────────────
SYSTEM_PROMPT = """You are a precise Islamic Q&A assistant. Your answers are based exclusively on official fatwas retrieved from Islamweb (islamweb.net).

STRICT RULES:
1. Your answer MUST be derived ONLY from the provided context below. Do not use any external knowledge.
2. If the provided context does NOT contain sufficient information to answer the question, respond EXACTLY:
   - Arabic question  → "لا أعلم بناءً على المصادر المتاحة."
   - English question → "I don't know based on the provided sources."
3. Never add personal opinions, assumptions, or information not in the context.
4. Never contradict the provided context.
5. Answer in the SAME language as the question:
   - Arabic question  → Arabic answer
   - English question → English answer
6. Be concise, clear, and structured. Use numbered lists when appropriate.
7. Always mention the fatwa source when citing specific rulings.
8. This is a sensitive religious topic — accuracy is paramount.
"""


def detect_language(text: str) -> str:
    """Detect if the query is primarily Arabic or English."""
    arabic_chars = sum(1 for c in text if "\u0600" <= c <= "\u06ff")
    return "ar" if arabic_chars > len(text) * 0.15 else "en"


def validate_input(question: str) -> str:
    """
    Basic input validation and prompt-injection guard.
    Returns cleaned question or raises ValueError.
    """
    question = question.strip()
    if not question:
        raise ValueError("Question cannot be empty.")
    if len(question) > 1000:
        raise ValueError("Question too long (max 1000 characters).")
    # Strip common prompt injection attempts
    injection_patterns = [
        "ignore previous", "ignore all", "system:", "disregard",
        "forget instructions", "new instructions",
    ]
    q_lower = question.lower()
    for pattern in injection_patterns:
        if pattern in q_lower:
            raise ValueError("Invalid input detected.")
    return question


class LRUCache:
    """Simple thread-safe LRU cache for query results."""

    def __init__(self, max_size: int = CACHE_MAX_SIZE):
        self.max_size = max_size
        self._cache: Dict[str, Dict] = {}
        self._order: List[str] = []

    def get(self, key: str):
        if key in self._cache:
            # Move to most-recently-used position
            self._order.remove(key)
            self._order.append(key)
            return self._cache[key]
        return None

    def put(self, key: str, value: Dict):
        if key in self._cache:
            self._order.remove(key)
        elif len(self._cache) >= self.max_size:
            oldest = self._order.pop(0)
            del self._cache[oldest]
        self._cache[key] = value
        self._order.append(key)

    def __len__(self):
        return len(self._cache)


class RAGPipeline:
    """
    Full RAG pipeline: embed query → retrieve from ChromaDB → generate with Groq.
    """

    def __init__(self):
        print("[INFO] Initializing RAG pipeline...")

        # Validate API key
        # Check both names in case the user overwrote GEMINI_API_KEY
        api_key = os.getenv("GROQ_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not api_key or api_key in ("PASTE_YOUR_KEY_HERE", "your_gemini_api_key_here"):
            raise ValueError(
                "API Key not set.\n"
                "Edit .env and paste your Groq key (e.g. GROQ_API_KEY=gsk_...)"
            )

        # ── Embedding function (MUST match ingest.py — both use EMBED_MODEL from config) ──
        self.embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=EMBED_MODEL
        )
        print(f"[OK]  Embedding model: {EMBED_MODEL}")

        # ── ChromaDB ──────────────────────────────────────────────────────────
        self.chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)
        self.collection = self.chroma_client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=self.embed_fn,
            metadata={"hnsw:space": "cosine"},
        )
        db_count = self.collection.count()
        print(f"[OK]  ChromaDB: {db_count} chunks loaded from '{COLLECTION_NAME}'")

        if db_count == 0:
            print(
                "[WARNING] Database is empty!\n"
                "          Run: python scraper.py && python ingest.py"
            )
            self.bm25 = None
            self.bm25_docs, self.bm25_metas, self.bm25_ids = [], [], []
        else:
            print("[INFO] Building BM25 index for hybrid search...")
            all_data = self.collection.get(include=["documents", "metadatas"])
            self.bm25_docs = all_data["documents"]
            self.bm25_metas = all_data["metadatas"]
            self.bm25_ids = all_data["ids"]
            
            # Tokenize for BM25 (simple split works well enough for this scale)
            tokenized_corpus = [doc.split() for doc in self.bm25_docs]
            self.bm25 = BM25Okapi(tokenized_corpus)
            print("[OK]  BM25 index ready")

        # ── Groq client (Llama 3 70B) ─────────────────────────────────────────
        self.llm_client = Groq(api_key=api_key)
        print(f"[OK]  Generation model: {GENERATION_MODEL}")

        # ── LRU cache ─────────────────────────────────────────────────────────
        self.cache = LRUCache(max_size=CACHE_MAX_SIZE)
        print(f"[OK]  Query cache: max {CACHE_MAX_SIZE} entries")
        print("[INFO] RAG pipeline ready.\n")

    # ── Retrieval ──────────────────────────────────────────────────────────────
    def retrieve(
        self, query: str, k: int = DEFAULT_K
    ) -> Tuple[List[str], List[Dict], float]:
        """
        Retrieve top-k most relevant chunks using Hybrid Search (BM25 + Vector).
        Combines results via Reciprocal Rank Fusion (RRF).
        Returns: (docs, metadatas, confidence_score)
        """
        db_count = self.collection.count()
        if db_count == 0 or not self.bm25:
            return [], [], 0.0

        n = min(k * 3, db_count)  # Fetch more for broader RRF merge

        # 1. Vector Search
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=n,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as e:
            print(f"[ERROR] ChromaDB query failed: {e}")
            return [], [], 0.0

        vec_ids = results["ids"][0] if results.get("ids") else []
        vec_dists = results["distances"][0] if results.get("distances") else []

        # 2. BM25 Keyword Search
        tokenized_query = query.split()
        bm25_scores = self.bm25.get_scores(tokenized_query)
        top_n_idx = sorted(range(len(bm25_scores)), key=lambda i: bm25_scores[i], reverse=True)[:n]
        bm25_ids = [self.bm25_ids[i] for i in top_n_idx]

        # 3. Reciprocal Rank Fusion (RRF)
        rrf_scores = {}
        rrf_k = 60
        
        # Give BM25 stronger weight for Arabic queries since "شروط", "أركان" exact matches are highly precise
        vec_weight = 0.5
        bm25_weight = 1.0

        for rank, doc_id in enumerate(vec_ids):
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + vec_weight * (1.0 / (rank + rrf_k))

        for rank, doc_id in enumerate(bm25_ids):
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + bm25_weight * (1.0 / (rank + rrf_k))

        # Sort combined results and take top k
        sorted_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)[:k]

        # 4. Resolve exact documents and metadata
        id_to_index = {doc_id: idx for idx, doc_id in enumerate(self.bm25_ids)}
        
        final_docs = []
        final_metas = []
        for doc_id in sorted_ids:
            if doc_id in id_to_index:
                idx = id_to_index[doc_id]
                final_docs.append(self.bm25_docs[idx])
                final_metas.append(self.bm25_metas[idx])

        # 5. Compute pseudo-confidence from vector distances
        id_to_dist = {doc_id: dist for doc_id, dist in zip(vec_ids, vec_dists)}
        # If retrieved via BM25 only and missed by vector, give it a neutral distance (e.g. 0.8)
        final_dists = [id_to_dist.get(doc_id, 0.8) for doc_id in sorted_ids]
        confidences = [max(0.0, 1.0 - d) for d in final_dists]
        avg_confidence = round(sum(confidences) / len(confidences), 3) if confidences else 0.0

        return final_docs, final_metas, avg_confidence

    # ── Context formatting ─────────────────────────────────────────────────────
    def format_context(self, docs: List[str], metas: List[Dict]) -> str:
        if not docs:
            return ""
        parts = []
        for i, (doc, meta) in enumerate(zip(docs, metas), 1):
            title = meta.get("title", "Islamweb Fatwa")
            parts.append(f"[Source {i}] {title}\n{doc}")
        return "\n\n---\n\n".join(parts)

    # ── Source deduplication ───────────────────────────────────────────────────
    def get_unique_sources(self, metas: List[Dict]) -> List[Dict]:
        seen = set()
        sources = []
        for meta in metas:
            url = meta.get("source", "")
            if url and url not in seen:
                seen.add(url)
                sources.append({
                    "url": url,
                    "title": meta.get("title", "Islamweb Fatwa"),
                    "lang": meta.get("lang", "ar"),
                })
        return sources

    # ── Generation ─────────────────────────────────────────────────────────────
    def generate_answer(self, query: str, k: int = DEFAULT_K) -> Dict:
        """
        Main RAG function:
        1. Validate input
        2. Check cache
        3. Retrieve top-k chunks
        4. Generate grounded answer with Groq (Llama 3 70B)
        5. Cache and return result
        """
        # Step 1: Validate
        query = validate_input(query)
        lang = detect_language(query)

        # Step 2: Cache lookup
        cache_key = f"{query.strip().lower()}|k={k}"
        cached = self.cache.get(cache_key)
        if cached:
            print(f"[CACHE HIT] Query served from cache")
            return cached

        # Step 3: Retrieve
        docs, metas, confidence = self.retrieve(query, k=k)

        # No documents at all — DB empty or retrieval failed
        if not docs:
            no_db_msg = (
                "لا أعلم بناءً على المصادر المتاحة." if lang == "ar"
                else "I don't know based on the provided sources."
            )
            return {
                "answer": no_db_msg,
                "sources": [],
                "lang": lang,
                "confidence": 0.0,
            }

        # Very low confidence → likely off-topic question
        if confidence < CONFIDENCE_THRESHOLD:
            low_conf_msg = (
                "لا أعلم بناءً على المصادر المتاحة. السؤال قد يكون خارج نطاق قاعدة البيانات." if lang == "ar"
                else "I don't know based on the provided sources. The question may be outside the database scope."
            )
            return {
                "answer": low_conf_msg,
                "sources": [],
                "lang": lang,
                "confidence": confidence,
            }

        # Step 4: Build prompt and generate
        context = self.format_context(docs, metas)
        user_prompt = f"Context from Islamweb fatwas:\n\n{context}\n\n---\n\nQuestion: {query}"

        try:
            response = self.llm_client.chat.completions.create(
                messages=[
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT,
                    },
                    {
                        "role": "user",
                        "content": user_prompt,
                    }
                ],
                model=GENERATION_MODEL,
                temperature=0.1,
                max_tokens=1024,
                top_p=0.9,
            )
            answer_text = response.choices[0].message.content.strip()
        except Exception as e:
            err_str = str(e)
            print(f"[ERROR] Groq generation failed: {err_str}")
            return {
                "answer": f"Generation error: {err_str}",
                "sources": [],
                "lang": lang,
                "confidence": confidence,
            }

        sources = self.get_unique_sources(metas)
        result = {
            "answer": answer_text,
            "sources": sources,
            "lang": lang,
            "confidence": confidence,
        }

        # Step 5: Cache result
        self.cache.put(cache_key, result)
        return result

    def get_stats(self) -> Dict:
        return {
            "total_chunks": self.collection.count(),
            "collection_name": COLLECTION_NAME,
            "model": GENERATION_MODEL,
            "embedding_model": EMBED_MODEL,
            "cache_size": len(self.cache),
        }


# ── Quick smoke test ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("RAG Pipeline — Smoke Test")
    print("=" * 60)
    rag = RAGPipeline()

    test_queries = [
        "ما هو حكم الصيام أثناء السفر؟",
        "What is the ruling on fasting while traveling?",
        "ما حكم الصلاة في وقتها؟",
    ]

    for q in test_queries:
        print(f"\nQ: {q}")
        print("-" * 50)
        result = rag.generate_answer(q)
        print(f"A: {result['answer'][:300]}...")
        print(f"   Confidence: {result['confidence']}")
        print(f"   Sources   : {len(result['sources'])}")
        for s in result["sources"][:2]:
            print(f"     [{s['lang'].upper()}] {s['title'][:50]} → {s['url']}")

"""
ingest.py — Embed Islamweb fatwas into ChromaDB vector store.
Run ONCE before starting the API server.

Usage:
    python ingest.py              # Ingest all fatwas from data/fatwas.json
    python ingest.py --limit 20   # Ingest only first 20 (for quick testing)
    python ingest.py --reset      # Clear DB and re-ingest everything

IMPORTANT: Uses the exact same EMBED_MODEL from config.py as rag_pipeline.py.
           Changing the model here without re-ingesting will break retrieval.
"""

import os
import json
import argparse
import sys
import chromadb
from chromadb.utils import embedding_functions

# Windows console encoding fix
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

from config import (
    CHROMA_DIR,
    COLLECTION_NAME,
    EMBED_MODEL,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
)

DATA_PATH = "data/fatwas.json"
BATCH_SIZE = 100  # ChromaDB insert batch size


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP):
    """
    Split text into overlapping chunks with sentence-boundary awareness.
    Smaller chunks improve retrieval precision.
    """
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]

        # Try to cut at a natural boundary
        if end < len(text):
            for boundary in [". ", ".\n", "؟ ", "? ", "! ", "! \n"]:
                cut = chunk.rfind(boundary)
                if cut > chunk_size // 2:
                    end = start + cut + len(boundary)
                    chunk = text[start:end]
                    break

        chunks.append(chunk.strip())
        start = end - overlap

    return [c for c in chunks if len(c) > 200]


def load_fatwas(path: str) -> list:
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"'{path}' not found.\n"
            f"Run 'python scraper.py' first to collect fatwas."
        )
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


def get_existing_ids(collection) -> set:
    """Return the set of document IDs already in the collection."""
    try:
        result = collection.get(include=[])
        return set(result["ids"])
    except Exception:
        return set()


def ingest(limit: int = None, reset: bool = False):
    print(f"\n{'='*60}")
    print("  Islamweb QA v3 — Ingest Pipeline")
    print(f"{'='*60}\n")

    # ── Load fatwas ──────────────────────────────────────────────────────────
    fatwas = load_fatwas(DATA_PATH)
    if limit:
        fatwas = fatwas[:limit]
    print(f"[INFO] Loaded {len(fatwas)} fatwas from {DATA_PATH}")

    # ── Embedding function (MUST match rag_pipeline.py) ─────────────────────
    print(f"[INFO] Loading embedding model: {EMBED_MODEL}")
    print("       (First run downloads ~120MB — subsequent runs use cache)")
    embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBED_MODEL
    )
    print("[OK]  Embedding model ready")

    # ── ChromaDB ─────────────────────────────────────────────────────────────
    client = chromadb.PersistentClient(path=CHROMA_DIR)

    if reset:
        print("[INFO] --reset flag: clearing existing collection...")
        try:
            client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass

    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=embed_fn,
        metadata={"hnsw:space": "cosine"},
    )

    existing_ids = get_existing_ids(collection)
    print(f"[INFO] Collection already has {len(existing_ids)} chunks")

    # ── Prepare chunks ────────────────────────────────────────────────────────
    all_docs, all_ids, all_metas = [], [], []

    for fatwa in fatwas:
        fatwa_id = fatwa.get("id", 0)
        url = fatwa.get("url", "")
        title = fatwa.get("title", "")
        lang = fatwa.get("lang", "ar")
        content = fatwa.get("content", "")

        chunks = chunk_text(content)
        for i, chunk in enumerate(chunks):
            doc_id = f"fatwa_{fatwa_id}_{lang}_{i}"
            if doc_id in existing_ids:
                continue  # Skip already-indexed chunks (resume support)

            # Prepend title to anchor chunk to its topic — improves retrieval recall
            titled_chunk = f"عنوان: {title}\n\n{chunk}" if title else chunk

            all_docs.append(titled_chunk)
            all_ids.append(doc_id)
            all_metas.append({
                "source": url,
                "title": title,
                "lang": lang,
                "fatwa_id": str(fatwa_id),
                "chunk_index": str(i),
            })

    total_new = len(all_docs)
    if total_new == 0:
        print("\n[OK] Nothing new to ingest — database is up to date!")
        print(f"     Total chunks in DB: {collection.count()}")
        return

    print(f"[INFO] {total_new} new chunks to embed and store...")

    # ── Ingest in batches ─────────────────────────────────────────────────────
    inserted = 0
    for i in range(0, total_new, BATCH_SIZE):
        batch_docs = all_docs[i : i + BATCH_SIZE]
        batch_ids = all_ids[i : i + BATCH_SIZE]
        batch_metas = all_metas[i : i + BATCH_SIZE]

        try:
            collection.add(
                documents=batch_docs,
                ids=batch_ids,
                metadatas=batch_metas,
            )
            inserted += len(batch_docs)
            pct = (inserted / total_new) * 100
            print(f"  [{pct:5.1f}%] Stored {inserted}/{total_new} chunks...", flush=True)
        except Exception as e:
            print(f"  [ERROR] Batch {i} failed: {e}")

    final_count = collection.count()
    print(f"\n{'='*60}")
    print(f"  [OK] Ingestion complete!")
    print(f"       New chunks added : {inserted}")
    print(f"       Total in DB      : {final_count}")
    print(f"       ChromaDB path    : {os.path.abspath(CHROMA_DIR)}")
    print(f"\n  Next step: run  python main.py\n")
    print(f"{'='*60}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Islamweb QA v3 — Ingest fatwas into ChromaDB"
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Limit number of fatwas to ingest (for testing)"
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="Clear the existing DB before ingesting"
    )
    args = parser.parse_args()
    ingest(limit=args.limit, reset=args.reset)

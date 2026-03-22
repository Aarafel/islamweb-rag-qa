"""
config.py — Single source of truth for all settings.
Both ingest.py and rag_pipeline.py import from here to guarantee consistency.
"""

# ── ChromaDB ─────────────────────────────────────────────────────────────────
CHROMA_DIR = "./chroma_db"
COLLECTION_NAME = "islamweb_fatwas"

# ── Embedding model (MUST be identical in ingest.py AND rag_pipeline.py) ─────
# pinned to avoid breaking changes from sentence-transformers updates
EMBED_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"

# ── Groq generation model ───────────────────────────────────────────────────
GENERATION_MODEL = "llama-3.1-8b-instant"

# ── Chunking ──────────────────────────────────────────────────────────────────
CHUNK_SIZE = 1000      # characters per chunk (optimal for dense embeddings)
CHUNK_OVERLAP = 200    # overlap between chunks (prevent context loss)

# ── Retrieval ─────────────────────────────────────────────────────────────────
DEFAULT_K = 10         # top-k chunks to retrieve
CONFIDENCE_THRESHOLD = 0.10   # min avg confidence to attempt generation

# ── Scraper ───────────────────────────────────────────────────────────────────
SCRAPER_DELAY_MIN = 1.0   # seconds (min delay between requests)
SCRAPER_DELAY_MAX = 2.0   # seconds (max delay)
SCRAPER_MAX_RETRIES = 3   # retries per fatwa ID

# ── API ───────────────────────────────────────────────────────────────────────
API_HOST = "0.0.0.0"
API_PORT = 8000
RATE_LIMIT = "10/minute"   # per IP on /ask
MAX_QUESTION_LENGTH = 1000  # characters

# ── Cache ─────────────────────────────────────────────────────────────────────
CACHE_MAX_SIZE = 256   # max number of cached query results (LRU)

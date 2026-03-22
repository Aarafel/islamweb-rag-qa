import chromadb
import sys
from chromadb.utils import embedding_functions

sys.stdout.reconfigure(encoding='utf-8')

embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name='paraphrase-multilingual-MiniLM-L12-v2'
)
client = chromadb.PersistentClient(path='./chroma_db')
collection = client.get_collection('islamweb_fatwas', embedding_function=embed_fn)

queries = [
    "ما حكم الصيام أثناء السفر؟",
    "ما حكم صلاة الجمعة؟",
    "ما مقدار زكاة الفطر؟",
    "ما هي شروط الحج؟",
]

for q in queries:
    print(f"\n--- QUERY: {q} ---")
    res = collection.query(query_texts=[q], n_results=5, include=['metadatas', 'distances'])
    for d, m in zip(res['distances'][0], res['metadatas'][0]):
        print(f"[{d:.3f}] {m.get('title')} ({m.get('source')})")

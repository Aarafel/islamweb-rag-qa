import sys
sys.stdout.reconfigure(encoding='utf-8')
from rag_pipeline import RAGPipeline

rag = RAGPipeline()
docs, metas, conf = rag.retrieve('ما هي شروط الحج؟', k=10)

print(f"Confidence: {conf}")
# Just print the top 3 doc texts
for i, (doc, meta) in enumerate(zip(docs[:3], metas[:3])):
    print(f"\n=== CHUNK {i+1} from {meta.get('source')} ===")
    print(doc)

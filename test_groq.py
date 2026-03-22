"""
Direct Groq test to see if the context actually contains the answer.
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')
import os
from dotenv import load_dotenv
from groq import Groq
from rag_pipeline import RAGPipeline, SYSTEM_PROMPT

load_dotenv()
api_key = os.getenv("GROQ_API_KEY") or os.getenv("GEMINI_API_KEY")
client = Groq(api_key=api_key)
rag = RAGPipeline()

q = 'ما هي شروط الحج؟'
docs, metas, conf = rag.retrieve(q, k=10)
context = rag.format_context(docs, metas)
user_prompt = f"Context from Islamweb fatwas:\n\n{context}\n\n---\n\nQuestion: {q}"

print("=== CONTEXT BEING SENT TO GROQ ===")
print(context[:2000])
print("=======")
print()

response = client.chat.completions.create(
    messages=[
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt}
    ],
    model="llama-3.3-70b-versatile",
    temperature=0.1,
    max_tokens=1024,
)
print("GROQ ANSWER:")
print(response.choices[0].message.content)

import json
import httpx
import math
import re
from typing import List, Dict

OLLAMA_BASE_URL = "http://localhost:11434"

class LocalVectorStore:
    def __init__(self):
        # Extremely fast vector collection matrix in memory
        self.documents: List[str] = []
        self.embeddings: List[List[float]] = []

    def clear(self):
        self.documents.clear()
        self.embeddings.clear()

    async def get_embedding(self, text: str) -> List[float]:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{OLLAMA_BASE_URL}/api/embeddings",
                json={"model": "nomic-embed-text", "prompt": text},
                timeout=30.0
            )
            if response.status_code == 200:
                return response.json().get("embedding", [])
            return []

    def cosine_similarity(self, v1: List[float], v2: List[float]) -> float:
        dot_product = sum(a * b for a, b in zip(v1, v2))
        norm_a = math.sqrt(sum(a * a for a in v1))
        norm_b = math.sqrt(sum(b * b for b in v2))
        if not norm_a or not norm_b:
            return 0.0
        return dot_product / (norm_a * norm_b)

    async def add_chunks(self, chunks: List[str]):
        for chunk in chunks:
            if not chunk.strip():
                continue
            embedding = await self.get_embedding(chunk)
            if embedding:
                self.documents.append(chunk)
                self.embeddings.append(embedding)

    async def query_relevant_context(self, query: str, top_k: int = 3) -> str:
        if not self.embeddings:
            return ""
        query_vector = await self.get_embedding(query)
        if not query_vector:
            return ""

        scores = [
            (self.cosine_similarity(query_vector, doc_vec), doc)
            for doc, doc_vec in zip(self.documents, self.embeddings)
        ]
        # Sort descending by proximity score match
        scores.sort(key=lambda x: x[0], reverse=True)
        relevant_chunks = [doc for score, doc in scores[:top_k] if score > 0.35]
        return "\n\n---\n\n".join(relevant_chunks)


rag_store = LocalVectorStore()


def chunk_text_or_code(text: str, filename: str, chunk_size: int = 800, overlap: int = 150) -> List[str]:
    ext = filename.split('.')[-1].lower()
    
    # 🛠️ Code-aware splitting strategy for C, C++, and structural configs
    if ext in ['c', 'cpp', 'h', 'java', 'json']:
        # Split across functions, closures, or clean logical block segments
        raw_chunks = re.split(r'(?<=\n)(?=\s*(?:void|int|char|long|float|double|struct|class|if|for|while)\b)', text)
        processed_chunks = []
        current_chunk = ""
        
        for piece in raw_chunks:
            if len(current_chunk) + len(piece) < chunk_size:
                current_chunk += piece
            else:
                if current_chunk.strip():
                    processed_chunks.append(f"Source file block [{filename}]:\n{current_chunk.strip()}")
                current_chunk = piece
        if current_chunk.strip():
            processed_chunks.append(f"Source file block [{filename}]:\n{current_chunk.strip()}")
        return processed_chunks
        
    else:
        # Standard sliding window text chunking algorithm for prose/documents
        words = text.split()
        chunks = []
        for i in range(0, len(words), chunk_size - overlap):
            chunk_words = words[i:i + chunk_size]
            chunks.append(" ".join(chunk_words))
            if i + chunk_size >= len(words):
                break
        return chunks
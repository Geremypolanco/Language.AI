"""Embedding Service - Semantic search and recommendations"""

import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

class EmbeddingService:
    def __init__(self):
        self.model = None
        self._initialize_model()

    def _initialize_model(self):
        """Lazy load embedding model"""
        try:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer('all-MiniLM-L6-v2')
        except ImportError:
            logger.warning("sentence-transformers not installed. Install with: pip install sentence-transformers")

    async def embed_text(self, text: str) -> List[float]:
        """Generate embedding for text"""
        if not self.model:
            return []
        try:
            return self.model.encode(text).tolist()
        except Exception as e:
            logger.error(f"Embedding error: {e}")
            return []

    async def find_similar(self, query: str, documents: List[str], top_k: int = 5) -> List[dict]:
        """Find similar documents to query"""
        if not self.model:
            return []
        
        try:
            query_embedding = self.model.encode(query)
            doc_embeddings = self.model.encode(documents)
            
            import numpy as np
            similarities = np.dot(doc_embeddings, query_embedding)
            top_indices = np.argsort(similarities)[-top_k:][::-1]
            
            return [
                {"text": documents[i], "similarity": float(similarities[i])}
                for i in top_indices
            ]
        except Exception as e:
            logger.error(f"Similarity search error: {e}")
            return []

# Singleton instance
_embedding_service: Optional[EmbeddingService] = None

def get_embedding_service() -> EmbeddingService:
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service

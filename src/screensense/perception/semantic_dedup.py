"""Semantic Deduplication

Uses sentence embeddings to detect semantically similar responses.
Prevents ARIA from repeating the same suggestion in different words.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass

try:
    from sentence_transformers import SentenceTransformer
    import numpy as np
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    SentenceTransformer = None  # type: ignore
    np = None  # type: ignore


@dataclass
class ResponseRecord:
    """Record of a past response"""
    text: str
    embedding: list[float] | None
    timestamp: float


class SemanticDeduplicator:
    """Detects semantically duplicate responses using embeddings"""
    
    def __init__(
        self,
        *,
        model_name: str = "all-MiniLM-L6-v2",
        similarity_threshold: float = 0.85,
        history_size: int = 20,
        time_window_seconds: float = 300.0,  # 5 minutes
    ):
        """
        Initialize semantic deduplicator.
        
        Args:
            model_name: Sentence transformer model name
            similarity_threshold: Cosine similarity threshold for duplicates
            history_size: Number of recent responses to keep
            time_window_seconds: Time window for deduplication
        """
        self._similarity_threshold = similarity_threshold
        self._history_size = history_size
        self._time_window = time_window_seconds
        self._history: deque[ResponseRecord] = deque(maxlen=history_size)
        self._model = None
        self._model_name = model_name
        self._initialized = False
    
    def initialize(self) -> bool:
        """Load sentence transformer model"""
        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            print("[SemanticDedup] sentence-transformers not available, using exact matching")
            self._initialized = True
            return True
        
        try:
            self._model = SentenceTransformer(self._model_name)
            self._initialized = True
            return True
        except Exception as e:
            print(f"[SemanticDedup] Failed to load model: {e}")
            self._initialized = True  # Fall back to exact matching
            return False
    
    def is_duplicate(self, response_text: str) -> bool:
        """
        Check if response is semantically duplicate of recent responses.
        
        Args:
            response_text: Response text to check
        
        Returns:
            True if duplicate, False otherwise
        """
        if not self._initialized:
            self.initialize()
        
        # Clean history (remove old entries)
        self._clean_history()
        
        # Exact match check (fast path)
        for record in self._history:
            if record.text.strip().lower() == response_text.strip().lower():
                return True
        
        # Semantic similarity check
        if self._model is not None and SENTENCE_TRANSFORMERS_AVAILABLE:
            try:
                # Compute embedding for new response
                new_embedding = self._model.encode(response_text, convert_to_numpy=True)
                
                # Compare with history
                for record in self._history:
                    if record.embedding is None:
                        continue
                    
                    similarity = self._cosine_similarity(
                        new_embedding,
                        np.array(record.embedding),
                    )
                    
                    if similarity >= self._similarity_threshold:
                        return True
            except Exception as e:
                print(f"[SemanticDedup] Embedding comparison failed: {e}")
        
        return False
    
    def add_to_history(self, response_text: str) -> None:
        """
        Add response to deduplication history.
        
        Args:
            response_text: Response text to add
        """
        if not self._initialized:
            self.initialize()
        
        # Compute embedding if model available
        embedding = None
        if self._model is not None and SENTENCE_TRANSFORMERS_AVAILABLE:
            try:
                embedding = self._model.encode(response_text, convert_to_numpy=True).tolist()
            except Exception:
                pass
        
        # Add to history
        self._history.append(
            ResponseRecord(
                text=response_text,
                embedding=embedding,
                timestamp=time.time(),
            )
        )
    
    def clear_history(self) -> None:
        """Clear deduplication history"""
        self._history.clear()
    
    def _clean_history(self) -> None:
        """Remove entries outside time window"""
        now = time.time()
        cutoff = now - self._time_window
        
        # Remove old entries
        while self._history and self._history[0].timestamp < cutoff:
            self._history.popleft()
    
    @staticmethod
    def _cosine_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
        """Calculate cosine similarity between two vectors"""
        if np is None:
            return 0.0
        
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return float(dot_product / (norm1 * norm2))

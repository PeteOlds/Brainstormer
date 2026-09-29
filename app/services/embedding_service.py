"""Embedding generation and similarity search service.

Uses nomic-embed-text via Ollama for generating embeddings.
Stores embeddings as float arrays in JSONB column.
Provides similarity search using cosine similarity in Python.
"""

import logging
import uuid
from typing import List, Optional, Tuple

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.extensions import db
from app.models import Idea
from app.services.ollama_client import OllamaClient, OllamaError

logger = structlog.get_logger()


def embedding_text(idea) -> str:
    """Text embedded for similarity search.

    Uses the human-readable excerpt (elevator pitch/summary) instead of the
    raw JSON blob: shared schema keys and boilerplate otherwise inflate
    cosine scores between unrelated ideas from the same prompt.
    """
    return f"{idea.prompt_title}\n\n{idea.excerpt(limit=500)}"


class EmbeddingService:
    """Service for generating and managing idea embeddings."""

    EMBEDDING_MODEL = "nomic-embed-text"
    EMBEDDING_DIM = 768  # nomic-embed-text produces 768-dim vectors
    SIMILARITY_THRESHOLD = 0.85  # Cosine similarity threshold for "similar" ideas

    def __init__(self, base_url: str | None = None):
        self.ollama_client = OllamaClient(base_url=base_url)

    async def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for a single text using nomic-embed-text."""
        try:
            response = await self.ollama_client.embeddings(
                model=self.EMBEDDING_MODEL, prompt=text
            )
            embedding = response.get("embedding")
            if not embedding or len(embedding) != self.EMBEDDING_DIM:
                raise ValueError(
                    f"Invalid embedding dimension: {len(embedding) if embedding else 0}"
                )
            return embedding
        except OllamaError as e:
            logger.error(
                "embedding_generation_failed",
                base_url=self.ollama_client.base_url,
                model=self.EMBEDDING_MODEL,
                status=e.status_code,
                body=e.response_body,
            )
            raise
        except Exception as e:
            logger.error("embedding_generation_failed", error=str(e))
            raise

    def generate_embedding_sync(self, text: str) -> List[float]:
        """Synchronous version for use in Celery tasks."""
        try:
            response = self.ollama_client.generate_sync(
                model=self.EMBEDDING_MODEL,
                prompt=text,
                format="json",
                options={"temperature": 0.0},
            )
            # nomic-embed-text returns embedding in response["embedding"]
            embedding = response.get("embedding")
            if not embedding or len(embedding) != self.EMBEDDING_DIM:
                raise ValueError(
                    f"Invalid embedding dimension: {len(embedding) if embedding else 0}"
                )
            return embedding
        except OllamaError as e:
            logger.error(
                "embedding_generation_failed",
                base_url=self.ollama_client.base_url,
                model=self.EMBEDDING_MODEL,
                status=e.status_code,
                body=e.response_body,
            )
            raise
        except Exception as e:
            logger.error("embedding_generation_failed", error=str(e))
            raise
            embedding = data.get("embedding")
            if not embedding or len(embedding) != self.EMBEDDING_DIM:
                raise ValueError(
                    f"Invalid embedding dimension: {len(embedding) if embedding else 0}"
                )
            return embedding
        except Exception as e:
            logger.error("embedding_generation_failed", error=str(e))
            raise

    def store_embedding(self, idea_id: uuid.UUID, embedding: List[float]) -> bool:
        """Store embedding for an idea."""
        try:
            idea = db.session.get(Idea, idea_id)
            if not idea:
                logger.warning("idea_not_found_for_embedding", idea_id=str(idea_id))
                return False
            # Store as JSON array of floats
            idea.embedding = embedding
            db.session.commit()
            logger.info("embedding_stored", idea_id=str(idea_id))
            return True
        except Exception as e:
            logger.error("embedding_store_failed", idea_id=str(idea_id), error=str(e))
            db.session.rollback()
            return False

    def cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Compute cosine similarity between two vectors."""
        from pgvector import Vector

        v1 = Vector(vec1)
        v2 = Vector(vec2)
        return float(v1.cosine_similarity(v2))

    def find_similar_to_embedding(
        self,
        embedding: List[float],
        threshold: float = None,
        limit: int = 10,
        exclude_id=None,
        instance_id=None,
    ) -> List[Tuple[Idea, float]]:
        """Find ideas similar to a raw embedding vector.

        Used by the generation dedup gate (the new idea isn't persisted
        yet, so there is no id to look up). Sorted by score descending.
        instance_id scopes the comparison to one instance (dedup is
        within-instance only); None keeps the legacy global behaviour.
        """
        threshold = threshold or self.SIMILARITY_THRESHOLD
        if not embedding:
            return []

        query = select(Idea).where(Idea.embedding.is_not(None))
        if exclude_id is not None:
            query = query.where(Idea.id != exclude_id)
        if instance_id is not None:
            query = query.where(Idea.instance_id == instance_id)
        ideas = db.session.execute(query).scalars().all()

        similar = []
        for idea in ideas:
            if not idea.embedding:
                continue
            similarity = self.cosine_similarity(embedding, idea.embedding)
            if similarity >= threshold:
                similar.append((idea, similarity))

        # Sort by similarity descending
        similar.sort(key=lambda x: x[1], reverse=True)
        return similar[:limit]

    def find_similar_ideas(
        self,
        idea_id: uuid.UUID,
        threshold: float = None,
        limit: int = 10,
        instance_id=None,
    ) -> List[Tuple[Idea, float]]:
        """Find ideas similar to the given idea.

        Returns list of (Idea, similarity_score) tuples sorted by similarity descending.
        """
        # Get the target idea's embedding
        target_idea = db.session.get(Idea, idea_id)
        if not target_idea or not target_idea.embedding:
            return []

        return self.find_similar_to_embedding(
            target_idea.embedding,
            threshold=threshold,
            limit=limit,
            exclude_id=idea_id,
            instance_id=instance_id,
        )

    def find_near_duplicates(
        self, idea_id: uuid.UUID, threshold: float = 0.95
    ) -> List[Tuple[Idea, float]]:
        """Find near-duplicate ideas (very high similarity)."""
        return self.find_similar_ideas(idea_id, threshold=threshold, limit=5)

    async def backfill_embeddings(self, batch_size: int = 10) -> dict:
        """Generate embeddings for all ideas that don't have them.

        Returns stats: {"processed": int, "succeeded": int, "failed": int}
        """
        stats = {"processed": 0, "succeeded": 0, "failed": 0}

        ideas = (
            db.session.execute(select(Idea).where(Idea.embedding.is_(None)))
            .scalars()
            .all()
        )

        for idea in ideas:
            stats["processed"] += 1
            try:
                embedding = await self.generate_embedding(embedding_text(idea))
                if self.store_embedding(idea.id, embedding):
                    stats["succeeded"] += 1
                else:
                    stats["failed"] += 1
            except Exception as e:
                logger.error(
                    "embedding_backfill_failed", idea_id=str(idea.id), error=str(e)
                )
                stats["failed"] += 1

        logger.info("embedding_backfill_complete", **stats)
        return stats


# Global instance
_embedding_service: Optional[EmbeddingService] = None


def get_embedding_service() -> EmbeddingService:
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service

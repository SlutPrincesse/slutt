"""
RedAmon Knowledge Base Integration - RAG/Embeddings system for AGENT_SYSTEM_V9
"""
from __future__ import annotations

import hashlib
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Document:
    """Document for knowledge base."""
    doc_id: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    embedding: list[float] | None = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


@dataclass
class SearchResult:
    """Search result from knowledge base."""
    document: Document
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


class EmbeddingProvider(ABC):
    """Abstract embedding provider."""

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for texts."""
        pass

    @abstractmethod
    async def embed_query(self, query: str) -> list[float]:
        """Generate embedding for a query."""
        pass


class VectorStore(ABC):
    """Abstract vector store."""

    @abstractmethod
    async def add(self, documents: list[Document]) -> list[str]:
        """Add documents to store."""
        pass

    @abstractmethod
    async def search(self, query_embedding: list[float], k: int = 10,
                     filter_metadata: dict | None = None) -> list[SearchResult]:
        """Search for similar documents."""
        pass

    @abstractmethod
    async def delete(self, doc_ids: list[str]) -> bool:
        """Delete documents by ID."""
        pass

    @abstractmethod
    async def get(self, doc_id: str) -> Document | None:
        """Get document by ID."""
        pass


class InMemoryVectorStore(VectorStore):
    """In-memory vector store for development/testing."""

    def __init__(self):
        self._documents: dict[str, Document] = {}
        self._embeddings: dict[str, list[float]] = {}

    async def add(self, documents: list[Document]) -> list[str]:
        ids = []
        for doc in documents:
            self._documents[doc.doc_id] = doc
            if doc.embedding:
                self._embeddings[doc.doc_id] = doc.embedding
            ids.append(doc.doc_id)
        return ids

    async def search(self, query_embedding: list[float], k: int = 10,
                     filter_metadata: dict | None = None) -> list[SearchResult]:
        import numpy as np

        query_vec = np.array(query_embedding)
        results = []

        for doc_id, doc in self._documents.items():
            if filter_metadata:
                match = all(doc.metadata.get(k) == v for k, v in filter_metadata.items())
                if not match:
                    continue

            if doc_id in self._embeddings:
                doc_vec = np.array(self._embeddings[doc_id])
                # Cosine similarity
                score = np.dot(query_vec, doc_vec) / (np.linalg.norm(query_vec) * np.linalg.norm(doc_vec) + 1e-8)
                results.append(SearchResult(document=doc, score=float(score)))

        results.sort(key=lambda x: x.score, reverse=True)
        return results[:k]

    async def delete(self, doc_ids: list[str]) -> bool:
        for doc_id in doc_ids:
            self._documents.pop(doc_id, None)
            self._embeddings.pop(doc_id, None)
        return True

    async def get(self, doc_id: str) -> Document | None:
        return self._documents.get(doc_id)


class KnowledgeBase:
    """
    Knowledge base with RAG capabilities.
    Integrates RedAmon's knowledge_base components.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.embedding_provider: EmbeddingProvider | None = None
        self.vector_store: VectorStore = InMemoryVectorStore()
        self._initialized = False

        # RedAmon components
        self._kb_orchestrator = None
        self._embedder = None
        self._reranker = None
        self._indexer = None

    async def initialize(self, embedding_provider: EmbeddingProvider | None = None) -> bool:
        """Initialize knowledge base."""
        if self._initialized:
            return True

        try:
            # Try to use RedAmon components
            from agent_system_v9.integrations.redamon.knowledge_base.chunking import chunk_text
            from agent_system_v9.integrations.redamon.knowledge_base.curation.data_ingestion import (
                DataIngestion,
            )
            from agent_system_v9.integrations.redamon.knowledge_base.curation.exploitdb_client import (
                ExploitDBClient,
            )
            from agent_system_v9.integrations.redamon.knowledge_base.curation.nuclei_client import (
                NucleiClient,
            )

            self._chunk_text = chunk_text
            self._data_ingestion = DataIngestion()

            # Try to initialize embedder
            try:
                from agent_system_v9.integrations.redamon.knowledge_base.embedder import Embedder
                self._embedder = Embedder()
            except ImportError:
                pass

        except ImportError as e:
            logger.warning(f"RedAmon knowledge_base not fully available: {e}")

        self.embedding_provider = embedding_provider or self._create_default_embedder()
        self._initialized = True
        logger.info("Knowledge base initialized")
        return True

    def _create_default_embedder(self) -> EmbeddingProvider:
        """Create default embedding provider using sentence-transformers or fallback."""

        class DefaultEmbedder(EmbeddingProvider):
            def __init__(self):
                self._model = None
                self._init_model()

            def _init_model(self):
                try:
                    from sentence_transformers import SentenceTransformer
                    self._model = SentenceTransformer('all-MiniLM-L6-v2')
                except ImportError:
                    logger.warning("sentence-transformers not available, using hash fallback")
                    self._model = None

            async def embed(self, texts: list[str]) -> list[list[float]]:
                if self._model:
                    return self._model.encode(texts).tolist()
                return [self._hash_embed(t) for t in texts]

            async def embed_query(self, query: str) -> list[float]:
                return (await self.embed([query]))[0]

            def _hash_embed(self, text: str) -> list[float]:
                """Simple hash-based embedding fallback."""
                hash_val = hashlib.md5(text.encode()).hexdigest()
                return [int(hash_val[i:i + 2], 16) / 255.0 for i in range(0, min(32, len(hash_val)), 2)]

        return DefaultEmbedder()

    async def add_documents(self, documents: list[Document | dict[str, Any]]) -> list[str]:
        """Add documents to knowledge base."""
        if not self._initialized:
            await self.initialize()

        # Convert to Document objects
        doc_objects = []
        for doc in documents:
            if isinstance(doc, Document):
                doc_objects.append(doc)
            elif isinstance(doc, dict):
                doc_objects.append(Document(
                    doc_id=doc.get("doc_id", hashlib.md5(doc.get("content", "").encode()).hexdigest()[:12]),
                    content=doc.get("content", ""),
                    metadata=doc.get("metadata", {})
                ))

        # Chunk documents if needed
        chunked_docs = []
        for doc in doc_objects:
            chunks = self._chunk_text(doc.content, chunk_size=512, overlap=50)
            for i, chunk in enumerate(chunks):
                chunk_doc = Document(
                    doc_id=f"{doc.doc_id}_chunk_{i}",
                    content=chunk,
                    metadata={**doc.metadata, "parent_doc_id": doc.doc_id, "chunk_index": i}
                )
                chunked_docs.append(chunk_doc)

        # Generate embeddings
        texts = [d.content for d in chunked_docs]
        embeddings = await self.embedding_provider.embed(texts)

        for doc, emb in zip(chunked_docs, embeddings):
            doc.embedding = emb

        # Store in vector store
        return await self.vector_store.add(chunked_docs)

    async def search(self, query: str, k: int = 10,
                     filter_metadata: dict | None = None) -> list[SearchResult]:
        """Search knowledge base."""
        if not self._initialized:
            await self.initialize()

        query_embedding = await self.embedding_provider.embed_query(query)
        return await self.vector_store.search(query_embedding, k, filter_metadata)

    async def search_by_vector(self, embedding: list[float], k: int = 10,
                                filter_metadata: dict | None = None) -> list[SearchResult]:
        """Search by pre-computed embedding."""
        if not self._initialized:
            await self.initialize()
        return await self.vector_store.search(embedding, k, filter_metadata)

    async def get_document(self, doc_id: str) -> Document | None:
        """Get document by ID."""
        return await self.vector_store.get(doc_id)

    async def delete_documents(self, doc_ids: list[str]) -> bool:
        """Delete documents."""
        return await self.vector_store.delete(doc_ids)

    async def ingest_from_source(self, source: str, source_type: str = "auto") -> list[str]:
        """Ingest documents from various sources."""
        if not self._initialized:
            await self.initialize()

        if source_type == "auto":
            if source.startswith("http"):
                source_type = "web"
            elif Path(source).is_dir():
                source_type = "directory"
            elif Path(source).is_file():
                source_type = "file"
            else:
                source_type = "text"

        documents = []

        if source_type == "file":
            content = Path(source).read_text()
            documents.append(Document(
                doc_id=hashlib.md5(source.encode()).hexdigest()[:12],
                content=content,
                metadata={"source": source, "source_type": "file"}
            ))

        elif source_type == "directory":
            for file_path in Path(source).rglob("*"):
                if file_path.is_file() and file_path.suffix in ['.py', '.md', '.txt', '.json', '.yaml', '.yml']:
                    try:
                        content = file_path.read_text()
                        documents.append(Document(
                            doc_id=hashlib.md5(str(file_path).encode()).hexdigest()[:12],
                            content=content,
                            metadata={"source": str(file_path), "source_type": "file"}
                        ))
                    except Exception:
                        pass

        elif source_type == "web":
            # Would use RedAmon's data ingestion
            pass

        elif source_type == "text":
            documents.append(Document(
                doc_id=hashlib.md5(source.encode()).hexdigest()[:12],
                content=source,
                metadata={"source_type": "text"}
            ))

        return await self.add_documents(documents)

    async def get_stats(self) -> dict[str, Any]:
        """Get knowledge base statistics."""
        return {
            "initialized": self._initialized,
            "document_count": len(await self.vector_store._documents) if hasattr(self.vector_store, '_documents') else 0,
            "embedding_model": getattr(self.embedding_provider, '__class__', {}).get('__name__', 'unknown')
        }


class KnowledgeBaseIntegration:
    """High-level integration for AGENT_SYSTEM_V9."""

    def __init__(self):
        self._knowledge_bases: dict[str, KnowledgeBase] = {}

    def create_knowledge_base(self, name: str, config: dict | None = None) -> KnowledgeBase:
        """Create a named knowledge base."""
        kb = KnowledgeBase(config)
        self._knowledge_bases[name] = kb
        return kb

    def get_knowledge_base(self, name: str) -> KnowledgeBase | None:
        """Get knowledge base by name."""
        return self._knowledge_bases.get(name)

    def list_knowledge_bases(self) -> list[str]:
        """List all knowledge base names."""
        return list(self._knowledge_bases.keys())

    async def close(self, name: str):
        """Close knowledge base."""
        if name in self._knowledge_bases:
            del self._knowledge_bases[name]


_kb_integration: KnowledgeBaseIntegration | None = None


def get_knowledge_base_integration() -> KnowledgeBaseIntegration:
    """Get global knowledge base integration."""
    global _kb_integration
    if _kb_integration is None:
        _kb_integration = KnowledgeBaseIntegration()
    return _kb_integration


# Alias for AGENT_SYSTEM_V9 main package to avoid naming conflict with memory.SearchResult
KBSearchResult = SearchResult

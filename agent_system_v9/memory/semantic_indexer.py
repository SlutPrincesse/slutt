import asyncio
import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

import numpy as np


class IndexBackend(Enum):
    IN_MEMORY = "in_memory"
    FAISS = "faiss"
    CHROMA = "chroma"
    QDRANT = "qdrant"
    WEVIATE = "weaviate"


@dataclass
class IndexConfig:
    backend: IndexBackend = IndexBackend.IN_MEMORY
    embedding_dim: int = 768
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    chunk_size: int = 512
    chunk_overlap: int = 50
    max_documents: int = 100000
    similarity_threshold: float = 0.7
    use_hybrid_search: bool = True
    bm25_weight: float = 0.3
    vector_weight: float = 0.7
    persist_path: Path | None = None


@dataclass
class Document:
    id: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    embedding: list[float] | None = None
    chunks: list[str] = field(default_factory=list)
    chunk_embeddings: list[list[float]] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def __post_init__(self):
        if not self.id:
            self.id = hashlib.sha256(self.content.encode()).hexdigest()[:16]


@dataclass
class SearchResult:
    document: Document
    score: float
    matched_chunks: list[str] = field(default_factory=list)
    match_type: str = "vector"


class EmbeddingProvider:
    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        self.model_name = model_name
        self._model = None

    def _load_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self.model_name)
            except ImportError:
                raise RuntimeError("sentence-transformers not installed. Install with: pip install sentence-transformers")

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self._load_model()
        loop = asyncio.get_event_loop()
        embeddings = await loop.run_in_executor(None, self._model.encode, texts)
        return embeddings.tolist()

    async def embed_single(self, text: str) -> list[float]:
        return (await self.embed([text]))[0]


class InMemoryVectorIndex:
    def __init__(self, dim: int):
        self.dim = dim
        self.vectors: np.ndarray = np.zeros((0, dim), dtype=np.float32)
        self.doc_ids: list[str] = []
        self.id_to_index: dict[str, int] = {}

    def add(self, doc_id: str, vector: list[float]):
        if doc_id in self.id_to_index:
            idx = self.id_to_index[doc_id]
            self.vectors[idx] = vector
        else:
            idx = len(self.doc_ids)
            self.doc_ids.append(doc_id)
            self.id_to_index[doc_id] = idx
            self.vectors = np.vstack([self.vectors, np.array(vector, dtype=np.float32).reshape(1, -1)])

    def search(self, query_vector: list[float], k: int = 10) -> list[tuple[str, float]]:
        if len(self.doc_ids) == 0:
            return []

        query_vec = np.array(query_vector, dtype=np.float32).reshape(1, -1)
        similarities = np.dot(self.vectors, query_vec.T).flatten()
        top_k = min(k, len(self.doc_ids))
        top_indices = np.argpartition(similarities, -top_k)[-top_k:]
        top_indices = top_indices[np.argsort(similarities[top_indices])[::-1]]

        return [(self.doc_ids[i], float(similarities[i])) for i in top_indices]

    def remove(self, doc_id: str):
        if doc_id not in self.id_to_index:
            return
        idx = self.id_to_index[doc_id]
        self.vectors = np.delete(self.vectors, idx, axis=0)
        self.doc_ids.pop(idx)
        self.id_to_index = {doc_id: i for i, doc_id in enumerate(self.doc_ids)}

    def clear(self):
        self.vectors = np.zeros((0, self.dim), dtype=np.float32)
        self.doc_ids.clear()
        self.id_to_index.clear()

    def save(self, path: Path):
        np.savez(path, vectors=self.vectors, doc_ids=self.doc_ids)

    def load(self, path: Path):
        data = np.load(path)
        self.vectors = data["vectors"]
        self.doc_ids = data["doc_ids"].tolist()
        self.id_to_index = {doc_id: i for i, doc_id in enumerate(self.doc_ids)}


class SemanticIndexer:
    def __init__(self, config: IndexConfig = None):
        self.config = config or IndexConfig()
        self.documents: dict[str, Document] = {}
        self.index = InMemoryVectorIndex(self.config.embedding_dim)
        self.embedding_provider = EmbeddingProvider(self.config.embedding_model)
        self._bm25_index: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self._doc_frequencies: dict[str, int] = defaultdict(int)
        self._total_docs = 0

    async def add_document(self, document: Document) -> str:
        if len(self.documents) >= self.config.max_documents:
            raise ValueError("Maximum documents reached")

        document.chunks = self._chunk_text(document.content)
        document.chunk_embeddings = await self.embedding_provider.embed(document.chunks)

        if document.chunk_embeddings:
            avg_embedding = np.mean(document.chunk_embeddings, axis=0).tolist()
            document.embedding = avg_embedding
            self.index.add(document.id, avg_embedding)

        self._update_bm25(document)
        self.documents[document.id] = document
        self._total_docs += 1

        return document.id

    async def add_text(self, content: str, metadata: dict[str, Any] = None) -> str:
        doc = Document(content=content, metadata=metadata or {})
        return await self.add_document(doc)

    def _chunk_text(self, text: str) -> list[str]:
        chunks = []
        words = text.split()
        for i in range(0, len(words), self.config.chunk_size - self.config.chunk_overlap):
            chunk = " ".join(words[i:i + self.config.chunk_size])
            if chunk:
                chunks.append(chunk)
        return chunks

    def _update_bm25(self, document: Document):
        import re
        from collections import Counter

        tokens = re.findall(r'\w+', document.content.lower())
        token_counts = Counter(tokens)

        for token, count in token_counts.items():
            self._bm25_index[document.id][token] = count
            self._doc_frequencies[token] += 1

    def _bm25_score(self, query_tokens: list[str], doc_id: str) -> float:
        k1 = 1.5
        b = 0.75

        doc_len = sum(self._bm25_index[doc_id].values())
        avg_doc_len = sum(sum(v.values()) for v in self._bm25_index.values()) / max(1, len(self._bm25_index))

        score = 0.0
        for token in query_tokens:
            if token not in self._doc_frequencies:
                continue
            tf = self._bm25_index[doc_id].get(token, 0)
            idf = np.log((self._total_docs - self._doc_frequencies[token] + 0.5) / (self._doc_frequencies[token] + 0.5) + 1)
            score += idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * doc_len / avg_doc_len))

        return score

    async def search(
        self,
        query: str,
        k: int = 10,
        filter_metadata: dict[str, Any] = None,
        threshold: float = None,
    ) -> list[SearchResult]:
        threshold = threshold or self.config.similarity_threshold
        query_embedding = await self.embedding_provider.embed_single(query)

        vector_results = self.index.search(query_embedding, k * 2)

        query_tokens = query.lower().split()

        results = []
        for doc_id, vector_score in vector_results:
            if doc_id not in self.documents:
                continue
            doc = self.documents[doc_id]

            if filter_metadata:
                match = all(doc.metadata.get(k) == v for k, v in filter_metadata.items())
                if not match:
                    continue

            if self.config.use_hybrid_search:
                bm25_score = self._bm25_score(query_tokens, doc_id)
                combined_score = (self.config.vector_weight * vector_score +
                                 self.config.bm25_weight * bm25_score)
            else:
                combined_score = vector_score

            if combined_score >= threshold:
                matched_chunks = []
                for i, chunk_emb in enumerate(doc.chunk_embeddings):
                    chunk_score = np.dot(query_embedding, chunk_emb) / (np.linalg.norm(query_embedding) * np.linalg.norm(chunk_emb))
                    if chunk_score >= threshold:
                        matched_chunks.append(doc.chunks[i])

                results.append(SearchResult(
                    document=doc,
                    score=combined_score,
                    matched_chunks=matched_chunks[:3],
                    match_type="hybrid" if self.config.use_hybrid_search else "vector",
                ))

        results.sort(key=lambda x: x.score, reverse=True)
        return results[:k]

    async def search_by_vector(self, vector: list[float], k: int = 10) -> list[SearchResult]:
        vector_results = self.index.search(vector, k)
        results = []
        for doc_id, score in vector_results:
            if doc_id in self.documents:
                results.append(SearchResult(
                    document=self.documents[doc_id],
                    score=score,
                    match_type="vector",
                ))
        return results

    def get_document(self, doc_id: str) -> Document | None:
        return self.documents.get(doc_id)

    def update_document(self, doc_id: str, content: str = None, metadata: dict[str, Any] = None) -> bool:
        if doc_id not in self.documents:
            return False

        doc = self.documents[doc_id]

        if content is not None:
            self._remove_from_bm25(doc)
            doc.content = content
            doc.chunks = self._chunk_text(content)
            doc.chunk_embeddings = asyncio.run(self.embedding_provider.embed(doc.chunks))
            if doc.chunk_embeddings:
                doc.embedding = np.mean(doc.chunk_embeddings, axis=0).tolist()
                self.index.add(doc_id, doc.embedding)
            self._update_bm25(doc)

        if metadata is not None:
            doc.metadata.update(metadata)

        doc.updated_at = datetime.utcnow().isoformat()
        return True

    def _remove_from_bm25(self, document: Document):
        for token, count in self._bm25_index[document.id].items():
            self._doc_frequencies[token] -= count
            if self._doc_frequencies[token] <= 0:
                del self._doc_frequencies[token]
        del self._bm25_index[document.id]

    def remove_document(self, doc_id: str) -> bool:
        if doc_id not in self.documents:
            return False
        doc = self.documents[doc_id]
        self._remove_from_bm25(doc)
        self.index.remove(doc_id)
        del self.documents[doc_id]
        self._total_docs -= 1
        return True

    def get_stats(self) -> dict[str, Any]:
        return {
            "total_documents": len(self.documents),
            "total_chunks": sum(len(d.chunks) for d in self.documents.values()),
            "vocabulary_size": len(self._doc_frequencies),
            "index_size": len(self.index.doc_ids),
        }

    async def persist(self, path: Path = None):
        path = path or self.config.persist_path
        if not path:
            return
        path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "config": {
                "embedding_dim": self.config.embedding_dim,
                "embedding_model": self.config.embedding_model,
                "chunk_size": self.config.chunk_size,
                "chunk_overlap": self.config.chunk_overlap,
            },
            "documents": {k: {
                "id": v.id,
                "content": v.content,
                "metadata": v.metadata,
                "embedding": v.embedding,
                "chunks": v.chunks,
                "chunk_embeddings": v.chunk_embeddings,
                "created_at": v.created_at,
                "updated_at": v.updated_at,
            } for k, v in self.documents.items()},
        }

        path.write_text(json.dumps(data, indent=2))
        self.index.save(path.with_suffix(".npz"))

    async def load(self, path: Path = None):
        path = path or self.config.persist_path
        if not path or not path.exists():
            return

        data = json.loads(path.read_text())
        for doc_id, doc_data in data.get("documents", {}).items():
            doc = Document(
                id=doc_data["id"],
                content=doc_data["content"],
                metadata=doc_data["metadata"],
                embedding=doc_data.get("embedding"),
                chunks=doc_data.get("chunks", []),
                chunk_embeddings=doc_data.get("chunk_embeddings", []),
                created_at=doc_data["created_at"],
                updated_at=doc_data["updated_at"],
            )
            self.documents[doc_id] = doc
            if doc.embedding:
                self.index.add(doc_id, doc.embedding)
            self._update_bm25(doc)

        self._total_docs = len(self.documents)

        index_path = path.with_suffix(".npz")
        if index_path.exists():
            self.index.load(index_path)

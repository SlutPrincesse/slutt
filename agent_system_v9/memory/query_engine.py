from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from .code_memory import CodeMemory, CodeNode, EdgeType, NodeType
from .episodic_store import Episode, EpisodeType, EpisodicStore
from .knowledge_graph import Entity, EntityType, KnowledgeGraph, Relation, RelationType
from .semantic_indexer import SearchResult, SemanticIndexer


class QueryType(Enum):
    SEMANTIC_SEARCH = "semantic_search"
    GRAPH_TRAVERSAL = "graph_traversal"
    CODE_LOOKUP = "code_lookup"
    EPISODE_RECALL = "episode_recall"
    HYBRID = "hybrid"
    STRUCTURAL = "structural"
    TEMPORAL = "temporal"


@dataclass
class QueryPlan:
    query_type: QueryType
    steps: list[dict[str, Any]]
    estimated_cost: float
    requires_embedding: bool = False
    requires_graph: bool = False


@dataclass
class QueryResult:
    query: str
    query_type: QueryType
    results: list[Any]
    metadata: dict[str, Any] = field(default_factory=dict)
    execution_time_ms: float = 0.0
    plan: QueryPlan | None = None


class QueryEngine:
    def __init__(
        self,
        code_memory: CodeMemory = None,
        episodic_store: EpisodicStore = None,
        semantic_indexer: SemanticIndexer = None,
        knowledge_graph: KnowledgeGraph = None,
    ):
        self.code_memory = code_memory or CodeMemory()
        self.episodic_store = episodic_store or EpisodicStore()
        self.semantic_indexer = semantic_indexer or SemanticIndexer()
        self.knowledge_graph = knowledge_graph or KnowledgeGraph()

        self._query_cache: dict[str, QueryResult] = {}
        self._cache_ttl = 300

    async def execute(self, query: str, query_type: QueryType = None, **kwargs) -> QueryResult:
        import time
        start_time = time.time()

        if query_type is None:
            query_type = self._infer_query_type(query)

        plan = self._create_plan(query, query_type)

        cache_key = f"{query_type.value}:{query}"
        if cache_key in self._query_cache:
            cached = self._query_cache[cache_key]
            cached.metadata["cached"] = True
            return cached

        results = await self._execute_plan(query, plan, **kwargs)

        result = QueryResult(
            query=query,
            query_type=query_type,
            results=results,
            execution_time_ms=(time.time() - start_time) * 1000,
            plan=plan,
        )

        self._query_cache[cache_key] = result
        return result

    def _infer_query_type(self, query: str) -> QueryType:
        query_lower = query.lower()

        if any(kw in query_lower for kw in ["find", "search", "look for", "similar"]):
            return QueryType.SEMANTIC_SEARCH
        if any(kw in query_lower for kw in ["call graph", "dependencies", "inheritance", "relationship"]):
            return QueryType.GRAPH_TRAVERSAL
        if any(kw in query_lower for kw in ["function", "class", "method", "variable", "definition"]):
            return QueryType.CODE_LOOKUP
        if any(kw in query_lower for kw in ["what happened", "when did", "history", "previous", "last time"]):
            return QueryType.EPISODE_RECALL
        if any(kw in query_lower for kw in ["structure", "architecture", "modules", "components"]):
            return QueryType.STRUCTURAL
        if any(kw in query_lower for kw in ["timeline", "sequence", "order", "before", "after"]):
            return QueryType.TEMPORAL
        return QueryType.HYBRID

    def _create_plan(self, query: str, query_type: QueryType) -> QueryPlan:
        steps = []
        estimated_cost = 0.0
        requires_embedding = False
        requires_graph = False

        if query_type == QueryType.SEMANTIC_SEARCH:
            steps = [
                {"action": "embed_query", "query": query},
                {"action": "vector_search", "k": 20},
                {"action": "rerank", "method": "hybrid"},
                {"action": "filter", "criteria": {}},
            ]
            estimated_cost = 50.0
            requires_embedding = True

        elif query_type == QueryType.GRAPH_TRAVERSAL:
            steps = [
                {"action": "identify_entities", "query": query},
                {"action": "graph_traversal", "depth": 3},
                {"action": "format_results"},
            ]
            estimated_cost = 30.0
            requires_graph = True

        elif query_type == QueryType.CODE_LOOKUP:
            steps = [
                {"action": "parse_query", "query": query},
                {"action": "code_memory_lookup", "by_name": True},
                {"action": "code_memory_lookup", "by_type": True},
                {"action": "format_results"},
            ]
            estimated_cost = 10.0

        elif query_type == QueryType.EPISODE_RECALL:
            steps = [
                {"action": "parse_temporal_query", "query": query},
                {"action": "episodic_store_search"},
                {"action": "filter_by_time"},
                {"action": "format_results"},
            ]
            estimated_cost = 20.0

        elif query_type == QueryType.HYBRID:
            steps = [
                {"action": "embed_query", "query": query},
                {"action": "vector_search", "k": 10},
                {"action": "identify_entities", "query": query},
                {"action": "graph_traversal", "depth": 2},
                {"action": "merge_results"},
                {"action": "rerank"},
            ]
            estimated_cost = 80.0
            requires_embedding = True
            requires_graph = True

        elif query_type == QueryType.STRUCTURAL:
            steps = [
                {"action": "get_modules"},
                {"action": "get_dependencies"},
                {"action": "analyze_structure"},
                {"action": "format_results"},
            ]
            estimated_cost = 40.0
            requires_graph = True

        elif query_type == QueryType.TEMPORAL:
            steps = [
                {"action": "episodic_store_recent", "limit": 50},
                {"action": "filter_by_time_range"},
                {"action": "sort_by_time"},
                {"action": "format_results"},
            ]
            estimated_cost = 15.0

        return QueryPlan(
            query_type=query_type,
            steps=steps,
            estimated_cost=estimated_cost,
            requires_embedding=requires_embedding,
            requires_graph=requires_graph,
        )

    async def _execute_plan(self, query: str, plan: QueryPlan, **kwargs) -> list[Any]:
        if plan.query_type == QueryType.SEMANTIC_SEARCH:
            return await self._semantic_search(query, **kwargs)
        if plan.query_type == QueryType.GRAPH_TRAVERSAL:
            return await self._graph_traversal(query, **kwargs)
        if plan.query_type == QueryType.CODE_LOOKUP:
            return await self._code_lookup(query, **kwargs)
        if plan.query_type == QueryType.EPISODE_RECALL:
            return await self._episode_recall(query, **kwargs)
        if plan.query_type == QueryType.HYBRID:
            return await self._hybrid_search(query, **kwargs)
        if plan.query_type == QueryType.STRUCTURAL:
            return await self._structural_analysis(query, **kwargs)
        if plan.query_type == QueryType.TEMPORAL:
            return await self._temporal_query(query, **kwargs)
        return []

    async def _semantic_search(self, query: str, k: int = 10, **kwargs) -> list[SearchResult]:
        return await self.semantic_indexer.search(query, k=k, **kwargs)

    async def _graph_traversal(self, query: str, depth: int = 3, **kwargs) -> list[dict[str, Any]]:
        entities = self._extract_entities_from_query(query)
        results = []

        for entity in entities:
            graph_entities = self.knowledge_graph.get_entities_by_name(entity)
            for ge in graph_entities:
                subgraph = self.knowledge_graph.get_subgraph([ge.id], depth=depth)
                results.append({
                    "entity": ge.to_dict(),
                    "subgraph": subgraph,
                })

        return results

    def _extract_entities_from_query(self, query: str) -> list[str]:
        import re
        words = re.findall(r'\b[A-Za-z_][A-Za-z0-9_]*\b', query)
        return [w for w in words if len(w) > 2]

    async def _code_lookup(self, query: str, **kwargs) -> list[CodeNode]:
        results = []

        by_name = self.code_memory.get_nodes_by_name(query)
        results.extend(by_name[:10])

        for node_type in NodeType:
            if node_type.value.lower() in query.lower():
                by_type = self.code_memory.get_nodes_by_type(node_type)
                results.extend(by_type[:10])

        return results[:20]

    async def _episode_recall(self, query: str, limit: int = 20, **kwargs) -> list[Episode]:
        results = self.episodic_store.search(query, limit=limit)

        if "recent" in query.lower() or "latest" in query.lower():
            results = self.episodic_store.get_recent(limit=limit)

        return results

    async def _hybrid_search(self, query: str, k: int = 10, **kwargs) -> list[dict[str, Any]]:
        semantic_results = await self.semantic_indexer.search(query, k=k)
        graph_results = await self._graph_traversal(query, depth=2)
        code_results = await self._code_lookup(query)

        merged = []

        for sr in semantic_results:
            merged.append({
                "source": "semantic",
                "score": sr.score,
                "data": sr.document.to_dict(),
                "matched_chunks": sr.matched_chunks,
            })

        for gr in graph_results:
            merged.append({
                "source": "graph",
                "score": 0.8,
                "data": gr,
            })

        for cr in code_results:
            merged.append({
                "source": "code",
                "score": 0.7,
                "data": cr.to_dict(),
            })

        merged.sort(key=lambda x: x["score"], reverse=True)
        return merged[:k]

    async def _structural_analysis(self, query: str, **kwargs) -> list[dict[str, Any]]:
        modules = self.code_memory.get_nodes_by_type(NodeType.MODULE)
        files = self.code_memory.get_nodes_by_type(NodeType.FILE)

        results = []
        for module in modules[:10]:
            deps = self.code_memory.get_neighbors(module.id, EdgeType.IMPORTS, "outgoing")
            results.append({
                "module": module.to_dict(),
                "dependencies": [d.to_dict() for d in deps[:10]],
            })

        return results

    async def _temporal_query(self, query: str, limit: int = 50, **kwargs) -> list[Episode]:
        return self.episodic_store.get_recent(limit=limit)

    def ingest_code_analysis(self, file_path: str, analysis: dict[str, Any]):
        for func in analysis.get("functions", []):
            node = CodeNode(
                id="",
                node_type=NodeType.FUNCTION,
                name=func["name"],
                qualified_name=f"{file_path}:{func['name']}",
                file_path=file_path,
                start_line=func["start_line"],
                end_line=func["end_line"],
                content=func.get("code", ""),
                summary=func.get("summary", ""),
                metadata={"analysis": func},
            )
            self.code_memory.add_node(node)

        for cls in analysis.get("classes", []):
            node = CodeNode(
                id="",
                node_type=NodeType.CLASS,
                name=cls["name"],
                qualified_name=f"{file_path}:{cls['name']}",
                file_path=file_path,
                start_line=cls["start_line"],
                end_line=cls["end_line"],
                content=cls.get("code", ""),
                summary=cls.get("summary", ""),
                metadata={"analysis": cls},
            )
            self.code_memory.add_node(node)

        for imp in analysis.get("imports", []):
            node = CodeNode(
                id="",
                node_type=NodeType.IMPORT,
                name=imp["name"],
                qualified_name=f"{file_path}:import:{imp['name']}",
                file_path=file_path,
                start_line=imp.get("line", 0),
                end_line=imp.get("line", 0),
                content=imp.get("statement", ""),
                metadata={"analysis": imp},
            )
            self.code_memory.add_node(node)

    def ingest_ablation_findings(self, findings: list[dict[str, Any]], source: str = "ablation"):
        for finding in findings:
            entity = Entity(
                id="",
                entity_type=EntityType.FINDING,
                name=finding.get("type", "finding"),
                qualified_name=f"{source}:{finding.get('id', 'unknown')}",
                properties=finding,
                description=finding.get("description", ""),
                source=source,
                confidence=finding.get("confidence", 0.8),
            )
            self.knowledge_graph.add_entity(entity)

            if "location" in finding:
                loc_entity = Entity(
                    id="",
                    entity_type=EntityType.CODE_FILE,
                    name=finding["location"].get("file", "unknown"),
                    qualified_name=finding["location"].get("file", "unknown"),
                    properties=finding["location"],
                    source=source,
                )
                self.knowledge_graph.add_entity(loc_entity)

                relation = Relation(
                    id="",
                    source_id=entity.id,
                    target_id=loc_entity.id,
                    relation_type=RelationType.REFERENCES,
                    properties={"finding_type": finding.get("type")},
                )
                self.knowledge_graph.add_relation(relation)

    def ingest_corecoder_result(self, task: str, result: dict[str, Any], source: str = "corecoder"):
        episode = Episode(
            id="",
            episode_type=EpisodeType.TASK_EXECUTION,
            title=f"CoreCoder: {task[:100]}",
            description=task,
            input_data={"task": task},
            output_data=result,
            status=EpisodeType.COMPLETED if result.get("success") else EpisodeType.FAILED,
            tags=["corecoder", "code_generation"],
            source=source,
        )
        self.episodic_store.add_episode(episode)

        if result.get("files_modified"):
            for file_path in result["files_modified"]:
                entity = Entity(
                    id="",
                    entity_type=EntityType.CODE_FILE,
                    name=file_path,
                    qualified_name=file_path,
                    properties={"modified_by": "corecoder", "task": task},
                    source=source,
                )
                self.knowledge_graph.add_entity(entity)

    def get_stats(self) -> dict[str, Any]:
        return {
            "code_memory": self.code_memory.get_stats(),
            "episodic_store": self.episodic_store.get_stats(),
            "semantic_indexer": self.semantic_indexer.get_stats(),
            "knowledge_graph": self.knowledge_graph.get_stats(),
        }

    async def persist_all(self, base_path: Path):
        base_path.mkdir(parents=True, exist_ok=True)

        self.code_memory.save(base_path / "code_memory.json")
        self.episodic_store.save(base_path / "episodic_store.json")
        await self.semantic_indexer.persist(base_path / "semantic_indexer.json")
        self.knowledge_graph.save(base_path / "knowledge_graph.json")

    async def load_all(self, base_path: Path):
        self.code_memory.load(base_path / "code_memory.json")
        self.episodic_store.load(base_path / "episodic_store.json")
        await self.semantic_indexer.load(base_path / "semantic_indexer.json")
        self.knowledge_graph.load(base_path / "knowledge_graph.json")

    def clear_cache(self):
        self._query_cache.clear()

"""
Automated Feature Engineering & Telemetry Analytics - Deep Feature Synthesis
"""
import asyncio
import hashlib
import itertools
import json
import time
from typing import Dict, List, Optional, Any, Callable, Set, Tuple, Union
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from collections import defaultdict
import math
import statistics


class PrimitiveType(Enum):
    AGGREGATION = "aggregation"
    TRANSFORMATION = "transformation"
    CUSTOM = "custom"


class DataType(Enum):
    NUMERIC = "numeric"
    CATEGORICAL = "categorical"
    DATETIME = "datetime"
    BOOLEAN = "boolean"
    TEXT = "text"
    ID = "id"


@dataclass
class Primitive:
    name: str
    primitive_type: PrimitiveType
    input_types: List[DataType]
    return_type: DataType
    function: Callable
    description: str = ""
    commutative: bool = False
    number_output_features: int = 1

    def __call__(self, *args, **kwargs):
        return self.function(*args, **kwargs)


@dataclass
class Entity:
    entity_id: str
    dataframe: List[Dict[str, Any]]
    index: str
    time_index: str = ""
    variables: Dict[str, DataType] = field(default_factory=dict)
    relationships: List['Relationship'] = field(default_factory=list)


@dataclass
class Relationship:
    parent_entity_id: str
    parent_variable: str
    child_entity_id: str
    child_variable: str


@dataclass
class EntitySet:
    id: str
    entities: Dict[str, Entity] = field(default_factory=dict)
    relationships: List[Relationship] = field(default_factory=list)

    def add_entity(self, entity: Entity):
        self.entities[entity.entity_id] = entity
        for rel in entity.relationships:
            self.relationships.append(rel)

    def add_relationship(self, relationship: Relationship):
        self.relationships.append(relationship)
        parent = self.entities.get(relationship.parent_entity_id)
        child = self.entities.get(relationship.child_entity_id)
        if parent and child:
            parent.relationships.append(relationship)
            child.relationships.append(relationship)


@dataclass
class Feature:
    name: str
    entity_id: str
    primitive: Primitive
    base_features: List['Feature'] = field(default_factory=list)
    parameters: Dict[str, Any] = field(default_factory=dict)
    data_type: DataType = DataType.NUMERIC

    def __hash__(self):
        return hash(self.name)


@dataclass
class FeatureVector:
    features: Dict[str, List[Any]]
    entity_id: str
    index: List[Any]

    def to_dataframe(self) -> List[Dict]:
        rows = []
        for i in range(len(self.index)):
            row = {self.entity_id + "_index": self.index[i]}
            for fname, values in self.features.items():
                row[fname] = values[i] if i < len(values) else None
            rows.append(row)
        return rows


class PrimitiveLibrary:
    def __init__(self):
        self.primitives: Dict[str, Primitive] = {}
        self._register_default_primitives()

    def _register_default_primitives(self):
        # Aggregation primitives
        self.add_primitive(Primitive(
            name="SUM",
            primitive_type=PrimitiveType.AGGREGATION,
            input_types=[DataType.NUMERIC],
            return_type=DataType.NUMERIC,
            function=lambda x: sum(v for v in x if v is not None),
            description="Sum of values",
        ))
        
        self.add_primitive(Primitive(
            name="MEAN",
            primitive_type=PrimitiveType.AGGREGATION,
            input_types=[DataType.NUMERIC],
            return_type=DataType.NUMERIC,
            function=lambda x: statistics.mean([v for v in x if v is not None]) if any(v is not None for v in x) else 0,
            description="Mean of values",
        ))
        
        self.add_primitive(Primitive(
            name="STD",
            primitive_type=PrimitiveType.AGGREGATION,
            input_types=[DataType.NUMERIC],
            return_type=DataType.NUMERIC,
            function=lambda x: statistics.stdev([v for v in x if v is not None]) if len([v for v in x if v is not None]) > 1 else 0,
            description="Standard deviation",
        ))
        
        self.add_primitive(Primitive(
            name="MIN",
            primitive_type=PrimitiveType.AGGREGATION,
            input_types=[DataType.NUMERIC, DataType.DATETIME],
            return_type=DataType.NUMERIC,
            function=lambda x: min(v for v in x if v is not None),
            description="Minimum value",
        ))
        
        self.add_primitive(Primitive(
            name="MAX",
            primitive_type=PrimitiveType.AGGREGATION,
            input_types=[DataType.NUMERIC, DataType.DATETIME],
            return_type=DataType.NUMERIC,
            function=lambda x: max(v for v in x if v is not None),
            description="Maximum value",
        ))
        
        self.add_primitive(Primitive(
            name="COUNT",
            primitive_type=PrimitiveType.AGGREGATION,
            input_types=[DataType.NUMERIC, DataType.CATEGORICAL, DataType.BOOLEAN],
            return_type=DataType.NUMERIC,
            function=lambda x: len([v for v in x if v is not None]),
            description="Count of non-null values",
        ))
        
        self.add_primitive(Primitive(
            name="MODE",
            primitive_type=PrimitiveType.AGGREGATION,
            input_types=[DataType.CATEGORICAL],
            return_type=DataType.CATEGORICAL,
            function=lambda x: max(set(v for v in x if v is not None), key=list(x).count) if any(v is not None for v in x) else None,
            description="Most common value",
        ))
        
        self.add_primitive(Primitive(
            name="NUM_UNIQUE",
            primitive_type=PrimitiveType.AGGREGATION,
            input_types=[DataType.CATEGORICAL],
            return_type=DataType.NUMERIC,
            function=lambda x: len(set(v for v in x if v is not None)),
            description="Number of unique values",
        ))
        
        # Transformation primitives
        self.add_primitive(Primitive(
            name="ADD",
            primitive_type=PrimitiveType.TRANSFORMATION,
            input_types=[DataType.NUMERIC, DataType.NUMERIC],
            return_type=DataType.NUMERIC,
            function=lambda x, y: (x or 0) + (y or 0),
            description="Add two numeric values",
            commutative=True,
        ))
        
        self.add_primitive(Primitive(
            name="SUBTRACT",
            primitive_type=PrimitiveType.TRANSFORMATION,
            input_types=[DataType.NUMERIC, DataType.NUMERIC],
            return_type=DataType.NUMERIC,
            function=lambda x, y: (x or 0) - (y or 0),
            description="Subtract y from x",
        ))
        
        self.add_primitive(Primitive(
            name="MULTIPLY",
            primitive_type=PrimitiveType.TRANSFORMATION,
            input_types=[DataType.NUMERIC, DataType.NUMERIC],
            return_type=DataType.NUMERIC,
            function=lambda x, y: (x or 0) * (y or 0),
            description="Multiply two numeric values",
            commutative=True,
        ))
        
        self.add_primitive(Primitive(
            name="DIVIDE",
            primitive_type=PrimitiveType.TRANSFORMATION,
            input_types=[DataType.NUMERIC, DataType.NUMERIC],
            return_type=DataType.NUMERIC,
            function=lambda x, y: (x or 0) / (y or 1) if (y or 1) != 0 else 0,
            description="Divide x by y",
        ))
        
        self.add_primitive(Primitive(
            name="ABS",
            primitive_type=PrimitiveType.TRANSFORMATION,
            input_types=[DataType.NUMERIC],
            return_type=DataType.NUMERIC,
            function=lambda x: abs(x or 0),
            description="Absolute value",
        ))
        
        self.add_primitive(Primitive(
            name="LOG",
            primitive_type=PrimitiveType.TRANSFORMATION,
            input_types=[DataType.NUMERIC],
            return_type=DataType.NUMERIC,
            function=lambda x: math.log(x) if x and x > 0 else 0,
            description="Natural logarithm",
        ))
        
        self.add_primitive(Primitive(
            name="SQRT",
            primitive_type=PrimitiveType.TRANSFORMATION,
            input_types=[DataType.NUMERIC],
            return_type=DataType.NUMERIC,
            function=lambda x: math.sqrt(x) if x and x >= 0 else 0,
            description="Square root",
        ))
        
        self.add_primitive(Primitive(
            name="IS_NULL",
            primitive_type=PrimitiveType.TRANSFORMATION,
            input_types=[DataType.NUMERIC, DataType.CATEGORICAL, DataType.DATETIME, DataType.BOOLEAN],
            return_type=DataType.BOOLEAN,
            function=lambda x: x is None,
            description="Check if value is null",
        ))
        
        self.add_primitive(Primitive(
            name="NOT",
            primitive_type=PrimitiveType.TRANSFORMATION,
            input_types=[DataType.BOOLEAN],
            return_type=DataType.BOOLEAN,
            function=lambda x: not x,
            description="Logical NOT",
        ))
        
        self.add_primitive(Primitive(
            name="AND",
            primitive_type=PrimitiveType.TRANSFORMATION,
            input_types=[DataType.BOOLEAN, DataType.BOOLEAN],
            return_type=DataType.BOOLEAN,
            function=lambda x, y: (x or False) and (y or False),
            description="Logical AND",
            commutative=True,
        ))
        
        self.add_primitive(Primitive(
            name="OR",
            primitive_type=PrimitiveType.TRANSFORMATION,
            input_types=[DataType.BOOLEAN, DataType.BOOLEAN],
            return_type=DataType.BOOLEAN,
            function=lambda x, y: (x or False) or (y or False),
            description="Logical OR",
            commutative=True,
        ))
        
        # Datetime primitives
        self.add_primitive(Primitive(
            name="YEAR",
            primitive_type=PrimitiveType.TRANSFORMATION,
            input_types=[DataType.DATETIME],
            return_type=DataType.NUMERIC,
            function=lambda x: x.year if hasattr(x, 'year') else 0,
            description="Extract year from datetime",
        ))
        
        self.add_primitive(Primitive(
            name="MONTH",
            primitive_type=PrimitiveType.TRANSFORMATION,
            input_types=[DataType.DATETIME],
            return_type=DataType.NUMERIC,
            function=lambda x: x.month if hasattr(x, 'month') else 0,
            description="Extract month from datetime",
        ))
        
        self.add_primitive(Primitive(
            name="DAY",
            primitive_type=PrimitiveType.TRANSFORMATION,
            input_types=[DataType.DATETIME],
            return_type=DataType.NUMERIC,
            function=lambda x: x.day if hasattr(x, 'day') else 0,
            description="Extract day from datetime",
        ))
        
        self.add_primitive(Primitive(
            name="HOUR",
            primitive_type=PrimitiveType.TRANSFORMATION,
            input_types=[DataType.DATETIME],
            return_type=DataType.NUMERIC,
            function=lambda x: x.hour if hasattr(x, 'hour') else 0,
            description="Extract hour from datetime",
        ))
        
        self.add_primitive(Primitive(
            name="WEEKDAY",
            primitive_type=PrimitiveType.TRANSFORMATION,
            input_types=[DataType.DATETIME],
            return_type=DataType.NUMERIC,
            function=lambda x: x.weekday() if hasattr(x, 'weekday') else 0,
            description="Extract weekday from datetime",
        ))
        
        self.add_primitive(Primitive(
            name="TIME_SINCE_PREVIOUS",
            primitive_type=PrimitiveType.TRANSFORMATION,
            input_types=[DataType.DATETIME],
            return_type=DataType.NUMERIC,
            function=lambda x: 0,
            description="Time since previous event",
        ))
        
        self.add_primitive(Primitive(
            name="CUMULATIVE_COUNT",
            primitive_type=PrimitiveType.TRANSFORMATION,
            input_types=[DataType.NUMERIC, DataType.CATEGORICAL, DataType.DATETIME, DataType.BOOLEAN],
            return_type=DataType.NUMERIC,
            function=lambda x: 0,
            description="Cumulative count",
        ))

    def add_primitive(self, primitive: Primitive):
        self.primitives[primitive.name] = primitive

    def get_primitives(self, primitive_type: PrimitiveType = None, input_type: DataType = None) -> List[Primitive]:
        result = list(self.primitives.values())
        if primitive_type:
            result = [p for p in result if p.primitive_type == primitive_type]
        if input_type:
            result = [p for p in result if input_type in p.input_types]
        return result

    def get_aggregation_primitives(self, input_type: DataType = None) -> List[Primitive]:
        return self.get_primitives(PrimitiveType.AGGREGATION, input_type)

    def get_transformation_primitives(self, input_type: DataType = None) -> List[Primitive]:
        return self.get_primitives(PrimitiveType.TRANSFORMATION, input_type)


class DeepFeatureSynthesis:
    def __init__(self, entityset: EntitySet, primitive_library: PrimitiveLibrary = None):
        self.entityset = entityset
        self.primitive_library = primitive_library or PrimitiveLibrary()
        self.features: Dict[str, List[Feature]] = defaultdict(list)
        self.feature_matrix: Dict[str, FeatureVector] = {}
        self.max_depth = 2

    def run(self, target_entity: str, max_depth: int = 2, 
            agg_primitives: List[str] = None, trans_primitives: List[str] = None,
            where_primitives: List[str] = None) -> FeatureVector:
        self.max_depth = max_depth
        
        target_entity_obj = self.entityset.entities.get(target_entity)
        if not target_entity_obj:
            raise ValueError(f"Entity {target_entity} not found")
        
        base_features = self._get_base_features(target_entity_obj)
        
        self.features[target_entity] = base_features[:]
        
        for depth in range(1, max_depth + 1):
            new_features = self._generate_features_at_depth(target_entity, depth, agg_primitives, trans_primitives)
            self.features[target_entity].extend(new_features)
        
        feature_vector = self._calculate_feature_matrix(target_entity)
        self.feature_matrix[target_entity] = feature_vector
        
        return feature_vector

    def _get_base_features(self, entity: Entity) -> List[Feature]:
        features = []
        for var_name, var_type in entity.variables.items():
            if var_name != entity.index and var_name != entity.time_index:
                features.append(Feature(
                    name=var_name,
                    entity_id=entity.entity_id,
                    primitive=Primitive(
                        name="IDENTITY",
                        primitive_type=PrimitiveType.TRANSFORMATION,
                        input_types=[var_type],
                        return_type=var_type,
                        function=lambda x: x,
                    ),
                    data_type=var_type,
                ))
        return features

    def _generate_features_at_depth(self, target_entity: str, depth: int,
                                    agg_primitives: List[str] = None,
                                    trans_primitives: List[str] = None) -> List[Feature]:
        new_features = []
        target_entity_obj = self.entityset.entities[target_entity]
        
        agg_prims = agg_primitives or [p.name for p in self.primitive_library.get_aggregation_primitives()]
        trans_prims = trans_primitives or [p.name for p in self.primitive_library.get_transformation_primitives()]
        
        for rel in self.entityset.relationships:
            if rel.child_entity_id == target_entity:
                parent_entity = self.entityset.entities.get(rel.parent_entity_id)
                if not parent_entity:
                    continue
                
                parent_features = self.features.get(rel.parent_entity_id, [])
                
                for feat in parent_features:
                    for prim_name in agg_prims:
                        prim = self.primitive_library.primitives.get(prim_name)
                        if prim and feat.data_type in prim.input_types:
                            new_feature = Feature(
                                name=f"{rel.parent_entity_id}_{feat.name}_{prim_name}",
                                entity_id=target_entity,
                                primitive=prim,
                                base_features=[feat],
                                parameters={"relationship": rel},
                                data_type=prim.return_type,
                            )
                            new_features.append(new_feature)
        
        for feat in self.features[target_entity]:
            if feat.primitive.primitive_type == PrimitiveType.TRANSFORMATION:
                continue
            
            for prim_name in trans_prims:
                prim = self.primitive_library.primitives.get(prim_name)
                if prim and feat.data_type in prim.input_types:
                    if len(prim.input_types) == 1:
                        new_feature = Feature(
                            name=f"{feat.name}_{prim_name}",
                            entity_id=target_entity,
                            primitive=prim,
                            base_features=[feat],
                            data_type=prim.return_type,
                        )
                        new_features.append(new_feature)
                    elif len(prim.input_types) == 2:
                        for feat2 in self.features[target_entity]:
                            if feat != feat2 and feat2.data_type in prim.input_types:
                                new_feature = Feature(
                                    name=f"{feat.name}_{prim_name}_{feat2.name}",
                                    entity_id=target_entity,
                                    primitive=prim,
                                    base_features=[feat, feat2],
                                    data_type=prim.return_type,
                                )
                                new_features.append(new_feature)
        
        return new_features

    def _calculate_feature_matrix(self, target_entity: str) -> FeatureVector:
        target_entity_obj = self.entityset.entities[target_entity]
        index_values = [row[target_entity_obj.index] for row in target_entity_obj.dataframe]
        
        features_dict = {}
        
        for feat in self.features[target_entity]:
            values = self._compute_feature_values(feat, target_entity_obj)
            features_dict[feat.name] = values
        
        return FeatureVector(
            features=features_dict,
            entity_id=target_entity,
            index=index_values,
        )

    def _compute_feature_values(self, feature: Feature, entity: Entity) -> List[Any]:
        if not feature.base_features:
            return [row.get(feature.name) for row in entity.dataframe]
        
        if feature.primitive.primitive_type == PrimitiveType.AGGREGATION:
            return self._compute_aggregation(feature, entity)
        else:
            return self._compute_transformation(feature, entity)

    def _compute_aggregation(self, feature: Feature, entity: Entity) -> List[Any]:
        prim = feature.primitive
        base_feat = feature.base_features[0]
        rel = feature.parameters.get("relationship")
        
        if not rel:
            return [None] * len(entity.dataframe)
        
        parent_entity = self.entityset.entities.get(rel.parent_entity_id)
        if not parent_entity:
            return [None] * len(entity.dataframe)
        
        parent_index_map = defaultdict(list)
        for i, row in enumerate(parent_entity.dataframe):
            parent_index_map[row[parent_entity.index]].append(i)
        
        child_to_parent = {}
        for i, row in enumerate(entity.dataframe):
            child_to_parent[i] = row.get(rel.child_variable)
        
        base_values = self._compute_feature_values(base_feat, parent_entity)
        
        results = []
        for i in range(len(entity.dataframe)):
            parent_key = child_to_parent.get(i)
            if parent_key and parent_key in parent_index_map:
                parent_indices = parent_index_map[parent_key]
                parent_vals = [base_values[idx] for idx in parent_indices]
                results.append(prim.function(parent_vals))
            else:
                results.append(None)
        
        return results

    def _compute_transformation(self, feature: Feature, entity: Entity) -> List[Any]:
        prim = feature.primitive
        base_values = [self._compute_feature_values(bf, entity) for bf in feature.base_features]
        
        results = []
        for i in range(len(entity.dataframe)):
            args = [bv[i] if i < len(bv) else None for bv in base_values]
            try:
                result = prim.function(*args)
                results.append(result)
            except Exception:
                results.append(None)
        
        return results


class FeatureToolsEngine:
    def __init__(self):
        self.primitive_library = PrimitiveLibrary()
        self.entitysets: Dict[str, EntitySet] = {}

    def create_entityset(self, entityset_id: str) -> EntitySet:
        es = EntitySet(id=entityset_id)
        self.entitysets[entityset_id] = es
        return es

    def add_entity(self, entityset_id: str, entity: Entity):
        if entityset_id in self.entitysets:
            self.entitysets[entityset_id].add_entity(entity)

    def add_relationship(self, entityset_id: str, relationship: Relationship):
        if entityset_id in self.entitysets:
            self.entitysets[entityset_id].add_relationship(relationship)

    def run_dfs(self, entityset_id: str, target_entity: str, **kwargs) -> FeatureVector:
        entityset = self.entitysets.get(entityset_id)
        if not entityset:
            raise ValueError(f"EntitySet {entityset_id} not found")
        
        dfs = DeepFeatureSynthesis(entityset, self.primitive_library)
        return dfs.run(target_entity, **kwargs)

    def register_primitive(self, primitive: Primitive):
        self.primitive_library.add_primitive(primitive)

    def get_feature_definitions(self, entityset_id: str, target_entity: str) -> List[Dict]:
        entityset = self.entitysets.get(entityset_id)
        if not entityset:
            return []
        
        dfs = DeepFeatureSynthesis(entityset, self.primitive_library)
        dfs.run(target_entity, max_depth=1)
        
        definitions = []
        for feat in dfs.features.get(target_entity, []):
            definitions.append({
                "name": feat.name,
                "entity": feat.entity_id,
                "primitive": feat.primitive.name,
                "type": feat.primitive.primitive_type.value,
                "base_features": [bf.name for bf in feat.base_features],
                "return_type": feat.data_type.value,
                "parameters": feat.parameters,
            })
        
        return definitions


class ExecutionLogFeatureExtractor:
    def __init__(self, engine: FeatureToolsEngine):
        self.engine = engine

    def extract_from_logs(self, logs: List[Dict], entity_name: str = "executions") -> FeatureVector:
        entity = Entity(
            entity_id=entity_name,
            dataframe=logs,
            index="execution_id",
            time_index="timestamp",
            variables={
                "execution_id": DataType.ID,
                "timestamp": DataType.DATETIME,
                "duration_ms": DataType.NUMERIC,
                "tokens_used": DataType.NUMERIC,
                "model": DataType.CATEGORICAL,
                "task_type": DataType.CATEGORICAL,
                "success": DataType.BOOLEAN,
                "error_type": DataType.CATEGORICAL,
                "memory_mb": DataType.NUMERIC,
                "cpu_percent": DataType.NUMERIC,
            },
        )
        
        es = self.engine.create_entityset("execution_analysis")
        es.add_entity(entity)
        
        return self.engine.run_dfs("execution_analysis", entity_name, max_depth=2)

    def extract_code_features(self, code_metrics: List[Dict], entity_name: str = "files") -> FeatureVector:
        entity = Entity(
            entity_id=entity_name,
            dataframe=code_metrics,
            index="file_id",
            variables={
                "file_id": DataType.ID,
                "file_path": DataType.TEXT,
                "lines_of_code": DataType.NUMERIC,
                "cyclomatic_complexity": DataType.NUMERIC,
                "cognitive_complexity": DataType.NUMERIC,
                "halstead_volume": DataType.NUMERIC,
                "function_count": DataType.NUMERIC,
                "class_count": DataType.NUMERIC,
                "import_count": DataType.NUMERIC,
                "test_coverage": DataType.NUMERIC,
                "language": DataType.CATEGORICAL,
            },
        )
        
        es = self.engine.create_entityset("code_analysis")
        es.add_entity(entity)
        
        return self.engine.run_dfs("code_analysis", entity_name, max_depth=2)

    def create_relational_model(self, entities_data: Dict[str, List[Dict]], 
                                relationships: List[Dict], 
                                target_entity: str) -> FeatureVector:
        es = self.engine.create_entityset("relational_model")
        
        for entity_id, data in entities_data.items():
            if not data:
                continue
            
            sample = data[0]
            variables = {}
            for col, val in sample.items():
                if isinstance(val, (int, float)) and not isinstance(val, bool):
                    variables[col] = DataType.NUMERIC
                elif isinstance(val, bool):
                    variables[col] = DataType.BOOLEAN
                elif isinstance(val, str):
                    if col.endswith('_id') or col == 'id':
                        variables[col] = DataType.ID
                    else:
                        variables[col] = DataType.CATEGORICAL
                else:
                    variables[col] = DataType.TEXT
            
            entity = Entity(
                entity_id=entity_id,
                dataframe=data,
                index=next((k for k in variables if variables[k] == DataType.ID), list(variables.keys())[0]),
                variables=variables,
            )
            es.add_entity(entity)
        
        for rel in relationships:
            relationship = Relationship(
                parent_entity_id=rel["parent_entity"],
                parent_variable=rel["parent_variable"],
                child_entity_id=rel["child_entity"],
                child_variable=rel["child_variable"],
            )
            es.add_relationship(relationship)
        
        return self.engine.run_dfs("relational_model", target_entity, max_depth=2)


class DaskFeatureEngine(FeatureToolsEngine):
    def __init__(self, n_workers: int = None):
        super().__init__()
        self.n_workers = n_workers
        self._dask_available = False
        try:
            import dask
            import dask.dataframe as dd
            from dask.distributed import Client
            self._dask_available = True
            self._client = None
        except ImportError:
            pass
    
    def _get_client(self):
        if not self._dask_available:
            return None
        if self._client is None:
            from dask.distributed import Client
            self._client = Client(n_workers=self.n_workers, processes=True, silence_logs=False)
        return self._client
    
    def run_dfs_parallel(self, entityset_id: str, target_entity: str, 
                         max_depth: int = 2, **kwargs) -> FeatureVector:
        if not self._dask_available:
            return self.run_dfs(entityset_id, target_entity, max_depth=max_depth, **kwargs)
        
        entityset = self.entitysets.get(entityset_id)
        if not entityset:
            raise ValueError(f"EntitySet {entityset_id} not found")
        
        target_entity_obj = entityset.entities.get(target_entity)
        if not target_entity_obj:
            raise ValueError(f"Entity {target_entity} not found")
        
        import dask
        import dask.dataframe as dd
        from dask.distributed import Client
        
        client = self._get_client()
        
        base_features = []
        for var_name, var_type in target_entity_obj.variables.items():
            if var_name != target_entity_obj.index and var_name != target_entity_obj.time_index:
                base_features.append(var_name)
        
        feature_batches = self._create_feature_batches(base_features, max_depth)
        
        futures = []
        for batch in feature_batches:
            future = client.submit(self._compute_batch, entityset, target_entity, batch)
            futures.append(future)
        
        results = client.gather(futures)
        
        combined_features = {}
        for result in results:
            combined_features.update(result)
        
        index_values = [row[target_entity_obj.index] for row in target_entity_obj.dataframe]
        
        return FeatureVector(
            features=combined_features,
            entity_id=target_entity,
            index=index_values,
        )
    
    def _create_feature_batches(self, base_features: List[str], max_depth: int) -> List[List[str]]:
        batch_size = max(1, len(base_features) // (self.n_workers or 4))
        return [base_features[i:i + batch_size] for i in range(0, len(base_features), batch_size)]
    
    def _compute_batch(self, entityset: EntitySet, target_entity: str, feature_names: List[str]) -> Dict:
        dfs = DeepFeatureSynthesis(entityset, self.primitive_library)
        dfs.run(target_entity, max_depth=2)
        
        target_entity_obj = entityset.entities[target_entity]
        results = {}
        for feat in dfs.features.get(target_entity, []):
            if feat.name in feature_names:
                values = dfs._compute_feature_values(feat, target_entity_obj)
                results[feat.name] = values
        return results
    
    def close(self):
        if self._client:
            self._client.close()
            self._client = None
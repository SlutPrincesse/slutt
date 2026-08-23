from __future__ import annotations
from typing import TypeVar, Generic, Callable, Dict, List, Any, Optional
from ..core.module import OmegaModule

T = TypeVar("T")
U = TypeVar("U")
C = TypeVar("C")

class Category(OmegaModule):
    def __init__(self, name: str, objects: List[str], morphisms: Dict[str, Callable]):
        super().__init__(name=name)
        self.objects = objects
        self.morphisms = morphisms

    def compose(self, f_name: str, g_name: str) -> Callable:
        def composed(x):
            return self.morphisms[f_name](self.morphisms[g_name](x))
        return composed

class Functor(OmegaModule):
    def __init__(self, source: Category, target: Category, obj_map: Dict[str, str], mor_map: Dict[str, Callable]):
        super().__init__(name=f"functor_{source.name}_to_{target.name}")
        self.source = source
        self.target = target
        self.obj_map = obj_map
        self.mor_map = mor_map

    def map_object(self, obj: str) -> str:
        return self.obj_map.get(obj, obj)

    def map_morphism(self, mor: str) -> Callable:
        return self.mor_map.get(mor, lambda x: x)

class Monad(OmegaModule):
    def __init__(self, category: Category, T: Callable, eta: Callable, mu: Callable):
        super().__init__(name=f"monad_{category.name}")
        self.category = category
        self.T = T
        self.eta = eta
        self.mu = mu

    def bind(self, x):
        return self.mu(self.T(x))

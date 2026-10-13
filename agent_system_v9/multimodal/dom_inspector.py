"""
DOM / Spatial Inspector - Vision pipeline parsing UI snapshots into spatial bounding boxes for automation
"""
import io
import json
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from PIL import Image


class ElementType(Enum):
    BUTTON = "button"
    INPUT = "input"
    LINK = "link"
    TEXT = "text"
    IMAGE = "image"
    CONTAINER = "container"
    NAVIGATION = "navigation"
    FORM = "form"
    TABLE = "table"
    LIST = "list"
    UNKNOWN = "unknown"


class InteractionType(Enum):
    CLICK = "click"
    HOVER = "hover"
    TYPE = "type"
    SELECT = "select"
    SCROLL = "scroll"
    DRAG = "drag"
    NONE = "none"


@dataclass
class SpatialBounds:
    x: int
    y: int
    width: int
    height: int
    confidence: float = 1.0

    @property
    def center(self) -> tuple[int, int]:
        return (self.x + self.width // 2, self.y + self.height // 2)

    @property
    def area(self) -> int:
        return self.width * self.height

    def contains(self, x: int, y: int) -> bool:
        return self.x <= x < self.x + self.width and self.y <= y < self.y + self.height

    def intersects(self, other: 'SpatialBounds') -> bool:
        return not (self.x + self.width <= other.x or
                   other.x + other.width <= self.x or
                   self.y + self.height <= other.y or
                   other.y + other.height <= self.y)

    def iou(self, other: 'SpatialBounds') -> float:
        inter_x1 = max(self.x, other.x)
        inter_y1 = max(self.y, other.y)
        inter_x2 = min(self.x + self.width, other.x + other.width)
        inter_y2 = min(self.y + self.height, other.y + other.height)

        if inter_x1 >= inter_x2 or inter_y1 >= inter_y2:
            return 0.0

        inter_area = (inter_x2 - inter_x1) * (inter_y2 - inter_y1)
        union_area = self.area + other.area - inter_area
        return inter_area / union_area if union_area > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "confidence": self.confidence
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'SpatialBounds':
        return cls(
            x=data["x"],
            y=data["y"],
            width=data["width"],
            height=data["height"],
            confidence=data.get("confidence", 1.0)
        )


@dataclass
class UIElement:
    element_id: str
    element_type: ElementType
    bounds: SpatialBounds
    text: str = ""
    attributes: dict[str, str] = field(default_factory=dict)
    children: list['UIElement'] = field(default_factory=list)
    parent_id: str | None = None
    interaction_type: InteractionType = InteractionType.NONE
    selector: str = ""
    xpath: str = ""
    css_path: str = ""
    visible: bool = True
    enabled: bool = True
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "element_id": self.element_id,
            "element_type": self.element_type.value,
            "bounds": self.bounds.to_dict(),
            "text": self.text,
            "attributes": self.attributes,
            "children": [c.to_dict() for c in self.children],
            "parent_id": self.parent_id,
            "interaction_type": self.interaction_type.value,
            "selector": self.selector,
            "xpath": self.xpath,
            "css_path": self.css_path,
            "visible": self.visible,
            "enabled": self.enabled,
            "confidence": self.confidence,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'UIElement':
        return cls(
            element_id=data["element_id"],
            element_type=ElementType(data["element_type"]),
            bounds=SpatialBounds.from_dict(data["bounds"]),
            text=data.get("text", ""),
            attributes=data.get("attributes", {}),
            children=[cls.from_dict(c) for c in data.get("children", [])],
            parent_id=data.get("parent_id"),
            interaction_type=InteractionType(data.get("interaction_type", "none")),
            selector=data.get("selector", ""),
            xpath=data.get("xpath", ""),
            css_path=data.get("css_path", ""),
            visible=data.get("visible", True),
            enabled=data.get("enabled", True),
            confidence=data.get("confidence", 1.0),
            metadata=data.get("metadata", {})
        )


class DOMSpatialInspector:
    def __init__(self):
        self._elements: dict[str, UIElement] = {}
        self._element_tree: UIElement | None = None
        self._lock = threading.RLock()
        self._analyzers: dict[str, Callable] = {}
        self._register_default_analyzers()

    def _register_default_analyzers(self):
        self._analyzers["button"] = self._analyze_button
        self._analyzers["input"] = self._analyze_input
        self._analyzers["link"] = self._analyze_link
        self._analyzers["image"] = self._analyze_image
        self._analyzers["container"] = self._analyze_container

    def analyze_screenshot(self, image_data: bytes,
                          dom_data: str | None = None) -> list[UIElement]:
        """Analyze a screenshot and optional DOM to extract UI elements"""
        elements = []

        # Load image
        try:
            img = Image.open(io.BytesIO(image_data))
            width, height = img.size
        except Exception:
            width, height = 1920, 1080

        # If DOM data provided, parse it
        if dom_data:
            elements = self._parse_dom(dom_data, width, height)
        else:
            # Vision-only analysis (simplified)
            elements = self._vision_analyze(image_data, width, height)

        # Build tree
        self._build_tree(elements)

        return elements

    def _parse_dom(self, dom_data: str, width: int, height: int) -> list[UIElement]:
        elements = []

        try:
            # Try to parse as JSON (from browser automation)
            dom_json = json.loads(dom_data)
            elements = self._parse_dom_json(dom_json, width, height)
        except json.JSONDecodeError:
            # Try to parse as HTML
            elements = self._parse_html(dom_data, width, height)

        return elements

    def _parse_dom_json(self, dom_json: dict[str, Any], width: int, height: int) -> list[UIElement]:
        elements = []

        def parse_node(node: dict[str, Any], parent_id: str | None = None) -> UIElement:
            bounds_data = node.get("bounds", {})
            bounds = SpatialBounds(
                x=bounds_data.get("x", 0),
                y=bounds_data.get("y", 0),
                width=bounds_data.get("width", 0),
                height=bounds_data.get("height", 0),
                confidence=bounds_data.get("confidence", 1.0)
            )

            element_type = self._infer_element_type(node)
            interaction = self._infer_interaction_type(node)

            element = UIElement(
                element_id=node.get("element_id", f"elem_{len(elements)}"),
                element_type=element_type,
                bounds=bounds,
                text=node.get("text", ""),
                attributes=node.get("attributes", {}),
                parent_id=parent_id,
                interaction_type=interaction,
                selector=node.get("selector", ""),
                xpath=node.get("xpath", ""),
                css_path=node.get("css_path", ""),
                visible=node.get("visible", True),
                enabled=node.get("enabled", True),
                confidence=node.get("confidence", 1.0)
            )

            children = node.get("children", [])
            for child in children:
                child_elem = parse_node(child, element.element_id)
                element.children.append(child_elem)

            return element

        if isinstance(dom_json, list):
            for node in dom_json:
                elements.append(parse_node(node))
        else:
            elements.append(parse_node(dom_json))

        return elements

    def _parse_html(self, html: str, width: int, height: int) -> list[UIElement]:
        # Simplified HTML parsing - in production use lxml/beautifulsoup
        elements = []
        return elements

    def _vision_analyze(self, image_data: bytes, width: int, height: int) -> list[UIElement]:
        # Placeholder for vision-based analysis
        # In production, this would use a vision model
        return []

    def _infer_element_type(self, node: dict[str, Any]) -> ElementType:
        tag = node.get("tag", "").lower()
        attrs = node.get("attributes", {})

        if tag == "button" or attrs.get("role") == "button":
            return ElementType.BUTTON
        if tag == "input":
            return ElementType.INPUT
        if tag == "a":
            return ElementType.LINK
        if tag == "img":
            return ElementType.IMAGE
        if tag in ("div", "section", "article", "main", "aside"):
            return ElementType.CONTAINER
        if tag == "nav":
            return ElementType.NAVIGATION
        if tag == "form":
            return ElementType.FORM
        if tag == "table":
            return ElementType.TABLE
        if tag in ("ul", "ol"):
            return ElementType.LIST
        if tag in ("p", "span", "h1", "h2", "h3", "h4", "h5", "h6"):
            return ElementType.TEXT
        return ElementType.UNKNOWN

    def _infer_interaction_type(self, node: dict[str, Any]) -> InteractionType:
        tag = node.get("tag", "").lower()
        attrs = node.get("attributes", {})

        if tag == "button" or attrs.get("role") == "button" or attrs.get("onclick"):
            return InteractionType.CLICK
        if tag == "input":
            input_type = attrs.get("type", "text")
            if input_type in ("text", "email", "password", "search", "textarea"):
                return InteractionType.TYPE
            if input_type in ("checkbox", "radio"):
                return InteractionType.CLICK
            if input_type == "select":
                return InteractionType.SELECT
        elif tag == "a":
            return InteractionType.CLICK
        elif tag == "select":
            return InteractionType.SELECT
        return InteractionType.NONE

    def _build_tree(self, elements: list[UIElement]):
        with self._lock:
            self._elements = {e.element_id: e for e in elements}

            # Find root elements
            roots = [e for e in elements if e.parent_id is None]
            if len(roots) == 1:
                self._element_tree = roots[0]
            elif len(roots) > 1:
                # Create virtual root
                self._element_tree = UIElement(
                    element_id="virtual_root",
                    element_type=ElementType.CONTAINER,
                    bounds=SpatialBounds(0, 0, 1920, 1080),
                    children=roots
                )
                for root in roots:
                    root.parent_id = "virtual_root"

    def find_elements(self, element_type: ElementType = None,
                     text_contains: str = None,
                     attribute: str = None,
                     attribute_value: str = None,
                     bounds: SpatialBounds = None,
                     interaction: InteractionType = None) -> list[UIElement]:
        with self._lock:
            results = list(self._elements.values())

        if element_type:
            results = [e for e in results if e.element_type == element_type]

        if text_contains:
            results = [e for e in results if text_contains.lower() in e.text.lower()]

        if attribute:
            if attribute_value:
                results = [e for e in results if e.attributes.get(attribute) == attribute_value]
            else:
                results = [e for e in results if attribute in e.attributes]

        if bounds:
            results = [e for e in results if e.bounds.intersects(bounds)]

        if interaction:
            results = [e for e in results if e.interaction_type == interaction]

        return results

    def get_element(self, element_id: str) -> UIElement | None:
        with self._lock:
            return self._elements.get(element_id)

    def get_tree(self) -> UIElement | None:
        with self._lock:
            return self._element_tree

    def get_interaction_point(self, element_id: str) -> tuple[int, int] | None:
        element = self.get_element(element_id)
        if element and element.visible and element.enabled:
            return element.bounds.center
        return None

    def get_clickable_elements(self) -> list[UIElement]:
        return self.find_elements(interaction=InteractionType.CLICK)

    def get_typeable_elements(self) -> list[UIElement]:
        return self.find_elements(interaction=InteractionType.TYPE)

    def register_analyzer(self, name: str, analyzer: Callable):
        self._analyzers[name] = analyzer

    def _analyze_button(self, element: UIElement) -> dict[str, Any]:
        return {"clickable": True, "role": "button"}

    def _analyze_input(self, element: UIElement) -> dict[str, Any]:
        input_type = element.attributes.get("type", "text")
        return {"input_type": input_type, "required": element.attributes.get("required") == "true"}

    def _analyze_link(self, element: UIElement) -> dict[str, Any]:
        return {"href": element.attributes.get("href", ""), "external": element.attributes.get("target") == "_blank"}

    def _analyze_image(self, element: UIElement) -> dict[str, Any]:
        return {"src": element.attributes.get("src", ""), "alt": element.attributes.get("alt", "")}

    def _analyze_container(self, element: UIElement) -> dict[str, Any]:
        return {"child_count": len(element.children)}


_dom_inspector: DOMSpatialInspector | None = None


def get_dom_inspector() -> DOMSpatialInspector:
    global _dom_inspector
    if _dom_inspector is None:
        _dom_inspector = DOMSpatialInspector()
    return _dom_inspector

"""
Linguistic Disambiguation Pre-Processor - Local heuristic engine resolving ambiguous queries before LLM dispatch
"""
import re
import threading
from typing import Dict, List, Optional, Any, Callable, Tuple
from dataclasses import dataclass, field
from enum import Enum


class AmbiguityType(Enum):
    PRONOUN = "pronoun"
    REFERENCE = "reference"
    SCOPE = "scope"
    INTENT = "intent"
    ENTITY = "entity"
    TEMPORAL = "temporal"


@dataclass
class DisambiguationResult:
    original_query: str
    clarified_query: str
    ambiguities: List[Dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0
    suggestions: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class LinguisticDisambiguator:
    def __init__(self):
        self._lock = threading.RLock()
        self._context: Dict[str, Any] = {}
        self._entity_map: Dict[str, str] = {}
        self._pronoun_references: Dict[str, str] = {}
        self._patterns = self._compile_patterns()
    
    def _compile_patterns(self) -> Dict[str, re.Pattern]:
        return {
            "pronoun": re.compile(r'\b(it|this|that|these|those|he|she|they|them|his|her|their)\b', re.IGNORECASE),
            "vague_reference": re.compile(r'\b(the|a|an)\s+(function|method|class|module|file|variable|parameter)\b', re.IGNORECASE),
            "temporal": re.compile(r'\b(recently|before|after|later|earlier|now|currently)\b', re.IGNORECASE),
            "scope": re.compile(r'\b(here|there|above|below|inside|outside|within)\b', re.IGNORECASE),
        }
    
    def set_context(self, context: Dict[str, Any]):
        with self._lock:
            self._context = context
            self._update_entity_map()
    
    def _update_entity_map(self):
        self._entity_map.clear()
        if "files" in self._context:
            for f in self._context["files"]:
                self._entity_map[f] = f
        if "functions" in self._context:
            for f in self._context["functions"]:
                self._entity_map[f] = f"function:{f}"
        if "classes" in self._context:
            for c in self._context["classes"]:
                self._entity_map[c] = f"class:{c}"
        if "variables" in self._context:
            for v in self._context["variables"]:
                self._entity_map[v] = f"variable:{v}"
    
    def disambiguate(self, query: str, context: Dict[str, Any] = None) -> DisambiguationResult:
        if context:
            self.set_context(context)
        
        ambiguities = []
        clarified = query
        
        # Detect ambiguities
        for amb_type, pattern in self._patterns.items():
            for match in pattern.finditer(query):
                ambiguities.append({
                    "type": amb_type,
                    "text": match.group(),
                    "position": match.span(),
                    "context": query[max(0, match.start()-20):match.end()+20]
                })
        
        # Resolve pronouns
        clarified = self._resolve_pronouns(clarified, ambiguities)
        
        # Resolve vague references
        clarified = self._resolve_vague_references(clarified, ambiguities)
        
        # Resolve temporal references
        clarified = self._resolve_temporal(clarified)
        
        # Calculate confidence
        confidence = self._calculate_confidence(ambiguities, clarified)
        
        # Generate suggestions
        suggestions = self._generate_suggestions(ambiguities)
        
        return DisambiguationResult(
            original_query=query,
            clarified_query=clarified,
            ambiguities=ambiguities,
            confidence=confidence,
            suggestions=suggestions,
            metadata={"entity_map": dict(self._entity_map)}
        )
    
    def _resolve_pronouns(self, query: str, ambiguities: List[Dict]) -> str:
        result = query
        
        for amb in ambiguities:
            if amb["type"] == "pronoun":
                pronoun = amb["text"].lower()
                
                # Try to find antecedent
                antecedent = self._find_antecedent(pronoun)
                if antecedent:
                    result = result.replace(amb["text"], antecedent, 1)
                    self._pronoun_references[pronoun] = antecedent
        
        return result
    
    def _find_antecedent(self, pronoun: str) -> Optional[str]:
        # Check recent context
        if "last_entity" in self._context:
            return self._context["last_entity"]
        
        if "last_function" in self._context and pronoun in ("it", "this", "that"):
            return self._context["last_function"]
        
        if "last_file" in self._context and pronoun in ("it", "this", "that"):
            return self._context["last_file"]
        
        # Check pronoun references
        if pronoun in self._pronoun_references:
            return self._pronoun_references[pronoun]
        
        return None
    
    def _resolve_vague_references(self, query: str, ambiguities: List[Dict]) -> str:
        result = query
        
        for amb in ambiguities:
            if amb["type"] == "vague_reference":
                # Try to find specific entity
                words = amb["text"].split()
                if len(words) >= 2:
                    entity_type = words[1].lower()
                    
                    if entity_type in ("function", "method") and "functions" in self._context:
                        if self._context["functions"]:
                            result = result.replace(amb["text"], f"the function {self._context['functions'][-1]}", 1)
                    elif entity_type in ("class", "type") and "classes" in self._context:
                        if self._context["classes"]:
                            result = result.replace(amb["text"], f"the class {self._context['classes'][-1]}", 1)
                    elif entity_type in ("file", "module") and "files" in self._context:
                        if self._context["files"]:
                            result = result.replace(amb["text"], f"the file {self._context['files'][-1]}", 1)
        
        return result
    
    def _resolve_temporal(self, query: str) -> str:
        result = query
        
        temporal_map = {
            "recently": "in the last few minutes",
            "before": "before the current operation",
            "after": "after the current operation",
            "now": "at the current time",
            "currently": "at the present moment"
        }
        
        for vague, specific in temporal_map.items():
            if re.search(rf'\b{vague}\b', result, re.IGNORECASE):
                result = re.sub(rf'\b{vague}\b', specific, result, flags=re.IGNORECASE)
        
        return result
    
    def _calculate_confidence(self, ambiguities: List[Dict], clarified: str) -> float:
        if not ambiguities:
            return 1.0
        
        resolved = sum(1 for a in ambiguities if a["type"] in ("pronoun", "vague_reference") 
                      and a["text"] not in clarified)
        
        return max(0.0, 1.0 - (len(ambiguities) - resolved) * 0.2)
    
    def _generate_suggestions(self, ambiguities: List[Dict]) -> List[str]:
        suggestions = []
        
        for amb in ambiguities:
            if amb["type"] == "pronoun":
                suggestions.append(f"Clarify what '{amb['text']}' refers to")
            elif amb["type"] == "vague_reference":
                suggestions.append(f"Specify which {amb['text'].split()[-1]} you mean")
            elif amb["type"] == "temporal":
                suggestions.append(f"Specify exact time for '{amb['text']}'")
        
        return suggestions
    
    def add_entity(self, name: str, entity_type: str):
        with self._lock:
            self._entity_map[name] = entity_type
    
    def clear_context(self):
        with self._lock:
            self._context.clear()
            self._entity_map.clear()
            self._pronoun_references.clear()


_disambiguator: Optional[LinguisticDisambiguator] = None

def get_disambiguator() -> LinguisticDisambiguator:
    global _disambiguator
    if _disambiguator is None:
        _disambiguator = LinguisticDisambiguator()
    return _disambiguator
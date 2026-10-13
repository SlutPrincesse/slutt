"""
COM-B Behavioral Framework - Digital Behavior Change Models
"""
import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class COMComponent(Enum):
    CAPABILITY = "capability"
    OPPORTUNITY = "opportunity"
    MOTIVATION = "motivation"


class CapabilityType(Enum):
    PHYSICAL = "physical"
    PSYCHOLOGICAL = "psychological"


class OpportunityType(Enum):
    PHYSICAL = "physical"
    SOCIAL = "social"


class MotivationType(Enum):
    REFLECTIVE = "reflective"
    AUTOMATIC = "automatic"


@dataclass
class COMFactor:
    component: COMComponent
    sub_type: Enum
    name: str
    description: str
    weight: float = 1.0
    measurable: bool = True
    assessment_method: str = ""


@dataclass
class Behavior:
    behavior_id: str
    name: str
    description: str
    target_population: str = ""
    context: str = ""
    com_factors: list[COMFactor] = field(default_factory=list)
    interventions: list['Intervention'] = field(default_factory=list)

    def get_capability_factors(self) -> list[COMFactor]:
        return [f for f in self.com_factors if f.component == COMComponent.CAPABILITY]

    def get_opportunity_factors(self) -> list[COMFactor]:
        return [f for f in self.com_factors if f.component == COMComponent.OPPORTUNITY]

    def get_motivation_factors(self) -> list[COMFactor]:
        return [f for f in self.com_factors if f.component == COMComponent.MOTIVATION]


@dataclass
class Intervention:
    intervention_id: str
    name: str
    description: str
    bct_codes: list[str] = field(default_factory=list)
    target_components: list[COMComponent] = field(default_factory=list)
    delivery_mode: str = "digital"
    intensity: float = 1.0
    duration_weeks: int = 4
    evidence_level: str = "theoretical"
    cost: float = 0.0


class BCTTaxonomy:
    BCTS = {
        "1.1": "Goal setting (behavior)",
        "1.2": "Problem solving",
        "1.3": "Goal setting (outcome)",
        "1.4": "Action planning",
        "1.5": "Review behavior goal(s)",
        "1.6": "Discrepancy between current behavior and goal",
        "1.7": "Review outcome goal(s)",
        "1.8": "Behavioral contract",
        "1.9": "Commitment",
        "2.1": "Monitoring of behavior by others without feedback",
        "2.2": "Feedback on behavior",
        "2.3": "Self-monitoring of behavior",
        "2.4": "Self-monitoring of outcome(s) of behavior",
        "2.5": "Monitoring of outcome(s) of behavior without feedback",
        "2.6": "Biofeedback",
        "2.7": "Feedback on outcome(s) of behavior",
        "3.1": "Social support (unspecified)",
        "3.2": "Social support (practical)",
        "3.3": "Social support (emotional)",
        "4.1": "Instruction on how to perform the behavior",
        "4.2": "Information about antecedents",
        "4.3": "Re-attribution",
        "4.4": "Behavioral experiments",
        "5.1": "Information about health consequences",
        "5.2": "Salience of consequences",
        "5.3": "Information about social and environmental consequences",
        "5.4": "Monitoring of emotional consequences",
        "5.5": "Anticipated regret",
        "5.6": "Information about emotional consequences",
        "6.1": "Demonstration of the behavior",
        "6.2": "Social comparison",
        "6.3": "Information about others' approval",
        "7.1": "Prompts/cues",
        "7.2": "Cue signalling reward",
        "7.3": "Reduce prompts/cues",
        "7.4": "Remove access to the reward",
        "7.5": "Remove aversive stimulus",
        "7.6": "Satiation",
        "7.7": "Exposure",
        "7.8": "Associative learning",
        "8.1": "Behavioural practice/rehearsal",
        "8.2": "Behaviour substitution",
        "8.3": "Habit formation",
        "8.4": "Habit reversal",
        "8.5": "Overcorrection",
        "8.6": "Generalisation of target behaviour",
        "8.7": "Graded tasks",
        "9.1": "Credible source",
        "9.2": "Pros and cons",
        "9.3": "Comparative imagining of future outcomes",
        "10.1": "Material incentive (behavior)",
        "10.2": "Material reward (behavior)",
        "10.3": "Non-specific reward",
        "10.4": "Social reward",
        "10.5": "Social incentive",
        "10.6": "Non-specific incentive",
        "10.7": "Self-incentive",
        "10.8": "Incentive (outcome)",
        "10.9": "Self-reward",
        "10.10": "Reward (outcome)",
        "10.11": "Future punishment",
        "11.1": "Pharmacological support",
        "11.2": "Reduce negative emotions",
        "11.3": "Conserving mental resources",
        "12.1": "Restructuring the physical environment",
        "12.2": "Restructuring the social environment",
        "12.3": "Avoidance/reducing exposure to cues for the behaviour",
        "12.4": "Distraction",
        "12.5": "Adding objects to the environment",
        "12.6": "Body changes",
        "13.1": "Identification of self as role model",
        "13.2": "Framing/reframing",
        "13.3": "Incompatible beliefs",
        "13.4": "Valued self-identity",
        "13.5": "Identity associated with changed behaviour",
        "14.1": "Behaviour cost",
        "14.2": "Punishment",
        "14.3": "Remove reward",
        "14.4": "Reward alternative behaviour",
        "14.5": "Reward approximation",
        "14.6": "Situation-specific reward",
        "14.7": "Reward incompatible behaviour",
        "14.8": "Reward alternative behaviour",
        "15.1": "Verbal persuasion about capability",
        "15.2": "Mental rehearsal of successful performance",
        "15.3": "Focus on past success",
        "15.4": "Self-talk",
        "16.1": "Imaginary punishment",
        "16.2": "Imaginary reward",
        "16.3": "Vicarious consequences",
    }

    @classmethod
    def get_bct(cls, code: str) -> str:
        return cls.BCTS.get(code, "Unknown BCT")

    @classmethod
    def search_bcts(cls, keyword: str) -> list[tuple[str, str]]:
        keyword = keyword.lower()
        return [(code, desc) for code, desc in cls.BCTS.items() if keyword in desc.lower()]


class COMModel:
    def __init__(self):
        self.behaviors: dict[str, Behavior] = {}
        self.interventions: dict[str, Intervention] = {}

    def add_behavior(self, behavior: Behavior):
        self.behaviors[behavior.behavior_id] = behavior

    def add_intervention(self, intervention: Intervention):
        self.interventions[intervention.intervention_id] = intervention

    def analyze_behavior(self, behavior_id: str) -> dict[str, Any]:
        behavior = self.behaviors.get(behavior_id)
        if not behavior:
            return {"error": "Behavior not found"}

        capability_score = self._score_component(behavior.get_capability_factors())
        opportunity_score = self._score_component(behavior.get_opportunity_factors())
        motivation_score = self._score_component(behavior.get_motivation_factors())

        total_score = (capability_score + opportunity_score + motivation_score) / 3

        return {
            "behavior_id": behavior_id,
            "behavior_name": behavior.name,
            "capability_score": capability_score,
            "opportunity_score": opportunity_score,
            "motivation_score": motivation_score,
            "overall_com_score": total_score,
            "bottleneck": self._identify_bottleneck(capability_score, opportunity_score, motivation_score),
            "recommended_interventions": self._recommend_interventions(behavior),
        }

    def _score_component(self, factors: list[COMFactor]) -> float:
        if not factors:
            return 0.0
        weighted_sum = sum(f.weight for f in factors)
        max_possible = sum(1.0 for _ in factors)
        return weighted_sum / max_possible if max_possible > 0 else 0.0

    def _identify_bottleneck(self, cap: float, opp: float, mot: float) -> COMComponent:
        scores = {COMComponent.CAPABILITY: cap, COMComponent.OPPORTUNITY: opp, COMComponent.MOTIVATION: mot}
        return min(scores, key=scores.get)

    def _recommend_interventions(self, behavior: Behavior) -> list[dict]:
        bottleneck = self._identify_bottleneck(
            self._score_component(behavior.get_capability_factors()),
            self._score_component(behavior.get_opportunity_factors()),
            self._score_component(behavior.get_motivation_factors()),
        )

        recommendations = []
        for intervention in self.interventions.values():
            if bottleneck in intervention.target_components:
                recommendations.append({
                    "intervention_id": intervention.intervention_id,
                    "name": intervention.name,
                    "bcts": [{"code": code, "description": BCTTaxonomy.get_bct(code)} for code in intervention.bct_codes],
                    "delivery_mode": intervention.delivery_mode,
                    "intensity": intervention.intensity,
                    "evidence_level": intervention.evidence_level,
                })

        return sorted(recommendations, key=lambda x: x["intensity"], reverse=True)


class NudgeEngine:
    def __init__(self, com_model: COMModel):
        self.com_model = com_model
        self.nudge_types = {
            "default": {"description": "Change the default option", "bct": "12.5"},
            "simplification": {"description": "Reduce complexity", "bct": "1.4"},
            "social_proof": {"description": "Show what others do", "bct": "6.2"},
            "commitment": {"description": "Get public commitment", "bct": "1.9"},
            "reminder": {"description": "Timely prompts", "bct": "7.1"},
            "feedback": {"description": "Immediate feedback", "bct": "2.3"},
            "incentive": {"description": "Rewards for behavior", "bct": "10.1"},
            "framing": {"description": "Reframe the choice", "bct": "13.2"},
        }

    def design_nudge(self, behavior_id: str, context: dict[str, Any] = None) -> list[dict]:
        analysis = self.com_model.analyze_behavior(behavior_id)
        if "error" in analysis:
            return []

        bottleneck = analysis["bottleneck"]
        nudges = []

        if bottleneck == COMComponent.CAPABILITY:
            nudges.append(self._create_nudge("simplification", behavior_id, context))
            nudges.append(self._create_nudge("feedback", behavior_id, context))
            nudges.append(self._create_nudge("default", behavior_id, context))
        elif bottleneck == COMComponent.OPPORTUNITY:
            nudges.append(self._create_nudge("default", behavior_id, context))
            nudges.append(self._create_nudge("reminder", behavior_id, context))
            nudges.append(self._create_nudge("social_proof", behavior_id, context))
        elif bottleneck == COMComponent.MOTIVATION:
            nudges.append(self._create_nudge("commitment", behavior_id, context))
            nudges.append(self._create_nudge("incentive", behavior_id, context))
            nudges.append(self._create_nudge("framing", behavior_id, context))

        return nudges

    def _create_nudge(self, nudge_type: str, behavior_id: str, context: dict = None) -> dict:
        nudge_info = self.nudge_types.get(nudge_type, {})
        return {
            "nudge_id": hashlib.md5(f"{nudge_type}:{behavior_id}:{time.time()}".encode()).hexdigest()[:12],
            "type": nudge_type,
            "description": nudge_info.get("description", ""),
            "bct_code": nudge_info.get("bct", ""),
            "bct_description": BCTTaxonomy.get_bct(nudge_info.get("bct", "")),
            "behavior_id": behavior_id,
            "context": context or {},
            "timestamp": time.time(),
        }

    def evaluate_nudge_effectiveness(self, nudge_id: str, before_data: list[float], after_data: list[float]) -> dict[str, Any]:
        if not before_data or not after_data:
            return {"error": "Insufficient data"}

        before_mean = statistics.mean(before_data)
        after_mean = statistics.mean(after_data)

        effect_size = (after_mean - before_mean) / statistics.stdev(before_data) if statistics.stdev(before_data) > 0 else 0

        return {
            "nudge_id": nudge_id,
            "before_mean": before_mean,
            "after_mean": after_mean,
            "absolute_change": after_mean - before_mean,
            "relative_change": (after_mean - before_mean) / before_mean if before_mean != 0 else 0,
            "effect_size": effect_size,
            "statistical_significance": effect_size > 0.2,
            "recommendation": "continue" if effect_size > 0.2 else "modify",
        }


class BehavioralDesigner:
    def __init__(self):
        self.com_model = COMModel()
        self.nudge_engine = NudgeEngine(self.com_model)

    def create_behavior(self, name: str, description: str,
                       capability_factors: list[dict] = None,
                       opportunity_factors: list[dict] = None,
                       motivation_factors: list[dict] = None) -> Behavior:
        behavior = Behavior(
            behavior_id=hashlib.md5(f"{name}:{time.time()}".encode()).hexdigest()[:12],
            name=name,
            description=description,
        )

        for factor_data in capability_factors or []:
            behavior.com_factors.append(COMFactor(
                component=COMComponent.CAPABILITY,
                sub_type=CapabilityType(factor_data.get("type", "psychological")),
                name=factor_data["name"],
                description=factor_data.get("description", ""),
                weight=factor_data.get("weight", 1.0),
            ))

        for factor_data in opportunity_factors or []:
            behavior.com_factors.append(COMFactor(
                component=COMComponent.OPPORTUNITY,
                sub_type=OpportunityType(factor_data.get("type", "physical")),
                name=factor_data["name"],
                description=factor_data.get("description", ""),
                weight=factor_data.get("weight", 1.0),
            ))

        for factor_data in motivation_factors or []:
            behavior.com_factors.append(COMFactor(
                component=COMComponent.MOTIVATION,
                sub_type=MotivationType(factor_data.get("type", "reflective")),
                name=factor_data["name"],
                description=factor_data.get("description", ""),
                weight=factor_data.get("weight", 1.0),
            ))

        self.com_model.add_behavior(behavior)
        return behavior

    def create_intervention(self, name: str, description: str,
                           bct_codes: list[str] = None,
                           target_components: list[COMComponent] = None,
                           **kwargs) -> Intervention:
        intervention = Intervention(
            intervention_id=hashlib.md5(f"{name}:{time.time()}".encode()).hexdigest()[:12],
            name=name,
            description=description,
            bct_codes=bct_codes or [],
            target_components=target_components or [COMComponent.CAPABILITY, COMComponent.OPPORTUNITY, COMComponent.MOTIVATION],
            **kwargs
        )
        self.com_model.add_intervention(intervention)
        return intervention

    def run_behavioral_analysis(self, behavior_id: str) -> dict[str, Any]:
        return self.com_model.analyze_behavior(behavior_id)

    def design_intervention_package(self, behavior_id: str) -> dict[str, Any]:
        analysis = self.com_model.analyze_behavior(behavior_id)
        if "error" in analysis:
            return {"error": analysis["error"]}

        nudges = self.nudge_engine.design_nudge(behavior_id)

        return {
            "behavior_analysis": analysis,
            "recommended_nudges": nudges,
            "intervention_sequence": self._create_intervention_sequence(analysis, nudges),
            "measurement_plan": self._create_measurement_plan(behavior_id),
        }

    def _create_intervention_sequence(self, analysis: dict, nudges: list[dict]) -> list[dict]:
        sequence = []

        for i, nudge in enumerate(nudges):
            sequence.append({
                "phase": i + 1,
                "nudge": nudge,
                "duration_weeks": 1,
                "intensity": 1.0 - (i * 0.1),
                "evaluation_point": i + 1 == len(nudges),
            })

        return sequence

    def _create_measurement_plan(self, behavior_id: str) -> dict[str, Any]:
        return {
            "baseline_period_weeks": 2,
            "intervention_period_weeks": 4,
            "followup_period_weeks": 4,
            "measures": [
                {"name": "behavior_frequency", "type": "count", "frequency": "daily"},
                {"name": "capability_self_report", "type": "likert", "frequency": "weekly"},
                {"name": "opportunity_environmental", "type": "observation", "frequency": "weekly"},
                {"name": "motivation_self_report", "type": "likert", "frequency": "weekly"},
            ],
            "analysis_method": "interrupted_time_series",
        }


import statistics

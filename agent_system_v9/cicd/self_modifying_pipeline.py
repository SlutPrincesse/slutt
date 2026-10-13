"""
Self-Modifying Pipeline - Pipeline that can modify itself at runtime
"""
import asyncio
import hashlib
import time
from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import yaml


class PipelineStage(Enum):
    SOURCE = "source"
    BUILD = "build"
    TEST = "test"
    SECURITY = "security"
    DEPLOY = "deploy"
    VALIDATE = "validate"
    NOTIFY = "notify"


class TriggerType(Enum):
    PUSH = "push"
    PR = "pull_request"
    SCHEDULE = "schedule"
    MANUAL = "manual"
    WEBHOOK = "webhook"
    DEPENDENCY = "dependency"


@dataclass
class PipelineStep:
    name: str
    stage: PipelineStage
    command: str
    image: str = "ubuntu:latest"
    environment: dict[str, str] = field(default_factory=dict)
    artifacts: list[str] = field(default_factory=list)
    cache_key: str = ""
    timeout: float = 300.0
    retries: int = 0
    condition: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineTrigger:
    trigger_type: TriggerType
    branches: list[str] = field(default_factory=lambda: ["main"])
    paths: list[str] = field(default_factory=list)
    schedule: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineRun:
    run_id: str
    pipeline_name: str
    trigger: PipelineTrigger
    status: str = "pending"
    started_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    steps: list['StepResult'] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class StepResult:
    step_name: str
    status: str = "pending"
    started_at: float | None = None
    completed_at: float | None = None
    output: str = ""
    error: str = ""
    artifacts: dict[str, str] = field(default_factory=dict)


class PipelineExecutor(ABC):
    @abstractmethod
    async def execute_step(self, step: PipelineStep, context: dict[str, Any]) -> StepResult:
        pass


class LocalExecutor(PipelineExecutor):
    async def execute_step(self, step: PipelineStep, context: dict[str, Any]) -> StepResult:
        result = StepResult(step_name=step.name)
        result.started_at = time.time()

        try:
            process = await asyncio.create_subprocess_shell(
                step.command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**context.get("env", {}), **step.environment},
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=step.timeout,
            )

            result.output = stdout.decode() + stderr.decode()
            result.status = "success" if process.returncode == 0 else "failed"
            if process.returncode != 0:
                result.error = stderr.decode()
        except asyncio.TimeoutError:
            result.status = "timeout"
            result.error = f"Step timed out after {step.timeout}s"
        except Exception as e:
            result.status = "error"
            result.error = str(e)

        result.completed_at = time.time()
        return result


class DockerExecutor(PipelineExecutor):
    async def execute_step(self, step: PipelineStep, context: dict[str, Any]) -> StepResult:
        result = StepResult(step_name=step.name)
        result.started_at = time.time()

        env_args = " ".join(f"-e {k}={v}" for k, v in {**context.get("env", {}), **step.environment}.items())
        cmd = f"docker run --rm {env_args} {step.image} sh -c '{step.command}'"

        try:
            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=step.timeout,
            )

            result.output = stdout.decode() + stderr.decode()
            result.status = "success" if process.returncode == 0 else "failed"
        except asyncio.TimeoutError:
            result.status = "timeout"
            result.error = f"Step timed out after {step.timeout}s"
        except Exception as e:
            result.status = "error"
            result.error = str(e)

        result.completed_at = time.time()
        return result


@dataclass
class PipelineDefinition:
    name: str
    version: str
    steps: list[PipelineStep]
    triggers: list[PipelineTrigger]
    environment: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_yaml(self) -> str:
        data = {
            "name": self.name,
            "version": self.version,
            "environment": self.environment,
            "triggers": [
                {
                    "type": t.trigger_type.value,
                    "branches": t.branches,
                    "paths": t.paths,
                    "schedule": t.schedule,
                }
                for t in self.triggers
            ],
            "steps": [
                {
                    "name": s.name,
                    "stage": s.stage.value,
                    "command": s.command,
                    "image": s.image,
                    "environment": s.environment,
                    "artifacts": s.artifacts,
                    "cache_key": s.cache_key,
                    "timeout": s.timeout,
                    "retries": s.retries,
                    "condition": s.condition,
                }
                for s in self.steps
            ],
        }
        return yaml.dump(data)

    @classmethod
    def from_yaml(cls, yaml_str: str) -> 'PipelineDefinition':
        data = yaml.safe_load(yaml_str)
        steps = [
            PipelineStep(
                name=s["name"],
                stage=PipelineStage(s["stage"]),
                command=s["command"],
                image=s.get("image", "ubuntu:latest"),
                environment=s.get("environment", {}),
                artifacts=s.get("artifacts", []),
                cache_key=s.get("cache_key", ""),
                timeout=s.get("timeout", 300.0),
                retries=s.get("retries", 0),
                condition=s.get("condition", ""),
            )
            for s in data.get("steps", [])
        ]

        triggers = [
            PipelineTrigger(
                trigger_type=TriggerType(t["type"]),
                branches=t.get("branches", ["main"]),
                paths=t.get("paths", []),
                schedule=t.get("schedule", ""),
            )
            for t in data.get("triggers", [])
        ]

        return cls(
            name=data["name"],
            version=data["version"],
            steps=steps,
            triggers=triggers,
            environment=data.get("environment", {}),
        )

    def get_hash(self) -> str:
        return hashlib.md5(self.to_yaml().encode()).hexdigest()[:12]


class SelfModifyingPipeline:
    def __init__(self, executor: PipelineExecutor = None):
        self.pipelines: dict[str, PipelineDefinition] = {}
        self.runs: dict[str, PipelineRun] = {}
        self.executor = executor or LocalExecutor()
        self.modification_hooks: list[Callable] = []
        self._lock = asyncio.Lock()

    def register_pipeline(self, pipeline: PipelineDefinition):
        self.pipelines[pipeline.name] = pipeline

    def unregister_pipeline(self, name: str) -> bool:
        if name in self.pipelines:
            del self.pipelines[name]
            return True
        return False

    def add_modification_hook(self, hook: Callable):
        self.modification_hooks.append(hook)

    def modify_pipeline(
        self,
        name: str,
        modifier: Callable[[PipelineDefinition], PipelineDefinition],
    ) -> PipelineDefinition:
        pipeline = self.pipelines.get(name)
        if not pipeline:
            raise ValueError(f"Pipeline not found: {name}")

        new_pipeline = modifier(pipeline)
        new_pipeline.version = f"{int(new_pipeline.version.split('.')[-1]) + 1}.0.0"

        self.pipelines[name] = new_pipeline

        for hook in self.modification_hooks:
            try:
                hook(name, pipeline, new_pipeline)
            except Exception:
                pass

        return new_pipeline

    def add_step(self, pipeline_name: str, step: PipelineStep, after: str = None):
        def modifier(p: PipelineDefinition) -> PipelineDefinition:
            new_steps = list(p.steps)
            if after:
                idx = next((i for i, s in enumerate(new_steps) if s.name == after), -1)
                if idx >= 0:
                    new_steps.insert(idx + 1, step)
                else:
                    new_steps.append(step)
            else:
                new_steps.append(step)
            p.steps = new_steps
            return p

        return self.modify_pipeline(pipeline_name, modifier)

    def remove_step(self, pipeline_name: str, step_name: str):
        def modifier(p: PipelineDefinition) -> PipelineDefinition:
            p.steps = [s for s in p.steps if s.name != step_name]
            return p

        return self.modify_pipeline(pipeline_name, modifier)

    def update_step(self, pipeline_name: str, step_name: str, updates: dict[str, Any]):
        def modifier(p: PipelineDefinition) -> PipelineDefinition:
            for step in p.steps:
                if step.name == step_name:
                    for key, value in updates.items():
                        if hasattr(step, key):
                            setattr(step, key, value)
            return p

        return self.modify_pipeline(pipeline_name, modifier)

    async def run(
        self,
        pipeline_name: str,
        trigger: PipelineTrigger,
        context: dict[str, Any] = None,
    ) -> PipelineRun:
        pipeline = self.pipelines.get(pipeline_name)
        if not pipeline:
            raise ValueError(f"Pipeline not found: {pipeline_name}")

        run = PipelineRun(
            run_id=hashlib.md5(f"{pipeline_name}:{time.time()}".encode()).hexdigest()[:12],
            pipeline_name=pipeline_name,
            trigger=trigger,
        )

        self.runs[run.run_id] = run
        context = context or {}
        context["pipeline"] = pipeline
        context["run"] = run

        for step in pipeline.steps:
            if step.condition:
                try:
                    if not eval(step.condition, {}, context):
                        continue
                except Exception:
                    continue

            step_result = StepResult(step_name=step.name)
            run.steps.append(step_result)

            for attempt in range(step.retries + 1):
                result = await self.executor.execute_step(step, context)
                step_result.status = result.status
                step_result.output = result.output
                step_result.error = result.error
                step_result.started_at = result.started_at
                step_result.completed_at = result.completed_at

                if result.status == "success":
                    break
                if attempt < step.retries:
                    await asyncio.sleep(2 ** attempt)

            if step_result.status != "success":
                run.status = "failed"
                break

        if run.status != "failed":
            run.status = "success"

        run.completed_at = time.time()
        return run

    def get_pipeline(self, name: str) -> PipelineDefinition | None:
        return self.pipelines.get(name)

    def list_pipelines(self) -> list[PipelineDefinition]:
        return list(self.pipelines.values())

    def get_run(self, run_id: str) -> PipelineRun | None:
        return self.runs.get(run_id)

    def get_pipeline_history(self, pipeline_name: str, limit: int = 50) -> list[PipelineRun]:
        runs = [r for r in self.runs.values() if r.pipeline_name == pipeline_name]
        runs.sort(key=lambda r: r.started_at, reverse=True)
        return runs[:limit]


class PipelineComposer:
    def __init__(self):
        self.templates: dict[str, PipelineDefinition] = {}

    def register_template(self, name: str, pipeline: PipelineDefinition):
        self.templates[name] = pipeline

    def compose(
        self,
        name: str,
        template_names: list[str],
        additional_steps: list[PipelineStep] = None,
        overrides: dict[str, Any] = None,
    ) -> PipelineDefinition:
        all_steps = []
        all_triggers = []
        environment = {}

        for template_name in template_names:
            template = self.templates.get(template_name)
            if template:
                all_steps.extend(template.steps)
                all_triggers.extend(template.triggers)
                environment.update(template.environment)

        if additional_steps:
            all_steps.extend(additional_steps)

        if overrides:
            for step in all_steps:
                if step.name in overrides:
                    for key, value in overrides[step.name].items():
                        if hasattr(step, key):
                            setattr(step, key, value)

        pipeline = PipelineDefinition(
            name=name,
            version="1.0.0",
            steps=all_steps,
            triggers=all_triggers,
            environment=environment,
        )

        return pipeline


class PipelineVersionManager:
    def __init__(self, pipeline_manager: SelfModifyingPipeline):
        self.manager = pipeline_manager
        self.versions: dict[str, list[PipelineDefinition]] = defaultdict(list)

    def save_version(self, pipeline_name: str):
        pipeline = self.manager.get_pipeline(pipeline_name)
        if pipeline:
            self.versions[pipeline_name].append(pipeline)

    def get_versions(self, pipeline_name: str) -> list[PipelineDefinition]:
        return self.versions.get(pipeline_name, [])

    def rollback(self, pipeline_name: str, version_index: int = -2) -> PipelineDefinition:
        versions = self.versions.get(pipeline_name, [])
        if len(versions) < 2:
            raise ValueError("Not enough versions to rollback")

        target = versions[version_index]
        self.manager.pipelines[pipeline_name] = target
        return target

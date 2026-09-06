"""User-defined agent workflow schema and helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from bluesnail.core.exceptions import WorkflowError

STEP_TYPES = (
    "ingest_user",
    "recall_memory",
    "inject_skills",
    "inject_text",
    "build_context",
    "llm",
    "execute_calls",
    "finish",
)

STEP_TYPE_META: list[dict[str, Any]] = [
    {
        "type": "ingest_user",
        "label": "接收用户输入",
        "description": "校验并写入本轮用户消息。",
        "params": [],
        "routes": ["next"],
    },
    {
        "type": "recall_memory",
        "label": "回忆记忆",
        "description": "按当前输入检索记忆，写入 recall_context。",
        "params": [{"name": "top_k", "type": "int", "default": 3}],
        "routes": ["next"],
    },
    {
        "type": "inject_skills",
        "label": "注入 Skills 目录",
        "description": "把已注册 Skill 说明注入上下文。",
        "params": [],
        "routes": ["next"],
    },
    {
        "type": "inject_text",
        "label": "注入自定义文本",
        "description": "把固定说明追加到 extra_context。",
        "params": [{"name": "text", "type": "string", "default": ""}],
        "routes": ["next"],
    },
    {
        "type": "build_context",
        "label": "组装上下文",
        "description": "根据系统提示、记忆、Skills 和对话历史构建发给模型的消息。",
        "params": [],
        "routes": ["next"],
    },
    {
        "type": "llm",
        "label": "调用模型",
        "description": "向 LLM 发起一轮推理，并按结果分支。",
        "params": [{"name": "use_tools", "type": "bool", "default": True}],
        "routes": ["tool_calls", "content", "empty", "error", "max_iterations"],
    },
    {
        "type": "execute_calls",
        "label": "执行工具 / Skill",
        "description": "执行模型给出的 tool/skill 调用，并把结果写回对话。",
        "params": [],
        "routes": ["next"],
    },
    {
        "type": "finish",
        "label": "结束",
        "description": "产出最终回答并结束本轮。",
        "params": [],
        "routes": [],
    },
]


@dataclass(slots=True)
class WorkflowStep:
    id: str
    type: str
    next: str | None = None
    on: dict[str, str] = field(default_factory=dict)
    params: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "type": self.type,
            "enabled": self.enabled,
        }
        if self.next:
            payload["next"] = self.next
        if self.on:
            payload["on"] = dict(self.on)
        if self.params:
            payload["params"] = dict(self.params)
        if self.note:
            payload["note"] = self.note
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowStep:
        if not isinstance(data, dict):
            raise WorkflowError("Workflow step must be an object.")
        step_id = str(data.get("id") or "").strip()
        step_type = str(data.get("type") or "").strip()
        if not step_id:
            raise WorkflowError("Each workflow step needs an id.")
        if not step_type:
            raise WorkflowError(f"Step '{step_id}' needs a type.")
        on_raw = data.get("on") or {}
        if not isinstance(on_raw, dict):
            raise WorkflowError(f"Step '{step_id}' on must be an object.")
        params = data.get("params") or {}
        if not isinstance(params, dict):
            raise WorkflowError(f"Step '{step_id}' params must be an object.")
        next_id = data.get("next")
        return cls(
            id=step_id,
            type=step_type,
            next=str(next_id).strip() if next_id else None,
            on={str(key): str(value) for key, value in on_raw.items() if value},
            params=dict(params),
            enabled=bool(data.get("enabled", True)),
            note=str(data.get("note") or ""),
        )


@dataclass(slots=True)
class Workflow:
    id: str
    name: str
    entry: str
    steps: list[WorkflowStep]
    description: str = ""
    max_iterations: int = 50

    def step_map(self) -> dict[str, WorkflowStep]:
        return {step.id: step for step in self.steps}

    def get_step(self, step_id: str) -> WorkflowStep:
        try:
            return self.step_map()[step_id]
        except KeyError as exc:
            raise WorkflowError(f"Unknown workflow step: {step_id}") from exc

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "entry": self.entry,
            "max_iterations": self.max_iterations,
            "steps": [step.to_dict() for step in self.steps],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Workflow:
        if not isinstance(data, dict):
            raise WorkflowError("Workflow must be an object.")
        workflow_id = str(data.get("id") or "").strip()
        name = str(data.get("name") or workflow_id).strip()
        entry = str(data.get("entry") or "").strip()
        steps_raw = data.get("steps") or []
        if not workflow_id:
            raise WorkflowError("Workflow needs an id.")
        if not isinstance(steps_raw, list) or not steps_raw:
            raise WorkflowError("Workflow needs at least one step.")
        try:
            max_iterations = int(data.get("max_iterations", 50))
        except (TypeError, ValueError) as exc:
            raise WorkflowError("max_iterations must be an integer.") from exc
        workflow = cls(
            id=workflow_id,
            name=name or workflow_id,
            description=str(data.get("description") or ""),
            entry=entry,
            max_iterations=max_iterations,
            steps=[WorkflowStep.from_dict(item) for item in steps_raw],
        )
        validate_workflow(workflow)
        return workflow


@dataclass
class WorkflowBundle:
    active_id: str
    workflows: list[Workflow]

    def active(self) -> Workflow:
        return self.resolve(self.active_id)

    def resolve(self, ref: str) -> Workflow:
        key = str(ref or "").strip()
        if not key:
            raise WorkflowError("Workflow id or name is required.")
        for workflow in self.workflows:
            if workflow.id == key:
                return workflow
        named = [workflow for workflow in self.workflows if workflow.name == key]
        if len(named) == 1:
            return named[0]
        if len(named) > 1:
            raise WorkflowError(
                f"Multiple workflows named '{key}'. Use the workflow id instead."
            )
        raise WorkflowError(f"Workflow not found: {key}")

    def summaries(self) -> list[dict[str, Any]]:
        return [
            {
                "id": workflow.id,
                "name": workflow.name,
                "description": workflow.description,
                "step_count": len(workflow.steps),
            }
            for workflow in self.workflows
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "active_id": self.active_id,
            "workflows": [workflow.to_dict() for workflow in self.workflows],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowBundle:
        if not isinstance(data, dict):
            raise WorkflowError("Workflow bundle must be an object.")
        workflows_raw = data.get("workflows") or []
        if not isinstance(workflows_raw, list) or not workflows_raw:
            raise WorkflowError("Workflow bundle needs at least one workflow.")
        workflows = [Workflow.from_dict(item) for item in workflows_raw]
        active_id = str(data.get("active_id") or workflows[0].id).strip()
        bundle = cls(active_id=active_id, workflows=workflows)
        ids = [workflow.id for workflow in workflows]
        if len(ids) != len(set(ids)):
            raise WorkflowError("Workflow ids must be unique.")
        names = [workflow.name for workflow in workflows]
        if len(names) != len(set(names)):
            raise WorkflowError("Workflow names must be unique.")
        try:
            bundle.resolve(active_id)
        except WorkflowError as exc:
            raise WorkflowError(f"Active workflow not found: {active_id}") from exc
        return bundle


def default_react_workflow(
    *,
    max_iterations: int = 50,
    auto_recall: bool = True,
    recall_top_k: int = 3,
) -> Workflow:
    """Reproduce the built-in think-act-observe loop."""
    ingest_next = "recall" if auto_recall else "skills"
    steps = [
        WorkflowStep(
            id="ingest",
            type="ingest_user",
            next=ingest_next,
            note="写入用户消息",
        ),
    ]
    if auto_recall:
        steps.append(
            WorkflowStep(
                id="recall",
                type="recall_memory",
                next="skills",
                params={"top_k": recall_top_k},
            )
        )
    steps.extend(
        [
            WorkflowStep(id="skills", type="inject_skills", next="context"),
            WorkflowStep(id="context", type="build_context", next="think"),
            WorkflowStep(
                id="think",
                type="llm",
                params={"use_tools": True},
                on={
                    "tool_calls": "act",
                    "content": "finish",
                    "empty": "finish",
                    "error": "finish",
                    "max_iterations": "finish",
                },
            ),
            WorkflowStep(id="act", type="execute_calls", next="think"),
            WorkflowStep(id="finish", type="finish"),
        ]
    )
    return Workflow(
        id="react",
        name="ReAct 循环",
        description="回忆记忆、注入 Skills，然后进入思考-行动-观察循环。",
        entry="ingest",
        max_iterations=max_iterations,
        steps=steps,
    )


def default_direct_workflow(*, max_iterations: int = 8) -> Workflow:
    return Workflow(
        id="direct",
        name="直接回答",
        description="不调用工具，模型直接根据上下文回答。",
        entry="ingest",
        max_iterations=max_iterations,
        steps=[
            WorkflowStep(id="ingest", type="ingest_user", next="recall"),
            WorkflowStep(
                id="recall",
                type="recall_memory",
                next="context",
                params={"top_k": 3},
            ),
            WorkflowStep(id="context", type="build_context", next="think"),
            WorkflowStep(
                id="think",
                type="llm",
                params={"use_tools": False},
                on={
                    "content": "finish",
                    "empty": "finish",
                    "error": "finish",
                    "max_iterations": "finish",
                    "tool_calls": "finish",
                },
            ),
            WorkflowStep(id="finish", type="finish"),
        ],
    )


def default_bundle(
    *,
    max_iterations: int = 50,
    auto_recall: bool = True,
    recall_top_k: int = 3,
) -> WorkflowBundle:
    react = default_react_workflow(
        max_iterations=max_iterations,
        auto_recall=auto_recall,
        recall_top_k=recall_top_k,
    )
    return WorkflowBundle(active_id=react.id, workflows=[react, default_direct_workflow()])


def workflow_catalog() -> dict[str, Any]:
    return {
        "step_types": STEP_TYPE_META,
        "presets": [
            default_react_workflow().to_dict(),
            default_direct_workflow().to_dict(),
        ],
    }


def validate_workflow(workflow: Workflow) -> None:
    if workflow.max_iterations < 1:
        raise WorkflowError("max_iterations must be >= 1.")
    ids = [step.id for step in workflow.steps]
    if len(ids) != len(set(ids)):
        raise WorkflowError("Workflow step ids must be unique.")
    if not workflow.entry:
        raise WorkflowError("Workflow needs an entry step.")
    if workflow.entry not in ids:
        raise WorkflowError(f"Entry step not found: {workflow.entry}")

    has_finish = False
    for step in workflow.steps:
        if step.type not in STEP_TYPES:
            raise WorkflowError(f"Unknown step type '{step.type}' on '{step.id}'.")
        if step.type == "finish":
            has_finish = True
        _validate_target(step.next, ids, step.id, "next")
        for route, target in step.on.items():
            _validate_target(target, ids, step.id, f"on.{route}")
        if step.type == "llm" and "use_tools" in step.params:
            if not isinstance(step.params["use_tools"], bool):
                raise WorkflowError(f"Step '{step.id}' use_tools must be a boolean.")
        if step.type == "recall_memory" and "top_k" in step.params:
            try:
                top_k = int(step.params["top_k"])
            except (TypeError, ValueError) as exc:
                raise WorkflowError(f"Step '{step.id}' top_k must be an integer.") from exc
            if top_k < 1:
                raise WorkflowError(f"Step '{step.id}' top_k must be >= 1.")
    if not has_finish:
        raise WorkflowError("Workflow needs a finish step.")


def _validate_target(target: str | None, ids: list[str], step_id: str, field: str) -> None:
    if not target:
        return
    if target not in ids:
        raise WorkflowError(f"Step '{step_id}' {field} points to unknown step '{target}'.")

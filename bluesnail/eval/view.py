"""Inspect BlueSnail / SWE-bench evaluation run output."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from bluesnail.eval.predictions import read_predictions_jsonl

SECTIONS = ("summary", "preds", "patch", "trace", "report", "answer", "all")


@dataclass
class InstanceOutput:
    instance_id: str
    stopped_reason: str | None = None
    iterations: int | None = None
    empty_patch: bool = False
    error: str | None = None
    answer: str = ""
    patch: str = ""
    trace: list[dict[str, Any]] = field(default_factory=list)
    files: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvalRunOutput:
    run_id: str
    run_dir: str
    summary: dict[str, Any] = field(default_factory=dict)
    predictions: list[dict[str, Any]] = field(default_factory=list)
    instances: list[InstanceOutput] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "run_dir": self.run_dir,
            "summary": self.summary,
            "predictions": self.predictions,
            "instances": [item.to_dict() for item in self.instances],
        }


def evaluation_root(report_dir: Path | str) -> Path:
    return Path(report_dir) / "logs" / "evaluation"


def resolve_run_dir(report_dir: Path | str, run_id: str | None = None) -> Path:
    root = evaluation_root(report_dir)
    if run_id:
        path = root / run_id
        if not path.is_dir():
            raise FileNotFoundError(f"Eval run not found: {path}")
        return path
    runs = list_run_ids(report_dir)
    if not runs:
        raise FileNotFoundError(f"No eval runs under {root}")
    if len(runs) > 1:
        raise FileNotFoundError(
            "Multiple eval runs found; pass --run_id. Runs: " + ", ".join(runs)
        )
    return root / runs[0]


def list_run_ids(report_dir: Path | str) -> list[str]:
    root = evaluation_root(report_dir)
    if not root.is_dir():
        return []
    names: list[str] = []
    for child in sorted(root.iterdir()):
        if child.is_dir() and _looks_like_run(child):
            names.append(child.name)
    return names


def load_eval_run(report_dir: Path | str, run_id: str | None = None) -> EvalRunOutput:
    run_dir = resolve_run_dir(report_dir, run_id)
    summary = _read_json(run_dir / "results.json")
    predictions = _load_predictions(run_dir, summary)
    pred_map = {
        str(item.get("instance_id")): item
        for item in predictions
        if item.get("instance_id")
    }
    instances = [
        _load_instance(path, pred_map.get(path.name))
        for path in _instance_dirs(run_dir)
    ]
    if not instances:
        instances = [
            InstanceOutput(
                instance_id=str(item.get("instance_id") or ""),
                empty_patch=not str(item.get("model_patch") or "").strip(),
                patch=str(item.get("model_patch") or ""),
            )
            for item in predictions
            if item.get("instance_id")
        ]
    return EvalRunOutput(
        run_id=run_dir.name,
        run_dir=str(run_dir),
        summary=summary,
        predictions=predictions,
        instances=instances,
    )


def format_eval_run(
    run: EvalRunOutput,
    *,
    instance_ids: list[str] | None = None,
    section: str = "summary",
) -> str:
    section = (section or "summary").strip().lower()
    if section not in SECTIONS:
        raise ValueError(f"Unknown section {section!r}. Choose from: {', '.join(SECTIONS)}")
    selected = _select_instances(run.instances, instance_ids)
    if section == "summary":
        text = _format_summary(run, selected)
    elif section == "preds":
        text = _format_preds(run, selected)
    else:
        parts = [_format_summary(run, selected)]
        for item in selected:
            parts.append(_format_instance(item, section=section))
        text = "\n\n".join(part for part in parts if part)
    return text.rstrip() + "\n"


def render_eval_text(
    report_dir: Path | str,
    *,
    run_id: str | None = None,
    instance_ids: list[str] | None = None,
    section: str = "summary",
) -> str:
    run = load_eval_run(report_dir, run_id)
    return format_eval_run(run, instance_ids=instance_ids, section=section)


def _looks_like_run(path: Path) -> bool:
    if (path / "results.json").is_file() or (path / "preds.jsonl").is_file():
        return True
    return any(child.is_dir() for child in path.iterdir())


def _instance_dirs(run_dir: Path) -> list[Path]:
    skip = {"logs"}
    dirs = []
    for child in sorted(run_dir.iterdir()):
        if not child.is_dir() or child.name in skip:
            continue
        if (child / "report.json").is_file() or (child / "patch.diff").is_file() or (
            child / "trace.jsonl"
        ).is_file():
            dirs.append(child)
    return dirs


def _load_predictions(run_dir: Path, summary: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = [run_dir / "preds.jsonl"]
    extra = summary.get("predictions_path")
    if extra:
        candidates.append(Path(str(extra)))
    for path in candidates:
        if path.is_file():
            return read_predictions_jsonl(path)
    return []


def _load_instance(path: Path, prediction: dict[str, Any] | None) -> InstanceOutput:
    report = _read_json(path / "report.json")
    result = report.get("result") if isinstance(report.get("result"), dict) else {}
    patch = ""
    patch_file = path / "patch.diff"
    if patch_file.is_file():
        patch = patch_file.read_text(encoding="utf-8")
    elif prediction:
        patch = str(prediction.get("model_patch") or "")
    answer = str(result.get("answer") or "")
    files = sorted(child.name for child in path.iterdir() if child.is_file())
    return InstanceOutput(
        instance_id=str(report.get("instance_id") or path.name),
        stopped_reason=report.get("stopped_reason"),
        iterations=report.get("iterations"),
        empty_patch=bool(report.get("empty_patch", not patch.strip())),
        error=report.get("error"),
        answer=answer,
        patch=patch.strip(),
        trace=_read_jsonl(path / "trace.jsonl"),
        files=files,
    )


def _select_instances(
    instances: list[InstanceOutput],
    instance_ids: list[str] | None,
) -> list[InstanceOutput]:
    if not instance_ids:
        return list(instances)
    wanted = set(instance_ids)
    selected = [item for item in instances if item.instance_id in wanted]
    missing = wanted.difference(item.instance_id for item in selected)
    if missing:
        raise ValueError("Unknown instance_ids: " + ", ".join(sorted(missing)))
    return selected


def _format_summary(run: EvalRunOutput, instances: list[InstanceOutput]) -> str:
    summary = run.summary
    lines = [
        f"Run: {run.run_id}",
        f"Dir: {run.run_dir}",
    ]
    if summary.get("predictions_path"):
        lines.append(f"Predictions: {summary['predictions_path']}")
    lines.append(
        "Submitted {submitted} · completed {completed} · empty patches {empty} · errors {errors}".format(
            submitted=summary.get("instances_submitted", len(run.predictions)),
            completed=summary.get("instances_completed", len(instances)),
            empty=len(summary.get("instances_with_empty_patches") or []),
            errors=len(summary.get("instances_with_errors") or []),
        )
    )
    if instances:
        lines.append("")
        lines.append("Instances:")
        for item in instances:
            status = "error" if item.error else ("empty" if item.empty_patch else "ok")
            extra = []
            if item.iterations is not None:
                extra.append(f"iter={item.iterations}")
            if item.stopped_reason:
                extra.append(str(item.stopped_reason))
            if item.patch:
                extra.append(f"patch={len(item.patch)} chars")
            suffix = f"  {' '.join(extra)}" if extra else ""
            lines.append(f"  {item.instance_id}  {status}{suffix}")
            if item.error:
                lines.append(f"    {item.error}")
    return "\n".join(lines)


def _format_preds(run: EvalRunOutput, instances: list[InstanceOutput]) -> str:
    wanted = {item.instance_id for item in instances} if instances else None
    rows = run.predictions
    if wanted is not None:
        rows = [item for item in rows if item.get("instance_id") in wanted]
    if not rows:
        return "(no predictions)"
    lines = []
    for item in rows:
        patch = str(item.get("model_patch") or "")
        lines.append(
            "{id}  model={model}  patch={n} chars".format(
                id=item.get("instance_id"),
                model=item.get("model_name_or_path"),
                n=len(patch),
            )
        )
        if patch:
            lines.append(patch)
            lines.append("")
    return "\n".join(lines).rstrip()


def _format_instance(item: InstanceOutput, *, section: str) -> str:
    header = [f"=== {item.instance_id} ==="]
    if item.error:
        header.append(f"error: {item.error}")
    if item.stopped_reason:
        header.append(f"stopped_reason: {item.stopped_reason}")
    if item.iterations is not None:
        header.append(f"iterations: {item.iterations}")
    if item.files:
        header.append("files: " + ", ".join(item.files))
    blocks = ["\n".join(header)]
    want_all = section == "all"
    if want_all or section in {"report", "answer"}:
        blocks.append("-- answer --\n" + (item.answer.strip() or "(empty)"))
    if want_all or section == "patch":
        blocks.append("-- patch --\n" + (item.patch.strip() or "(empty)"))
    if want_all or section == "trace":
        blocks.append("-- trace --\n" + (_format_trace(item.trace) or "(empty)"))
    if section == "report":
        return "\n".join(blocks)
    return "\n\n".join(blocks)


def _format_trace(events: list[dict[str, Any]], *, limit: int = 80) -> str:
    lines: list[str] = []
    for event in events[:limit]:
        kind = event.get("event") or event.get("event_type") or "?"
        data = event.get("data") if isinstance(event.get("data"), dict) else event
        if kind == "workflow" or data.get("step_type"):
            phase = data.get("phase", "")
            step = data.get("step_id") or data.get("step_type")
            outcome = data.get("outcome") or ""
            line = f"{kind} {phase} {step}".strip()
            if outcome:
                line += f" -> {outcome}"
            lines.append(line)
            continue
        if kind == "step":
            iteration = data.get("iteration", "?")
            content = (data.get("content") or "").strip().replace("\n", " ")
            if len(content) > 120:
                content = content[:119] + "…"
            tools = ",".join(
                call.get("name", "?") for call in (data.get("tool_calls") or [])
            )
            extra = f" tools={tools}" if tools else ""
            if content:
                extra += f" {content}"
            lines.append(f"step #{iteration}{extra}".rstrip())
            continue
        if kind == "done":
            lines.append(
                f"done iterations={data.get('iterations')} reason={data.get('stopped_reason')}"
            )
            continue
        if kind == "start":
            ctx = data.get("run_context") or {}
            lines.append(f"start workflow={ctx.get('workflow_name') or ctx.get('workflow_id') or '-'}")
            continue
        lines.append(kind)
    if len(events) > limit:
        lines.append(f"... {len(events) - limit} more events")
    return "\n".join(lines)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            rows.append(payload)
    return rows

"""SWE-bench-compatible dataset loading."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

DATASET_ALIASES = {
    "lite": "SWE-bench/SWE-bench_Lite",
    "verified": "SWE-bench/SWE-bench_Verified",
    "full": "SWE-bench/SWE-bench",
    "multimodal": "SWE-bench/SWE-bench_Multimodal",
    "multilingual": "SWE-bench/SWE-bench_Multilingual",
    "SWE-bench_Lite": "SWE-bench/SWE-bench_Lite",
    "princeton-nlp/SWE-bench_Lite": "SWE-bench/SWE-bench_Lite",
    "princeton-nlp/SWE-bench": "SWE-bench/SWE-bench",
    "princeton-nlp/SWE-bench_Verified": "SWE-bench/SWE-bench_Verified",
}


@dataclass(slots=True)
class BenchInstance:
    instance_id: str
    problem_statement: str
    repo: str = ""
    base_commit: str = ""
    hints_text: str = ""
    patch: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> BenchInstance:
        instance_id = str(payload.get("instance_id") or "").strip()
        if not instance_id:
            raise ValueError("Dataset record is missing instance_id.")
        problem = str(
            payload.get("problem_statement")
            or payload.get("issue")
            or payload.get("prompt")
            or ""
        ).strip()
        if not problem:
            raise ValueError(f"Instance '{instance_id}' is missing problem_statement.")
        extra = dict(payload)
        return cls(
            instance_id=instance_id,
            problem_statement=problem,
            repo=str(payload.get("repo") or ""),
            base_commit=str(payload.get("base_commit") or ""),
            hints_text=str(payload.get("hints_text") or payload.get("hints") or ""),
            patch=str(payload.get("patch") or payload.get("gold_patch") or ""),
            extra=extra,
        )


def resolve_dataset_name(name: str) -> str:
    trimmed = name.strip()
    return DATASET_ALIASES.get(trimmed, DATASET_ALIASES.get(trimmed.lower(), trimmed))


def load_instances(
    dataset_name: str,
    *,
    split: str = "test",
    instance_ids: list[str] | None = None,
) -> list[BenchInstance]:
    resolved = resolve_dataset_name(dataset_name)
    path = Path(resolved)
    if path.exists():
        records = _load_local_records(path)
    else:
        records = _load_huggingface_records(resolved, split)
    instances = [BenchInstance.from_dict(item) for item in records]
    if instance_ids:
        wanted = set(instance_ids)
        instances = [item for item in instances if item.instance_id in wanted]
        missing = wanted.difference(item.instance_id for item in instances)
        if missing:
            raise ValueError("Unknown instance_ids: " + ", ".join(sorted(missing)))
    return instances


def _load_local_records(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".jsonl":
        rows = [_parse_json_line(line) for line in text.splitlines() if line.strip()]
        return [row for row in rows if row is not None]
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        rows = [_parse_json_line(line) for line in text.splitlines() if line.strip()]
        return [row for row in rows if row is not None]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("instances", "data", "test", "dev", "train"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        if payload.get("instance_id"):
            return [payload]
    raise ValueError(f"Unsupported dataset file: {path}")


def _parse_json_line(line: str) -> dict[str, Any] | None:
    payload = json.loads(line)
    return payload if isinstance(payload, dict) else None


def _load_huggingface_records(dataset_name: str, split: str) -> list[dict[str, Any]]:
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise ImportError(
            "Remote SWE-bench datasets require the Hugging Face datasets package. "
            "Install it, or pass -d /path/to/dataset.jsonl. "
            f"Tried to load {dataset_name!r}."
        ) from exc
    dataset = load_dataset(dataset_name, split=split)
    return [dict(row) for row in dataset]


def iter_gold_predictions(instances: Iterable[BenchInstance], model_name: str) -> list[dict[str, str]]:
    return [
        {
            "instance_id": item.instance_id,
            "model_name_or_path": model_name,
            "model_patch": item.patch,
        }
        for item in instances
    ]

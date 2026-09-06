"""Dataset loading for SWE-bench-compatible eval."""

from pathlib import Path

import pytest

from bluesnail.eval.dataset import load_instances, resolve_dataset_name


def test_resolve_dataset_aliases() -> None:
    assert resolve_dataset_name("lite") == "SWE-bench/SWE-bench_Lite"
    assert resolve_dataset_name("verified") == "SWE-bench/SWE-bench_Verified"
    assert resolve_dataset_name("princeton-nlp/SWE-bench_Lite") == "SWE-bench/SWE-bench_Lite"


def test_load_local_jsonl_and_filter(tmp_path: Path) -> None:
    path = tmp_path / "mini.jsonl"
    path.write_text(
        '{"instance_id": "demo__repo-1", "problem_statement": "Fix crash", "patch": "diff --git a/a.py b/a.py\\n"}\n'
        '{"instance_id": "demo__repo-2", "problem_statement": "Fix leak", "patch": ""}\n',
        encoding="utf-8",
    )
    instances = load_instances(str(path), instance_ids=["demo__repo-1"])
    assert len(instances) == 1
    assert instances[0].instance_id == "demo__repo-1"
    assert instances[0].patch.startswith("diff --git")


def test_unknown_instance_ids_raise(tmp_path: Path) -> None:
    path = tmp_path / "one.json"
    path.write_text(
        '[{"instance_id": "only-one", "problem_statement": "x"}]',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Unknown instance_ids"):
        load_instances(str(path), instance_ids=["missing"])

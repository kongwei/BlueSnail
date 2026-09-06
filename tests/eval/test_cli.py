"""SWE-bench-aligned CLI flags."""

from pathlib import Path

from bluesnail.eval.cli import parse_args
from bluesnail.eval.harness import harness_command
from bluesnail.eval import cli as eval_cli


def test_parse_args_match_swebench_flags() -> None:
    args = parse_args(
        [
            "lite",
            "-s",
            "test",
            "-i",
            "sympy__sympy-20590",
            "-p",
            "preds.jsonl",
            "--run_id",
            "my_run",
            "-j",
            "2",
            "-t",
            "120",
            "--report_dir",
            "logs",
        ]
    )
    assert args.dataset_name == "SWE-bench/SWE-bench_Lite"
    assert args.split == "test"
    assert args.instance_ids == ["sympy__sympy-20590"]
    assert args.predictions_path == "preds.jsonl"
    assert args.run_id == "my_run"
    assert args.max_workers == 2
    assert args.timeout == 120
    assert args.report_dir == "logs"


def test_gold_flag_and_predictions_path_gold() -> None:
    args = parse_args(["-d", "lite", "-p", "gold", "--run_id", "validate-gold"])
    assert args.gold is True
    args = parse_args(["--gold", "--run_id", "validate-gold", "-d", "verified"])
    assert args.gold is True
    assert args.dataset_name == "SWE-bench/SWE-bench_Verified"


def test_harness_command_uses_swebench_module() -> None:
    command = harness_command(
        dataset_name="SWE-bench/SWE-bench_Lite",
        split="test",
        predictions_path="preds.jsonl",
        run_id="my_run",
        max_workers=8,
        timeout=1800,
        report_dir=".",
        instance_ids=["sympy__sympy-20590"],
    )
    assert command[1:3] == ["-m", "swebench.harness.run_evaluation"]
    assert "--dataset_name" in command
    assert "--predictions_path" in command
    assert "--run_id" in command
    assert "--instance_ids" in command
    assert "sympy__sympy-20590" in command


def test_main_gold_local_dataset(tmp_path: Path, monkeypatch) -> None:
    dataset = tmp_path / "data.jsonl"
    dataset.write_text(
        '{"instance_id": "demo__repo-1", "problem_statement": "fix", "patch": "diff --git a/a b/a\\n"}\n',
        encoding="utf-8",
    )
    recorded: dict[str, list[str]] = {}

    def fake_run(cmd, check=False):
        recorded["cmd"] = list(cmd)
        return type("R", (), {"returncode": 0})()

    monkeypatch.setattr(eval_cli.subprocess, "run", fake_run)
    code = eval_cli.main(
        [
            "-d",
            str(dataset),
            "--gold",
            "--run_id",
            "cli-gold",
            "--report_dir",
            str(tmp_path),
            "--harness",
        ]
    )
    assert code == 0
    preds = tmp_path / "logs" / "evaluation" / "cli-gold" / "preds.jsonl"
    assert preds.is_file()
    assert "demo__repo-1" in preds.read_text(encoding="utf-8")
    assert recorded["cmd"][1:3] == ["-m", "swebench.harness.run_evaluation"]
    pred_idx = recorded["cmd"].index("--predictions_path")
    assert recorded["cmd"][pred_idx + 1] == "gold"


def test_main_show_lists_runs(tmp_path: Path, capsys) -> None:
    dataset = tmp_path / "data.jsonl"
    dataset.write_text(
        '{"instance_id": "demo__repo-1", "problem_statement": "fix", "patch": "diff --git a/a b/a\\n"}\n',
        encoding="utf-8",
    )
    assert eval_cli.main(
        ["-d", str(dataset), "--gold", "--run_id", "show-gold", "--report_dir", str(tmp_path)]
    ) == 0
    code = eval_cli.main(["show", "--list-runs", "--report_dir", str(tmp_path)])
    assert code == 0
    assert "show-gold" in capsys.readouterr().out

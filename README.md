# BlueSnail

Modular AI Agent framework. Each Agent capability lives in its own package; `bluesnail.integration` wires them into a runnable `Agent`.

## Modules

| Module | Package | Unit tests |
| --- | --- | --- |
| Shared contracts | `bluesnail.core` | `tests/core` |
| LLM providers | `bluesnail.llm` | `tests/llm` |
| Memory | `bluesnail.memory` | `tests/memory` |
| Context window | `bluesnail.context` | `tests/context` |
| Tools | `bluesnail.tools` | `tests/tools` |
| Skills | `bluesnail.skills` | `tests/skills` |
| Workflow schema | `bluesnail.workflow` | `tests/workflow` |
| Scheduler | `bluesnail.scheduler` | `tests/scheduler` |
| Integration (Agent) | `bluesnail.integration` | `tests/integration` |
| Web UI | `bluesnail.web` | `tests/web` |

## Install

```bash
pip install -e ".[dev,web,tui]"
```

## Test

All tests:

```bash
pytest
```

One module's unit-test guard:

```bash
pytest tests/core
pytest tests/integration
python scripts/guard.py
```

`scripts/guard.py` runs each module test directory on its own so a broken module cannot hide behind the full suite.

## Run

```bash
bluesnail
bluesnail-tui --url http://127.0.0.1:7860
```

## SWE-Bench

端到端评测命令 bluesnail-eval，参数与 SWE-bench harness（python -m swebench.harness.run_evaluation）对齐。

### 生成预测

```bash
bluesnail-eval lite \
  --run_id my_run \
  -i sympy__sympy-20590 \
  -p preds.jsonl \
  -j 1 \
  -t 1800 \
  --report_dir .
```

输出 SWE-bench 格式的 JSONL（instance_id / model_name_or_path / model_patch），并在 logs/evaluation/<run_id>/ 下保存每条任务的推理 trace。

### Gold 校验（对齐 swebench eval … --gold）

```bluesnail-eval verified --gold --run_id validate-gold -i sympy__sympy-20590```

### 生成后转调官方评测

```bluesnail-eval lite -p preds.jsonl --run_id my_run --harness```

等价于调用：

```
python -m swebench.harness.run_evaluation --dataset_name … --predictions_path … --run_id … --max_workers …
```

共用标志：`-d/--dataset_name`、`-s/--split`、`-i/--instance_ids`、`-p/--predictions_path`、`--run_id`、`--max_workers/-j`、`-t/--timeout`、`--report_dir`、`--rewrite_reports`、`--modal`。数据集可用别名 `lite` / `verified` / `full`，或本地 JSON/JSONL。
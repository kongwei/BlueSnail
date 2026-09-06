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

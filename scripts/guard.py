"""Run each module's unit-test directory in isolation."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULES = [
    "core",
    "llm",
    "memory",
    "context",
    "tools",
    "skills",
    "workflow",
    "scheduler",
    "integration",
    "service",
    "web",
    "tui",
]


def main() -> int:
    failed: list[str] = []
    for name in MODULES:
        target = ROOT / "tests" / name
        print(f"\n=== guard {name} ({target.relative_to(ROOT)}) ===")
        result = subprocess.run(
            [sys.executable, "-m", "pytest", str(target)],
            cwd=ROOT,
        )
        if result.returncode != 0:
            failed.append(name)
    if failed:
        print("\nFailed modules:", ", ".join(failed))
        return 1
    print("\nAll module guards passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Ensure every module keeps its own source tree and unit-test guard."""

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
    "web",
]


def test_each_module_has_package_and_tests() -> None:
    missing: list[str] = []
    for name in MODULES:
        package = ROOT / "bluesnail" / name / "__init__.py"
        tests = list((ROOT / "tests" / name).glob("test_*.py"))
        if not package.is_file():
            missing.append(f"{name}: missing package")
        if not tests:
            missing.append(f"{name}: missing unit tests")
    assert not missing, missing

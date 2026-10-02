"""Research tooling remains executable, checked, and separate from historical outputs."""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "scripts" / "studio_research"
NAMES = (
    "acceptance_authority_probe",
    "acceptance_authority_serena",
    "acceptance_current_probe",
    "acceptance_flags_probe",
    "acceptance_serena",
    "audit_upload_response_loss",
    "authority_guard_serena",
    "authority_posix_probe",
    "authority_posix_runtime_probe",
    "comparison_repair_serena",
    "editorial_split_probe",
    "paired_comparison_posix_probe",
    "positive_acceptance_grounded_serena",
    "positive_acceptance_serena",
    "private_journal_posix_probe",
    "private_journal_serena",
    "private_storage_serena",
    "storage_adoption_posix_probe",
    "storage_adoption_serena",
    "checked_research_serena",
)


def test_studio_research_tools_are_in_checked_scope() -> None:
    assert {path.stem for path in TOOLS.glob("*.py")} == set(NAMES)
    assert not list((ROOT / "specs" / "evidence-based-studio").glob("*.py"))


@pytest.mark.parametrize("name", NAMES)
def test_studio_research_tools_compile(name: str) -> None:
    path = TOOLS / f"{name}.py"
    compile(path.read_bytes(), str(path), "exec")


@pytest.mark.parametrize(
    ("name", "filename"),
    (
        ("acceptance_authority_probe", "T8-authority-native-replay.json"),
        ("acceptance_flags_probe", "T8-flags-admission-counterexample.json"),
        ("editorial_split_probe", "T8-editorial-split-counterexample.json"),
        ("paired_comparison_posix_probe", "T8-paired-posix.json"),
        ("acceptance_current_probe", "probe.json"),
    ),
)
def test_studio_research_outputs_keep_original_evidence_location(name: str, filename: str) -> None:
    path = TOOLS / f"{name}.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    assignments = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "destination" for target in node.targets
        )
    ]
    assert len(assignments) == 1
    # Evaluate only the tool's actual path expression, never its historical diagnostic.
    expression = compile(ast.Expression(assignments[0].value), str(path), "eval")
    destination = eval(
        expression,
        {
            "__builtins__": {},
            "Path": Path,
            "__file__": str(path),
            "root": ROOT,
            "sys": SimpleNamespace(
                argv=[str(path), str(ROOT / "specs/evidence-based-studio" / filename)]
            ),
        },
    )
    assert destination == ROOT / "specs" / "evidence-based-studio" / filename

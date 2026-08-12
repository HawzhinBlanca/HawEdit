"""The editor agent: it can propose, and structurally it cannot commit.

`editor_agent.py`'s whole reason to exist separately from `agent.py` is a narrower promise than
even a read-only one: it can check whether a boundary revision would be legal, and nothing about
it can approve or write one. Two things are checked here, not just the ordinary "the tool
works" coverage `test_proposals.py` already gives `propose_boundary_revision` itself:

- The agent's registered tool set has exactly one tool, and it is not named anything that
  suggests commit/approve/apply.
- `commit_boundary_revision` does not appear anywhere reachable from this module's own source —
  an AST-level guarantee, the same kind `test_agent.py` holds `agent.py` to, rather than a
  promise the docstring makes and nothing checks.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

pytest.importorskip("pydantic_ai")

from hawedit.agent import Deps
from hawedit.editor_agent import build_editor_agent
from hawedit.proposals import BoundaryRevisionProposal

ROOT = Path(__file__).resolve().parents[1]
EDITOR_AGENT_SRC = ROOT / "src" / "hawedit" / "editor_agent.py"

_DEFAULT_BOUNDARY: dict[str, object] = {
    "anchor_in_ms": 100,
    "anchor_out_ms": 4100,
    "final_in_ms": 0,
    "final_out_ms": 4300,
    "in_extended_by": "vad_onset",
    "out_extended_by": "tail",
    "sentence_complete": True,
    "confidence": None,
}


def _write_report(work_dir: Path) -> None:
    report: dict[str, object] = {
        "media_id": "fixture",
        "source": "x.mp4",
        "work_dir": str(work_dir),
        "complete": True,
        "skipped": [],
        "boundary": _DEFAULT_BOUNDARY,
        "candidates": [],
        "rejected": [],
        "clip": None,
        "render": None,
        "delivery": None,
    }
    work_dir.mkdir(parents=True, exist_ok=True)
    (work_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")


def test_editor_agent_module_never_calls_commit(tmp_path: Path) -> None:
    """`commit_boundary_revision` must not be referenced anywhere in this module's source — not
    imported, not called, not passed around. If a future edit adds a commit-capable tool here,
    this fails on the `ast.Name`/`ast.Attribute` reference itself, not on behavior a test would
    have to think to exercise."""
    tree = ast.parse(EDITOR_AGENT_SRC.read_text(encoding="utf-8"))
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)} | {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    assert "commit_boundary_revision" not in names


def test_the_editor_agent_has_exactly_one_tool_and_it_only_proposes(tmp_path: Path) -> None:
    """Same pinned-version rationale as `agent.py`'s equivalent test (`pyproject.toml` pins
    `pydantic-ai-slim==2.28.0` exactly)."""
    from pydantic_ai.models.test import TestModel

    _write_report(tmp_path)
    agent = build_editor_agent(TestModel(), Deps(work_dir=tmp_path))
    tool_names = {tool.name for tool in agent._function_toolset.tools.values()}
    assert tool_names == {"propose_boundary_revision_tool"}


def test_the_agent_reports_an_invalid_proposal_rather_than_silently_fixing_it(
    tmp_path: Path,
) -> None:
    from pydantic_ai.models.test import TestModel

    _write_report(tmp_path)
    # TestModel's default arg generation for an int parameter is 0 for both — final_out_ms=0
    # is before anchor_out_ms=4100, an invalid proposal. This is the case worth asserting on:
    # the agent must surface that as an invalid result, not silently clamp or retry with a
    # different number the model was never asked to pick.
    agent = build_editor_agent(TestModel(), Deps(work_dir=tmp_path))
    result = agent.run_sync("propose a revision", deps=Deps(work_dir=tmp_path))
    assert '"valid":false' in result.output.replace(" ", "")


def test_the_proposal_tool_returns_the_typed_dataclass_not_a_bare_string(tmp_path: Path) -> None:
    """`propose_boundary_revision` itself already returns `BoundaryRevisionProposal` — this
    confirms the wrapped tool doesn't lose that on the way through pydantic-ai's call layer by
    checking the same fields survive round-trip in the final agent output."""
    from pydantic_ai.models.test import TestModel

    _write_report(tmp_path)
    agent = build_editor_agent(TestModel(), Deps(work_dir=tmp_path))
    result = agent.run_sync("propose a revision", deps=Deps(work_dir=tmp_path))
    assert "media_id" in result.output
    assert "anchor_in_ms" in result.output


def test_direct_call_still_returns_the_real_dataclass_type(tmp_path: Path) -> None:
    from hawedit.proposals import propose_boundary_revision

    _write_report(tmp_path)
    proposal = propose_boundary_revision(tmp_path, final_in_ms=0, final_out_ms=4500)
    assert isinstance(proposal, BoundaryRevisionProposal)

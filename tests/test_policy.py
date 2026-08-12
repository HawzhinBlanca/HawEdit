"""The Policy Gate, enforced: every tool any agent registers is declared, or the build fails.

`policy.py` is a declaration; this file is the gate. The property worth having is not "the
policy file lists some tools" — it is that **a capability cannot ship without someone deciding
its approval class**. That needs the check to run against agents discovered from the source
tree, not against a list a future edit would have to remember to update.

So `_all_agent_builders` finds every `build_*_agent` function exported by `src/hawedit/`, builds
each one, and reads the tools it actually registered. A new agent module with an undeclared tool
fails here on the day it is added, without this file being touched.
"""

from __future__ import annotations

import importlib
import inspect
import json
import pkgutil
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("pydantic_ai")

import hawedit
from hawedit.agent import Deps, app_manifest
from hawedit.policy import (
    BLOCKED_OPERATIONS,
    POLICY_VERSION,
    TOOL_POLICIES,
    ApprovalClass,
    PolicyViolation,
    approval_for,
    assert_tools_are_declared,
    mutating_tool_names,
)

ROOT = Path(__file__).resolve().parents[1]


def _write_report(work_dir: Path) -> None:
    """The minimum a `build_*_agent` needs to construct — none of them read at build time, but
    a builder that grew a validating read would fail loudly here rather than silently skip."""
    work_dir.mkdir(parents=True, exist_ok=True)
    (work_dir / "report.json").write_text(
        json.dumps(
            {
                "media_id": "fixture",
                "source": "x.mp4",
                "work_dir": str(work_dir),
                "complete": True,
                "skipped": [],
                "candidates": [],
                "rejected": [],
                "clip": None,
                "render": None,
                "delivery": None,
                "boundary": {
                    "anchor_in_ms": 100,
                    "anchor_out_ms": 900,
                    "final_in_ms": 0,
                    "final_out_ms": 1000,
                    "in_extended_by": None,
                    "out_extended_by": None,
                    "sentence_complete": True,
                    "confidence": None,
                },
            }
        ),
        encoding="utf-8",
    )


def _all_agent_builders() -> Iterator[tuple[str, Callable[..., Any]]]:
    """Every `build_*_agent` callable exported anywhere under `hawedit`.

    Discovered rather than listed: the whole value of this gate is that it covers an agent
    nobody remembered to add to a test.
    """
    for module_info in pkgutil.iter_modules(hawedit.__path__):
        module = importlib.import_module(f"hawedit.{module_info.name}")
        for name, obj in vars(module).items():
            if (
                name.startswith("build_")
                and name.endswith("_agent")
                and inspect.isfunction(obj)
                and obj.__module__ == module.__name__
            ):
                yield f"{module.__name__}.{name}", obj


def _registered_tool_names(agent: Any) -> set[str]:
    return {tool.name for tool in agent._function_toolset.tools.values()}


# --- the gate itself --------------------------------------------------------------------------


def test_at_least_two_agent_builders_are_discovered() -> None:
    """The discovery above must actually find things, or every test below passes vacuously."""
    found = dict(_all_agent_builders())
    assert len(found) >= 2, f"expected the read-only and editor agents at minimum, found {found}"
    assert any("editor_agent" in name for name in found)
    assert any(name.endswith("agent.build_agent") for name in found)


def test_every_registered_tool_on_every_agent_is_declared_in_policy(tmp_path: Path) -> None:
    """The gate: a capability cannot ship without a declared approval class."""
    from pydantic_ai.models.test import TestModel

    _write_report(tmp_path)
    for label, builder in _all_agent_builders():
        agent = builder(TestModel(), Deps(work_dir=tmp_path))
        names = _registered_tool_names(agent)
        assert names, f"{label} registered no tools at all"
        # Raises PolicyViolation on an undeclared tool or a blocked-capability name.
        assert_tools_are_declared(names)


def test_no_agent_exposes_a_blocked_operation(tmp_path: Path) -> None:
    """`BLOCKED_OPERATIONS` as a checked contract rather than a paragraph."""
    from pydantic_ai.models.test import TestModel

    _write_report(tmp_path)
    for label, builder in _all_agent_builders():
        agent = builder(TestModel(), Deps(work_dir=tmp_path))
        for name in _registered_tool_names(agent):
            assert approval_for(name) is not ApprovalClass.FORBIDDEN, (
                f"{label} registered {name!r}, which policy declares FORBIDDEN"
            )


def test_nothing_reachable_from_an_agent_mutates_anything() -> None:
    """Today's strongest statement, and one that should fail loudly the day it stops holding:
    the set of mutating capabilities reachable from any agent is empty, not merely small."""
    assert mutating_tool_names() == ()


def test_an_undeclared_tool_is_refused() -> None:
    """The gate must reject, not just accept — checked directly rather than inferred from the
    passing cases above."""
    with pytest.raises(PolicyViolation, match="not declared"):
        assert_tools_are_declared({"inspect_run", "some_new_tool_nobody_declared"})


def test_a_blocked_capability_name_is_refused() -> None:
    for forbidden in ("run_shell", "install_package", "publish_clip", "delete_run"):
        with pytest.raises(PolicyViolation, match="blocked-capability"):
            assert_tools_are_declared({forbidden})


def test_a_blocked_capability_is_refused_even_when_someone_declares_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The case that makes `_FORBIDDEN_NAME_FRAGMENTS` load-bearing rather than dead code.

    A forbidden capability is nearly always *also* undeclared, so if the declaration check ran
    first it would report merely "undeclared" and the blocked list would never fire — which is
    exactly what the original ordering did, caught by the test above failing. The realistic
    failure this defends is a future edit that adds a `ToolPolicy` for something forbidden and
    passes review; declaring it must not be a way through.
    """
    import hawedit.policy as policy_module

    declared_forbidden = policy_module.ToolPolicy(
        name="publish_clip",
        approval=ApprovalClass.NONE,
        mutating=False,
        note="deliberately declared, to prove declaring is not a way through",
    )
    monkeypatch.setattr(
        policy_module, "TOOL_POLICIES", (*TOOL_POLICIES, declared_forbidden), raising=True
    )
    with pytest.raises(PolicyViolation, match="blocked-capability"):
        policy_module.assert_tools_are_declared({"publish_clip"})


def test_approval_for_an_undeclared_tool_raises() -> None:
    with pytest.raises(PolicyViolation, match="not declared"):
        approval_for("no_such_tool")


# --- the policy reaches the model -------------------------------------------------------------


def test_the_manifest_carries_the_policy_version_and_blocked_operations() -> None:
    """The architecture record's App Manifest contents list names both explicitly."""
    manifest = app_manifest()
    assert manifest.policy_version == POLICY_VERSION
    assert manifest.blocked_operations == BLOCKED_OPERATIONS
    prompt = manifest.as_prompt()
    assert f"policy version: {POLICY_VERSION}" in prompt
    for operation in BLOCKED_OPERATIONS:
        assert operation in prompt


def test_every_declared_policy_has_a_note() -> None:
    """A declared approval class with no stated reason is a decision nobody recorded."""
    undocumented = [policy.name for policy in TOOL_POLICIES if not policy.note.strip()]
    assert not undocumented, f"ToolPolicy entries with no note: {undocumented}"

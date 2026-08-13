"""The Policy Gate: which tools may exist, and which need a human before they act.

`AGENT_ARCHITECTURE_DEFINITIVE_2026-08-11.md` names this as a numbered architectural component:
"A hard **Policy Gate** outside the model. The production agent receives only named HawEdit
tools and cannot write source code, invoke an unrestricted shell, install packages, or silently
publish an edit." And: "**The Policy Gate owns authority.** It decides which action is allowed
and whether human approval is required. A model's promise to behave is never considered
authorization."

**This module is a declaration, and the tests are the gate.** Nothing here inspects a running
agent at request time — that would be a second enforcement layer duplicating what the tool
functions already do, and a weaker one, since it could only see calls that reached it.
Instead every tool this codebase registers must appear in `TOOL_POLICIES`, and
`tests/test_policy.py` walks every agent constructor in `src/` and fails if any registered tool
is undeclared, or if any declared-`FORBIDDEN` capability was registered at all. The effect is
that adding a tool without deciding its approval class is a failing build, not a silent
capability grant — which is the property "the policy gate owns authority" actually needs.

**Why a declaration rather than a runtime interceptor.** The enforcement that matters already
lives in the functions: `commit_boundary_revision` refuses an unattributed or unconfirmed
approval, `assert_boundary_invariant` refuses an illegal span, `Deps.work_dir` is not
model-suppliable. A runtime policy layer wrapping those would add a place for the two to
disagree — and the architecture record is explicit that "tool implementations—not prompts—verify
all of these." So this module's job is to make the *set* of capabilities an auditable, tested
contract, and to give the model an honest statement of what it may not do; not to re-check what
the implementations already check.

**`BLOCKED_OPERATIONS` is the record's own never-expose list, verbatim in intent.** It exists
to be asserted against: `tests/test_policy.py` requires that no tool named anything matching
these capabilities is registered on any agent, so the list is a test fixture rather than
documentation that could drift from what ships.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final

__all__ = [
    "BLOCKED_OPERATIONS",
    "POLICY_VERSION",
    "TOOL_POLICIES",
    "ApprovalClass",
    "PolicyViolation",
    "ToolPolicy",
    "approval_for",
    "assert_tools_are_declared",
    "mutating_tool_names",
]

# Bumped when an approval class changes or a capability is added/removed — the manifest shows
# this to the model, and the architecture record's rollback gate ("a rollback restores the
# previous model, prompt, skill, policy and workflow version") needs policy to be a version,
# not an implicit state of the source tree.
POLICY_VERSION: Final = "1"


class PolicyViolation(RuntimeError):
    """Raised when a tool is registered that policy does not declare, or declares forbidden."""


class ApprovalClass(Enum):
    """What a capability needs before it may take effect."""

    #: Read-only. No approval, because nothing changes.
    NONE = "none"
    #: A named human must approve this specific change before it takes effect. `proposals.py`'s
    #: `commit_boundary_revision` is the implementation: attributed, confirmed, and refused
    #: otherwise. A model asserting that a human approved is never sufficient.
    HUMAN = "human"
    #: Must never be reachable from an agent at all. Not "needs approval" — not offered.
    FORBIDDEN = "forbidden"


@dataclass(frozen=True, slots=True)
class ToolPolicy:
    """One capability's declared class. `mutating` is stated, not inferred from the name."""

    name: str
    approval: ApprovalClass
    mutating: bool
    note: str = ""


# Every tool any agent in this codebase registers. A tool absent from here fails
# `assert_tools_are_declared`, so a new capability cannot ship without an explicit decision
# about whether it changes anything and who must approve it.
TOOL_POLICIES: Final[tuple[ToolPolicy, ...]] = (
    ToolPolicy(
        name="inspect_run",
        approval=ApprovalClass.NONE,
        mutating=False,
        note="Reads report.json for one run.",
    ),
    ToolPolicy(
        name="explain_run_state",
        approval=ApprovalClass.NONE,
        mutating=False,
        note="Quotes the run's own recorded StageSkipped reason.",
    ),
    ToolPolicy(
        name="compare_candidates",
        approval=ApprovalClass.NONE,
        mutating=False,
        note="Lists §3 Stage 3 survivors and rejections.",
    ),
    ToolPolicy(
        name="run_timeline",
        approval=ApprovalClass.NONE,
        mutating=False,
        note="Reads the append-only events.jsonl ledger.",
    ),
    ToolPolicy(
        name="run_quality_checks",
        approval=ApprovalClass.NONE,
        mutating=False,
        note=(
            "Runs the deterministic render-gate checks against the current clip and reports "
            "each one. Reuses assert_boundary_invariant; writes nothing."
        ),
    ),
    ToolPolicy(
        name="propose_boundary_revision_tool",
        approval=ApprovalClass.NONE,
        mutating=False,
        note=(
            "Validates a proposed span and returns the verdict. Writes nothing: the proposal "
            "is a value, and committing it is a separate function no agent may call."
        ),
    ),
    ToolPolicy(
        name="propose_caption_revision_tool",
        approval=ApprovalClass.NONE,
        mutating=False,
        note=(
            "Validates a proposed caption style against Kurdish invariant #4 and returns the "
            "verdict. Writes nothing, same shape as propose_boundary_revision_tool: committing "
            "is a separate function (commit_caption_revision) no agent may call."
        ),
    ),
    ToolPolicy(
        name="export_developer_report_tool",
        approval=ApprovalClass.NONE,
        mutating=False,
        note=(
            "Composes and validates a structured developer report (sanitized against Kurdish-"
            "script content) and returns it as a value. Writes nothing: write_developer_report "
            "is a separate function no agent may call."
        ),
    ),
)

# The architecture record's "never expose to the production creative agent" list. Asserted
# against every registered toolset by `tests/test_policy.py`, so this is a checked contract
# rather than a paragraph that could drift from what ships.
BLOCKED_OPERATIONS: Final[tuple[str, ...]] = (
    "arbitrary shell execution",
    "general filesystem write access",
    "package installation",
    "source-code mutation",
    "unrestricted web browsing or arbitrary MCP servers",
    "direct publishing without a separate approval token",
)

# Substrings that would indicate one of `BLOCKED_OPERATIONS` had been registered as a tool.
# Deliberately broad: a false positive is a five-second rename, a false negative is a shipped
# capability nobody decided to grant.
_FORBIDDEN_NAME_FRAGMENTS: Final[tuple[str, ...]] = (
    "shell",
    "exec",
    "subprocess",
    "system",
    "install",
    "pip",
    "write_file",
    "delete",
    "rmtree",
    "unlink",
    "publish",
    "upload",
    "commit_",
    "browse",
    "fetch_url",
    "http",
)


def approval_for(tool_name: str) -> ApprovalClass:
    """The declared approval class for `tool_name`.

    Raises:
        PolicyViolation: the tool is not declared in `TOOL_POLICIES`.
    """
    for policy in TOOL_POLICIES:
        if policy.name == tool_name:
            return policy.approval
    raise PolicyViolation(
        f"tool {tool_name!r} is not declared in policy.TOOL_POLICIES. A capability with no "
        f"declared approval class is a capability nobody decided to grant."
    )


def mutating_tool_names() -> tuple[str, ...]:
    """Every declared tool that changes something. Empty today, and that is the point: no agent
    in this codebase can mutate anything, so the set a reviewer must scrutinise is empty rather
    than merely small."""
    return tuple(policy.name for policy in TOOL_POLICIES if policy.mutating)


def assert_tools_are_declared(tool_names: frozenset[str] | set[str]) -> None:
    """Refuse a toolset containing an undeclared tool, or one matching a blocked capability.

    Args:
        tool_names: the names an agent actually registered, read off the built agent rather
            than from a constant — the point is to catch a tool that exists and was never
            declared, which a constant-to-constant comparison would miss by construction.

    Raises:
        PolicyViolation: a registered tool is undeclared, or its name indicates a capability
            `BLOCKED_OPERATIONS` forbids.
    """
    # Blocked-capability names are checked FIRST, before the declaration check, and this order
    # is the whole point rather than an accident. A forbidden capability is nearly always also
    # undeclared, so checking declaration first would report it as merely undeclared and leave
    # `_FORBIDDEN_NAME_FRAGMENTS` unreachable — dead code defending nothing. Checked first, the
    # list also refuses a forbidden tool that someone *did* add a `ToolPolicy` for, which is the
    # realistic failure: a future edit declaring `publish_clip` and sailing through review.
    # Found by `test_a_blocked_capability_name_is_refused` failing on the original order.
    for name in sorted(tool_names):
        # `commit_` is in the fragment list, and the proposal tool is deliberately named so it
        # cannot match: `propose_boundary_revision_tool`. If a future rename made a read-only
        # tool look like a mutating one, that is worth failing on rather than explaining away.
        hit = next((f for f in _FORBIDDEN_NAME_FRAGMENTS if f in name.lower()), None)
        if hit is not None:
            raise PolicyViolation(
                f"tool {name!r} matches the blocked-capability fragment {hit!r}. "
                f"BLOCKED_OPERATIONS forbids exposing these to an agent: "
                f"{', '.join(BLOCKED_OPERATIONS)}."
            )
    declared = {policy.name for policy in TOOL_POLICIES}
    undeclared = sorted(set(tool_names) - declared)
    if undeclared:
        raise PolicyViolation(
            f"registered tools are not declared in policy.TOOL_POLICIES: {undeclared}. Add a "
            f"ToolPolicy with an explicit approval class, or do not register the tool."
        )

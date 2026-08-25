"""Acceptance gate: "Sensitive media/transcript content is absent from telemetry unless a
project policy explicitly enables it."

No telemetry, error-reporting, or APM SDK is imported anywhere in this codebase — checked
directly via AST, not assumed from the absence of a line in `pyproject.toml`. `policy.py`'s
`BLOCKED_OPERATIONS`/`TOOL_POLICIES` (D-A10) declare no telemetry capability either, so the
qualifier "unless a project policy explicitly enables it" has nothing enabling it today: the
gate holds by construction rather than by nobody having gotten around to violating it.

`grep -rln "logging"` finds real hits — DBOS logs its own operation internally (visible in
every `verify.sh` run's `[INFO] (dbos:...)` lines) and Python's stdlib `logging` module is
already imported in a few places for local, non-transmitting output. Neither is what this test
is about: the risk this acceptance gate names is content leaving the machine to an external
collector, and stdlib `logging` writing to a local stream is not that. The check below is
scoped to the SDKs that actually transmit — the same "does this module even *import* the
capability" discipline `test_capability_surface.py` already applies to shell/network access
(D-A11), applied here to the one capability that acceptance gate names specifically.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "hawedit"

# Import names of real external telemetry/APM/error-reporting SDKs. Not `logging` (stdlib,
# local by default) and not generic words like "segment" or "analytics" that collide with this
# codebase's own vocabulary (audio segments, editorial analytics) — every name here is the
# actual PyPI/import name of a product whose entire purpose is sending data off this machine.
_TELEMETRY_IMPORTS: frozenset[str] = frozenset(
    {
        "sentry_sdk",
        "opentelemetry",
        "datadog",
        "ddtrace",
        "newrelic",
        "honeycomb",
        "honeycomb_opentelemetry",
        "posthog",
        "mixpanel",
        "rollbar",
        "bugsnag",
        "elasticapm",
        "loggly",
        "splunklib",
        "amplitude",
    }
)


def _imported_top_level_names(source: Path) -> set[str]:
    tree = ast.parse(source.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.add(node.module.split(".")[0])
    return names


def test_at_least_some_modules_are_scanned() -> None:
    """Guards against the check below passing vacuously over an empty directory."""
    modules = list(SRC.glob("*.py"))
    assert len(modules) >= 50, f"expected the full hawedit package, found {len(modules)} files"


def test_no_module_imports_an_external_telemetry_sdk() -> None:
    hits: dict[str, set[str]] = {}
    for path in SRC.glob("*.py"):
        imported = _imported_top_level_names(path) & _TELEMETRY_IMPORTS
        if imported:
            hits[path.name] = imported
    assert not hits, (
        f"these modules import an external telemetry/APM SDK, which would transmit whatever "
        f"they touch (potentially transcript/media content) off this machine — no policy in "
        f"policy.py enables that capability, so importing it here is a capability nobody "
        f"declared: {hits}"
    )


def test_no_declared_tool_policy_names_a_telemetry_capability() -> None:
    """The other half of "unless a project policy explicitly enables it" — checked from the
    policy side too, so a future edit cannot add telemetry by declaring it there instead of
    importing an SDK directly."""
    from hawedit.policy import TOOL_POLICIES

    hits = [
        p.name for p in TOOL_POLICIES if "telemetry" in p.name.lower() or "sentry" in p.name.lower()
    ]
    assert not hits, f"policy.py declares a telemetry-shaped tool nothing here expected: {hits}"

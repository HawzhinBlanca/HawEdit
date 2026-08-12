"""Import-level proof that no agent-defining module can even reach a dangerous capability.

`test_policy.py` proves no *tool* exposes a blocked operation — it checks what got
registered. This file proves something stronger and independent: the module that *defines*
those tools does not import anything that could perform one, whether or not it is ever wired
to a tool. A tool the Policy Gate would catch is a capability someone remembered to register;
a bare import sitting unused in the same file is one a future edit could reach by writing a
single new line, with no test forcing a decision about its approval class first.

Scoped to the modules that define `build_*_agent` functions (found the same way
`test_policy.py` finds them), not their transitive dependency tree — `pydantic_ai` itself
uses httpx internally, and auditing every third-party import is a different, much bigger
property than "did this codebase's own agent-definition file add a dangerous import."
"""

from __future__ import annotations

import ast
import importlib
import pkgutil
from pathlib import Path

import hawedit

# Import names whose mere presence is disqualifying, mapped to the BLOCKED_OPERATIONS
# capability they would open: arbitrary shell execution, filesystem mutation outside what
# the tested tool functions already do, package installation, and network/browsing.
_DANGEROUS_IMPORTS: frozenset[str] = frozenset(
    {
        "subprocess",
        "os",
        "shutil",
        "socket",
        "urllib",
        "requests",
        "httpx",
        "aiohttp",
        "ftplib",
        "telnetlib",
        "smtplib",
        "pip",
        "ensurepip",
    }
)


def _agent_module_names() -> set[str]:
    """Every module under `hawedit` that defines a `build_*_agent` function."""
    found: set[str] = set()
    for module_info in pkgutil.iter_modules(hawedit.__path__):
        module = importlib.import_module(f"hawedit.{module_info.name}")
        for name, obj in vars(module).items():
            if (
                name.startswith("build_")
                and name.endswith("_agent")
                and getattr(obj, "__module__", None) == module.__name__
            ):
                found.add(module.__name__)
    return found


def _imported_top_level_names(source: Path) -> set[str]:
    tree = ast.parse(source.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.add(node.module.split(".")[0])
    return names


def test_at_least_two_agent_modules_are_found() -> None:
    """Guards against the discovery below passing vacuously over an empty set."""
    assert len(_agent_module_names()) >= 2


def test_no_agent_module_imports_a_dangerous_capability() -> None:
    root = Path(hawedit.__file__).resolve().parent
    for module_name in _agent_module_names():
        source = root / f"{module_name.rsplit('.')[-1]}.py"
        imported = _imported_top_level_names(source)
        hit = imported & _DANGEROUS_IMPORTS
        assert not hit, (
            f"{module_name} imports {sorted(hit)}, which BLOCKED_OPERATIONS forbids exposing "
            f"to an agent — even unused, it is one call away from a capability nobody "
            f"declared in policy.TOOL_POLICIES."
        )

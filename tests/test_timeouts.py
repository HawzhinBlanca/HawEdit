"""Subprocess timeout invariant tests (§7, D3).

Asserts that no `subprocess.run` or `subprocess.Popen` in `src/hawedit/` executes
without a finite, non-null timeout parameter.
"""

from __future__ import annotations

import ast
from pathlib import Path


def _is_subprocess_call(node: ast.Call, target_name: str) -> bool:
    """Check if AST call node matches subprocess.<target_name>."""
    if (
        isinstance(node.func, ast.Attribute)
        and node.func.attr == target_name
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "subprocess"
    ):
        return True
    return bool(isinstance(node.func, ast.Name) and node.func.id == target_name)


def test_no_subprocess_call_lacks_a_timeout() -> None:
    """D3: Every subprocess.run and Popen in src/ must enforce a finite timeout."""
    src_dir = Path(__file__).resolve().parents[1] / "src" / "hawedit"
    assert src_dir.is_dir(), f"src directory not found at {src_dir}"

    py_files = sorted(src_dir.rglob("*.py"))
    assert len(py_files) > 10, "expected multiple Python files in src/hawedit"

    violations: list[str] = []

    for file_path in py_files:
        content = file_path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(content, filename=str(file_path))
        except SyntaxError as exc:
            violations.append(f"{file_path.name}: SyntaxError: {exc}")
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue

            if _is_subprocess_call(node, "run"):
                timeout_arg = None
                for kw in node.keywords:
                    if kw.arg == "timeout":
                        timeout_arg = kw.value
                        break

                if timeout_arg is None:
                    violations.append(
                        f"{file_path.name}:{node.lineno}: subprocess.run lacks 'timeout=' keyword"
                    )
                elif isinstance(timeout_arg, ast.Constant) and timeout_arg.value is None:
                    violations.append(
                        f"{file_path.name}:{node.lineno}: subprocess.run passes 'timeout=None'"
                    )

            # Popen calls: must have enclosing or follow-up wait/communicate with timeout
            elif _is_subprocess_call(node, "Popen"):
                if "wait(timeout=" not in content and "communicate(timeout=" not in content:
                    violations.append(
                        f"{file_path.name}:{node.lineno}: Popen lacks wait/communicate timeout"
                    )

    assert not violations, (
        f"Found {len(violations)} subprocess call(s) without proper timeout:\n"
        + "\n".join(violations)
    )

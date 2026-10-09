"""Invalid independent budgets refuse before OS launch on every platform."""

from __future__ import annotations

from typing import Any

import pytest

from hawedit.native_io import NativeIOError, run_native


@pytest.mark.parametrize(
    "budgets",
    [
        {"output_limit_bytes": None},
        {"output_limit_bytes": None, "stdout_limit_bytes": 1},
        {"output_limit_bytes": None, "stderr_limit_bytes": 1},
        {"output_limit_bytes": 1, "stdout_limit_bytes": 1, "stderr_limit_bytes": 1},
        {"output_limit_bytes": None, "stdout_limit_bytes": True, "stderr_limit_bytes": 1},
        {"output_limit_bytes": None, "stdout_limit_bytes": 0, "stderr_limit_bytes": 1},
        {"output_limit_bytes": None, "stdout_limit_bytes": 1, "stderr_limit_bytes": -1},
        {"output_limit_bytes": None, "stdout_limit_bytes": 1.5, "stderr_limit_bytes": 1},
        {"output_limit_bytes": None, "stdout_limit_bytes": 16777217, "stderr_limit_bytes": 1},
    ],
)
def test_native_independent_limits_refuse_invalid_configuration(budgets: dict[str, Any]) -> None:
    with pytest.raises(NativeIOError, match="output limit"):
        run_native(
            (),
            cwd=None,  # type: ignore[arg-type]
            environment={},
            expected_executable_sha256="",
            input_bytes=b"",
            timeout_seconds=1,
            **budgets,
        )

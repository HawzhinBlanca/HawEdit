"""Real private journal observations refuse invalid cooperative read limits."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

import test_studio_billing as protocol
from hawedit.studio_billing import GuardedGeminiTransport
from hawedit.studio_private import StudioStorageError


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_rows", 0),
        ("max_rows", True),
        ("max_rows", 10001),
        ("max_rows", "2"),
        ("max_bytes", 0),
        ("max_bytes", True),
        ("max_bytes", (256 << 20) + 1),
        ("max_bytes", "2"),
        ("max_seconds", 0),
        ("max_seconds", True),
        ("max_seconds", float("nan")),
        ("max_seconds", float("inf")),
        ("max_seconds", "1"),
        ("max_seconds", None),
        ("max_seconds", 11),
    ],
)
def test_studio_effects_invalid_read_limits_are_actionable(
    tmp_path: Path, field: str, value: Any
) -> None:
    def no_egress(url: str, payload: bytes | None, headers: Mapping[str, str]) -> tuple[int, str]:
        raise AssertionError("Inspection must not request a provider")

    client = GuardedGeminiTransport(
        protocol.private_billing_path(tmp_path), protocol.JOB, protocol.policy(), no_egress
    )
    with sqlite3.connect(client.path) as db:
        before = tuple(db.iterdump())
    with pytest.raises(StudioStorageError, match="limit"):
        client.inspect_effects(**{field: value})
    with sqlite3.connect(client.path) as db:
        assert tuple(db.iterdump()) == before

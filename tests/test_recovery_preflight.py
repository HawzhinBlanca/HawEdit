"""Real filesystem resource ownership checks, not protected-worker acceptance."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from hawedit.workflow_recovery import ResourceCapacityError, validate_preflight_resources


@pytest.mark.parametrize("existing", ["file", "hardlink", "directory"])
def test_preflight_preserves_existing_probe_name(tmp_path: Path, existing: str) -> None:
    work = tmp_path / "work"
    work.mkdir()
    marker = work / ".probe_write.tmp"
    expected = b"existing evidence must survive resource preflight"
    if existing == "directory":
        marker.mkdir()
        (marker / "evidence.bin").write_bytes(expected)
    elif existing == "hardlink":
        target = tmp_path / "original.bin"
        target.write_bytes(expected)
        os.link(target, marker)
    else:
        marker.write_bytes(expected)
    original_names = set(work.iterdir())
    validate_preflight_resources(work, min_disk_free_mb=0)
    assert set(work.iterdir()) == original_names
    if existing == "directory":
        assert (marker / "evidence.bin").read_bytes() == expected
    else:
        assert marker.read_bytes() == expected
    if existing == "hardlink":
        assert target.read_bytes() == expected
        assert marker.stat().st_nlink == 2


@pytest.mark.parametrize("budget", [-1, True, 1.5, float("inf"), float("nan"), "12", None])
def test_preflight_refuses_invalid_budget_before_storage(tmp_path: Path, budget: Any) -> None:
    work = tmp_path / "not-created"
    with pytest.raises(ResourceCapacityError, match="non-negative integer"):
        validate_preflight_resources(work, min_disk_free_mb=budget)
    assert not work.exists()


def test_preflight_reports_real_directory_failure_without_mutating_evidence(tmp_path: Path) -> None:
    work = tmp_path / "not-a-directory"
    before = b"existing unrelated file"
    work.write_bytes(before)
    with pytest.raises(ResourceCapacityError, match="Cannot") as caught:
        validate_preflight_resources(work)
    assert isinstance(caught.value.__cause__, OSError)
    assert work.read_bytes() == before


def test_preflight_removes_only_its_own_successful_probe(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    original = work / "saved.bin"
    before = b"retained data"
    original.write_bytes(before)
    validate_preflight_resources(work, min_disk_free_mb=0)
    assert set(work.iterdir()) == {original}
    assert original.read_bytes() == before


def test_preflight_capacity_refusal_preserves_existing_evidence(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    marker = work / ".probe_write.tmp"
    expected = b"retain before capacity refusal"
    marker.write_bytes(expected)
    with pytest.raises(ResourceCapacityError, match="Insufficient disk space"):
        validate_preflight_resources(work, min_disk_free_mb=999_999_999)
    assert set(work.iterdir()) == {marker}
    assert marker.read_bytes() == expected

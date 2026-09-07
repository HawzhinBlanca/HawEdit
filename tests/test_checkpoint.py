"""Tests for stage checkpoint and resume engine — Claim R3."""

from __future__ import annotations

from pathlib import Path

from hawedit.checkpoint import (
    clear_stage_checkpoint,
    hash_bytes,
    is_stage_complete,
    load_stage_checkpoint,
    save_stage_checkpoint,
)


def test_checkpoint_lifecycle(tmp_path: Path) -> None:
    stage = "stage_0_ingest"
    hashes = {
        "source": hash_bytes(b"mock video data"),
        "config": hash_bytes(b"fps=25,proxy=1fps"),
    }

    assert not is_stage_complete(tmp_path, stage, hashes)

    marker = save_stage_checkpoint(
        tmp_path,
        stage,
        hashes,
        metadata={"proxy_path": "proxy.mp4", "duration_s": 48.5},
    )
    assert marker.is_file()
    assert marker.name == "stage_0_ingest.done"

    assert is_stage_complete(tmp_path, stage, hashes)

    loaded = load_stage_checkpoint(tmp_path, stage)
    assert loaded is not None
    assert loaded.stage_name == stage
    assert loaded.input_hashes == hashes
    assert loaded.metadata["duration_s"] == 48.5

    # Altered inputs must fail validation
    altered_hashes = dict(hashes)
    altered_hashes["source"] = hash_bytes(b"different video data")
    assert not is_stage_complete(tmp_path, stage, altered_hashes)

    # Clearing the checkpoint
    cleared = clear_stage_checkpoint(tmp_path, stage)
    assert cleared
    assert not is_stage_complete(tmp_path, stage, hashes)
    assert load_stage_checkpoint(tmp_path, stage) is None


def test_corrupted_checkpoint_fails_gracefully(tmp_path: Path) -> None:
    stage = "stage_1_speech"
    marker = tmp_path / f"{stage}.done"
    marker.write_text("{invalid json truncated", encoding="utf-8")

    assert not is_stage_complete(tmp_path, stage, {"source": "abc"})
    assert load_stage_checkpoint(tmp_path, stage) is None

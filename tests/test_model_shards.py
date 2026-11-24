"""Real filesystem regressions for the pre-load shard metadata boundary."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from hawedit.models import UnsafeModelConfig, assert_transformers_config_safe


def _checkpoint(root: Path, index: object) -> Path:
    checkpoint = root / "checkpoint"
    checkpoint.mkdir()
    (checkpoint / "config.json").write_text('{"model_type":"qwen3_asr"}', encoding="utf-8")
    (checkpoint / "model.safetensors.index.json").write_text(json.dumps(index), encoding="utf-8")
    return checkpoint


def _guard(checkpoint: Path) -> None:
    assert_transformers_config_safe(checkpoint, {"qwen3_asr"})


@pytest.mark.parametrize(
    "target",
    [
        "../outside.safetensors",
        "/tmp/owned.safetensors",
        "C:/owned.safetensors",
        "C:owned.safetensors",
        "..\\owned.safetensors",
        "\\\\host\\owned\\model.safetensors",
        "NUL",
        "CON",
        "COM1.safetensors",
        "NUL::$DATA",
        "shards/../../outside.safetensors",
        "shards//model.safetensors",
        "shards/./model.safetensors",
        "shards/",
        "model.safetensors\x00",
        "model.safetensors.",
        "model.safetensors ",
        "model\ud800.safetensors",
    ],
)
def test_model_shard_unsafe_paths_are_refused(tmp_path: Path, target: str) -> None:
    checkpoint = _checkpoint(tmp_path, {"weight_map": {"weight": target}})
    with pytest.raises(UnsafeModelConfig, match="unsafe shard"):
        _guard(checkpoint)


@pytest.mark.parametrize("member", ["index", "shard"])
def test_model_shard_nonregular_members_are_refused(tmp_path: Path, member: str) -> None:
    checkpoint = _checkpoint(tmp_path, {"weight_map": {"weight": "model.safetensors"}})
    target = checkpoint / (
        "model.safetensors.index.json" if member == "index" else "model.safetensors"
    )
    if member == "index":
        target.unlink()
    target.mkdir()
    with pytest.raises(UnsafeModelConfig, match="regular"):
        _guard(checkpoint)


@pytest.mark.parametrize("member", ["index", "shard"])
def test_model_shard_hardlinked_members_are_refused(tmp_path: Path, member: str) -> None:
    checkpoint = _checkpoint(tmp_path, {"weight_map": {"weight": "model.safetensors"}})
    (checkpoint / "model.safetensors").write_bytes(b"owned opaque unit-test bytes")
    target = checkpoint / (
        "model.safetensors.index.json" if member == "index" else "model.safetensors"
    )
    os.link(target, tmp_path / "owned-alias")
    with pytest.raises(UnsafeModelConfig, match="hard link"):
        _guard(checkpoint)


def test_model_shard_parent_link_is_refused(tmp_path: Path) -> None:
    checkpoint = _checkpoint(tmp_path, {"weight_map": {"weight": "shards/model.safetensors"}})
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "model.safetensors").write_bytes(b"owned outside bytes")
    link = checkpoint / "shards"
    if os.name == "nt":
        subprocess.run(
            [os.environ.get("COMSPEC", "cmd.exe"), "/c", "mklink", "/J", str(link), str(outside)],
            check=True,
            capture_output=True,
        )
    else:
        link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(UnsafeModelConfig, match="link|reparse"):
        _guard(checkpoint)
    assert (outside / "model.safetensors").read_bytes() == b"owned outside bytes"


def test_model_shard_missing_member_is_refused(tmp_path: Path) -> None:
    checkpoint = _checkpoint(tmp_path, {"weight_map": {"weight": "missing.safetensors"}})
    with pytest.raises(UnsafeModelConfig, match="cannot safely inspect shard"):
        _guard(checkpoint)


@pytest.mark.parametrize(
    "index",
    [
        None,
        [],
        {},
        {"weight_map": []},
        {"weight_map": {}},
        {"weight_map": {"": "a"}},
        {"weight_map": {"weight": 3}},
    ],
)
def test_model_shard_invalid_indexes_are_refused(tmp_path: Path, index: object) -> None:
    checkpoint = _checkpoint(tmp_path, index)
    with pytest.raises(UnsafeModelConfig, match="weight_map"):
        _guard(checkpoint)


def test_model_shard_invalid_json_is_refused(tmp_path: Path) -> None:
    checkpoint = _checkpoint(tmp_path, {})
    (checkpoint / "model.safetensors.index.json").write_text("{", encoding="utf-8")
    with pytest.raises(UnsafeModelConfig, match="cannot safely read shard index"):
        _guard(checkpoint)


@pytest.mark.parametrize(
    "raw",
    [
        '{"weight_map":{"weight":"../outside","weight":"model.safetensors"}}',
        '{"weight_map":{"weight":"../outside"},"weight_map":{"weight":"model.safetensors"}}',
    ],
)
def test_model_shard_duplicate_keys_are_refused(tmp_path: Path, raw: str) -> None:
    checkpoint = _checkpoint(tmp_path, {})
    (checkpoint / "model.safetensors").write_bytes(b"owned opaque unit-test bytes")
    (checkpoint / "model.safetensors.index.json").write_text(raw, encoding="utf-8")
    with pytest.raises(UnsafeModelConfig, match="duplicate"):
        _guard(checkpoint)


def test_model_shard_oversized_index_is_refused(tmp_path: Path) -> None:
    checkpoint = _checkpoint(tmp_path, {"weight_map": {"weight": "model.safetensors"}})
    (checkpoint / "model.safetensors").write_bytes(b"owned opaque unit-test bytes")
    with (checkpoint / "model.safetensors.index.json").open("ab") as stream:
        stream.write(b" " * 1_048_576)
    with pytest.raises(UnsafeModelConfig, match="exceeds"):
        _guard(checkpoint)


def test_model_shard_nonfinite_json_is_refused(tmp_path: Path) -> None:
    checkpoint = _checkpoint(tmp_path, {})
    (checkpoint / "model.safetensors").write_bytes(b"owned opaque unit-test bytes")
    (checkpoint / "model.safetensors.index.json").write_text(
        '{"weight_map":{"weight":"model.safetensors"},"metadata":{"total_size":NaN}}',
        encoding="utf-8",
    )
    with pytest.raises(UnsafeModelConfig, match="nonfinite"):
        _guard(checkpoint)


@pytest.mark.parametrize(
    ("index_name", "shard_name"),
    [
        ("model.safetensors.index.json", "model.safetensors"),
        ("pytorch_model.bin.index.json", "shards/model.bin"),
        ("weights.index.json", "shards/model.safetensors"),
    ],
)
def test_model_shard_valid_indexes_are_accepted(
    tmp_path: Path, index_name: str, shard_name: str
) -> None:
    checkpoint = _checkpoint(tmp_path, {"weight_map": {"weight": shard_name}})
    (checkpoint / "model.safetensors.index.json").rename(checkpoint / index_name)
    shard = checkpoint / shard_name
    shard.parent.mkdir(exist_ok=True)
    shard.write_bytes(b"owned opaque unit-test bytes")
    _guard(checkpoint)

"""Real bundle/bridge identity contracts, not model inference or licence evidence."""

from __future__ import annotations

import hashlib
import json
import os
import wave
from pathlib import Path

import pytest

from hawedit import omni_assets
from hawedit.asr import (
    ChampionUnavailable,
    OmniAsrBackend,
    OmniAsrProducer,
    WslOmniAsrProducer,
    adapter_fingerprint,
    create_omni_asr_producer,
)
from hawedit.asr_worker import run_request
from hawedit.omni_assets import FusedCheckpointAsset


def bundle(path: Path) -> Path:
    path.mkdir()
    (path / "adapter_config.json").write_bytes(b'{"peft_type":"LORA"}')
    (path / "adapter_model.safetensors").write_bytes(b"synthetic-weights")
    (path / "tokenizer.model").write_bytes(b"synthetic-tokenizer")
    return path


def test_tokenizer_change_changes_both_adapter_identities(tmp_path: Path) -> None:
    root = bundle(tmp_path / "adapter")
    native = OmniAsrBackend(lora_adapter=root)
    bridge = WslOmniAsrProducer(lora_adapter=root)
    first = native.adapter_name
    assert first == bridge.model_identity
    (root / "tokenizer.model").write_bytes(b"changed-tokenizer")
    assert native.adapter_name != first
    assert native.adapter_name == bridge.model_identity


def test_adapter_identity_is_full_versioned_three_file_digest(tmp_path: Path) -> None:
    root = bundle(tmp_path / "adapter")
    files = []
    for role, name in (
        ("configuration", "adapter_config.json"),
        ("weights", "adapter_model.safetensors"),
        ("tokenizer", "tokenizer.model"),
    ):
        data = (root / name).read_bytes()
        files.append(
            {
                "role": role,
                "name": name,
                "size_bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
    expected = hashlib.sha256(
        json.dumps(
            {"schema": 2, "kind": "hawedit-peft-bundle", "files": files},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    assert adapter_fingerprint(root) == expected
    assert adapter_fingerprint(bundle(tmp_path / "relocated")) == expected


def test_adapter_identity_separates_config_and_weight_boundaries(tmp_path: Path) -> None:
    first, second = bundle(tmp_path / "one"), bundle(tmp_path / "two")
    for root, config, weights in ((first, b"ab", b"c"), (second, b"a", b"bc")):
        (root / "adapter_config.json").write_bytes(config)
        (root / "adapter_model.safetensors").write_bytes(weights)
    assert adapter_fingerprint(first) != adapter_fingerprint(second)


@pytest.mark.parametrize(
    "damage",
    ["missing", "ambiguous", "directory", "empty", "config_link", "weights_link", "tokenizer_link"],
)
def test_adapter_identity_refuses_unsafe_or_ambiguous_inputs(tmp_path: Path, damage: str) -> None:
    root = bundle(tmp_path / "adapter")
    before = {p.name: p.read_bytes() for p in root.iterdir()}
    if damage == "missing":
        (root / "tokenizer.model").unlink()
    elif damage == "ambiguous":
        (root / "other.model").write_bytes(b"other-tokenizer")
    elif damage == "directory":
        (root / "adapter_model.safetensors").unlink()
        (root / "adapter_model.safetensors").mkdir()
    elif damage == "empty":
        (root / "tokenizer.model").write_bytes(b"")
    else:
        name = {
            "config_link": "adapter_config.json",
            "weights_link": "adapter_model.safetensors",
            "tokenizer_link": "tokenizer.model",
        }[damage]
        os.link(root / name, tmp_path / "alias")
    with pytest.raises((RuntimeError, ValueError, FileNotFoundError)):
        adapter_fingerprint(root)
    assert (root / "adapter_config.json").read_bytes() == before["adapter_config.json"]


@pytest.mark.parametrize("damage", ["config", "weights", "tokenizer", "removed_selection"])
def test_cached_backend_refuses_changed_adapter_identity(tmp_path: Path, damage: str) -> None:
    root = bundle(tmp_path / "adapter")
    backend = OmniAsrBackend(lora_adapter=root)
    # Loaded dependency handles, not inference: exercise the real backend cache guard.
    backend._loaded_adapter_identity = backend.adapter_name
    backend._pipelines = (object(), object())
    assert backend._load() == backend._pipelines
    if damage == "removed_selection":
        backend.lora_adapter = None
    else:
        name = {
            "config": "adapter_config.json",
            "weights": "adapter_model.safetensors",
            "tokenizer": "tokenizer.model",
        }[damage]
        (root / name).write_bytes(b"changed")
    with pytest.raises(RuntimeError, match="identity"):
        backend._load()
    with pytest.raises(RuntimeError, match="identity"):
        _ = backend.adapter_name


@pytest.mark.parametrize("identity", [None, True, "lora:old16digitkey", "lora:" + "0" * 64])
def test_worker_refuses_foreign_adapter_identity_before_inference(
    tmp_path: Path, identity: object
) -> None:
    root = bundle(tmp_path / "adapter")
    with wave.open(str(tmp_path / "speech.wav"), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16000)
        stream.writeframes(b"\0\0" * 16000)
    request = tmp_path / "request.json"
    request.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "media_id": "identity-probe",
                "validator_model_dir": "unused-before-inference",
                "segments": [{"path": "speech.wav", "start_ms": 0, "end_ms": 1000}],
                "lora_adapter": str(root),
                "model_identity": identity,
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "output.json"
    with pytest.raises(ValueError, match="identity"):
        run_request(request, output)
    assert not output.exists()


def test_adapter_identity_refuses_drift_between_descriptor_checks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = bundle(tmp_path / "adapter")
    assert len(adapter_fingerprint(root)) == 64
    real_fstat = os.fstat
    observations = 0

    def observed_fstat(fd: int) -> os.stat_result:
        nonlocal observations
        result = real_fstat(fd)
        observations += 1
        if observations == 4:
            (root / "tokenizer.model").write_bytes(b"changed-at-native-file-boundary")
        return result

    # Real metadata and real byte mutation; only the I/O boundary schedules the fault.
    monkeypatch.setattr(os, "fstat", observed_fstat)
    with pytest.raises(RuntimeError, match="changed"):
        adapter_fingerprint(root)
    assert observations >= 4
    assert (root / "tokenizer.model").read_bytes() == b"changed-at-native-file-boundary"


# --- D-331: fused champion identity `fused:<sha256>` ------------------------------------------


def fused(path: Path, monkeypatch: pytest.MonkeyPatch, data: bytes = b"synthetic-fused") -> Path:
    """A synthetic fused file placed on the code allowlist (the only authority, D-331)."""
    path.mkdir()
    checkpoint = path / "kurdish_omniasr_7b_v12_c750.pt"
    checkpoint.write_bytes(data)
    allowed = FusedCheckpointAsset(
        "synthetic fused checkpoint", checkpoint.name, len(data), hashlib.sha256(data).hexdigest()
    )
    monkeypatch.setattr(omni_assets, "FUSED_CHECKPOINT_ASSETS", (allowed,))
    return checkpoint


def test_fused_identity_agrees_across_native_and_bridge_producers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkpoint = fused(tmp_path / "v12", monkeypatch)
    expected = "fused:" + hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    assert OmniAsrBackend(fused_checkpoint=checkpoint).adapter_name == expected
    assert OmniAsrProducer(fused_checkpoint=checkpoint).model_identity == expected
    assert WslOmniAsrProducer(fused_checkpoint=checkpoint).model_identity == expected
    assert WslOmniAsrProducer(lora_adapter=bundle(tmp_path / "adapter")).model_identity != expected


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"fused_checkpoint": "CHECKPOINT", "model_identity": "lora:" + "0" * 64}, "identity"),
        ({"lora_adapter": "ADAPTER", "model_identity": "fused:" + "0" * 64}, "identity"),
        ({"fused_checkpoint": "CHECKPOINT", "model_identity": "fused:" + "0" * 64}, "differs"),
        ({"fused_checkpoint": "CHECKPOINT", "model_identity": None}, "identity"),
        (
            {
                "fused_checkpoint": "CHECKPOINT",
                "lora_adapter": "ADAPTER",
                "model_identity": "fused:" + "0" * 64,
            },
            "both",
        ),
        ({"model_identity": "fused:" + "0" * 64}, "stock request cannot claim"),
    ],
)
def test_worker_refuses_foreign_or_impersonating_fused_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fields: dict[str, object], message: str
) -> None:
    replacements = {
        "CHECKPOINT": str(fused(tmp_path / "v12", monkeypatch)),
        "ADAPTER": str(bundle(tmp_path / "adapter")),
    }
    with wave.open(str(tmp_path / "speech.wav"), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16000)
        stream.writeframes(b"\0\0" * 16000)
    request = tmp_path / "request.json"
    request.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "media_id": "identity-probe",
                "validator_model_dir": "unused-before-inference",
                "segments": [{"path": "speech.wav", "start_ms": 0, "end_ms": 1000}],
                **{
                    key: replacements.get(value, value) if isinstance(value, str) else value
                    for key, value in fields.items()
                },
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "output.json"
    with pytest.raises(ValueError, match=message):
        run_request(request, output)
    assert not output.exists()


def test_fused_and_lora_producers_refuse_both_weights(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkpoint, adapter = fused(tmp_path / "v12", monkeypatch), bundle(tmp_path / "adapter")
    with pytest.raises(ValueError, match="not both"):
        WslOmniAsrProducer(lora_adapter=adapter, fused_checkpoint=checkpoint)
    with pytest.raises(ValueError, match="not both"):
        create_omni_asr_producer("wsl", lora_adapter=adapter, fused_checkpoint=checkpoint)


def test_missing_fused_checkpoint_is_refused_before_stage_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(ChampionUnavailable, match="missing"):
        create_omni_asr_producer("wsl", fused_checkpoint=tmp_path / "absent.pt")
    producer = create_omni_asr_producer(
        "wsl", fused_checkpoint=fused(tmp_path / "v12", monkeypatch)
    )
    assert isinstance(producer, WslOmniAsrProducer)
    assert producer.model_identity is not None
    assert producer.model_identity.startswith("fused:")

"""Real file-boundary tests; dependency composition is not ASR quality evidence."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import hawedit.asr as asr
from hawedit.omni_assets import OmniAssetError


def _bundle(path: Path) -> Path:
    path.mkdir()
    (path / "adapter_config.json").write_bytes(b'{"peft_type":"LORA"}')
    (path / "adapter_model.safetensors").write_bytes(b"synthetic-weights")
    (path / "tokenizer.model").write_bytes(b"synthetic-tokenizer")
    return path


def test_champion_verifies_canonical_assets_before_import(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    backend = asr.OmniAsrBackend(lora_adapter=_bundle(tmp_path / "adapter"))

    def refuse() -> None:
        raise OmniAssetError("champion canonical integrity sentinel")

    monkeypatch.setattr(asr, "open_verified_omni_assets", refuse)
    monkeypatch.setitem(sys.modules, "omnilingual_asr.models.inference.pipeline", None)
    with pytest.raises(OmniAssetError, match="champion canonical integrity sentinel"):
        backend._load()
    assert backend._pipelines is None
    assert backend._loaded_adapter_identity is None


def test_open_adapter_bundle_retains_and_closes_inputs(tmp_path: Path) -> None:
    root = _bundle(tmp_path / "adapter")
    expected = asr.adapter_fingerprint(root)
    with asr._open_adapter_bundle(root) as (fingerprint, streams):
        assert fingerprint == expected
        assert set(streams) == {
            "adapter_config.json",
            "adapter_model.safetensors",
            "tokenizer.model",
        }
        for name, stream in streams.items():
            assert not stream.closed
            assert stream.read() == (root / name).read_bytes()
            assert os.fstat(stream.fileno()).st_size == (root / name).stat().st_size
    assert all(stream.closed for stream in streams.values())
    assert asr.adapter_fingerprint(root) == expected


@pytest.mark.parametrize(
    "member", ["adapter_config.json", "adapter_model.safetensors", "tokenizer.model"]
)
def test_open_adapter_bundle_refuses_mutation_during_consumption(
    tmp_path: Path, member: str
) -> None:
    root = _bundle(tmp_path / "adapter")
    with (
        pytest.raises(RuntimeError, match="changed"),
        asr._open_adapter_bundle(root) as (_fingerprint, streams),
    ):
        (root / member).write_bytes(b"changed-during-real-consumption")
    assert all(stream.closed for stream in streams.values())
    assert (root / member).read_bytes() == b"changed-during-real-consumption"


def test_verified_adapter_aliases_bind_replaced_paths(tmp_path: Path) -> None:
    root = _bundle(tmp_path / "adapter")
    before = {p.name: p.read_bytes() for p in root.iterdir()}
    if not any(Path(p).is_dir() for p in ("/proc/self/fd", "/dev/fd")):
        with (
            pytest.raises(RuntimeError, match="descriptor.*WSL"),
            asr._verified_adapter_aliases(root),
        ):
            pytest.fail("unsupported runtime admitted original-path loading")
        assert before == {p.name: p.read_bytes() for p in root.iterdir()}
        return
    with (
        pytest.raises(RuntimeError, match="changed"),
        asr._verified_adapter_aliases(root) as (aliases, fingerprint),
    ):
        assert fingerprint == asr.adapter_fingerprint(root)
        assert aliases != root
        assert aliases.stat().st_mode & 0o777 == 0o500
        assert set(p.name for p in aliases.iterdir()) == set(before)
        for name, data in before.items():
            assert (aliases / name).is_symlink()
            (root / name).rename(root / (name + ".old"))
            (root / name).write_bytes(b"pathname-replacement")
            # The actual consumer reads the held original bytes, not the new pathname.
            assert (aliases / name).read_bytes() == data
    assert not aliases.exists()
    assert all((root / name).read_bytes() == b"pathname-replacement" for name in before)


def test_verified_adapter_cleanup_on_consumer_failure(tmp_path: Path) -> None:
    root = _bundle(tmp_path / "adapter")
    expected = asr.adapter_fingerprint(root)
    if not any(Path(p).is_dir() for p in ("/proc/self/fd", "/dev/fd")):
        with (
            pytest.raises(RuntimeError, match="descriptor.*WSL"),
            asr._verified_adapter_aliases(root),
        ):
            pytest.fail("unsupported runtime admitted original-path loading")
    else:
        with (
            pytest.raises(ValueError, match="consumer sentinel"),
            asr._verified_adapter_aliases(root) as (aliases, _fingerprint),
        ):
            links = [p.readlink() for p in aliases.iterdir()]
            raise ValueError("consumer sentinel")
        assert not aliases.exists()
        assert all(not p.exists() for p in links)
    assert asr.adapter_fingerprint(root) == expected


def test_champion_consumers_receive_held_assets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exercise the actual adapter assembly against external API doubles, not inference."""
    root = _bundle(tmp_path / "held-bundle")
    checkpoint = "file:///held/omniASR-LLM-7B-v2.pt"
    metadata: dict[str, dict[str, Any]] = {}
    events: list[str] = []
    config = SimpleNamespace(
        llama_config=SimpleNamespace(vocab_size=1),
        wav2vec2_asr_config=SimpleNamespace(target_vocab_size=1),
    )

    def read_metadata(source: str, rows: list[dict[str, Any]]) -> object:
        assert source == "hawedit_adapted"
        metadata.update({row["name"]: row for row in rows})
        return SimpleNamespace(_source=source)

    def load_tokenizer(name: str) -> object:
        events.append("tokenizer")
        uri = metadata[name]["tokenizer"]
        assert uri == (root / "tokenizer.model").absolute().as_uri()
        return SimpleNamespace(vocab_info=SimpleNamespace(size=10288))

    base = object()

    def load_model(name: str, **kwargs: Any) -> object:
        events.append("base")
        row = metadata[name]
        assert row["model_arch"] == "7b"
        assert row["checkpoint"] == checkpoint
        assert row["tokenizer_ref"] == "hawedit_adapted_omniASR_LLM_7B_v2_tokenizer"
        assert kwargs["config"].llama_config.vocab_size == 10288
        assert kwargs["config"].wav2vec2_asr_config.target_vocab_size == 10288
        assert kwargs["dtype"] == "bf16"
        return base

    class LoraConfig:
        def __post_init__(self) -> None:
            events.append("lora-config")

        def _register_custom_module(self, mapping: dict[type, type]) -> None:
            assert mapping == {FairseqLinear: LoraLinear}
            events.append("linear-registration")

    class FairseqLinear:
        input_dim = 8
        output_dim = 16

    class LoraLinear:
        pass

    adapted_model = object()

    class PeftModel:
        @staticmethod
        def from_pretrained(model: object, path: str) -> object:
            assert model is base
            assert path == str(root)
            cfg = LoraConfig()
            cfg.__post_init__()
            assert FairseqLinear().in_features == 8  # type: ignore[attr-defined]
            assert FairseqLinear().out_features == 16  # type: ignore[attr-defined]
            events.append("peft")
            return SimpleNamespace(base_model=SimpleNamespace(model=adapted_model))

    def pipeline(**kwargs: object) -> object:
        assert kwargs["model_card"] is None
        assert kwargs["model"] is adapted_model
        assert kwargs["device"] == "cuda:0"
        assert kwargs["dtype"] == "bf16"
        events.append("pipeline")
        return kwargs

    store = SimpleNamespace(_metadata_providers=[])
    modules = {
        "torch": SimpleNamespace(device=lambda value: value, bfloat16="bf16"),
        "fairseq2.assets": SimpleNamespace(
            get_asset_store=lambda: store, load_in_memory_asset_metadata=read_metadata
        ),
        "fairseq2.data.tokenizers": SimpleNamespace(load_tokenizer=load_tokenizer),
        "fairseq2.models.hub": SimpleNamespace(load_model=load_model),
        "fairseq2.nn.projection": SimpleNamespace(Linear=FairseqLinear),
        "fairseq2.runtime.config_registry": SimpleNamespace(
            get_config=lambda _resolver, _cls, arch: config if arch == "7b" else pytest.fail(arch)
        ),
        "fairseq2.runtime.dependency": SimpleNamespace(get_dependency_resolver=lambda: object()),
        "omnilingual_asr.models.inference.pipeline": SimpleNamespace(ASRInferencePipeline=pipeline),
        "omnilingual_asr.models.wav2vec2_llama": SimpleNamespace(Wav2Vec2LlamaConfig=object),
        "peft": SimpleNamespace(LoraConfig=LoraConfig, PeftModel=PeftModel),
        "peft.tuners.lora": SimpleNamespace(Linear=LoraLinear),
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    result = asr.OmniAsrBackend()._load_adapted_llm(root, checkpoint_uri=checkpoint)
    assert result
    assert events == ["tokenizer", "base", "lora-config", "linear-registration", "peft", "pipeline"]
    assert config.llama_config.vocab_size == 1, "trainer config registry must stay unchanged"

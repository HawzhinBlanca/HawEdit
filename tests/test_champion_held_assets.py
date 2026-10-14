"""Real file-boundary tests; dependency composition is not ASR quality evidence."""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import hawedit.asr as asr
from hawedit import omni_assets
from hawedit.omni_assets import FUSED_CHECKPOINT_ASSETS, FusedCheckpointAsset, OmniAssetError


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
    _exercise_champion_consumers(tmp_path, monkeypatch)


@pytest.mark.parametrize("failure_stage", ["config", "peft", "pipeline"])
def test_champion_config_failure_does_not_change_shared_constructor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure_stage: str
) -> None:
    _exercise_champion_consumers(tmp_path, monkeypatch, failure_stage=failure_stage)


def _exercise_champion_consumers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, failure_stage: str | None = None
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

    class DirectCard:
        def __init__(self, name: str, row: dict[str, Any]) -> None:
            self.name = name
            self.metadata = row
            metadata[name] = row

    def load_tokenizer(card: DirectCard) -> object:
        events.append("tokenizer")
        assert isinstance(card, DirectCard), "tokenizer must bypass global name lookup"
        uri = card.metadata["tokenizer"]
        assert uri == (root / "tokenizer.model").absolute().as_uri()
        return SimpleNamespace(vocab_info=SimpleNamespace(size=10288))

    base = object()

    def load_model(card: DirectCard, **kwargs: Any) -> object:
        events.append("base")
        assert isinstance(card, DirectCard), "checkpoint must bypass global name lookup"
        row = card.metadata
        assert row["model_arch"] == "7b"
        assert row["checkpoint"] == checkpoint
        assert row["tokenizer_ref"] == "hawedit_adapted_omniASR_LLM_7B_v2_tokenizer"
        assert kwargs["config"].llama_config.vocab_size == 10288
        assert kwargs["config"].wav2vec2_asr_config.target_vocab_size == 10288
        assert kwargs["dtype"] == "bf16"
        return base

    class LoraConfig:
        def __init__(self) -> None:
            self.mapping: dict[type, type] = {}
            self.__post_init__()

        def __post_init__(self) -> None:
            events.append("lora-config")

        @classmethod
        def from_pretrained(cls, path: str) -> LoraConfig:
            assert path == str(root), "config must use the held bundle"
            if failure_stage == "config":
                raise ValueError("config sentinel")
            return cls()

        def _register_custom_module(self, mapping: dict[type, type]) -> None:
            assert mapping == {FairseqLinear: LoraLinear}
            self.mapping.update(mapping)
            events.append("linear-registration")

    original_post_init = LoraConfig.__post_init__

    class FairseqLinear:
        input_dim = 8
        output_dim = 16

    class LoraLinear:
        pass

    adapted_model = object()

    class PeftModel:
        @staticmethod
        def from_pretrained(model: object, path: str, *, config: LoraConfig) -> object:
            assert model is base
            assert path == str(root)
            assert config.mapping == {FairseqLinear: LoraLinear}
            assert FairseqLinear().in_features == 8  # type: ignore[attr-defined]
            assert FairseqLinear().out_features == 16  # type: ignore[attr-defined]
            events.append("peft")
            if failure_stage == "peft":
                raise ValueError("peft sentinel")
            return SimpleNamespace(base_model=SimpleNamespace(model=adapted_model))

    def pipeline(**kwargs: object) -> object:
        assert kwargs["model_card"] is None
        assert kwargs["model"] is adapted_model
        assert kwargs["device"] == "cuda:0"
        assert kwargs["dtype"] == "bf16"
        events.append("pipeline")
        if failure_stage == "pipeline":
            raise ValueError("pipeline sentinel")
        return kwargs

    modules = {
        "torch": SimpleNamespace(device=lambda value: value, bfloat16="bf16"),
        "fairseq2.assets": SimpleNamespace(
            AssetCard=DirectCard,
            get_asset_store=lambda: pytest.fail("adapted assembly consulted global card overrides"),
            load_in_memory_asset_metadata=lambda *_args: pytest.fail("global provider mutation"),
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
    try:
        if failure_stage:
            with pytest.raises(ValueError, match=f"{failure_stage} sentinel"):
                asr.OmniAsrBackend()._load_adapted_llm(root, checkpoint_uri=checkpoint)
        else:
            result = asr.OmniAsrBackend()._load_adapted_llm(root, checkpoint_uri=checkpoint)
            assert result
            assert events == [
                "tokenizer",
                "base",
                "lora-config",
                "linear-registration",
                "peft",
                "pipeline",
            ]
    finally:
        assert LoraConfig.__post_init__ is original_post_init
        assert LoraConfig().mapping == {}, "a later unrelated configuration must stay untouched"
    assert config.llama_config.vocab_size == 1, "trainer config registry must stay unchanged"


# --- D-331: fused trainer checkpoint (v12). Fakes only; no weights load here. ---------------


def _fused(
    path: Path,
    monkeypatch: pytest.MonkeyPatch | None = None,
    data: bytes = b"synthetic-fused-weights",
    *,
    size: int | None = None,
    sha256: str | None = None,
) -> Path:
    """A synthetic fused file; with ``monkeypatch`` it is put on the code allowlist."""
    path.mkdir()
    checkpoint = path / "kurdish_omniasr_7b_v12_c750.pt"
    checkpoint.write_bytes(data)
    if monkeypatch is not None:
        monkeypatch.setattr(
            omni_assets,
            "FUSED_CHECKPOINT_ASSETS",
            (
                FusedCheckpointAsset(
                    "synthetic fused checkpoint",
                    checkpoint.name,
                    len(data) if size is None else size,
                    hashlib.sha256(data).hexdigest() if sha256 is None else sha256,
                ),
            ),
        )
    return checkpoint


def _fused_modules(
    monkeypatch: pytest.MonkeyPatch, events: list[str], *, vocab: int = 10288
) -> object:
    tokenizer = SimpleNamespace(vocab_info=SimpleNamespace(size=vocab))
    model = object()
    config = SimpleNamespace(
        llama_config=SimpleNamespace(vocab_size=1),
        wav2vec2_asr_config=SimpleNamespace(target_vocab_size=1),
    )

    class DirectCard:
        def __init__(self, name: str, row: dict[str, Any]) -> None:
            self.name = name
            self.metadata = row

    def load_tokenizer(card: DirectCard) -> object:
        assert card.metadata == {
            "tokenizer_family": "char_tokenizer",
            "tokenizer": "file:///held/omniASR_tokenizer_written_v2.model",
        }
        events.append("tokenizer")
        return tokenizer

    def load_model(card: DirectCard, **kwargs: Any) -> object:
        assert card.name == "hawedit_fused_omniASR_LLM_7B_v2"
        assert card.metadata == {
            "model_family": "wav2vec2_llama",
            "model_arch": "7b",
            "checkpoint": "file:///held/fused.pt",
            "tokenizer_ref": "hawedit_fused_omniASR_LLM_7B_v2_tokenizer",
        }
        assert kwargs["config"].llama_config.vocab_size == 10288
        assert kwargs["config"].wav2vec2_asr_config.target_vocab_size == 10288
        assert kwargs["dtype"] == "bf16"
        events.append("weights")
        return model

    def pipeline(**kwargs: object) -> object:
        assert kwargs["model"] is model and kwargs["tokenizer"] is tokenizer
        assert kwargs["model_card"] is None and kwargs["dtype"] == "bf16"
        events.append("pipeline")
        return kwargs

    modules = {
        "torch": SimpleNamespace(device=lambda value: value, bfloat16="bf16"),
        "fairseq2.assets": SimpleNamespace(AssetCard=DirectCard),
        "fairseq2.data.tokenizers": SimpleNamespace(load_tokenizer=load_tokenizer),
        "fairseq2.models.hub": SimpleNamespace(load_model=load_model),
        "fairseq2.runtime.config_registry": SimpleNamespace(
            get_config=lambda _resolver, _cls, arch: config if arch == "7b" else pytest.fail(arch)
        ),
        "fairseq2.runtime.dependency": SimpleNamespace(get_dependency_resolver=lambda: object()),
        "omnilingual_asr.models.inference.pipeline": SimpleNamespace(ASRInferencePipeline=pipeline),
        "omnilingual_asr.models.wav2vec2_llama": SimpleNamespace(Wav2Vec2LlamaConfig=object),
        # A fused checkpoint is not an adapter: importing PEFT at all would be a wrong route.
        "peft": None,
        "peft.tuners.lora": None,
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    return model


def test_fused_checkpoint_loads_trainer_7b_without_peft(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    model = _fused_modules(monkeypatch, events)
    backend = asr.OmniAsrBackend(fused_checkpoint=_fused(tmp_path / "v12"))
    result = backend._load_fused_llm(
        "file:///held/omniASR_tokenizer_written_v2.model", checkpoint_uri="file:///held/fused.pt"
    )
    assert result["model"] is model
    assert result["device"] == backend.llm_device
    assert events == ["tokenizer", "weights", "pipeline"]


def test_fused_checkpoint_vocab_mismatch_halts_before_weights(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    _fused_modules(monkeypatch, events, vocab=10287)
    backend = asr.OmniAsrBackend(fused_checkpoint=_fused(tmp_path / "v12"))
    with pytest.raises(RuntimeError, match=r"10287 ids.*trained with 10288"):
        backend._load_fused_llm(
            "file:///held/omniASR_tokenizer_written_v2.model",
            checkpoint_uri="file:///held/fused.pt",
        )
    assert events == ["tokenizer"], "no weights may load under a mismatched vocabulary"


def test_fused_checkpoint_and_lora_adapter_are_mutually_exclusive(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="not both"):
        asr.OmniAsrBackend(
            lora_adapter=_bundle(tmp_path / "adapter"),
            fused_checkpoint=_fused(tmp_path / "v12"),
        )


def test_fused_load_holds_only_ctc_and_tokenizer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = asr.OmniAsrBackend(fused_checkpoint=_fused(tmp_path / "v12", monkeypatch))
    held: list[tuple[str, ...]] = []

    def refuse(**kwargs: Any) -> None:
        held.append(tuple(asset.filename for asset in kwargs["assets"]))
        raise OmniAssetError("fused held-asset sentinel")

    monkeypatch.setattr(asr, "open_verified_omni_assets", refuse)
    for load in (backend._load, backend._load_ctc):
        with pytest.raises(OmniAssetError, match="sentinel"):
            load()
    assert held == [("omniASR-CTC-3B-v2.pt", "omniASR_tokenizer_written_v2.model")] * 2
    assert backend._pipelines is None and backend._ctc_pipeline is None


def test_the_code_allowlist_names_exactly_the_reviewed_v12_checkpoint() -> None:
    assert (
        FusedCheckpointAsset(
            name="Kurdish OmniASR-7B v12 fused checkpoint (c750)",
            filename="kurdish_omniasr_7b_v12_c750.pt",
            size=15_610_646_560,
            sha256="f7b3a5e272e52d6c0677f78fd44c22cf6196a79a3a3057a85b7d72f759ff5fb2",
        ),
    ) == FUSED_CHECKPOINT_ASSETS


def test_fused_identity_is_derived_from_the_allowlist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkpoint = _fused(tmp_path / "v12", monkeypatch)
    digest = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    assert asr.fused_checkpoint_asset(checkpoint) == omni_assets.FUSED_CHECKPOINT_ASSETS[0]
    assert asr.OmniAsrBackend(fused_checkpoint=checkpoint).adapter_name == f"fused:{digest}"
    # The identity is the allowlisted value, not something read from the file's neighbours.
    (checkpoint.parent / "SHA256SUMS").write_text(f"{'0' * 64}  {checkpoint.name}\n", "utf-8")
    assert asr.OmniAsrBackend(fused_checkpoint=checkpoint).adapter_name == f"fused:{digest}"


def test_sha256sums_alone_does_not_authorise_a_fused_checkpoint(tmp_path: Path) -> None:
    """A writer of the .pt can write its SHA256SUMS too; only the code allowlist admits."""
    checkpoint = _fused(tmp_path / "v12")
    digest = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    (checkpoint.parent / "SHA256SUMS").write_text(f"{digest}  {checkpoint.name}\n", "utf-8")
    with pytest.raises(asr.ChampionUnavailable, match="allowlist"):
        asr.fused_checkpoint_asset(checkpoint)
    with pytest.raises(asr.ChampionUnavailable, match="allowlist"):
        _ = asr.OmniAsrBackend(fused_checkpoint=checkpoint).adapter_name


@pytest.mark.parametrize("damage", ["missing", "renamed", "wrong_size", "directory"])
def test_fused_admission_refuses_unlisted_or_unsafe_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, damage: str
) -> None:
    checkpoint = _fused(tmp_path / "v12", monkeypatch)
    selected = checkpoint
    if damage == "missing":
        checkpoint.unlink()
    elif damage == "renamed":
        selected = checkpoint.rename(checkpoint.with_name("other.pt"))
    elif damage == "wrong_size":
        checkpoint.write_bytes(checkpoint.read_bytes() + b"x")
    else:
        checkpoint.unlink()
        checkpoint.mkdir()
    with pytest.raises(asr.ChampionUnavailable):
        asr.fused_checkpoint_asset(selected)


@pytest.mark.parametrize("damage", ["size", "sha256"])
def test_held_fused_checkpoint_refuses_bytes_off_the_allowlist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, damage: str
) -> None:
    data = b"synthetic-fused-weights"
    size = len(data) + 1 if damage == "size" else None
    checkpoint = _fused(tmp_path / "v12", monkeypatch, data, size=size)
    hashed: list[Path] = []

    def other_bytes(stream: Any, before: os.stat_result, path: Path) -> tuple[Any, str]:
        hashed.append(path)
        return before, "1" * 64

    monkeypatch.setattr(asr, "_hash_open_stream", other_bytes)
    monkeypatch.setattr(asr, "_FUSED_DIGESTS", {})
    with (
        pytest.raises(asr.ChampionUnavailable, match="allowlist"),
        asr._held_fused_checkpoint(checkpoint, omni_assets.FUSED_CHECKPOINT_ASSETS[0]),
    ):
        pytest.fail("bytes off the allowlist reached the loader")
    # An exact-size mismatch refuses before 15.6 GB would be hashed.
    assert hashed == ([] if damage == "size" else [checkpoint])


def test_held_fused_checkpoint_hashes_once_per_stat_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkpoint = _fused(tmp_path / "v12", monkeypatch)
    allowed = omni_assets.FUSED_CHECKPOINT_ASSETS[0]
    real = omni_assets._hash_open_stream
    hashed: list[Path] = []

    def counted(stream: Any, before: os.stat_result, path: Path) -> tuple[os.stat_result, str]:
        hashed.append(path)
        return real(stream, before, path)

    monkeypatch.setattr(asr, "_hash_open_stream", counted)
    monkeypatch.setattr(asr, "_FUSED_DIGESTS", {})
    linux = any(Path(p).is_dir() for p in ("/proc/self/fd", "/dev/fd"))
    for _ in range(2):
        if linux:
            with asr._held_fused_checkpoint(checkpoint, allowed) as uri:
                assert Path(uri.removeprefix("file://")).read_bytes() == checkpoint.read_bytes()
        else:
            with (
                pytest.raises(RuntimeError, match="descriptors need Linux"),
                asr._held_fused_checkpoint(checkpoint, allowed),
            ):
                pytest.fail("unsupported runtime admitted original-path loading")
    assert hashed == [checkpoint]

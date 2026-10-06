"""Resource/entry-point contracts, not synthetic inference quality evidence."""

from __future__ import annotations

import gc
import sys
import weakref
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import hawedit.asr as asr
import hawedit.asr_worker as worker
import test_adapter_identity as identity_fixtures
import test_asr_stop as stop_fixtures
from hawedit.transcripts import RawTranscript, Word


class Handle:
    pass


@pytest.fixture
def consumers(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    events: list[str] = []

    @contextmanager
    def held() -> Any:
        events.append("held-open")
        yield tuple(
            SimpleNamespace(asset=SimpleNamespace(filename=name), file_uri="file:///held/" + name)
            for name in (
                "omniASR-LLM-7B-v2.pt",
                "omniASR-CTC-3B-v2.pt",
                "omniASR_tokenizer_written_v2.model",
            )
        )
        events.append("held-close")

    class Card:
        def __init__(self, name: str, metadata: dict[str, object]) -> None:
            self.name, self.metadata = name, metadata

    def model(card: Card, **kwargs: object) -> Handle:
        assert kwargs["dtype"] == "bf16"
        assert str(card.metadata["checkpoint"]).startswith("file:///held/")
        assert (card.metadata["model_family"], card.metadata["model_arch"]) in (
            ("wav2vec2_asr", "3b_v2"),
            ("wav2vec2_llama", "7b_v2"),
        )
        events.append(str(card.metadata["checkpoint"]))
        return Handle()

    def tokenizer(card: Card) -> Handle:
        assert card.metadata == {
            "tokenizer_family": "char_tokenizer",
            "tokenizer": "file:///held/omniASR_tokenizer_written_v2.model",
        }
        events.append("tokenizer")
        return Handle()

    def pipeline(**kwargs: object) -> Handle:
        assert kwargs["model_card"] is None
        handle = Handle()
        vars(handle).update(kwargs)
        return handle

    for name, module in {
        "torch": SimpleNamespace(
            device=lambda value: value,
            bfloat16="bf16",
            cuda=SimpleNamespace(empty_cache=lambda: events.append("empty-cache")),
        ),
        "fairseq2.assets": SimpleNamespace(AssetCard=Card, get_asset_store=lambda: object()),
        "fairseq2.data.tokenizers.hub": SimpleNamespace(load_tokenizer=tokenizer),
        "fairseq2.models.hub": SimpleNamespace(load_model=model),
        "omnilingual_asr.models.inference.pipeline": SimpleNamespace(ASRInferencePipeline=pipeline),
    }.items():
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setattr(asr, "open_verified_omni_assets", held)
    monkeypatch.setattr(asr, "assert_omni_card_integrity", lambda: None)
    monkeypatch.setattr(asr, "freeze_fairseq2_asset_overrides", lambda: Path("private"))
    monkeypatch.setattr(asr, "assert_effective_omni_cards", lambda _store: None)
    return events


def test_alignment_loads_only_held_ctc(
    consumers: list[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    backend = asr.OmniAsrBackend(lora_adapter=identity_fixtures.bundle(tmp_path / "adapter"))
    word = Word("correction", 10, 510, 0.8)
    seen: list[object] = []

    def emissions(pipeline: object, _path: Path) -> tuple[object, int, str]:
        seen.append(pipeline)
        return object(), 10, "ctc"

    monkeypatch.setattr(backend, "_ctc_emissions", emissions)
    monkeypatch.setattr(backend, "_align_emissions", lambda *_args: (word,))
    result = backend.align_segment(tmp_path / "segment.wav", 1.0, "correction")
    repeated = backend.align_segment(tmp_path / "segment.wav", 1.0, "correction")
    assert result == repeated
    assert result.words == (word,)
    assert seen[0] is seen[1]
    assert backend._pipelines is None
    assert consumers == [
        "held-open",
        "tokenizer",
        "file:///held/omniASR-CTC-3B-v2.pt",
        "held-close",
    ]


def test_alignment_verifies_before_import(monkeypatch: pytest.MonkeyPatch) -> None:
    @contextmanager
    def refused() -> Any:
        raise RuntimeError("verification sentinel")
        yield

    monkeypatch.setattr(asr, "open_verified_omni_assets", refused)
    with pytest.raises(RuntimeError, match="verification sentinel"):
        asr.OmniAsrBackend().align_segment(Path("segment.wav"), 1.0, "correction")


def test_ctc_guard_failure_does_not_admit_cache(
    consumers: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    original = getattr(asr, "open_verified_omni_assets")

    @contextmanager
    def failed_exit() -> Any:
        with original() as opened:
            yield opened
        raise RuntimeError("exit guard sentinel")

    monkeypatch.setattr(asr, "open_verified_omni_assets", failed_exit)
    backend = asr.OmniAsrBackend()
    with pytest.raises(RuntimeError, match="exit guard sentinel"):
        backend._load_ctc()
    assert backend._pipelines is None
    assert backend._ctc_pipeline is None


def test_release_retains_ctc_and_drops_draft(consumers: list[str]) -> None:
    backend = asr.OmniAsrBackend()
    llm, ctc = backend._load()
    llm_ref = weakref.ref(llm)
    del llm
    backend.release_draft_model()
    gc.collect()
    assert llm_ref() is None
    assert backend._pipelines is None
    assert backend._load_ctc() is ctc
    assert consumers[-1] == "empty-cache"
    previous = list(consumers)
    backend.release_draft_model()
    assert consumers == previous, "repeated release must not import/load/flush again"


@pytest.mark.parametrize("released", [False, True])
def test_ctc_cache_retains_adapter_guard(
    consumers: list[str], tmp_path: Path, released: bool
) -> None:
    bundle = identity_fixtures.bundle(tmp_path / "adapter")
    backend = asr.OmniAsrBackend(lora_adapter=bundle)
    backend._load_ctc()
    if released:
        backend._pipelines = (Handle(), backend._ctc_pipeline)
        backend.release_draft_model()
    (bundle / "tokenizer.model").write_bytes(b"changed tokenizer")
    for operation in (backend._load_ctc, backend._load, backend.release_draft_model):
        with pytest.raises(RuntimeError, match="adapter identity changed"):
            operation()


def test_drafting_after_release_reuses_ctc(consumers: list[str]) -> None:
    backend = asr.OmniAsrBackend()
    original_llm, original_ctc = backend._load()
    backend.release_draft_model()
    llm, ctc = backend._load()
    assert llm is not original_llm
    assert ctc is original_ctc
    assert consumers.count("file:///held/omniASR-LLM-7B-v2.pt") == 2
    assert consumers.count("file:///held/omniASR-CTC-3B-v2.pt") == 1


def invoke_production(
    route: str,
    root: Path,
    backend: asr.OmniAsrBackend,
    validator: stop_fixtures.RegionValidator,
    monkeypatch: pytest.MonkeyPatch,
) -> RawTranscript:
    if route == "worker":
        return worker.run_request(
            stop_fixtures.worker_request(root), root / "output.json", backend, validator
        )
    prepared = stop_fixtures.prepared_regions(root)
    monkeypatch.setattr(asr, "_cut_speech_regions", lambda *_args: prepared)
    return asr.OmniAsrProducer(backend, validator).transcribe(
        "episode", root / "audio.wav", (), root
    )


@pytest.mark.parametrize("route", ["native", "worker"])
def test_production_releases_draft_before_validation(
    route: str, tmp_path: Path, consumers: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = asr.OmniAsrBackend()
    backend._load()
    decoder = stop_fixtures.RegionBackend()
    validator = stop_fixtures.RegionValidator()
    events: list[str] = []
    original_validation = validator.transcribe_segment

    def draft(path: Path, duration: float) -> asr.SegmentTranscript:
        events.append("draft")
        return decoder.transcribe_segment(path, duration)

    def validate(path: Path, duration: float) -> str:
        assert events == ["draft"] * 3 or "validate" in events
        assert backend._pipelines is None, "draft model was retained during validation"
        assert backend._ctc_pipeline is not None
        events.append("validate")
        return original_validation(path, duration)

    monkeypatch.setattr(backend, "transcribe_segment", draft)
    monkeypatch.setattr(backend, "align_segment", decoder.align_segment)
    monkeypatch.setattr(validator, "transcribe_segment", validate)
    result = invoke_production(route, tmp_path, backend, validator, monkeypatch)
    assert result.unaligned == ()
    assert consumers.count("empty-cache") == 1
    assert len(validator.calls) == 3


@pytest.mark.parametrize("route", ["native", "worker"])
@pytest.mark.parametrize("failed_index", [0, 1, 2])
def test_production_draft_failure_never_hands_off(
    route: str, failed_index: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = asr.OmniAsrBackend()
    decoder = stop_fixtures.RegionBackend(fail_draft=failed_index)
    validator = stop_fixtures.RegionValidator()
    monkeypatch.setattr(backend, "transcribe_segment", decoder.transcribe_segment)
    monkeypatch.setattr(
        backend, "release_draft_model", lambda: pytest.fail("handoff after failure"), raising=False
    )
    with pytest.raises(RuntimeError, match="declared draft failure"):
        invoke_production(route, tmp_path, backend, validator, monkeypatch)
    assert len(decoder.calls) == failed_index + 1
    assert validator.calls == []
    assert not (tmp_path / "output.json").exists()


@pytest.mark.parametrize("route", ["native", "worker"])
def test_production_release_failure_never_validates(
    route: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = asr.OmniAsrBackend()
    decoder = stop_fixtures.RegionBackend()
    validator = stop_fixtures.RegionValidator()

    def failed_release() -> None:
        raise RuntimeError("release sentinel")

    monkeypatch.setattr(backend, "transcribe_segment", decoder.transcribe_segment)
    monkeypatch.setattr(backend, "align_segment", decoder.align_segment)
    monkeypatch.setattr(backend, "release_draft_model", failed_release, raising=False)
    with pytest.raises(RuntimeError, match="release sentinel"):
        invoke_production(route, tmp_path, backend, validator, monkeypatch)
    assert len(decoder.calls) == 3
    assert validator.calls == []
    assert not (tmp_path / "output.json").exists()

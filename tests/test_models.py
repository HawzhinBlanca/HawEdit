"""M1.6 — model provisioning: where §7's models live and whether a stage can run.

The registry is the single source of truth for what may be fetched, so a model outside §7
cannot be provisioned even by editing a config file. And a checkpoint whose source §7 does
not fix is *refused* rather than guessed — §7 names `omniASR_LLM_7B_v2` as a checkpoint, not
a repository, and inventing a plausible repo id produces a 404 on hawapc01 that nobody can
explain from the code.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from types import SimpleNamespace

import pytest

from hawedit.models import (
    CheckpointIntegrityError,
    ModelNotProvisioned,
    ModelStore,
    SourceNotConfigured,
    UnsafeModelConfig,
    assert_transformers_config_safe,
    readiness_report,
)
from hawedit.registry import REGISTRY, Provisioning

ROOT = Path(__file__).resolve().parents[1]


def store(tmp_path: Path) -> ModelStore:
    return ModelStore(root=tmp_path)


def _stub_local_omni_runtime(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    version_overrides: dict[str, str] | None = None,
    failed_import: str | None = None,
    cuda_devices: int = 2,
) -> None:
    from hawedit import omni_assets

    versions = {
        "fairseq2": "0.6",
        "fonttools": "4.60.2",
        "klpt": "0.1.7",
        "omnilingual-asr": "0.2.0",
        "qwen-asr": "0.0.6",
        "torch": "2.8.0",
        "torchaudio": "2.8.0",
        **(version_overrides or {}),
    }
    monkeypatch.setattr("hawedit.models.sys.version_info", (3, 12, 0))
    monkeypatch.setattr("hawedit.models.importlib.metadata.version", versions.__getitem__)
    monkeypatch.setattr(omni_assets, "assert_omni_card_integrity", lambda: None)
    reports = (
        SimpleNamespace(path=tmp_path / "cache" / "asset" / "llm.pt", size=43_546_500_166),
        SimpleNamespace(path=tmp_path / "cache" / "asset" / "ctc.pt", size=1),
        SimpleNamespace(path=tmp_path / "cache" / "asset" / "tokenizer.model", size=1),
    )
    monkeypatch.setattr(omni_assets, "assert_omni_asset_integrity", lambda: reports)
    monkeypatch.setattr(omni_assets, "freeze_fairseq2_asset_overrides", lambda: tmp_path)
    monkeypatch.setattr(omni_assets, "assert_effective_omni_cards", lambda _store: None)
    cuda = SimpleNamespace(
        is_available=lambda: cuda_devices > 0,
        device_count=lambda: cuda_devices,
    )
    modules = {
        "torch": SimpleNamespace(__version__="2.8.0", cuda=cuda),
        "torchaudio": SimpleNamespace(__version__="2.8.0"),
        "fairseq2.assets": SimpleNamespace(get_asset_store=lambda: object()),
        "fairseq2.data.tokenizers.hub": SimpleNamespace(load_tokenizer=object()),
        "fairseq2.models.hub": SimpleNamespace(load_model=object()),
        "omnilingual_asr.models.inference.pipeline": SimpleNamespace(ASRInferencePipeline=object()),
        "qwen_asr": SimpleNamespace(Qwen3ASRModel=object()),
    }

    def import_module(name: str) -> object:
        if name == failed_import:
            raise ImportError(f"missing {name}")
        return modules[name]

    monkeypatch.setattr("hawedit.models.importlib.import_module", import_module)


def _fetcher_download_block() -> str:
    """The download block out of `fetch-models.sh`, as executable source.

    Deliberately not a grep of the script: an assertion about the text of a command is not an
    assertion about what it does — the mistake D-067 recorded, one layer up. The tests that use
    this execute the real block against a stubbed Hub and inspect the call it makes.
    """
    script = (ROOT / "scripts" / "fetch-models.sh").read_text(encoding="utf-8")
    blocks = [b for b in script.split("<<'PYEOF'")[1:] if "snapshot_download" in b]
    assert len(blocks) == 1, f"expected exactly one download block, found {len(blocks)}"
    return blocks[0].split("\nPYEOF")[0]


# --- provisioning is classified, not assumed -------------------------------------------


def test_every_section_7_component_declares_how_it_arrives() -> None:
    for entry in REGISTRY.values():
        assert isinstance(entry.provisioning, Provisioning)


def test_silero_and_klpt_come_from_pip_not_a_download() -> None:
    """Silero ships its ONNX model inside the wheel — treating it as a 2 GB download would
    send an operator looking for something that is already there."""
    assert REGISTRY["Silero VAD"].provisioning is Provisioning.PIP
    assert REGISTRY["KLPT"].provisioning is Provisioning.PIP


def test_the_judge_needs_credentials_not_disk() -> None:
    assert REGISTRY["gemini-2.5-pro"].provisioning is Provisioning.CLOUD


def test_forced_alignment_is_our_own_code() -> None:
    assert REGISTRY["Custom Viterbi on CTC emissions"].provisioning is Provisioning.IN_HOUSE


def test_the_asr_model_cards_are_managed_by_the_official_runtime() -> None:
    for model_id in ("omniASR_LLM_7B_v2", "omniASR_CTC_3B_v2"):
        assert REGISTRY[model_id].provisioning is Provisioning.PIP


# --- paths ---------------------------------------------------------------------------------


def test_a_slash_in_a_model_id_becomes_a_directory_safe_name(tmp_path: Path) -> None:
    path = store(tmp_path).path_for(REGISTRY["MCG-NJU/VideoChat3-4B"])
    assert path.name == "MCG-NJU__VideoChat3-4B"
    assert path.parent == tmp_path


# --- sources are configured, never guessed ---------------------------------------------


def test_a_repo_id_stated_by_section_7_is_used_directly(tmp_path: Path) -> None:
    entry = REGISTRY["pyannote/speaker-diarization-community-1"]
    assert store(tmp_path).source_for(entry) == "pyannote/speaker-diarization-community-1"


def test_a_checkpoint_name_without_a_repo_is_refused_not_invented(tmp_path: Path) -> None:
    """§7 names Qwen3-VL-Embedding-2B as a checkpoint. A guessed repo id 404s on the machine
    least able to debug it."""
    with pytest.raises(SourceNotConfigured, match="sources.json"):
        store(tmp_path).source_for(REGISTRY["Qwen3-VL-Embedding-2B"])


def test_a_configured_source_supplies_what_section_7_leaves_open(tmp_path: Path) -> None:
    (tmp_path / "sources.json").write_text(
        json.dumps({"Qwen3-VL-Embedding-2B": "Qwen/repo"}), encoding="utf-8"
    )
    assert store(tmp_path).source_for(REGISTRY["Qwen3-VL-Embedding-2B"]) == "Qwen/repo"


def test_the_installed_source_manifest_location_is_stable() -> None:
    from hawedit.models import INSTALLED_SOURCES

    assert INSTALLED_SOURCES.parts[-4:] == ("share", "hawedit", "models", "sources.json")


def test_unconfigured_sources_are_listed_so_an_operator_knows_what_to_supply(
    tmp_path: Path,
) -> None:
    unconfigured = {e.model_id for e in store(tmp_path).unconfigured_sources()}
    assert "Qwen3-VL-Embedding-2B" in unconfigured
    assert "pyannote/speaker-diarization-community-1" not in unconfigured


# --- status and readiness -----------------------------------------------------------------


def test_every_registry_entry_appears_in_the_status_report(tmp_path: Path) -> None:
    assert len(store(tmp_path).status()) == len(REGISTRY)


def test_an_absent_checkpoint_reports_as_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("hawedit.models._is_importable", lambda module: module != "omnilingual_asr")
    statuses = {s.model_id: s for s in store(tmp_path).status()}
    assert statuses["omniASR_LLM_7B_v2"].available is False


def test_importability_alone_cannot_report_omniasr_ready(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = 0

    def missing_runtime() -> tuple[str, Path, int]:
        nonlocal calls
        calls += 1
        raise RuntimeError("assets are absent")

    monkeypatch.setattr("hawedit.models._is_importable", lambda _module: True)
    monkeypatch.setattr("hawedit.models._probe_canonical_omni_runtime", missing_runtime)
    statuses = {status.model_id: status for status in store(tmp_path).status()}
    for model_id in ("omniASR_LLM_7B_v2", "omniASR_CTC_3B_v2"):
        assert statuses[model_id].available is False
        assert "assets are absent" in statuses[model_id].detail
        assert "first load" not in statuses[model_id].detail
    assert calls == 1, "LLM and CTC must share one 43.5 GB runtime verification"


def test_verified_omniasr_runtime_reports_exact_shared_bytes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runtime = tmp_path / "runtime" / "venvs" / "versioned"
    monkeypatch.setattr(
        "hawedit.models._probe_canonical_omni_runtime",
        lambda: ("verified versioned WSL generation", runtime, 43_546_500_168),
    )
    model_store = store(tmp_path)
    statuses = {status.model_id: status for status in model_store.status()}
    for model_id in ("omniASR_LLM_7B_v2", "omniASR_CTC_3B_v2"):
        assert statuses[model_id].available is True
        assert statuses[model_id].path == runtime
        assert statuses[model_id].size_bytes == 43_546_500_168
    assert model_store.assert_available("omniASR_LLM_7B_v2") == runtime


def test_local_omniasr_readiness_refuses_wrong_package_version(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from hawedit.models import _probe_local_omni_runtime

    _stub_local_omni_runtime(monkeypatch, tmp_path, version_overrides={"omnilingual-asr": "0.1.0"})
    with pytest.raises(RuntimeError, match="omnilingual-asr.*must be 0.2.0"):
        _probe_local_omni_runtime()


def test_local_omniasr_readiness_refuses_wrong_python_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hawedit.models import _probe_local_omni_runtime

    monkeypatch.setattr("hawedit.models.sys.version_info", (3, 11, 9))
    with pytest.raises(RuntimeError, match="requires Python 3.12, got 3.11"):
        _probe_local_omni_runtime()


def test_local_omniasr_readiness_refuses_missing_required_import(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from hawedit.models import _probe_local_omni_runtime

    _stub_local_omni_runtime(monkeypatch, tmp_path, failed_import="qwen_asr")
    with pytest.raises(RuntimeError, match="imports are incomplete.*missing qwen_asr"):
        _probe_local_omni_runtime()


def test_local_omniasr_readiness_refuses_fewer_than_two_cuda_devices(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from hawedit.models import _probe_local_omni_runtime

    _stub_local_omni_runtime(monkeypatch, tmp_path, cuda_devices=1)
    with pytest.raises(RuntimeError, match="requires two visible CUDA devices"):
        _probe_local_omni_runtime()


def test_local_omniasr_readiness_accepts_only_the_fully_verified_runtime(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from hawedit.models import _probe_local_omni_runtime

    _stub_local_omni_runtime(monkeypatch, tmp_path)
    detail, path, total = _probe_local_omni_runtime()
    assert "7 packages" in detail
    assert "2 CUDA devices" in detail
    assert path == tmp_path / "cache"
    assert total == 43_546_500_168


def test_a_nonempty_checkpoint_without_a_byte_manifest_is_not_reported_ready(
    tmp_path: Path,
) -> None:
    entry = REGISTRY["MCG-NJU/VideoChat3-4B"]
    weights = store(tmp_path).path_for(entry)
    weights.mkdir(parents=True)
    (weights / "model.safetensors").write_bytes(b"x" * 2048)
    status = next(s for s in store(tmp_path).status() if s.model_id == entry.model_id)
    assert status.available is False
    assert "integrity failed" in status.detail
    assert status.size_bytes == 2048


def test_an_empty_directory_does_not_count_as_downloaded(tmp_path: Path) -> None:
    """An interrupted download leaves the directory behind. Treating it as present is how a
    stage starts and dies half an hour later."""
    weights = store(tmp_path).path_for(REGISTRY["MCG-NJU/VideoChat3-4B"])
    weights.mkdir(parents=True)
    status = next(s for s in store(tmp_path).status() if s.model_id == "MCG-NJU/VideoChat3-4B")
    assert status.available is False


def test_pip_provisioned_components_report_from_the_environment(tmp_path: Path) -> None:
    """These are genuinely installed here, so this asserts the real environment."""
    statuses = {s.model_id: s for s in store(tmp_path).status()}
    assert statuses["KLPT"].available is True
    assert statuses["Silero VAD"].available is True


def test_missing_weights_lists_only_downloadable_components(tmp_path: Path) -> None:
    missing = {e.model_id for e in store(tmp_path).missing_weights()}
    assert "Qwen3-VL-Embedding-2B" in missing
    assert "KLPT" not in missing, "pip components are not downloads"
    assert "gemini-2.5-pro" not in missing, "a cloud API is not a download"


# --- refusing to start without what a stage needs -----------------------------------------


def test_a_stage_refuses_to_start_without_its_weights(tmp_path: Path) -> None:
    with pytest.raises(ModelNotProvisioned, match="fetch-models"):
        store(tmp_path).assert_available("Qwen3-VL-Embedding-2B")


def test_missing_omniasr_is_not_misreported_as_a_fetch_models_problem(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("hawedit.models._is_importable", lambda _module: False)
    with pytest.raises(ModelNotProvisioned) as raised:
        store(tmp_path).assert_available("omniASR_LLM_7B_v2")
    assert "fetch-models" not in str(raised.value)


def test_a_model_outside_section_7_cannot_be_provisioned(tmp_path: Path) -> None:
    with pytest.raises(ModelNotProvisioned, match="§7"):
        store(tmp_path).assert_available("openai/whisper-large-v3")


def test_an_available_component_passes(tmp_path: Path) -> None:
    store(tmp_path).assert_available("KLPT")


# --- the report -----------------------------------------------------------------------------


def test_the_report_names_what_is_missing(tmp_path: Path) -> None:
    report = readiness_report(store(tmp_path).status())
    assert "omniASR_LLM_7B_v2" in report
    assert "available" in report


def test_the_report_covers_every_component(tmp_path: Path) -> None:
    report = readiness_report(store(tmp_path).status())
    for entry in REGISTRY.values():
        assert entry.model_id in report


# --- a model that loads is not a model that works ------------------------------------------


def test_a_checkpoint_missing_a_weight_is_refused() -> None:
    """`from_pretrained` invents anything the checkpoint omits and carries on.

    Measured on `MCG-NJU/VideoChat3-4B` (D-054): `missing_keys = {'lm_head.weight'}`, filled
    with a fresh random initialisation at std 0.0200 — against the real embedding's 0.0201, so
    no statistic separates them. `lm_head` turns hidden states into tokens, so §3 Stage 3
    Path B would have produced confident nonsense from a model that loaded in 4.8 s and
    reported 4.86B parameters.
    """
    from hawedit.models import WeightsIncomplete, assert_fully_loaded

    with pytest.raises(WeightsIncomplete, match="lm_head.weight"):
        assert_fully_loaded("MCG-NJU/VideoChat3-4B", ["lm_head.weight"])


def test_a_complete_checkpoint_is_accepted() -> None:
    """The positive control. Measured: both Qwen3-VL checkpoints report no missing keys and
    tie `lm_head` to their embeddings, so this guard must not refuse them — a check that
    refused every load would pass the test above and stop Stage 2 working."""
    from hawedit.models import assert_fully_loaded

    assert_fully_loaded("Qwen3-VL-Reranker-2B", [])  # must not raise


def test_the_refusal_names_every_invented_weight() -> None:
    """One name would let a second silently through, and the fix differs per tensor."""
    from hawedit.models import WeightsIncomplete, assert_fully_loaded

    with pytest.raises(WeightsIncomplete) as raised:
        assert_fully_loaded("m", ["b.weight", "a.weight"])
    assert "a.weight" in str(raised.value) and "b.weight" in str(raised.value)


# --- a pinned revision is not proof that the local bytes still match it -------------------


def _git_blob_id(payload: bytes) -> str:
    digest = hashlib.sha1(usedforsecurity=False)
    digest.update(f"blob {len(payload)}\0".encode())
    digest.update(payload)
    return digest.hexdigest()


def _integrity_checkpoint(tmp_path: Path) -> tuple[ModelStore, Path]:
    model_id = "Qwen3-VL-Embedding-2B"
    repository = "Qwen/test-embedding"
    revision = "a" * 40
    config = b'{"model_type":"qwen3_vl"}'
    weights = b"safe tensor bytes"
    (tmp_path / "sources.json").write_text(json.dumps({model_id: repository}), encoding="utf-8")
    (tmp_path / "revisions.json").write_text(json.dumps({repository: revision}), encoding="utf-8")
    (tmp_path / "integrity.json").write_text(
        json.dumps(
            {
                "schema": 1,
                "models": {
                    model_id: {
                        "status": "verified",
                        "repository": repository,
                        "revision": revision,
                        "files": {
                            "config.json": {
                                "algorithm": "git-sha1",
                                "digest": _git_blob_id(config),
                                "size_bytes": len(config),
                            },
                            "model.safetensors": {
                                "algorithm": "sha256",
                                "digest": hashlib.sha256(weights).hexdigest(),
                                "size_bytes": len(weights),
                            },
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    checkpoint = tmp_path / model_id
    checkpoint.mkdir()
    (checkpoint / "config.json").write_bytes(config)
    (checkpoint / "model.safetensors").write_bytes(weights)
    # Downloader state is not repository content and must not become an unexplained extra.
    (checkpoint / ".cache" / "huggingface").mkdir(parents=True)
    (checkpoint / ".cache" / "huggingface" / "metadata").write_text("ignored")
    return ModelStore(root=tmp_path), checkpoint


def test_checkpoint_bytes_are_verified_against_git_and_lfs_identities(tmp_path: Path) -> None:
    model_store, checkpoint = _integrity_checkpoint(tmp_path)
    report = model_store.verify_checkpoint("Qwen3-VL-Embedding-2B", checkpoint)
    assert report.files_verified == 2
    assert report.size_bytes == sum(
        path.stat().st_size
        for path in (checkpoint / "config.json", checkpoint / "model.safetensors")
    )
    assert report.revision == "a" * 40


def test_verified_checkpoint_is_reported_ready_and_can_start(tmp_path: Path) -> None:
    model_store, checkpoint = _integrity_checkpoint(tmp_path)
    status = next(item for item in model_store.status() if item.model_id == "Qwen3-VL-Embedding-2B")
    assert status.available is True
    assert status.path == checkpoint
    assert "verified 2 files" in status.detail
    assert model_store.assert_available("Qwen3-VL-Embedding-2B") == checkpoint


def test_same_size_weight_tampering_is_refused_before_load(tmp_path: Path) -> None:
    """Size/mtime checks miss this; a numeric weight can change without changing file shape."""
    model_store, checkpoint = _integrity_checkpoint(tmp_path)
    weights = checkpoint / "model.safetensors"
    original = weights.read_bytes()
    weights.write_bytes(bytes([original[0] ^ 1]) + original[1:])
    assert weights.stat().st_size == len(original)
    with pytest.raises(CheckpointIntegrityError, match="Same-size weight corruption"):
        model_store.verify_checkpoint("Qwen3-VL-Embedding-2B", checkpoint)


@pytest.mark.parametrize("change", ["missing", "extra"])
def test_checkpoint_file_set_must_exactly_match_the_snapshot(tmp_path: Path, change: str) -> None:
    model_store, checkpoint = _integrity_checkpoint(tmp_path)
    if change == "missing":
        (checkpoint / "config.json").unlink()
    else:
        (checkpoint / "modeling_attacker.py").write_text("raise SystemExit")
    with pytest.raises(CheckpointIntegrityError, match=rf"{change}="):
        model_store.verify_checkpoint("Qwen3-VL-Embedding-2B", checkpoint)


def test_integrity_manifest_cannot_drift_from_the_provisioning_revision(tmp_path: Path) -> None:
    model_store, checkpoint = _integrity_checkpoint(tmp_path)
    (tmp_path / "revisions.json").write_text(
        json.dumps({"Qwen/test-embedding": "b" * 40}), encoding="utf-8"
    )
    with pytest.raises(CheckpointIntegrityError, match="different weights"):
        model_store.verify_checkpoint("Qwen3-VL-Embedding-2B", checkpoint)


def test_tracked_integrity_manifest_covers_every_weight_repository() -> None:
    model_store = ModelStore()
    manifest = model_store.integrity()
    expected = {
        model_id
        for model_id, entry in REGISTRY.items()
        if entry.provisioning is Provisioning.WEIGHTS
    }
    assert set(manifest) == expected
    for model_id in expected:
        entry = REGISTRY[model_id]
        model = manifest[model_id]
        assert isinstance(model, dict)
        repository = model_store.source_for(entry)
        assert model["repository"] == repository
        assert model["revision"] == model_store.revision_for(repository)
        files = model["files"]
        assert isinstance(files, dict) and files
        status = model["status"]
        if status == "blocked":
            assert model_id == "pyannote/speaker-diarization-community-1"
            assert isinstance(model.get("reason"), str) and model["reason"]
            redacted = 0
            for relative, expectation in files.items():
                assert isinstance(relative, str) and isinstance(expectation, dict)
                assert isinstance(expectation.get("size_bytes"), int)
                if expectation.get("hub_digest_redacted") is True:
                    assert set(expectation) == {"hub_digest_redacted", "size_bytes"}
                    redacted += 1
                else:
                    assert expectation.get("algorithm") == "git-sha1"
                    assert re.fullmatch(r"[0-9a-f]{40}", expectation.get("digest", ""))
            assert redacted == 5
            continue
        assert status == "verified"
        for relative, expectation in files.items():
            assert isinstance(relative, str)
            path = PurePosixPath(relative)
            assert relative and "\\" not in relative and not path.is_absolute()
            assert ".." not in path.parts
            assert isinstance(expectation, dict)
            assert set(expectation) == {"algorithm", "digest", "size_bytes"}
            algorithm = expectation["algorithm"]
            digest = expectation["digest"]
            assert algorithm in {"git-sha1", "sha256"}
            assert isinstance(digest, str)
            expected_length = 40 if algorithm == "git-sha1" else 64
            assert re.fullmatch(rf"[0-9a-f]{{{expected_length}}}", digest)
            size = expectation["size_bytes"]
            assert isinstance(size, int) and not isinstance(size, bool) and size >= 0


def test_gated_checkpoint_with_redacted_digests_is_refused_not_approximated(
    tmp_path: Path,
) -> None:
    entry = REGISTRY["pyannote/speaker-diarization-community-1"]
    checkpoint = tmp_path / entry.model_id.replace("/", "__")
    checkpoint.mkdir()
    (checkpoint / "placeholder").write_text("not trusted", encoding="utf-8")
    with pytest.raises(CheckpointIntegrityError, match="verification is blocked.*redacts"):
        ModelStore().verify_checkpoint(entry.model_id, checkpoint)


def test_installed_integrity_manifest_location_is_stable() -> None:
    from hawedit.models import INSTALLED_INTEGRITY

    assert INSTALLED_INTEGRITY.parts[-4:] == ("share", "hawedit", "models", "integrity.json")


# --- checkpoint configuration is data, not an implicit code-loading instruction -----------


def _write_transformers_config(root: Path, value: object) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "config.json").write_text(json.dumps(value), encoding="utf-8")


def test_builtin_transformers_implementations_are_accepted(tmp_path: Path) -> None:
    _write_transformers_config(
        tmp_path,
        {
            "model_type": "qwen3_vl",
            "text_config": {"attn_implementation": "sdpa"},
            "vision_config": {"attn_implementation": "flash_attention_2"},
        },
    )
    assert_transformers_config_safe(tmp_path, {"qwen3_vl"})


@pytest.mark.parametrize(
    "field", ["_attn_implementation_internal", "_experts_implementation_internal"]
)
def test_private_implementation_fields_are_refused_recursively(tmp_path: Path, field: str) -> None:
    """CVE-2026-4372 bypasses trust_remote_code through deserialised private fields."""
    _write_transformers_config(
        tmp_path,
        {
            "model_type": "qwen3_vl",
            "vision_config": {"layers": [{field: "attacker/remote-kernel"}]},
        },
    )
    with pytest.raises(UnsafeModelConfig, match=rf"{field}.*CVE-2026-4372"):
        assert_transformers_config_safe(tmp_path, {"qwen3_vl"})


@pytest.mark.parametrize("field", ["attn_implementation", "experts_implementation"])
def test_public_implementation_fields_cannot_name_a_remote_kernel(
    tmp_path: Path, field: str
) -> None:
    _write_transformers_config(
        tmp_path,
        {"model_type": "qwen3_vl", field: "attacker/remote-kernel@main:entry"},
    )
    with pytest.raises(UnsafeModelConfig, match="remote kernel"):
        assert_transformers_config_safe(tmp_path, {"qwen3_vl"})


def test_public_implementation_mapping_cannot_hide_a_remote_kernel(tmp_path: Path) -> None:
    _write_transformers_config(
        tmp_path,
        {
            "model_type": "qwen3_vl",
            "attn_implementation": {
                "encoder": "sdpa",
                "decoder": {"fallback": "attacker/remote-kernel"},
            },
        },
    )
    with pytest.raises(UnsafeModelConfig, match="config.attn_implementation.decoder.fallback"):
        assert_transformers_config_safe(tmp_path, {"qwen3_vl"})


def test_config_cannot_override_trust_remote_code_in_a_nested_model(tmp_path: Path) -> None:
    _write_transformers_config(
        tmp_path,
        {
            "model_type": "qwen3_vl",
            "keypoint_detector_config": {
                "model_type": "qwen3_vl",
                "trust_remote_code": True,
            },
        },
    )
    with pytest.raises(UnsafeModelConfig, match="CVE-2026-5241"):
        assert_transformers_config_safe(tmp_path, {"qwen3_vl"})


@pytest.mark.parametrize("model_type", ["xclip", "lightglue"])
def test_checkpoint_cannot_dispatch_into_an_unapproved_model_family(
    tmp_path: Path, model_type: str
) -> None:
    _write_transformers_config(tmp_path, {"model_type": model_type})
    with pytest.raises(UnsafeModelConfig, match="unapproved"):
        assert_transformers_config_safe(tmp_path, {"qwen3_vl", "qwen3_vl_text"})


def test_a_missing_or_malformed_transformers_config_is_refused_before_loading(
    tmp_path: Path,
) -> None:
    with pytest.raises(UnsafeModelConfig, match="is missing"):
        assert_transformers_config_safe(tmp_path, {"qwen3_vl"})
    (tmp_path / "config.json").write_text("{", encoding="utf-8")
    with pytest.raises(UnsafeModelConfig, match="cannot safely read"):
        assert_transformers_config_safe(tmp_path, {"qwen3_vl"})


# --- revisions are pinned, never resolved at download time -------------------------------
#
# `snapshot_download` without `revision=` resolves whatever the branch head points at on the
# day it runs. Measured 2026-08-09: nothing on disk or in the tree recorded which revision
# produced the 27 GB of weights already on hawapc01, so every number in `evidence/m5-*.md` was
# about weights nobody could identify. D-073.


def test_a_repository_with_no_pinned_revision_is_refused_not_resolved(tmp_path: Path) -> None:
    """The whole point: a missing pin must stop the download, not fall back to the head."""
    from hawedit.models import RevisionNotPinned

    with pytest.raises(RevisionNotPinned, match="revisions.json"):
        store(tmp_path).revision_for("Qwen/Qwen3-VL-Embedding-2B")


def test_a_pinned_revision_is_returned_for_download(tmp_path: Path) -> None:
    """The control. A `revision_for` that raised unconditionally passes the test above."""
    (tmp_path / "revisions.json").write_text(json.dumps({"Qwen/repo": "0" * 40}), encoding="utf-8")
    assert store(tmp_path).revision_for("Qwen/repo") == "0" * 40


def test_comment_keys_are_not_mistaken_for_repositories(tmp_path: Path) -> None:
    """`revisions.json` carries its provenance in `_`-prefixed keys, as `sources.json` does."""
    (tmp_path / "revisions.json").write_text(
        json.dumps({"_measured": "2026-08-09 from the Hub", "Qwen/repo": "a" * 40}),
        encoding="utf-8",
    )
    assert dict(store(tmp_path).revisions()) == {"Qwen/repo": "a" * 40}


def test_every_repository_the_fetcher_would_download_is_pinned() -> None:
    """The tracked manifest must cover what this checkout actually fetches.

    Reads the real `models/revisions.json` rather than a fixture: a pin file that is correct
    in a temp directory and incomplete in the repository would protect nothing.
    """
    from hawedit.models import DEFAULT_MODELS_ROOT, ModelStore, SourceNotConfigured

    real = ModelStore()
    pinned = set(real.revisions())
    assert pinned, f"no pinned revisions found under {DEFAULT_MODELS_ROOT}"
    unpinned = []
    for entry in REGISTRY.values():
        try:
            source = real.source_for(entry)
        except SourceNotConfigured:
            continue  # §7 names a checkpoint, not a repo — covered by the source tests above
        if source not in pinned:
            unpinned.append(source)
    # No exemptions. This asserted `== ["pyannote/speaker-diarization-community-1"]` until
    # D-075: that repo is gated for *downloads* and public for *metadata*, so its revision was
    # always a verifiable fact here and leaving it unpinned was an error, not a principle.
    assert unpinned == [], unpinned


def test_every_pinned_revision_is_a_full_commit_sha() -> None:
    """A tag or a branch name here would reintroduce exactly what the pin removes."""
    import re

    from hawedit.models import ModelStore

    for repo, revision in ModelStore().revisions().items():
        assert re.fullmatch(r"[0-9a-f]{40}", revision), f"{repo} is pinned to {revision!r}"


def test_the_installed_revision_manifest_location_is_stable() -> None:
    from hawedit.models import INSTALLED_REVISIONS

    assert INSTALLED_REVISIONS.parts[-4:] == ("share", "hawedit", "models", "revisions.json")


def test_the_fetcher_passes_the_pinned_revision_to_snapshot_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Runs the download block out of `fetch-models.sh` itself, against a stubbed Hub.

    Deliberately not a grep of the script. An assertion about the text of a command is not an
    assertion about what the command does — the same mistake D-067 recorded one layer up. This
    executes the real block and inspects the call it makes.
    """
    import sys as _sys
    import types

    source_code = _fetcher_download_block()

    calls: list[dict[str, object]] = []
    stub = types.ModuleType("huggingface_hub")
    stub.snapshot_download = lambda **kwargs: calls.append(kwargs)  # type: ignore[attr-defined]
    monkeypatch.setitem(_sys.modules, "huggingface_hub", stub)

    (tmp_path / "revisions.json").write_text(json.dumps({"Qwen/repo": "b" * 40}), encoding="utf-8")
    monkeypatch.setenv("HAWEDIT_MODELS_DIR", str(tmp_path))
    monkeypatch.setattr(_sys, "argv", ["fetch", "Qwen/repo", str(tmp_path / "dest")])

    import importlib

    import hawedit.models

    importlib.reload(hawedit.models)  # pick up HAWEDIT_MODELS_DIR
    try:
        exec(compile(source_code, "fetch-models.sh:PYEOF", "exec"), {"__name__": "__main__"})
        assert calls == [
            {"repo_id": "Qwen/repo", "revision": "b" * 40, "local_dir": str(tmp_path / "dest")}
        ], calls
    finally:
        monkeypatch.undo()
        importlib.reload(hawedit.models)


def test_the_fetcher_refuses_a_repository_that_is_not_pinned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control for the test above: no pin means no download call at all, and exit 1."""
    import sys as _sys
    import types

    source_code = _fetcher_download_block()

    calls: list[dict[str, object]] = []
    stub = types.ModuleType("huggingface_hub")
    stub.snapshot_download = lambda **kwargs: calls.append(kwargs)  # type: ignore[attr-defined]
    monkeypatch.setitem(_sys.modules, "huggingface_hub", stub)

    (tmp_path / "revisions.json").write_text(json.dumps({}), encoding="utf-8")
    monkeypatch.setenv("HAWEDIT_MODELS_DIR", str(tmp_path))
    monkeypatch.setattr(_sys, "argv", ["fetch", "Qwen/unpinned", str(tmp_path / "dest")])

    import importlib

    import hawedit.models

    importlib.reload(hawedit.models)
    try:
        with pytest.raises(SystemExit) as exited:
            exec(compile(source_code, "fetch-models.sh:PYEOF", "exec"), {"__name__": "__main__"})
        assert exited.value.code == 1
        assert calls == [], f"downloaded despite no pin: {calls}"
    finally:
        monkeypatch.undo()
        importlib.reload(hawedit.models)

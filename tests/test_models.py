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
import os
import re
import stat
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from typing import Any

import pytest

from hawedit.models import (
    CheckpointIntegrityError,
    ModelNotProvisioned,
    ModelStore,
    SourceNotConfigured,
    UnsafeModelConfig,
    _checkpoint_digest,
    assert_transformers_config_safe,
    readiness_report,
)
from hawedit.registry import REGISTRY, Provisioning

ROOT = Path(__file__).resolve().parents[1]


def store(tmp_path: Path) -> ModelStore:
    return ModelStore(root=tmp_path, metadata_root=tmp_path)


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
    """Compatibility harness that executes the installed module's real transaction.

    The checkout wrapper is intentionally shell-only now. These older adversarial regressions
    still execute the production ``fetch_checkpoint`` function against a stubbed Hub instead of
    degrading into source-text assertions.
    """
    return """
import importlib
import sys
from pathlib import Path

from huggingface_hub import snapshot_download
import hawedit.model_fetch as model_fetch
from hawedit.models import ModelStore, RevisionNotPinned
from hawedit.registry import REGISTRY

model_fetch = importlib.reload(model_fetch)
model_id, source, destination = sys.argv[1], sys.argv[2], Path(sys.argv[3])
store = ModelStore()
try:
    revision = store.revision_for(source)
except RevisionNotPinned as exc:
    print(f"REFUSED: {exc}", file=sys.stderr)
    raise SystemExit(1) from None
item = model_fetch.FetchItem(REGISTRY[model_id], source, revision, destination)
try:
    report = model_fetch.fetch_checkpoint(item, store, snapshot_download)
except Exception as exc:
    print(f"FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
    raise SystemExit(1) from None
print(f"done: {report.files_verified} files, {report.size_bytes} bytes")
"""


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


@pytest.mark.parametrize(
    "document",
    [
        [],
        {"Qwen3-VL-Embedding-2B": ["Qwen/repo"]},
        {"Qwen3-VL-Embedding-2B": "https://user:hf_SECRET@host/Qwen/repo"},
        {"unknown/model": "Qwen/repo"},
    ],
)
def test_source_metadata_requires_a_typed_allowlisted_object(
    tmp_path: Path, document: object
) -> None:
    (tmp_path / "sources.json").write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(
        CheckpointIntegrityError, match="JSON object|repository id|unknown"
    ) as raised:
        store(tmp_path).sources()
    assert "hf_SECRET" not in str(raised.value)


def test_the_installed_source_manifest_location_is_stable() -> None:
    from hawedit.models import INSTALLED_SOURCES

    assert INSTALLED_SOURCES.parts[-4:] == ("share", "hawedit", "models", "sources.json")


def test_installed_metadata_uses_authenticated_distribution_files_under_target_layout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hawedit import models as models_module

    target = tmp_path / "target"
    metadata = target / "share" / "hawedit" / "models"
    metadata.mkdir(parents=True)
    for name in ("sources.json", "revisions.json", "integrity.json"):
        (metadata / name).write_text("{}", encoding="utf-8")
    fake_module = target / "hawedit" / "models.py"
    fake_module.parent.mkdir()
    fake_module.write_text("", encoding="utf-8")
    requested: list[str] = []

    def resolve(relative: str) -> Path:
        requested.append(relative)
        return target / relative

    monkeypatch.setattr(models_module, "__file__", str(fake_module))
    monkeypatch.setattr(models_module, "resolve_installed_hawedit_data", resolve)

    model_store = models_module.ModelStore(root=tmp_path / "weights")

    assert model_store.metadata_root == metadata
    assert requested == [
        "share/hawedit/models/sources.json",
        "share/hawedit/models/revisions.json",
        "share/hawedit/models/integrity.json",
    ]


def test_fresh_custom_checkpoint_root_uses_tracked_metadata_only_for_identity(
    tmp_path: Path,
) -> None:
    model_store = ModelStore(root=tmp_path)
    entry = REGISTRY["Qwen3-VL-Embedding-2B"]
    repository = model_store.source_for(entry)
    assert repository == "Qwen/Qwen3-VL-Embedding-2B"
    assert re.fullmatch(r"[0-9a-f]{40}", model_store.revision_for(repository))
    assert "Qwen3-VL-Embedding-2B" in model_store.integrity()
    assert model_store.path_for(entry).parent == tmp_path
    assert not tuple(tmp_path.iterdir()), (
        "immutable metadata must not be copied into the model root"
    )


def test_mutable_checkpoint_root_cannot_override_trusted_metadata(tmp_path: Path) -> None:
    trusted = ModelStore()
    (tmp_path / "sources.json").write_text(
        json.dumps({"Qwen3-VL-Embedding-2B": "attacker/substitute"}), encoding="utf-8"
    )
    (tmp_path / "revisions.json").write_text(
        json.dumps({"attacker/substitute": "0" * 40}), encoding="utf-8"
    )
    (tmp_path / "integrity.json").write_text(
        json.dumps({"schema": 1, "models": {}}), encoding="utf-8"
    )

    custom = ModelStore(root=tmp_path)
    assert dict(custom.sources()) == dict(trusted.sources())
    assert dict(custom.revisions()) == dict(trusted.revisions())
    assert custom.integrity() == trusted.integrity()


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
    return ModelStore(root=tmp_path, metadata_root=tmp_path), checkpoint


def test_checkpoint_bytes_are_verified_against_git_and_lfs_identities(tmp_path: Path) -> None:
    model_store, checkpoint = _integrity_checkpoint(tmp_path)
    report = model_store.verify_checkpoint("Qwen3-VL-Embedding-2B", checkpoint)
    assert report.files_verified == 2
    assert report.size_bytes == sum(
        path.stat().st_size
        for path in (checkpoint / "config.json", checkpoint / "model.safetensors")
    )
    assert report.revision == "a" * 40


def test_checkpoint_hash_accepts_windows_fd_and_path_ctime_semantics(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    checkpoint_file = tmp_path / "model.safetensors"
    payload = b"verified model bytes"
    checkpoint_file.write_bytes(payload)
    actual = os.lstat(checkpoint_file)

    def metadata(*, ctime_ns: int) -> SimpleNamespace:
        return SimpleNamespace(
            st_mode=actual.st_mode,
            st_dev=actual.st_dev,
            st_ino=actual.st_ino,
            st_size=actual.st_size,
            st_mtime_ns=actual.st_mtime_ns,
            st_ctime_ns=ctime_ns,
            st_nlink=actual.st_nlink,
        )

    descriptor_metadata = metadata(ctime_ns=100)
    pathname_metadata = metadata(ctime_ns=200)
    monkeypatch.setattr("hawedit.models.os.fstat", lambda _descriptor: descriptor_metadata)
    monkeypatch.setattr("hawedit.models.os.lstat", lambda _path: pathname_metadata)
    monkeypatch.setattr("hawedit.models._path_is_reparse", lambda _path: False)

    assert (
        _checkpoint_digest(checkpoint_file, "sha256", len(payload))
        == hashlib.sha256(payload).hexdigest()
    )


def test_wsl_snapshot_model_store_uses_adjacent_validator_identity_metadata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import hawedit.models as models_module
    from hawedit.wsl_setup import WSL_MODEL_METADATA_DIRECTORY

    model_id = "rzgar/qwen3-asr-sorani-kurdish-ckb-v1"
    repository = model_id
    revision = "b" * 40
    config = b'{"model_type":"qwen3_asr"}'
    weights = b"fixture validator tensor bytes"

    snapshot = tmp_path / "snapshots" / "digest-random"
    package = snapshot / "hawedit"
    package.mkdir(parents=True)
    metadata = snapshot / WSL_MODEL_METADATA_DIRECTORY
    metadata.mkdir()
    (metadata / "sources.json").write_text("{}", encoding="utf-8")
    (metadata / "revisions.json").write_text(json.dumps({repository: revision}), encoding="utf-8")
    (metadata / "integrity.json").write_text(
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
    checkpoint = tmp_path / "weights" / "validator"
    checkpoint.mkdir(parents=True)
    (checkpoint / "config.json").write_bytes(config)
    (checkpoint / "model.safetensors").write_bytes(weights)

    monkeypatch.setattr(models_module, "__file__", str(package / "models.py"))
    model_store = ModelStore(root=tmp_path / "weights")
    assert model_store.metadata_root == metadata
    report = model_store.verify_checkpoint(model_id, checkpoint)
    assert report.repository == repository
    assert report.revision == revision
    assert report.files_verified == 2


def test_verified_checkpoint_is_reported_ready_and_can_start(tmp_path: Path) -> None:
    model_store, checkpoint = _integrity_checkpoint(tmp_path)
    status = next(item for item in model_store.status() if item.model_id == "Qwen3-VL-Embedding-2B")
    assert status.available is True
    assert status.path == checkpoint
    assert "verified 2 files" in status.detail
    assert model_store.assert_available("Qwen3-VL-Embedding-2B") == checkpoint


def test_fetch_plan_uses_verified_status_and_includes_invalid_existing_final(
    tmp_path: Path,
) -> None:
    model_store, checkpoint = _integrity_checkpoint(tmp_path)
    model_id = "Qwen3-VL-Embedding-2B"
    assert model_id not in {entry.model_id for entry in model_store.missing_weights()}

    (checkpoint / "model.safetensors").write_bytes(b"same directory, invalid bytes")

    assert model_id in {entry.model_id for entry in model_store.missing_weights()}
    assert checkpoint.is_dir(), "planning must never remove or quarantine user data"


def test_verified_checkpoint_access_verifies_before_yield_and_holds_sibling_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hawedit.models import ModelStore, verified_checkpoint_access

    checkpoint = tmp_path / "checkpoint"
    checkpoint.mkdir()
    events: list[str] = []

    def verify(_store: ModelStore, model_id: str, selected: Path | None = None) -> SimpleNamespace:
        assert model_id == "Qwen3-VL-Embedding-2B"
        assert selected == checkpoint
        events.append("verified")
        return SimpleNamespace()

    monkeypatch.setattr(ModelStore, "verify_checkpoint", verify)
    with verified_checkpoint_access("Qwen3-VL-Embedding-2B", checkpoint) as selected:
        events.append("consumer")
        assert selected == checkpoint.resolve()
        assert (tmp_path / ".checkpoint.hawedit.lock").is_file()
    assert events == ["verified", "consumer"]


def test_checkpoint_publication_never_replaces_a_concurrently_appearing_final(
    tmp_path: Path,
) -> None:
    from hawedit.models import _publish_checkpoint_directory

    staging = tmp_path / ".checkpoint.download-revision"
    staging.mkdir()
    (staging / "verified.bin").write_bytes(b"verified")
    destination = tmp_path / "checkpoint"
    destination.mkdir()
    destination_inode = destination.stat().st_ino

    with pytest.raises(FileExistsError):
        _publish_checkpoint_directory(staging, destination)

    assert destination.stat().st_ino == destination_inode
    assert not tuple(destination.iterdir())
    assert (staging / "verified.bin").read_bytes() == b"verified"


def test_same_size_weight_tampering_is_refused_before_load(tmp_path: Path) -> None:
    """Size/mtime checks miss this; a numeric weight can change without changing file shape."""
    model_store, checkpoint = _integrity_checkpoint(tmp_path)
    weights = checkpoint / "model.safetensors"
    original = weights.read_bytes()
    weights.write_bytes(bytes([original[0] ^ 1]) + original[1:])
    assert weights.stat().st_size == len(original)
    with pytest.raises(CheckpointIntegrityError, match="Same-size weight corruption"):
        model_store.verify_checkpoint("Qwen3-VL-Embedding-2B", checkpoint)


def test_checkpoint_hardlinked_member_is_refused(tmp_path: Path) -> None:
    model_store, checkpoint = _integrity_checkpoint(tmp_path)
    weights = checkpoint / "model.safetensors"
    os.link(weights, tmp_path / "weights-alias.safetensors")
    with pytest.raises(CheckpointIntegrityError, match="exactly one hard link"):
        model_store.verify_checkpoint("Qwen3-VL-Embedding-2B", checkpoint)


def test_checkpoint_root_reparse_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model_store, checkpoint = _integrity_checkpoint(tmp_path)
    linked = tmp_path / "linked-checkpoint"
    try:
        linked.symlink_to(checkpoint, target_is_directory=True)
        selected = linked
    except OSError:
        selected = checkpoint
        original = __import__("hawedit.models", fromlist=["_path_is_reparse"])._path_is_reparse
        monkeypatch.setattr(
            "hawedit.models._path_is_reparse",
            lambda path: Path(path) == checkpoint or original(path),
        )
    with pytest.raises(CheckpointIntegrityError, match="root must not be.*reparse"):
        model_store.verify_checkpoint("Qwen3-VL-Embedding-2B", selected)


def test_checkpoint_member_reparse_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model_store, checkpoint = _integrity_checkpoint(tmp_path)
    config = checkpoint / "config.json"
    external = tmp_path / "external-config.json"
    external.write_bytes(config.read_bytes())
    config.unlink()
    try:
        config.symlink_to(external)
    except OSError:
        config.write_bytes(external.read_bytes())
        original = __import__("hawedit.models", fromlist=["_path_is_reparse"])._path_is_reparse
        monkeypatch.setattr(
            "hawedit.models._path_is_reparse",
            lambda path: Path(path) == config or original(path),
        )
    with pytest.raises(CheckpointIntegrityError, match="link or reparse point"):
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


@pytest.mark.parametrize("document", [[], {"Qwen/repo": ["a" * 40]}, {"https://bad": "a" * 40}])
def test_revision_metadata_requires_a_typed_allowlisted_object(
    tmp_path: Path, document: object
) -> None:
    (tmp_path / "revisions.json").write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises((CheckpointIntegrityError, RuntimeError)):
        store(tmp_path).revisions()


@pytest.mark.parametrize("revision", ["A" * 40, "a" * 39, "main", 7])
def test_revision_for_rejects_every_noncanonical_commit_pin(
    tmp_path: Path, revision: object
) -> None:
    from hawedit.models import RevisionNotPinned

    (tmp_path / "revisions.json").write_text(json.dumps({"Qwen/repo": revision}), encoding="utf-8")
    with pytest.raises(RevisionNotPinned, match="full lowercase 40-hex"):
        store(tmp_path).revision_for("Qwen/repo")


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
    """Runs the installed Python transaction itself against a stubbed Hub.

    Deliberately not a grep of the script. An assertion about the text of a command is not an
    assertion about what the command does — the same mistake D-067 recorded one layer up. This
    executes the real block and inspects the call it makes.
    """
    import sys as _sys
    import types

    source_code = _fetcher_download_block()

    calls: list[dict[str, object]] = []
    stub = types.ModuleType("huggingface_hub")

    def snapshot_download(**kwargs: object) -> None:
        calls.append(kwargs)
        Path(str(kwargs["local_dir"]), "downloaded.bin").write_bytes(b"verified")

    stub.snapshot_download = snapshot_download  # type: ignore[attr-defined]
    monkeypatch.setitem(_sys.modules, "huggingface_hub", stub)

    monkeypatch.setenv("HAWEDIT_MODELS_DIR", str(tmp_path))
    destination = tmp_path / "dest"
    monkeypatch.setattr(
        _sys,
        "argv",
        ["fetch", "Qwen3-VL-Embedding-2B", "Qwen/repo", str(destination)],
    )

    import importlib

    import hawedit.models

    importlib.reload(hawedit.models)  # pick up HAWEDIT_MODELS_DIR
    monkeypatch.setattr(
        hawedit.models.ModelStore,
        "revision_for",
        lambda _store, repository: "b" * 40 if repository == "Qwen/repo" else None,
    )
    verified: list[Path] = []

    def verify(_store: object, _model_id: str, checkpoint: Path | None = None) -> SimpleNamespace:
        assert checkpoint is not None
        verified.append(checkpoint)
        return SimpleNamespace(files_verified=1, size_bytes=8)

    monkeypatch.setattr(hawedit.models.ModelStore, "verify_checkpoint", verify)
    try:
        exec(compile(source_code, "hawedit.model_fetch:harness", "exec"), {"__name__": "__main__"})
        assert len(calls) == 1
        assert calls[0]["repo_id"] == "Qwen/repo"
        assert calls[0]["revision"] == "b" * 40
        staging = Path(str(calls[0]["local_dir"]))
        assert staging.parent == tmp_path
        assert staging.name == ".dest.resume-" + "b" * 40
        assert verified == [staging]
        assert (destination / "downloaded.bin").read_bytes() == b"verified"
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
    monkeypatch.setattr(
        _sys,
        "argv",
        ["fetch", "Qwen3-VL-Embedding-2B", "Qwen/unpinned", str(tmp_path / "dest")],
    )

    import importlib

    import hawedit.models

    importlib.reload(hawedit.models)
    try:
        with pytest.raises(SystemExit) as exited:
            exec(
                compile(source_code, "hawedit.model_fetch:harness", "exec"),
                {"__name__": "__main__"},
            )
        assert exited.value.code == 1
        assert calls == [], f"downloaded despite no pin: {calls}"
    finally:
        monkeypatch.undo()
        importlib.reload(hawedit.models)


def test_fetcher_preserves_and_refuses_invalid_existing_final(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import importlib
    import sys as _sys
    import types

    import hawedit.models

    source_code = _fetcher_download_block()
    calls: list[dict[str, object]] = []
    stub = types.ModuleType("huggingface_hub")
    stub.snapshot_download = lambda **kwargs: calls.append(kwargs)  # type: ignore[attr-defined]
    monkeypatch.setitem(_sys.modules, "huggingface_hub", stub)
    destination = tmp_path / "dest"
    destination.mkdir()
    sentinel = destination / "user-data.bin"
    sentinel.write_bytes(b"preserve-me")
    monkeypatch.setenv("HAWEDIT_MODELS_DIR", str(tmp_path))
    monkeypatch.setattr(
        _sys,
        "argv",
        ["fetch", "Qwen3-VL-Embedding-2B", "Qwen/repo", str(destination)],
    )
    importlib.reload(hawedit.models)
    monkeypatch.setattr(
        hawedit.models.ModelStore,
        "revision_for",
        lambda _store, repository: "c" * 40 if repository == "Qwen/repo" else None,
    )

    def invalid(*_args: object, **_kwargs: object) -> None:
        raise hawedit.models.CheckpointIntegrityError("invalid existing bytes")

    monkeypatch.setattr(hawedit.models.ModelStore, "verify_checkpoint", invalid)
    try:
        with pytest.raises(SystemExit) as exited:
            exec(
                compile(source_code, "hawedit.model_fetch:harness", "exec"),
                {"__name__": "__main__"},
            )
        assert exited.value.code == 1
        assert calls == []
        assert sentinel.read_bytes() == b"preserve-me"
        assert not tuple(tmp_path.glob(".dest.download-*"))
    finally:
        monkeypatch.undo()
        importlib.reload(hawedit.models)


def test_fetcher_preserves_private_stage_when_manifest_verification_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import importlib
    import sys as _sys
    import types

    import hawedit.models

    source_code = _fetcher_download_block()
    stub = types.ModuleType("huggingface_hub")

    def snapshot_download(**kwargs: object) -> None:
        Path(str(kwargs["local_dir"]), "partial.bin").write_bytes(b"diagnose-me")

    stub.snapshot_download = snapshot_download  # type: ignore[attr-defined]
    monkeypatch.setitem(_sys.modules, "huggingface_hub", stub)
    destination = tmp_path / "dest"
    monkeypatch.setenv("HAWEDIT_MODELS_DIR", str(tmp_path))
    monkeypatch.setattr(
        _sys,
        "argv",
        ["fetch", "Qwen3-VL-Embedding-2B", "Qwen/repo", str(destination)],
    )
    importlib.reload(hawedit.models)
    monkeypatch.setattr(
        hawedit.models.ModelStore,
        "revision_for",
        lambda _store, repository: "d" * 40 if repository == "Qwen/repo" else None,
    )

    def invalid(*_args: object, **_kwargs: object) -> None:
        raise hawedit.models.CheckpointIntegrityError("downloaded bytes do not match manifest")

    monkeypatch.setattr(hawedit.models.ModelStore, "verify_checkpoint", invalid)
    try:
        with pytest.raises(SystemExit) as exited:
            exec(
                compile(source_code, "hawedit.model_fetch:harness", "exec"),
                {"__name__": "__main__"},
            )
        assert exited.value.code == 1
        assert not destination.exists()
        staging = tuple(tmp_path.glob(".dest.resume-*"))
        assert len(staging) == 1
        assert (staging[0] / "partial.bin").read_bytes() == b"diagnose-me"
    finally:
        monkeypatch.undo()
        importlib.reload(hawedit.models)


def test_fetcher_refuses_preplanted_staging_hardlink_before_downloader_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import importlib
    import sys as _sys
    import types

    import hawedit.models

    source_code = _fetcher_download_block()
    calls: list[dict[str, object]] = []
    stub = types.ModuleType("huggingface_hub")

    def snapshot_download(**kwargs: object) -> None:
        calls.append(kwargs)
        Path(str(kwargs["local_dir"]), "config.json").write_bytes(b"CLOBBERED")

    stub.snapshot_download = snapshot_download  # type: ignore[attr-defined]
    monkeypatch.setitem(_sys.modules, "huggingface_hub", stub)
    destination = tmp_path / "dest"
    monkeypatch.setenv("HAWEDIT_MODELS_DIR", str(tmp_path))
    monkeypatch.setattr(
        _sys,
        "argv",
        ["fetch", "Qwen3-VL-Embedding-2B", "Qwen/repo", str(destination)],
    )
    importlib.reload(hawedit.models)
    revision = "e" * 40
    monkeypatch.setattr(
        hawedit.models.ModelStore,
        "revision_for",
        lambda _store, repository: revision if repository == "Qwen/repo" else None,
    )
    resume = tmp_path / f".dest.resume-{revision}"
    resume.mkdir(mode=0o700)
    victim = tmp_path / "external-victim.bin"
    victim.write_bytes(b"ORIGINAL")
    os.link(victim, resume / "config.json")

    try:
        with pytest.raises(SystemExit) as exited:
            exec(
                compile(source_code, "hawedit.model_fetch:harness", "exec"),
                {"__name__": "__main__"},
            )
        assert exited.value.code == 1
        assert calls == []
        assert victim.read_bytes() == b"ORIGINAL"
        assert (resume / "config.json").stat().st_nlink == 2
        assert not destination.exists()
    finally:
        monkeypatch.undo()
        importlib.reload(hawedit.models)


def test_fetcher_refuses_nonprivate_posix_resume_mode_before_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import importlib
    import sys as _sys
    import types

    import hawedit.models

    source_code = _fetcher_download_block()
    calls: list[dict[str, object]] = []
    stub = types.ModuleType("huggingface_hub")
    stub.snapshot_download = lambda **kwargs: calls.append(kwargs)  # type: ignore[attr-defined]
    monkeypatch.setitem(_sys.modules, "huggingface_hub", stub)
    destination = tmp_path / "dest"
    monkeypatch.setenv("HAWEDIT_MODELS_DIR", str(tmp_path))
    monkeypatch.setattr(
        _sys,
        "argv",
        ["fetch", "Qwen3-VL-Embedding-2B", "Qwen/repo", str(destination)],
    )
    importlib.reload(hawedit.models)
    revision = "f" * 40
    monkeypatch.setattr(
        hawedit.models.ModelStore,
        "revision_for",
        lambda _store, repository: revision if repository == "Qwen/repo" else None,
    )
    resume = tmp_path / f".dest.resume-{revision}"
    resume.mkdir(mode=0o700)
    real_lstat = os.lstat

    class PublicRootStat:
        def __init__(self, original: os.stat_result) -> None:
            self._original = original
            self.st_mode = (original.st_mode & ~0o777) | stat.S_IFDIR | 0o777
            self.st_uid = 1000

        def __getattr__(self, name: str) -> Any:
            return getattr(self._original, name)

    def public_resume_lstat(path: Any, *args: Any, **kwargs: Any) -> Any:
        result = real_lstat(path, *args, **kwargs)
        if not isinstance(path, int) and Path(os.fsdecode(path)) == resume:
            return PublicRootStat(result)
        return result

    monkeypatch.setattr(os, "getuid", lambda: 1000, raising=False)
    monkeypatch.setattr(os, "lstat", public_resume_lstat)
    try:
        with pytest.raises(SystemExit) as exited:
            exec(
                compile(source_code, "hawedit.model_fetch:harness", "exec"),
                {"__name__": "__main__"},
            )
        assert exited.value.code == 1
        assert calls == []
        assert resume.is_dir()
        assert not destination.exists()
    finally:
        monkeypatch.undo()
        importlib.reload(hawedit.models)

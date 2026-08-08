"""M1.6 — model provisioning: where §7's models live and whether a stage can run.

The registry is the single source of truth for what may be fetched, so a model outside §7
cannot be provisioned even by editing a config file. And a checkpoint whose source §7 does
not fix is *refused* rather than guessed — §7 names `omniASR_LLM_7B_v2` as a checkpoint, not
a repository, and inventing a plausible repo id produces a 404 on hawapc01 that nobody can
explain from the code.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hawedit.models import (
    ModelNotProvisioned,
    ModelStore,
    SourceNotConfigured,
    readiness_report,
)
from hawedit.registry import REGISTRY, Provisioning


def store(tmp_path: Path) -> ModelStore:
    return ModelStore(root=tmp_path)


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


def test_a_present_checkpoint_reports_as_available_with_its_size(tmp_path: Path) -> None:
    entry = REGISTRY["MCG-NJU/VideoChat3-4B"]
    weights = store(tmp_path).path_for(entry)
    weights.mkdir(parents=True)
    (weights / "model.safetensors").write_bytes(b"x" * 2048)
    status = next(s for s in store(tmp_path).status() if s.model_id == entry.model_id)
    assert status.available is True
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

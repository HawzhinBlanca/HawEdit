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

from hawedit2.models import (
    ModelNotProvisioned,
    ModelStore,
    SourceNotConfigured,
    readiness_report,
)
from hawedit2.registry import REGISTRY, Provisioning


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


def test_the_asr_checkpoints_need_weights() -> None:
    for model_id in ("omniASR_LLM_7B_v2", "omniASR_CTC_3B_v2"):
        assert REGISTRY[model_id].provisioning is Provisioning.WEIGHTS


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
    """§7 names omniASR_LLM_7B_v2 as a checkpoint. A guessed repo id 404s on the machine
    least able to debug it."""
    with pytest.raises(SourceNotConfigured, match="sources.json"):
        store(tmp_path).source_for(REGISTRY["omniASR_LLM_7B_v2"])


def test_a_configured_source_supplies_what_section_7_leaves_open(tmp_path: Path) -> None:
    (tmp_path / "sources.json").write_text(
        json.dumps({"omniASR_LLM_7B_v2": "facebook/some-omniasr-repo"}), encoding="utf-8"
    )
    assert store(tmp_path).source_for(REGISTRY["omniASR_LLM_7B_v2"]) == "facebook/some-omniasr-repo"


def test_unconfigured_sources_are_listed_so_an_operator_knows_what_to_supply(
    tmp_path: Path,
) -> None:
    unconfigured = {e.model_id for e in store(tmp_path).unconfigured_sources()}
    assert "omniASR_LLM_7B_v2" in unconfigured
    assert "pyannote/speaker-diarization-community-1" not in unconfigured


# --- status and readiness -----------------------------------------------------------------


def test_every_registry_entry_appears_in_the_status_report(tmp_path: Path) -> None:
    assert len(store(tmp_path).status()) == len(REGISTRY)


def test_an_absent_checkpoint_reports_as_missing(tmp_path: Path) -> None:
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
    assert "omniASR_LLM_7B_v2" in missing
    assert "KLPT" not in missing, "pip components are not downloads"
    assert "gemini-2.5-pro" not in missing, "a cloud API is not a download"


# --- refusing to start without what a stage needs -----------------------------------------


def test_a_stage_refuses_to_start_without_its_weights(tmp_path: Path) -> None:
    with pytest.raises(ModelNotProvisioned, match="fetch-models"):
        store(tmp_path).assert_available("omniASR_LLM_7B_v2")


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

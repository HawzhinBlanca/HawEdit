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

from hawedit import models
from hawedit.models import (
    ModelNotProvisioned,
    ModelStatus,
    ModelStore,
    SourceNotConfigured,
    readiness_report,
)
from hawedit.registry import (
    APACHE_2_0,
    CC_BY_NC_4_0,
    REGISTRY,
    Licence,
    ModelEntry,
    NonCommercialLicence,
    Provisioning,
)

ROOT = Path(__file__).resolve().parents[1]


def store(tmp_path: Path) -> ModelStore:
    return ModelStore(root=tmp_path)


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


# --- D-099: downloaded is not runnable ------------------------------------------------------


def test_a_downloaded_checkpoint_whose_loader_is_missing_is_not_available(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The readiness report is read as "can this stage run", so disk alone cannot answer it.

    Measured 2026-08-09: the report said `OK ... weights (10.1 GB)` for the rzgar validator while
    `transformers` 4.57.6 has no `qwen3_asr` module, `AutoModel` cannot map the config's
    `model_type`, and `Qwen3ASRForConditionalGeneration` is not importable. M1.4's row then
    concluded in prose that "what is missing is the composition, not the download" about a
    checkpoint nothing on this machine can load. D-099.
    """
    entry = REGISTRY["MCG-NJU/VideoChat3-4B"]
    weights = store(tmp_path).path_for(entry)
    weights.mkdir(parents=True)
    (weights / "model.safetensors").write_bytes(b"x" * 2048)
    monkeypatch.setattr(
        models, "_WEIGHTS_RUNTIMES", {entry.model_id: "hawedit_loader_that_is_not_installed"}
    )

    status = next(s for s in store(tmp_path).status() if s.model_id == entry.model_id)
    assert status.available is False
    assert "hawedit_loader_that_is_not_installed" in status.detail
    assert "cannot be loaded here" in status.detail
    assert status.size_bytes == 2048, "the weights are still on disk and still worth reporting"


def test_the_same_checkpoint_is_available_once_its_loader_can_be_imported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control. Declaring a runtime must not by itself make a component unavailable.

    Without this, "every entry in the runtime map reports MISS" passes the test above and would
    retire three working components — VideoChat3, TimeLens2 and the Qwen embedding pair all load
    today, and M5.4/M6.3 have the decoded-frame evidence to prove it.
    """
    entry = REGISTRY["MCG-NJU/VideoChat3-4B"]
    weights = store(tmp_path).path_for(entry)
    weights.mkdir(parents=True)
    (weights / "model.safetensors").write_bytes(b"x" * 2048)
    monkeypatch.setattr(models, "_WEIGHTS_RUNTIMES", {entry.model_id: "json"})

    status = next(s for s in store(tmp_path).status() if s.model_id == entry.model_id)
    assert status.available is True
    assert status.detail.startswith("weights from ")
    assert "cannot be loaded" not in status.detail


def test_the_validators_readiness_tracks_whether_its_loader_is_installed(tmp_path: Path) -> None:
    """The real entry, asserted as a coupling rather than as today's answer.

    `qwen_asr` is absent here and in CI, so hardcoding "unavailable" would pass for the wrong
    reason and flip the day someone installs it. This states the property instead: the validator
    is available exactly when the loader its model card names can be imported.
    """
    entry = REGISTRY["rzgar/qwen3-asr-sorani-kurdish-ckb-v1"]
    weights = store(tmp_path).path_for(entry)
    weights.mkdir(parents=True)
    (weights / "model.safetensors").write_bytes(b"x" * 1024)

    status = next(s for s in store(tmp_path).status() if s.model_id == entry.model_id)
    assert status.available is models._is_importable("qwen_asr")
    if not status.available:
        assert "qwen_asr" in status.detail


# --- D-100: the report a human reads could print the opposite of the truth -------------------


def _status(model_id: str, *, available: bool, size_bytes: int | None = None) -> ModelStatus:
    return ModelStatus(
        model_id=model_id,
        component=model_id,
        provisioning=Provisioning.WEIGHTS,
        available=available,
        detail="present" if available else "not downloaded",
        size_bytes=size_bytes,
    )


def _mark_for(report: str, model_id: str) -> str:
    """The verdict on this component's own line, not somewhere in the document."""
    line = next(row for row in report.splitlines() if model_id in row)
    return line.split()[0]


_MIXED = (
    _status("present-and-loadable", available=True, size_bytes=2_000_000_000),
    _status("absent-entirely", available=False),
    _status("also-present", available=True),
)


def test_the_report_marks_each_component_on_its_own_line() -> None:
    """Measured 2026-08-09 against a green 1,175 baseline: `readiness_report` could print
    **every** component as OK, or invert every verdict, or claim 15/15 while six were missing,
    and nothing in the suite noticed. The two tests that existed asserted
    `"omniASR_LLM_7B_v2" in report` and `"available" in report` — substring presence over the
    whole document, satisfied by the summary line no matter what the marks said. The same shape
    as D-094's `"hewler" in payload`.

    This is the artifact an operator reads to answer "can this machine run the pipeline", and it
    is the artifact whose `OK` led M1.4's row to conclude the wrong thing in prose (D-099). D-100.
    """
    report = readiness_report(_MIXED)
    assert _mark_for(report, "present-and-loadable") == "OK"
    assert _mark_for(report, "also-present") == "OK"
    assert _mark_for(report, "absent-entirely") == "MISS"


def test_the_summary_counts_what_is_available_and_names_what_is_not() -> None:
    report = readiness_report(_MIXED)
    assert "2/3 available" in report
    assert "missing: absent-entirely" in report
    assert "present-and-loadable" not in report.splitlines()[-1]


def test_a_report_with_nothing_missing_says_so_without_an_empty_list() -> None:
    """The control for the summary: an all-available run must not print a dangling "missing:"."""
    report = readiness_report((_status("only-one", available=True),))
    assert "1/1 available" in report
    assert "missing:" not in report


def test_a_report_with_nothing_available_does_not_read_as_ready() -> None:
    """The other control. A renderer that always prints OK passes every all-available test.

    Both directions have to be pinned on the same function, because the defect measured was
    exactly an inversion — every OK became MISS and every MISS became OK, with the suite green.
    """
    report = readiness_report((_status("nothing-here", available=False),))
    assert _mark_for(report, "nothing-here") == "MISS"
    assert "0/1 available" in report
    assert "missing: nothing-here" in report


def test_the_size_of_a_downloaded_checkpoint_reaches_the_line() -> None:
    report = readiness_report(_MIXED)
    line = next(row for row in report.splitlines() if "present-and-loadable" in row)
    assert "(2.0 GB)" in line


def test_a_measured_size_of_zero_is_reported_rather_than_omitted() -> None:
    """`if status.size_bytes` treated a measured zero as unmeasured.

    A checkpoint directory holding only empty files is non-empty, so it reports as present with a
    size of 0 — and a falsy check rendered no size at all, which reads as "this component has no
    weights to measure", the same line a pip component gets. Measured zero and unmeasured are
    different facts; this repo's rule is that the second is `None`.
    """
    report = readiness_report((_status("empty-files-only", available=True, size_bytes=0),))
    line = next(row for row in report.splitlines() if "empty-files-only" in row)
    assert "(0.0 GB)" in line, f"a measured zero was omitted: {line!r}"


# --- D-175: the licence gate that runs before a single byte moves ---------------------------


def _fetcher_planning_block() -> str:
    """The planning block out of `fetch-models.sh`, as executable source.

    Same reasoning as `_fetcher_download_block`: the tests below execute the real block rather
    than grepping it, because an assertion about the text of a check is not an assertion that
    the check runs (D-067).
    """
    script = (ROOT / "scripts" / "fetch-models.sh").read_text(encoding="utf-8")
    blocks = [b for b in script.split("<<'PYEOF'")[1:] if "missing_weights" in b]
    assert len(blocks) == 1, f"expected exactly one planning block, found {len(blocks)}"
    return blocks[0].split("\nPYEOF")[0]


def _run_planning_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, entries: tuple[ModelEntry, ...]
) -> None:
    """Execute the real planning block with `missing_weights` offering `entries`."""
    import sys as _sys

    import hawedit.models

    # `hawedit.models.ModelStore`, not the name this module bound at import time: other
    # tests here `importlib.reload` the module, so the class object imported at the top is
    # not always the one the executed block will import. Patching the stale one left the
    # block reading the real §7 table and the refusal never fired — measured, and the
    # reason this looks the class up dynamically.
    monkeypatch.setattr(hawedit.models.ModelStore, "missing_weights", lambda _self: entries)
    monkeypatch.setattr(_sys, "argv", ["fetch", str(tmp_path)])
    source_code = _fetcher_planning_block()
    exec(compile(source_code, "fetch-models.sh:PYEOF", "exec"), {"__name__": "__main__"})


def _an_entry(licence: Licence) -> ModelEntry:
    return ModelEntry(
        model_id="a-checkpoint",
        component="fabricated for this test",
        blueprint_model_cell="",
        licence=licence,
        provisioning=Provisioning.WEIGHTS,
        hf_repo="org/repo",
    )


def test_the_fetcher_refuses_a_noncommercial_checkpoint_before_downloading_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`assert_commercially_usable` sits in the planning block, "checked before a single byte
    moves" — and deleting that line left the whole suite green.

    It cannot fire on the committed tree: `missing_weights` reads §7's production table and
    D-168's `test_no_registered_model_is_non_commercial` forbids an NC entry there. That makes
    it defence in depth rather than dead code — the registry docstring says the check "keys off
    the licence, not off those two names, so the next NC dependency fails the same way" — and
    defence in depth still has to be shown to work. The state is unconstructible in the tree and
    perfectly constructible here. D-175.
    """
    with pytest.raises(NonCommercialLicence, match="commercial use"):
        _run_planning_block(tmp_path, monkeypatch, (_an_entry(CC_BY_NC_4_0),))


def test_the_fetcher_plans_a_commercially_usable_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The control. Without it the test above passes for a block that refuses *everything* —
    including a licence §7 permits — and the gate would look present while blocking the fetch
    of every model this system is allowed to run.
    """
    (tmp_path / "sources.json").write_text(
        json.dumps({"a-checkpoint": "org/repo"}), encoding="utf-8"
    )
    _run_planning_block(tmp_path, monkeypatch, (_an_entry(APACHE_2_0),))
    planned = capsys.readouterr().out
    assert "a-checkpoint\torg/repo" in planned, (
        f"the commercial checkpoint was not planned: {planned!r}"
    )
    assert "UNCONFIGURED" not in planned, planned

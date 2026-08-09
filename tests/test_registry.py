"""M0.2 — the model registry must be §7 of the blueprint, not a copy of it that drifts.

Gate rule: "Nothing in the model registry that isn't in §7". A hand-written list satisfies
that on the day it is written and silently stops satisfying it later. These tests parse §7
out of the frozen `BLUEPRINT.md` and require an exact correspondence with the code, so
adding a model without amending the blueprint fails the gate.
"""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path

import pytest

from hawedit.registry import (
    EXCLUDED,
    REGISTRY,
    ModelExcluded,
    ModelNotInRegistry,
    NonCommercialLicence,
    assert_commercially_usable,
    attribution_notices,
    resolve,
)

BLUEPRINT = Path(__file__).resolve().parents[1] / "BLUEPRINT.md"


def _clean(cell: str) -> str:
    """Strip markdown emphasis/backticks from a table cell, keeping the text verbatim."""
    return re.sub(r"[`*]", "", cell).strip()


def _section_7() -> str:
    text = BLUEPRINT.read_text(encoding="utf-8")
    start = text.index("## 7. Model registry")
    end = text.index("## 8. Evaluation harness")
    return text[start:end]


def _table_rows(block: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in block.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [_clean(c) for c in line.strip("|").split("|")]
        if not cells or set("".join(cells)) <= {"-", " ", ":"}:
            continue  # separator row
        rows.append(cells)
    return rows


def blueprint_registry_cells() -> set[str]:
    """The Model column of §7's registry table."""
    block = _section_7().split("**Excluded, with reasons:**")[0]
    rows = _table_rows(block)
    assert rows[0][0] == "Component", f"unexpected §7 header: {rows[0]}"
    return {r[1] for r in rows[1:]}


def blueprint_excluded_cells() -> set[str]:
    block = _section_7().split("**Excluded, with reasons:**")[1]
    rows = _table_rows(block)
    assert rows[0][0] == "Excluded", f"unexpected §7 exclusion header: {rows[0]}"
    return {r[0] for r in rows[1:]}


# --- the registry is exactly §7 -------------------------------------------------------


def test_blueprint_section_7_is_parseable() -> None:
    """Guard the guard: if §7's shape changes, these tests must fail loudly, not vacuously."""
    assert len(blueprint_registry_cells()) == 15
    assert len(blueprint_excluded_cells()) == 9


def test_registry_contains_nothing_that_is_not_in_section_7() -> None:
    extra = {e.blueprint_model_cell for e in REGISTRY.values()} - blueprint_registry_cells()
    assert not extra, f"models in code but not in BLUEPRINT §7: {sorted(extra)}"


def test_registry_omits_nothing_that_is_in_section_7() -> None:
    missing = blueprint_registry_cells() - {e.blueprint_model_cell for e in REGISTRY.values()}
    assert not missing, f"models in BLUEPRINT §7 but not in code: {sorted(missing)}"


def test_exclusions_match_section_7_exactly() -> None:
    coded = {e.blueprint_model_cell for e in EXCLUDED.values()}
    assert coded == blueprint_excluded_cells()


def test_every_exclusion_records_the_blueprint_reason() -> None:
    for entry in EXCLUDED.values():
        assert entry.reason.strip(), f"{entry.model_id} excluded without a reason"


# --- licence policy: NC is a hard reject ----------------------------------------------


def test_no_registered_model_is_non_commercial() -> None:
    for entry in REGISTRY.values():
        assert entry.licence.commercial_use, f"{entry.model_id} is NC — must not be registered"


def test_non_commercial_licence_is_hard_rejected() -> None:
    """§4.2 and §7 exclude two models specifically for CC-BY-NC-4.0. The check is on the
    licence, not on a name blacklist — a new NC dependency must fail the same way."""
    for model_id in ("mms-300m-1130-forced-aligner", "RevgeAI/vekol-stt-ckb-small"):
        entry = EXCLUDED[model_id]
        assert not entry.licence.commercial_use
        with pytest.raises(NonCommercialLicence):
            assert_commercially_usable(entry)


def test_resolving_an_excluded_model_raises_with_the_reason() -> None:
    with pytest.raises(ModelExcluded) as exc:
        resolve("RevgeAI/vekol-stt-ckb-small")
    assert "NC" in str(exc.value) or "NonCommercial" in str(exc.value)


def test_resolving_an_unknown_model_raises() -> None:
    with pytest.raises(ModelNotInRegistry):
        resolve("openai/whisper-large-v3")


def test_excluded_is_a_subclass_of_not_in_registry() -> None:
    """Callers that guard with `except ModelNotInRegistry` must also catch exclusions."""
    assert issubclass(ModelExcluded, ModelNotInRegistry)


# --- the specific §7 pins the blueprint calls out -------------------------------------


def test_canonical_asr_is_the_llm_7b() -> None:
    entry = resolve("omniASR_LLM_7B_v2")
    assert entry.role == "canonical_asr"
    assert entry.licence.name == "Apache-2.0"


def test_alignment_emissions_come_from_the_ctc_model() -> None:
    assert resolve("omniASR_CTC_3B_v2").role == "asr_emissions"


def test_judge_is_pinned_and_shadow_is_not_routable() -> None:
    """§4: SHADOW is 'evaluated, not routed'. Routing to it must be impossible by accident."""
    assert resolve("gemini-2.5-pro").routable
    assert not resolve("gemini-3.1-pro").routable


def test_gated_repos_are_flagged() -> None:
    """§3 Stage 0: Community-1 is gated on Hugging Face — deployment must know."""
    assert resolve("pyannote/speaker-diarization-community-1").gated


def test_attribution_notices_cover_every_attribution_licence() -> None:
    """CC-BY-4.0 (Community-1) and CC-BY-SA-4.0 (KLPT) both require shipped attribution."""
    notices = attribution_notices()
    assert any("community-1" in n.lower() for n in notices)
    assert any("klpt" in n.lower() for n in notices)
    for entry in REGISTRY.values():
        if entry.licence.attribution_required:
            assert any(entry.model_id.lower() in n.lower() for n in notices), (
                f"{entry.model_id} requires attribution but has no notice"
            )


# --- benchmark controls are measurement-only, never production ------------------------


def test_the_diarization_control_is_not_in_the_production_registry() -> None:
    """§7's table lists Community-1 only. §3 Stage 0 and §8.1 still require 3.1 as a
    control, so it lives outside the registry rather than being appended to it (D-011)."""
    from hawedit.registry import BENCHMARK_CONTROLS

    assert "pyannote/speaker-diarization-3.1" in BENCHMARK_CONTROLS
    assert "pyannote/speaker-diarization-3.1" not in REGISTRY


def test_a_benchmark_control_cannot_be_resolved_for_production_use() -> None:
    with pytest.raises(ModelNotInRegistry):
        resolve("pyannote/speaker-diarization-3.1")


def test_benchmark_controls_are_not_routable() -> None:
    from hawedit.registry import BENCHMARK_CONTROLS

    for entry in BENCHMARK_CONTROLS.values():
        assert not entry.routable


# --- §7 must not both register and exclude a model ---------------------------------------
#
# `resolve` reads REGISTRY before EXCLUDED, so a model in both resolves *in favour of the
# excluded one*. Measured 2026-08-09: adding `Whisper` (§7 excludes it — "OmniASR is stronger
# for ckb") to `_ENTRIES` with a blueprint cell §7 already contains, no role, and a licence
# requiring no attribution made `resolve("Whisper")` return the entry with no `ModelExcluded`
# raised, and the full suite stayed at `exit=0, 0 FAILED`. The set-equality tests compare the
# cells each table self-declares, so a duplicate cell is invisible and nothing related the two
# tables to each other. Two of §7's nine exclusions are CC-BY-NC-4.0 hard rejects. D-082.


def test_the_real_tables_do_not_both_register_and_exclude_anything() -> None:
    """Asserted on the shipped data, not a fixture — importing already enforces it."""
    assert set(REGISTRY) & set(EXCLUDED) == set()


def test_a_model_in_both_tables_is_refused() -> None:
    from hawedit.registry import (
        RegistryContradiction,
        assert_registry_excludes_nothing_it_registers,
    )

    entry = REGISTRY["KLPT"]
    excluded = EXCLUDED["Whisper"]
    with pytest.raises(RegistryContradiction, match="both registers and excludes"):
        assert_registry_excludes_nothing_it_registers({"Whisper": entry}, {"Whisper": excluded})


def test_disjoint_tables_are_accepted() -> None:
    """The control. A guard that raised unconditionally passes the test above."""
    from hawedit.registry import assert_registry_excludes_nothing_it_registers

    assert_registry_excludes_nothing_it_registers(
        {"KLPT": REGISTRY["KLPT"]}, {"Whisper": EXCLUDED["Whisper"]}
    )


def test_an_excluded_model_is_still_refused_by_resolve() -> None:
    """The behaviour the contradiction would have silently reversed."""
    with pytest.raises(ModelExcluded, match="excluded by BLUEPRINT"):
        resolve("Whisper")
    with pytest.raises(ModelExcluded):
        resolve("mms-300m-1130-forced-aligner")


def test_two_entries_cannot_claim_one_blueprint_cell() -> None:
    """The other half of the same hole: set-equality cannot see a duplicated cell.

    `test_registry_matches_section_7_exactly` compares the *set* of cells the registry declares
    against §7's. A second entry claiming a cell §7 already has leaves that set unchanged, so it
    is invisible — which is how the rogue `Whisper` entry hid. §7 names one model per cell.
    """
    from hawedit.registry import (
        RegistryContradiction,
        assert_registry_excludes_nothing_it_registers,
    )

    klpt = REGISTRY["KLPT"]
    impostor = replace(klpt, model_id="NotKLPT")
    with pytest.raises(RegistryContradiction, match="claimed by more than one"):
        assert_registry_excludes_nothing_it_registers({"KLPT": klpt, "NotKLPT": impostor}, {})


def test_every_real_registry_entry_claims_its_own_cell() -> None:
    """Asserted on the shipped data: 15 entries, 15 distinct §7 cells."""
    cells = [entry.blueprint_model_cell for entry in REGISTRY.values()]
    assert len(cells) == len(set(cells)), "two entries claim one §7 cell"

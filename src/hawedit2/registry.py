"""§7 model registry — the allowlist of every model this system may run.

Two rules from the operating gates are enforced here rather than remembered:

* **Nothing in the registry that isn't in §7.** Each entry carries the verbatim §7 "Model"
  cell it came from, and `tests/test_registry.py` parses §7 out of the frozen
  `BLUEPRINT.md` and requires an exact set correspondence. Adding a model without amending
  the blueprint fails the gate.
* **NonCommercial is a hard reject.** §4.2 and §7 exclude `mms-300m-1130-forced-aligner`
  and `RevgeAI/vekol-stt-ckb-small` on CC-BY-NC-4.0 grounds. `assert_commercially_usable`
  keys off the licence, not off those two names, so the next NC dependency fails the same
  way.

**On licence provenance.** The `Licence.name` strings mirror §7's Licence column, which the
blueprint itself flags as "vendor- or author-reported and not independently replicated". A
licence is only restated here in a more precise form once it has been read from the shipped
package metadata and recorded in `DECISIONS.md` — so far that is KLPT (D-002: the wheel
metadata says CC BY-SA 4.0, which is narrower than §7's "open"). Models excluded for
non-licence reasons are marked `NOT_ASSESSED`, which is default-deny: we have not cleared
them for commercial use, and saying so is not the same as claiming they are restricted.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

__all__ = [
    "EXCLUDED",
    "REGISTRY",
    "ExcludedEntry",
    "Licence",
    "ModelEntry",
    "ModelExcluded",
    "ModelNotInRegistry",
    "NonCommercialLicence",
    "assert_commercially_usable",
    "attribution_notices",
    "resolve",
]


@dataclass(frozen=True, slots=True)
class Licence:
    """A licence as it bears on shipping this system commercially."""

    name: str
    commercial_use: bool
    attribution_required: bool = False
    share_alike: bool = False


APACHE_2_0: Final = Licence("Apache-2.0", commercial_use=True)
MIT: Final = Licence("MIT", commercial_use=True)
CC_BY_4_0: Final = Licence("CC-BY-4.0", commercial_use=True, attribution_required=True)
CC_BY_SA_4_0: Final = Licence(
    "CC-BY-SA-4.0", commercial_use=True, attribution_required=True, share_alike=True
)
CC_BY_NC_4_0: Final = Licence("CC-BY-NC-4.0", commercial_use=False)
COMMERCIAL: Final = Licence("commercial", commercial_use=True)
OPEN_PER_SECTION_7: Final = Licence("open (§7, not independently verified)", commercial_use=True)
LGPL_GPL: Final = Licence("LGPL/GPL", commercial_use=True, attribution_required=True)
IN_HOUSE: Final = Licence("in-house", commercial_use=True)
NOT_ASSESSED: Final = Licence("not assessed (excluded for a non-licence reason)", False)


@dataclass(frozen=True, slots=True)
class ModelEntry:
    """A model §7 permits, with the blueprint cell it is accountable to."""

    model_id: str
    component: str
    blueprint_model_cell: str
    licence: Licence
    role: str = ""
    routable: bool = True
    gated: bool = False
    notes: str = ""


@dataclass(frozen=True, slots=True)
class ExcludedEntry:
    """A model §7 names and refuses, with the blueprint's stated reason."""

    model_id: str
    blueprint_model_cell: str
    licence: Licence
    reason: str


class ModelNotInRegistry(LookupError):
    """Raised for any model the blueprint does not permit."""


class ModelExcluded(ModelNotInRegistry):
    """Raised for a model §7 explicitly excludes. Subclass so one `except` catches both."""


class NonCommercialLicence(ValueError):
    """Raised when a NonCommercial licence reaches a decision point. Hard reject."""


def _registry() -> Mapping[str, ModelEntry]:
    entries = (
        ModelEntry(
            model_id="PySceneDetect",
            component="Scene detection",
            blueprint_model_cell="PySceneDetect",
            licence=OPEN_PER_SECTION_7,
            role="shot_detection",
            notes="§3 Stage 0: ContentDetector, threshold ~27, tuned per content type.",
        ),
        ModelEntry(
            model_id="Silero VAD",
            component="VAD",
            blueprint_model_cell="Silero VAD",
            licence=MIT,
            role="vad",
            notes="§3 Stage 0: max_speech_duration_s=38, margin under OmniASR's 40 s ceiling.",
        ),
        ModelEntry(
            model_id="pyannote/speaker-diarization-community-1",
            component="Diarization",
            blueprint_model_cell="pyannote/speaker-diarization-community-1",
            licence=CC_BY_4_0,
            role="diarization",
            gated=True,
            notes=(
                "§3 Stage 0: exclusive speaker diarization, chosen for reconciliation with "
                "transcript timestamps. Gated on Hugging Face — acceptance is a deploy step. "
                "speaker-diarization-3.1 (MIT) is kept as the §8.1 benchmark control."
            ),
        ),
        ModelEntry(
            model_id="omniASR_LLM_7B_v2",
            component="Canonical ASR",
            blueprint_model_cell="omniASR_LLM_7B_v2",
            licence=APACHE_2_0,
            role="canonical_asr",
            notes=(
                "§3 Stage 1: GPU 0, ~17 GiB. Canonical Sorani transcript. ckb_Arab CER 6.0 is "
                "Meta's only published Central Kurdish figure — provisional pending §8.1."
            ),
        ),
        ModelEntry(
            model_id="omniASR_CTC_3B_v2",
            component="ASR confidence + emissions",
            blueprint_model_cell="omniASR_CTC_3B_v2",
            licence=APACHE_2_0,
            role="asr_emissions",
            notes=(
                "§3 Stage 1: GPU 1, ~8 GiB. The LLM decoder gives no frame-level posteriors; "
                "these emissions are what forced alignment consumes (§4.2)."
            ),
        ),
        ModelEntry(
            model_id="rzgar/qwen3-asr-sorani-kurdish-ckb-v1",
            component="ASR validator",
            blueprint_model_cell="rzgar/qwen3-asr-sorani-kurdish-ckb-v1",
            licence=APACHE_2_0,
            role="asr_validator",
            notes=(
                "§3 Stage 1: ~4 GiB. Escalation target for the bottom log-prob quartile and "
                "material LLM/CTC disagreement. Never escalate on duration or word count."
            ),
        ),
        ModelEntry(
            model_id="Custom Viterbi on CTC emissions",
            component="Forced alignment",
            blueprint_model_cell="Custom Viterbi on CTC emissions",
            licence=IN_HOUSE,
            role="forced_alignment",
            notes="§4.2: an engineering module with its own tests, not a library call.",
        ),
        ModelEntry(
            model_id="KLPT",
            component="Normalization",
            blueprint_model_cell="KLPT",
            licence=CC_BY_SA_4_0,
            role="normalization",
            notes=(
                "§4.1. §7 records 'open'; the shipped wheel metadata says CC BY-SA 4.0 — "
                "narrower, and verified in DECISIONS.md D-002. Attribution required; "
                "share-alike attaches only if we adapt its rule tables."
            ),
        ),
        ModelEntry(
            model_id="Qwen3-VL-Embedding-2B",
            component="Visual embedding",
            blueprint_model_cell="Qwen3-VL-Embedding-2B",
            licence=APACHE_2_0,
            role="visual_embedding",
            notes="§3 Stage 2: one embedding per scene, ~1 fps, max 64 frames.",
        ),
        ModelEntry(
            model_id="Qwen3-VL-Reranker-2B",
            component="Reranking",
            blueprint_model_cell="Qwen3-VL-Reranker-2B",
            licence=APACHE_2_0,
            role="visual_rerank",
            notes="§3 Stage 2: top 50 retrieved, reranked to top 5–10.",
        ),
        ModelEntry(
            model_id="MCG-NJU/VideoChat3-4B",
            component="Local video understanding",
            blueprint_model_cell="MCG-NJU/VideoChat3-4B",
            licence=APACHE_2_0,
            role="visual_discovery",
            notes=(
                "§3 Stage 3 Path B. Provisional, not proven superior — replacement must stay "
                "a config change. Segmentation mandatory: ~17.7 GB at 256 frames."
            ),
        ),
        ModelEntry(
            model_id="MCG-NJU/TimeLens2-4B",
            component="Visual temporal evidence",
            blueprint_model_cell="MCG-NJU/TimeLens2-4B",
            licence=APACHE_2_0,
            role="temporal_evidence",
            notes=(
                "§3 Stage 5: returns intervals containing visual evidence, NOT editorial "
                "cuts. One input among five to boundary fusion."
            ),
        ),
        ModelEntry(
            model_id="gemini-2.5-pro",
            component="Kurdish judge (both stages)",
            blueprint_model_cell="gemini-2.5-pro, pinned",
            licence=COMMERCIAL,
            role="kurdish_editorial_judge",
            routable=True,
            notes=(
                "§4: pinned on tested Sorani evidence. All cloud calls route through the "
                "KURDISH_EDITORIAL_JUDGE interface so a provider swap is config, not refactor."
            ),
        ),
        ModelEntry(
            model_id="gemini-3.1-pro",
            component="Judge shadow",
            blueprint_model_cell="gemini-3.1-pro",
            licence=COMMERCIAL,
            role="judge_shadow",
            routable=False,
            notes=(
                "§4: 'evaluated, not routed'. Switch only when it beats 2.5 Pro on the Sorani "
                "regression set — newer is not automatically better on Kurdish."
            ),
        ),
        ModelEntry(
            model_id="ASS + libass/HarfBuzz/FriBidi",
            component="Captions",
            blueprint_model_cell="ASS + libass/HarfBuzz/FriBidi",
            licence=LGPL_GPL,
            role="captions",
            notes=(
                "§4.3: shaping=complex explicitly, libass built with HarfBuzz verified at "
                "deploy, golden-file render test in CI."
            ),
        ),
    )
    return MappingProxyType({e.model_id: e for e in entries})


def _excluded() -> Mapping[str, ExcludedEntry]:
    entries = (
        ExcludedEntry(
            model_id="CLIP",
            blueprint_model_cell="CLIP as primary retrieval",
            licence=NOT_ASSESSED,
            reason="Frame-averaging loses temporal structure — 0.325 vs 0.75+ NDCG@10",
        ),
        ExcludedEntry(
            model_id="Whisper",
            blueprint_model_cell="Whisper",
            licence=NOT_ASSESSED,
            reason="OmniASR is stronger for ckb",
        ),
        ExcludedEntry(
            model_id="Qwen3.6-35B-A3B",
            blueprint_model_cell="Qwen3.6-35B-A3B",
            licence=NOT_ASSESSED,
            reason="GPTQ-Int4 checkpoint is 24.4 GB of weights — no margin on a 24 GB card",
        ),
        ExcludedEntry(
            model_id="mms-300m-1130-forced-aligner",
            blueprint_model_cell="mms-300m-1130-forced-aligner",
            licence=CC_BY_NC_4_0,
            reason="CC-BY-NC-4.0 (NonCommercial — hard reject)",
        ),
        ExcludedEntry(
            model_id="RevgeAI/vekol-stt-ckb-small",
            blueprint_model_cell="RevgeAI/vekol-stt-ckb-small",
            licence=CC_BY_NC_4_0,
            reason="CC-BY-NC-4.0 (NonCommercial — hard reject)",
        ),
        ExcludedEntry(
            model_id="Leum-VL-8B",
            blueprint_model_cell="Leum-VL-8B (the model)",
            licence=NOT_ASSESSED,
            reason=(
                "39 downloads/mo, unchanged since March 2026. The SV6D schema is kept; "
                "the weights are not"
            ),
        ),
        ExcludedEntry(
            model_id="Seed2.1 Pro",
            blueprint_model_cell="Seed2.1 Pro (in v1)",
            licence=NOT_ASSESSED,
            reason=(
                "Best published video scores anywhere but zero Sorani evidence; do not add a "
                "second cloud dependency on benchmarks alone — benchmark in §8.2 first"
            ),
        ),
        ExcludedEntry(
            model_id="Gemini YouTube-URL input",
            blueprint_model_cell="Gemini YouTube-URL input",
            licence=NOT_ASSESSED,
            reason="No audio track means no OmniASR pass. Triage only, never a pipeline input",
        ),
        ExcludedEntry(
            model_id="OmniASR Unlimited (as default)",
            blueprint_model_cell="OmniASR Unlimited as default",
            licence=NOT_ASSESSED,
            reason=("VAD already yields sub-40 s units; internal N=15, M=1 segmentation remains"),
        ),
    )
    return MappingProxyType({e.model_id: e for e in entries})


REGISTRY: Final[Mapping[str, ModelEntry]] = _registry()
EXCLUDED: Final[Mapping[str, ExcludedEntry]] = _excluded()


def resolve(model_id: str) -> ModelEntry:
    """Return the §7 entry for `model_id`, or refuse.

    Raises:
        ModelExcluded: `model_id` is named in §7's exclusion table.
        ModelNotInRegistry: `model_id` is not in §7 at all.
    """
    entry = REGISTRY.get(model_id)
    if entry is not None:
        return entry
    excluded = EXCLUDED.get(model_id)
    if excluded is not None:
        raise ModelExcluded(f"{model_id!r} is excluded by BLUEPRINT §7: {excluded.reason}")
    raise ModelNotInRegistry(
        f"{model_id!r} is not in BLUEPRINT §7. Models are added to the blueprint first — "
        f"the architecture is frozen, and §8 measurement on real Kurdish data is what "
        f"justifies a swap, not a leaderboard."
    )


def assert_commercially_usable(entry: ModelEntry | ExcludedEntry) -> None:
    """Hard-reject a NonCommercial licence at the point of use.

    Raises:
        NonCommercialLicence: the entry's licence forbids commercial use.
    """
    if not entry.licence.commercial_use:
        raise NonCommercialLicence(
            f"{entry.model_id!r} is licensed {entry.licence.name}, which does not permit "
            f"commercial use. NonCommercial is a hard reject — this system ships to clients."
        )


def attribution_notices() -> list[str]:
    """Attribution text every shipped build must carry.

    §7 and §10 make this an obligation, not a courtesy: Community-1 is CC-BY-4.0 and KLPT
    is CC-BY-SA-4.0 (D-002). Both require credit in shipped product docs.
    """
    notices: list[str] = []
    for entry in REGISTRY.values():
        if not entry.licence.attribution_required:
            continue
        note = f"{entry.model_id} — {entry.component}, licensed {entry.licence.name}"
        if entry.licence.share_alike:
            note += " (share-alike applies to any adaptation of this work)"
        notices.append(note)
    return notices

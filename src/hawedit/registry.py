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
from enum import Enum
from types import MappingProxyType
from typing import Final

__all__ = [
    "ASR_ROLES",
    "BENCHMARK_CONTROLS",
    "EXCLUDED",
    "REGISTRY",
    "SHIPPED_ASSETS",
    "ExcludedEntry",
    "Licence",
    "ModelEntry",
    "ModelExcluded",
    "ModelNotInRegistry",
    "NonCommercialLicence",
    "Provisioning",
    "ShippedAsset",
    "WrongRole",
    "assert_commercially_usable",
    "attribution_notices",
    "resolve",
    "resolve_role",
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
OFL_1_1: Final = Licence("OFL-1.1", commercial_use=True, attribution_required=True)
IN_HOUSE: Final = Licence("in-house", commercial_use=True)
NOT_ASSESSED: Final = Licence("not assessed (excluded for a non-licence reason)", False)


class Provisioning(Enum):
    """How a §7 component actually arrives on a machine.

    Knowing this per component is what turns "is the app ready to run?" from a guess into a
    check: only `WEIGHTS` entries need the multi-gigabyte download, and only those can be
    missing in a way that stops a stage.
    """

    PIP = "pip"  # arrives with a package (model bundled, package-managed, or none needed)
    WEIGHTS = "weights"  # multi-GB checkpoint that must be downloaded
    CLOUD = "cloud"  # an API; nothing local but credentials
    SYSTEM = "system"  # a system binary or library
    IN_HOUSE = "in_house"  # our own code


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
    provisioning: Provisioning = Provisioning.WEIGHTS
    # The Hugging Face repo id, when §7 states it unambiguously. `None` means the source
    # must be configured rather than guessed — see models.py and D-022.
    hf_repo: str | None = None


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


_ENTRIES: Final = (
    ModelEntry(
        model_id="PySceneDetect",
        component="Scene detection",
        provisioning=Provisioning.PIP,
        blueprint_model_cell="PySceneDetect",
        licence=OPEN_PER_SECTION_7,
        role="shot_detection",
        notes="§3 Stage 0: ContentDetector, threshold ~27, tuned per content type.",
    ),
    ModelEntry(
        model_id="Silero VAD",
        component="VAD",
        provisioning=Provisioning.PIP,
        blueprint_model_cell="Silero VAD",
        licence=MIT,
        role="vad",
        notes="§3 Stage 0: max_speech_duration_s=38, margin under OmniASR's 40 s ceiling.",
    ),
    ModelEntry(
        model_id="pyannote/speaker-diarization-community-1",
        component="Diarization",
        provisioning=Provisioning.WEIGHTS,
        hf_repo="pyannote/speaker-diarization-community-1",
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
        provisioning=Provisioning.PIP,
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
        provisioning=Provisioning.PIP,
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
        provisioning=Provisioning.WEIGHTS,
        hf_repo="rzgar/qwen3-asr-sorani-kurdish-ckb-v1",
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
        provisioning=Provisioning.IN_HOUSE,
        blueprint_model_cell="Custom Viterbi on CTC emissions",
        licence=IN_HOUSE,
        role="forced_alignment",
        notes="§4.2: an engineering module with its own tests, not a library call.",
    ),
    ModelEntry(
        model_id="KLPT",
        component="Normalization",
        provisioning=Provisioning.PIP,
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
        provisioning=Provisioning.WEIGHTS,
        blueprint_model_cell="Qwen3-VL-Embedding-2B",
        licence=APACHE_2_0,
        role="visual_embedding",
        notes="§3 Stage 2: one embedding per scene, ~1 fps, max 64 frames.",
    ),
    ModelEntry(
        model_id="Qwen3-VL-Reranker-2B",
        component="Reranking",
        provisioning=Provisioning.WEIGHTS,
        blueprint_model_cell="Qwen3-VL-Reranker-2B",
        licence=APACHE_2_0,
        role="visual_rerank",
        notes="§3 Stage 2: top 50 retrieved, reranked to top 5–10.",
    ),
    ModelEntry(
        model_id="MCG-NJU/VideoChat3-4B",
        component="Local video understanding",
        provisioning=Provisioning.WEIGHTS,
        hf_repo="MCG-NJU/VideoChat3-4B",
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
        provisioning=Provisioning.WEIGHTS,
        hf_repo="MCG-NJU/TimeLens2-4B",
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
        provisioning=Provisioning.CLOUD,
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
        provisioning=Provisioning.CLOUD,
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
        provisioning=Provisioning.SYSTEM,
        blueprint_model_cell="ASS + libass/HarfBuzz/FriBidi",
        licence=LGPL_GPL,
        role="captions",
        notes=(
            "§4.3: shaping=complex explicitly, libass built with HarfBuzz verified at "
            "deploy, golden-file render test in CI."
        ),
    ),
)

_EXCLUDED_ENTRIES: Final = (
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

REGISTRY: Final[Mapping[str, ModelEntry]] = MappingProxyType({e.model_id: e for e in _ENTRIES})
EXCLUDED: Final[Mapping[str, ExcludedEntry]] = MappingProxyType(
    {e.model_id: e for e in _EXCLUDED_ENTRIES}
)

# Benchmark controls: models the blueprint requires for *measurement* but deliberately keeps
# out of §7's production table. §3 Stage 0 — "Keep speaker-diarization-3.1 (MIT) as a
# benchmark control" — and §8.1 — "pyannote Community-1 vs 3.1 on Kurdish multi-speaker
# material". §7's table lists only Community-1, and that table is authoritative for what
# ships, so the control lives here instead of being quietly appended to the registry. It is
# not routable: `resolve` does not find it, and nothing in the pipeline can select it.
# See DECISIONS.md D-011.
BENCHMARK_CONTROLS: Final[Mapping[str, ModelEntry]] = MappingProxyType(
    {
        "pyannote/speaker-diarization-3.1": ModelEntry(
            model_id="pyannote/speaker-diarization-3.1",
            component="Diarization benchmark control",
            blueprint_model_cell="",  # deliberately absent from §7's table
            licence=MIT,
            role="diarization_control",
            routable=False,
            notes=(
                "§3 Stage 0 keeps it as a control; §8.1 benchmarks Community-1 against it. "
                "Measurement only — never a production diarizer."
            ),
        )
    }
)


ASR_ROLES: Final = frozenset({"canonical_asr", "asr_emissions", "asr_validator"})


class WrongRole(ValueError):
    """Raised when a §7 model is used for a component it is not the model for."""


def resolve_role(model_id: str, allowed: frozenset[str], purpose: str) -> ModelEntry:
    """Resolve `model_id` and require it to fill one of `allowed` roles.

    Membership in §7 says a model may be *used by this system*, not that it may be used
    *here*. Without this, PySceneDetect passed as an ASR adapter and as the editorial judge —
    every call site checked only that the name was in the registry. Audit finding #8.

    Raises:
        ModelNotInRegistry / ModelExcluded: as `resolve`.
        WrongRole: the model is in §7 but is not that kind of component.
    """
    entry = resolve(model_id)
    if entry.role not in allowed:
        raise WrongRole(
            f"{model_id!r} is §7's {entry.component!r} (role {entry.role!r}) and cannot be "
            f"used as {purpose}. Being in the registry means the blueprint permits the "
            f"model, not that it fits this slot."
        )
    return entry


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


@dataclass(frozen=True, slots=True)
class ShippedAsset:
    """A non-model artifact that ships with the product and carries a licence obligation.

    Deliberately **not** in `REGISTRY`. §7 is the model registry and the rule is that nothing
    is in it that is not in §7 — a font is not a model and putting it there to get an
    attribution notice would corrupt the one table the blueprint fixes. §10's obligation is
    about shipped product docs, which is a wider set than §7's models, so it gets its own.
    """

    name: str
    role: str
    licence: Licence
    licence_file: str | None = None


SHIPPED_ASSETS: Final[tuple[ShippedAsset, ...]] = (
    ShippedAsset(
        name="Noto Naskh Arabic (The Noto Project Authors)",
        role="Captions font",
        licence=OFL_1_1,
        # OFL-1.1 requires the licence to accompany the font. Shipping the .ttf without it is
        # a licence violation in every build, and `tests/test_claims.py` asserts the file.
        licence_file="assets/fonts/OFL.txt",
    ),
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
    for asset in SHIPPED_ASSETS:
        if not asset.licence.attribution_required:
            continue
        note = f"{asset.name} — {asset.role}, licensed {asset.licence.name}"
        if asset.licence_file:
            note += f" (the licence must accompany it: {asset.licence_file})"
        notices.append(note)
    return notices

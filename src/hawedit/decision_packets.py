"""Deterministic, evidence-bound packets for HawEdit's unresolved owner decisions.

The packet makes recommendations and proves which reviewed facts they were based on.  It never
selects an option: every owner field remains JSON ``null`` and every rendered page says UNSET.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Final

from hawedit.atomic_fs import rename_directory_noreplace
from hawedit.cli import machine_readable_stdout, program_name, use_utf8_streams

__all__ = [
    "DECISION_IDS",
    "DecisionPacketError",
    "PreparedDecisionPackets",
    "main",
    "prepare_decision_packets",
]

DECISION_IDS: Final = (9, 13, 14, 15, 18, 21)
_SCHEMA: Final = 1
_MAX_AUTHORITY_BYTES: Final = 8 * 1024 * 1024
_BLUEPRINT_SHA256: Final = "b7e05d219be4e527e7d5cb779692272d16d4e42bf3d255400273ebc1123ec9ee"
_BLOCKER_SECTION_SHA256: Final = {
    9: "caf8c7a37cf6b7ff46d0893627efca497c39919988928fc84059578326151891",
    13: "2bbd13ab17d6a0f9c77a2344579848baf2ad6c1472d851fd4935949014e5428c",
    14: "6982da735298915fbb15dbb1bc9139bbb7e1ef80d060f42d5c0a03cfc931963d",
    15: "acf54b5ef8b241cb7e11fa971be08cf506e0973f33e29c1af80cdb7614c470db",
    18: "b9c4871be91e898c0da5a4195c311d2ba8a37c5891a21bc802f7bbebe031308c",
    21: "7d19f51971fdd2c7a53e609be5a199694470730397f1731fee605a9cc15ff30b",
}
_EVIDENCE_SHA256: Final = {
    "evidence/adversarial-pass-19-2026-08-10.md": (
        "a3443258698130feed24de5335926165963066d68aa1abc61835bcd1ffc8a9b8"
    ),
    "evidence/adversarial-pass-2026-08-09.md": (
        "043107f2bca1a26b81ec36679802197335369cd0ef6bf592565505b24f326791"
    ),
    "evidence/the-champion-adapter-would-have-shipped-the-base-models-words.md": (
        "455371520f8afd6fad54911efca324b256e25991b8b8fb30f58c0fa3e21ce284"
    ),
    "evidence/timelens-relevance-unbounded.md": (
        "d83365c3e0d446fa6637d72dc90a52e0498d09bdc6144cc932c153024580fa66"
    ),
    "evidence/unlisted-modules.md": (
        "6d52a5b4738f6a50848fb51a85adf274b346440a748751101924f47907bba26c"
    ),
    "evidence/vad-pause-segmentation-dead.md": (
        "91324b882040bd61f7a37efdb33442c3c6016381a693371353c03055a15e8380"
    ),
}


class DecisionPacketError(ValueError):
    """The packet authority drifted or publication would overwrite another operator."""


@dataclass(frozen=True, slots=True)
class _Option:
    option_id: str
    label: str
    consequences: str
    requires: str


@dataclass(frozen=True, slots=True)
class _Definition:
    blocker_id: int
    governing_refs: tuple[str, ...]
    evidence_paths: tuple[str, ...]
    current_behavior: str
    question: str
    options: tuple[_Option, ...]
    recommended_option: str
    recommendation_basis: str


_DEFINITIONS: Final = (
    _Definition(
        blocker_id=9,
        governing_refs=("BLUEPRINT §3 Stage 6", "BLUEPRINT §7", "BLUEPRINT §9 M8"),
        evidence_paths=("evidence/unlisted-modules.md",),
        current_behavior=(
            "Face-aware reframing exists and honestly falls back, but no real speaker footage has "
            "shown that face-centred cropping is insufficient; SAM 3 and Molmo2 have no §7 rows."
        ),
        question=(
            "Should SAM 3/Molmo2 enter §7 now, remain deferred until real crop failure, or be "
            "explicitly excluded from the production plan?"
        ),
        options=(
            _Option(
                "defer_until_measured",
                "Defer both models until face-centred cropping fails real footage",
                "Preserves §3's conditional gate and avoids new weight/licence exposure; M8 "
                "remains "
                "truthfully blocked.",
                "Authorised real multi-speaker footage and a measured crop-quality review.",
            ),
            _Option(
                "add_registry_rows_after_measurement",
                "Add only the model proved necessary after measurement",
                "Expands §7 and the deployment/supply-chain surface, but only for a demonstrated "
                "product need.",
                "A BLUEPRINT amendment plus commercial licence and exact checkpoint provenance.",
            ),
            _Option(
                "exclude_optional_models",
                "Close M8 with face/speaker tracking and exclude SAM 3/Molmo2",
                "Keeps the stack smaller but accepts that difficult occlusion or non-face scenes "
                "may "
                "remain static-centred.",
                "An explicit product-scope ADR and representative crop review.",
            ),
        ),
        recommended_option="defer_until_measured",
        recommendation_basis=(
            "The frozen Stage 6 text makes SAM 3 conditional, and there is currently zero real "
            "evidence that the condition is true."
        ),
    ),
    _Definition(
        blocker_id=13,
        governing_refs=("BLUEPRINT §4.1", "DECISIONS D-076"),
        evidence_paths=("evidence/adversarial-pass-2026-08-09.md",),
        current_behavior=(
            "The Arabic-script Sorani normalizer leaves Latin `ř` and `ł` unchanged and does not "
            "claim the fifth collision complete."
        ),
        question=(
            "Is Latin-script Kurdish in this ckb_Arab pipeline's scope, and if so what non-lossy "
            "target form is authoritative for `ř/ł`?"
        ),
        options=(
            _Option(
                "exclude_latin_from_ckb_arab",
                "Explicitly exclude Latin-script Kurdish from this pipeline",
                "Closes the false completeness claim without destroying phonemic distinctions; a "
                "future Latin pipeline remains possible.",
                "A scope ADR and BLUEPRINT clarification.",
            ),
            _Option(
                "preserve_phonemic_letters",
                "Accept Latin material while preserving `ř/ł` byte-for-byte",
                "Avoids lossy folding, but requires Latin-script tokenization, fonts and benchmark "
                "coverage beyond the current RTL product.",
                "Representative authorised Latin Kurdish and explicit output-script requirements.",
            ),
            _Option(
                "define_corpus_measured_mapping",
                "Define a target mapping from labelled bilingual evidence",
                "May enable cross-script search, but any mapping is deferred until real data "
                "proves "
                "it does not erase meaning.",
                "A licensed corpus, linguist review and exact reversible/irreversible mapping ADR.",
            ),
        ),
        recommended_option="exclude_latin_from_ckb_arab",
        recommendation_basis=(
            "Canonical ASR is ckb_Arab and folding distinct phonemes to ASCII would be "
            "irreversible; "
            "scope exclusion is safer than invented normalization."
        ),
    ),
    _Definition(
        blocker_id=14,
        governing_refs=("BLUEPRINT §4.2", "BLUEPRINT §5", "DECISIONS D-081"),
        evidence_paths=("evidence/vad-pause-segmentation-dead.md",),
        current_behavior=(
            "Punctuation and word-gap segmentation work; the VAD-pause branch is provably inert "
            "and "
            "is pinned as a known partial implementation."
        ),
        question=(
            "When VAD silence and CTC word timing disagree, must silence merely overlap the word "
            "gap, span the complete boundary, or remain disabled until labelled evaluation?"
        ),
        options=(
            _Option(
                "boundary_point_containment",
                "Require VAD silence to span the complete inter-word boundary",
                "Conservative: reduces false sentence breaks but may miss alignment tails that "
                "partially cover genuine silence.",
                "A code change plus labelled boundary precision/recall evaluation.",
            ),
            _Option(
                "any_overlap",
                "Split when qualifying VAD silence overlaps the boundary at all",
                "Recovers more stretched-alignment cases but a one-millisecond contact can "
                "over-split "
                "sentences and change every downstream anchor.",
                "A code change and stronger labelled false-split evidence.",
            ),
            _Option(
                "defer_vad_split",
                "Keep VAD segmentation disabled and state punctuation/word-gap scope",
                "Avoids guessed boundaries but leaves §4.2 partial and forfeits VAD evidence "
                "already "
                "computed by Stage 0.",
                "A product-scope ADR; no algorithmic threshold is claimed.",
            ),
        ),
        recommended_option="boundary_point_containment",
        recommendation_basis=(
            "It is the least permissive rule that makes the dead VAD branch real, so it minimizes "
            "misleading over-segmentation until labelled Sorani boundary data can compare it."
        ),
    ),
    _Definition(
        blocker_id=15,
        governing_refs=("BLUEPRINT §3 Stage 5", "BLUEPRINT §8.2", "DECISIONS D-085"),
        evidence_paths=("evidence/timelens-relevance-unbounded.md",),
        current_behavior=(
            "Any positive TimeLens overlap may extend final_out; one millisecond can therefore "
            "turn "
            "a short sentence into minutes of untranscribed footage."
        ),
        question=(
            "Should TimeLens remain evidence-only until measured, or what overlap/extension rule "
            "makes an interval relevant enough to change delivery?"
        ),
        options=(
            _Option(
                "evidence_only_until_measured",
                "Report TimeLens evidence but do not let it extend delivery",
                "Prevents unbounded misleading clips now, at the cost of a temporary documented "
                "divergence from Stage 5's final_out formula.",
                "An ADR plus labelled footage before enabling extension.",
            ),
            _Option(
                "minimum_anchor_overlap",
                "Require a measured minimum fraction of anchor overlap",
                "Rejects tiny contacts but can miss a genuine reaction beginning at the sentence "
                "end.",
                "A labelled threshold study and recorded protected-metric tolerance.",
            ),
            _Option(
                "maximum_extension",
                "Cap TimeLens extension by an absolute window",
                "Predictable and simple, but can neuter long semantic payoffs and guesses a "
                "duration.",
                "A measured millisecond cap and BLUEPRINT/ADR update.",
            ),
            _Option(
                "relative_duration_cap",
                "Cap the final clip relative to anchor duration",
                "Scales across speech lengths but still requires a multiplier and may bias long "
                "speech.",
                "A labelled multiplier study and misleading-edit comparison.",
            ),
        ),
        recommended_option="evidence_only_until_measured",
        recommendation_basis=(
            "Misleading output is the protected error class and no defensible threshold exists; "
            "disabling extension is safer than shipping the measured one-millisecond failure."
        ),
    ),
    _Definition(
        blocker_id=18,
        governing_refs=("BLUEPRINT §2", "BLUEPRINT §3 Path A", "BLUEPRINT §9 M2"),
        evidence_paths=("evidence/adversarial-pass-19-2026-08-10.md",),
        current_behavior=(
            "The runner builds a correct sentence index but Path A sends the full normalized "
            "transcript to Gemini and no production component calls Bm25Index.search."
        ),
        question=(
            "Who supplies the BM25 query, and may its hits filter Path A context despite §3's "
            "full-transcript instruction?"
        ),
        options=(
            _Option(
                "full_transcript_path_a_bm25_brief",
                "Keep full-transcript Path A; use BM25 only for explicit brief/operator queries",
                "Preserves §3 recall and gives the index a real consumer without silently changing "
                "Gemini context.",
                "An explicit brief/search interface and separate recall/cost measurement.",
            ),
            _Option(
                "bm25_filter_path_a",
                "Filter Gemini context to BM25 sentence hits",
                "Reduces cost and context length but can lower Path A recall or remove narrative "
                "setup.",
                "A query producer plus labelled Recall@20 and misleading-edit non-regression.",
            ),
            _Option(
                "remove_bm25_from_m2",
                "Remove BM25 from the Path A vertical-slice claim",
                "Makes the current architecture honest, but §2 search becomes a separate/unowned "
                "feature rather than discovery infrastructure.",
                "A BLUEPRINT roadmap amendment and updated milestone evidence.",
            ),
        ),
        recommended_option="full_transcript_path_a_bm25_brief",
        recommendation_basis=(
            "It obeys §3's explicit full-transcript instruction and avoids inventing a query while "
            "still preserving the tested index for a concrete user-provided retrieval intent."
        ),
    ),
    _Definition(
        blocker_id=21,
        governing_refs=("BLUEPRINT §7", "DECISIONS D-181"),
        evidence_paths=(
            "evidence/the-champion-adapter-would-have-shipped-the-base-models-words.md",
        ),
        current_behavior=(
            "The local LoRA can run and is digest-attributed in every transcript, but it is "
            "omitted "
            "from §7/readiness because no owner licence has been asserted."
        ),
        question=(
            "Under what terms may the owner-trained champion adapter be used, redistributed and "
            "listed in the production registry?"
        ),
        options=(
            _Option(
                "internal_only_pending_licence",
                "Keep the adapter internal-only until rights and terms are signed",
                "Allows measured private use without implying redistribution rights; registry and "
                "public release remain blocked.",
                "An owner rights statement and training-data/licence review.",
            ),
            _Option(
                "apache_2_0_owner_asserted",
                "Owner licenses the adapter under Apache-2.0",
                "Aligns with the base model and permits commercial redistribution, but only if the "
                "owner actually controls all adapter/training rights.",
                "A signed owner licence grant and required NOTICE/source documentation.",
            ),
            _Option(
                "do_not_use_adapter",
                "Exclude the adapter from production and releases",
                "Eliminates the unresolved licence surface but gives up its measured Sorani "
                "changes.",
                "An ADR and removal from production runbooks; stock OmniASR remains canonical.",
            ),
        ),
        recommended_option="internal_only_pending_licence",
        recommendation_basis=(
            "Licence terms are a human legal assertion. Internal-only refusal preserves provenance "
            "without fabricating redistribution rights."
        ),
    ),
)


def _canonical_json(document: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _is_reparse(info: os.stat_result) -> bool:
    flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(getattr(info, "st_file_attributes", 0) & flag)


def _identity(info: os.stat_result) -> tuple[int, int, int, int, int]:
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_nlink)


def _read_stable(path: Path, label: str) -> bytes:
    try:
        before_path = os.lstat(path)
    except OSError as exc:
        raise DecisionPacketError(f"cannot inspect {label} {path}: {exc}") from exc
    if stat.S_ISLNK(before_path.st_mode) or _is_reparse(before_path):
        raise DecisionPacketError(f"{label} must not be a symlink or reparse point: {path}")
    if not stat.S_ISREG(before_path.st_mode):
        raise DecisionPacketError(f"{label} must be a regular file: {path}")
    if before_path.st_nlink != 1:
        raise DecisionPacketError(f"{label} must not be a hardlink: {path}")
    if before_path.st_size > _MAX_AUTHORITY_BYTES:
        raise DecisionPacketError(f"{label} exceeds {_MAX_AUTHORITY_BYTES} bytes: {path}")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise DecisionPacketError(f"cannot open {label} {path}: {exc}") from exc
    try:
        before_fd = os.fstat(descriptor)
        if _identity(before_fd) != _identity(before_path):
            raise DecisionPacketError(f"{label} changed while opening: {path}")
        chunks: list[bytes] = []
        total = 0
        while chunk := os.read(descriptor, 1024 * 1024):
            total += len(chunk)
            if total > _MAX_AUTHORITY_BYTES:
                raise DecisionPacketError(f"{label} exceeded its byte limit while reading")
            chunks.append(chunk)
        after_fd = os.fstat(descriptor)
        if _identity(after_fd) != _identity(before_fd) or (
            after_fd.st_ctime_ns != before_fd.st_ctime_ns
        ):
            raise DecisionPacketError(f"{label} changed while reading: {path}")
    finally:
        os.close(descriptor)
    try:
        after_path = os.lstat(path)
    except OSError as exc:
        raise DecisionPacketError(f"cannot re-inspect {label} {path}: {exc}") from exc
    if _identity(after_path) != _identity(before_path) or (
        after_path.st_ctime_ns != before_path.st_ctime_ns
    ):
        raise DecisionPacketError(f"{label} path changed while reading: {path}")
    return b"".join(chunks)


def _project_file(root: Path, relative: str, label: str) -> Path:
    posix = PurePosixPath(relative)
    if (
        posix.is_absolute()
        or not posix.parts
        or any(part in {"", ".", ".."} or ":" in part for part in posix.parts)
    ):
        raise DecisionPacketError(f"invalid reviewed {label} path {relative!r}")
    current = root
    for index, part in enumerate(posix.parts):
        current /= part
        try:
            info = os.lstat(current)
        except OSError as exc:
            raise DecisionPacketError(f"cannot inspect reviewed {label} {current}: {exc}") from exc
        if stat.S_ISLNK(info.st_mode) or _is_reparse(info):
            raise DecisionPacketError(f"reviewed {label} path contains a link: {current}")
        if index < len(posix.parts) - 1 and not stat.S_ISDIR(info.st_mode):
            raise DecisionPacketError(f"reviewed {label} parent is not a directory: {current}")
    return current


def _root(path: Path) -> Path:
    absolute = Path(os.path.abspath(path))
    try:
        info = os.lstat(absolute)
    except OSError as exc:
        raise DecisionPacketError(f"cannot inspect project root {absolute}: {exc}") from exc
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or _is_reparse(info):
        raise DecisionPacketError(f"project root must be one real directory: {absolute}")
    return absolute


def _extract_blocker_section(blocked_text: str, blocker_id: int) -> tuple[str, str]:
    match = re.search(
        rf"(?ms)^## #{blocker_id} ·.*?(?=^---\s*$|\Z)",
        blocked_text,
    )
    if match is None:
        raise DecisionPacketError(f"BLOCKED.md has no unique section for #{blocker_id}")
    section = match.group(0).rstrip()
    title = section.splitlines()[0].split(" · ", 1)[1]
    return title, section


def _option_document(option: _Option) -> dict[str, str]:
    return {
        "consequences": option.consequences,
        "id": option.option_id,
        "label": option.label,
        "requires": option.requires,
    }


def _page(packet: Mapping[str, Any]) -> bytes:
    lines = [
        f"# Decision #{packet['blocker_id']} — {packet['title']}",
        "",
        "OWNER DECISION: **UNSET**",
        "",
        "## Content bindings",
        "",
        f"- Frozen blueprint SHA-256: `{packet['blueprint_sha256']}`",
        f"- BLOCKED section SHA-256: `{packet['blocker_section_sha256']}`",
    ]
    for evidence in packet["evidence"]:
        lines.append(f"- `{evidence['path']}`: `{evidence['sha256']}`")
    lines.extend(
        [
            "",
            "## Governing references",
            "",
            *[f"- {reference}" for reference in packet["governing_refs"]],
            "",
            "## Current behavior",
            "",
            str(packet["current_behavior"]),
            "",
            "## Question",
            "",
            str(packet["question"]),
            "",
            "## Options",
            "",
        ]
    )
    for option in packet["options"]:
        lines.extend(
            [
                f"### `{option['id']}` — {option['label']}",
                "",
                f"Consequences: {option['consequences']}",
                "",
                f"Requires: {option['requires']}",
                "",
            ]
        )
    lines.extend(
        [
            "## Engineering recommendation — not an owner decision",
            "",
            f"Recommended: `{packet['recommended_option']}`",
            "",
            str(packet["recommendation_basis"]),
            "",
            "Fill the separate owner template with exactly one listed option. A recommendation, "
            "generated page, fixture or green test is not approval.",
            "",
        ]
    )
    return "\n".join(lines).encode("utf-8")


def _write_private(path: Path, payload: bytes) -> None:
    try:
        with path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as exc:
        raise DecisionPacketError(f"cannot stage decision packet file {path}: {exc}") from exc


def _publish(output_dir: Path, payloads: Mapping[str, bytes]) -> Path:
    destination = Path(os.path.abspath(output_dir))
    parent = destination.parent
    try:
        parent_info = os.lstat(parent)
    except OSError as exc:
        raise DecisionPacketError(f"cannot inspect decision packet parent {parent}: {exc}") from exc
    if (
        not stat.S_ISDIR(parent_info.st_mode)
        or stat.S_ISLNK(parent_info.st_mode)
        or _is_reparse(parent_info)
    ):
        raise DecisionPacketError(f"decision packet parent must be one real directory: {parent}")
    parent_identity = (parent_info.st_dev, parent_info.st_ino)
    if os.path.lexists(destination):
        raise DecisionPacketError(f"decision packet output already exists at {destination}")
    try:
        staging = Path(
            tempfile.mkdtemp(prefix=f".{destination.name}.", suffix=".staging", dir=parent)
        )
    except OSError as exc:
        raise DecisionPacketError(f"cannot create decision packet staging under {parent}") from exc
    try:
        for name in sorted(payloads):
            _write_private(staging / name, payloads[name])
        current_parent = os.lstat(parent)
        if (current_parent.st_dev, current_parent.st_ino) != parent_identity:
            raise DecisionPacketError("decision packet output parent identity changed")
        if {path.name for path in staging.iterdir()} != set(payloads):
            raise DecisionPacketError("decision packet staging file set changed")
        rename_directory_noreplace(staging, destination)
    except BaseException as primary:
        if os.path.lexists(staging):
            try:
                shutil.rmtree(staging)
            except OSError as cleanup:
                primary.add_note(f"decision packet staging cleanup also failed: {cleanup}")
        if isinstance(primary, FileExistsError):
            raise DecisionPacketError(
                f"decision packet output already exists at {destination}"
            ) from primary
        if isinstance(primary, OSError):
            raise DecisionPacketError(f"cannot publish decision packet {destination}") from primary
        raise
    return destination


@dataclass(frozen=True, slots=True)
class PreparedDecisionPackets:
    directory: Path
    manifest_path: Path
    owner_template_path: Path


def prepare_decision_packets(project_root: Path, output_dir: Path) -> PreparedDecisionPackets:
    """Publish the six reviewed recommendation packets with every owner field unset."""
    root = _root(project_root)
    blueprint = _read_stable(_project_file(root, "BLUEPRINT.md", "blueprint"), "blueprint")
    blueprint_sha = hashlib.sha256(blueprint).hexdigest()
    if blueprint_sha != _BLUEPRINT_SHA256:
        raise DecisionPacketError(
            "reviewed blueprint digest changed; re-research every affected option before packaging"
        )
    blocked_payload = _read_stable(
        _project_file(root, "BLOCKED.md", "blocker ledger"), "blocker ledger"
    )
    try:
        blocked_text = blocked_payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DecisionPacketError("BLOCKED.md is not strict UTF-8") from exc

    packets: list[dict[str, Any]] = []
    for definition in _DEFINITIONS:
        title, section = _extract_blocker_section(blocked_text, definition.blocker_id)
        section_sha = hashlib.sha256(section.encode("utf-8")).hexdigest()
        if section_sha != _BLOCKER_SECTION_SHA256[definition.blocker_id]:
            raise DecisionPacketError(
                f"reviewed blocker section #{definition.blocker_id} changed; re-research its packet"
            )
        evidence: list[dict[str, str]] = []
        for relative in definition.evidence_paths:
            payload = _read_stable(
                _project_file(root, relative, f"evidence for #{definition.blocker_id}"),
                f"evidence for #{definition.blocker_id}",
            )
            measured_sha = hashlib.sha256(payload).hexdigest()
            if measured_sha != _EVIDENCE_SHA256[relative]:
                raise DecisionPacketError(
                    f"reviewed evidence digest changed for {relative}; re-research the packet"
                )
            evidence.append({"path": relative, "sha256": measured_sha})
        packet: dict[str, Any] = {
            "blocker_id": definition.blocker_id,
            "blocker_path": "BLOCKED.md",
            "blocker_section_sha256": section_sha,
            "blueprint_sha256": blueprint_sha,
            "current_behavior": definition.current_behavior,
            "evidence": evidence,
            "governing_refs": list(definition.governing_refs),
            "options": [_option_document(option) for option in definition.options],
            "question": definition.question,
            "recommendation_basis": definition.recommendation_basis,
            "recommended_option": definition.recommended_option,
            "title": title,
        }
        if definition.recommended_option not in {option.option_id for option in definition.options}:
            raise DecisionPacketError(
                f"packet #{definition.blocker_id} recommends an option it does not present"
            )
        packets.append(packet)

    manifest: dict[str, Any] = {
        "acceptance_boundary": (
            "recommendations and reviewed evidence bindings only; all owner decisions remain unset"
        ),
        "blueprint": {"path": "BLUEPRINT.md", "sha256": blueprint_sha},
        "packets": packets,
        "schema": _SCHEMA,
    }
    manifest_bytes = _canonical_json(manifest)
    template = {
        "decided_at_utc": None,
        "decided_by": None,
        "decisions": [
            {
                "allowed_options": [option["id"] for option in packet["options"]],
                "blocker_id": packet["blocker_id"],
                "rationale": None,
                "recommended_option": packet["recommended_option"],
                "selected_option": None,
            }
            for packet in packets
        ],
        "packet_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "schema": _SCHEMA,
    }
    payloads: dict[str, bytes] = {
        "INSTRUCTIONS.txt": (
            b"HAWEDIT OWNER DECISIONS - ALL UNSET\n\n"
            b"Read each decision page and its content hashes. Fill only option identifiers listed "
            b"in that page into owner-decisions.template.json, add the responsible owner, UTC "
            b"timestamp and rationale, then review the required ADR/BLUEPRINT/code consequences. "
            b"This packet makes recommendations; it grants no licence and approves nothing.\n"
        ),
        "decisions.json": manifest_bytes,
        "owner-decisions.template.json": _canonical_json(template),
    }
    for packet in packets:
        payloads[f"decision-{packet['blocker_id']:02d}.md"] = _page(packet)
    directory = _publish(output_dir, payloads)
    return PreparedDecisionPackets(
        directory=directory,
        manifest_path=directory / "decisions.json",
        owner_template_path=directory / "owner-decisions.template.json",
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Prepare the reviewed owner packet without making an owner decision."""
    use_utf8_streams()
    parser = argparse.ArgumentParser(
        prog=program_name("hawedit.decision_packets"),
        description="Prepare evidence-bound packets for HawEdit's six unresolved owner decisions",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare", help="publish a write-once packet with unset fields")
    prepare.add_argument("--project-root", type=Path, required=True)
    prepare.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        prepared = prepare_decision_packets(args.project_root, args.output_dir)
        with machine_readable_stdout() as report_stream:
            print(
                json.dumps(
                    {
                        "directory": str(prepared.directory),
                        "manifest": str(prepared.manifest_path),
                        "owner_template": str(prepared.owner_template_path),
                        "status": "prepared-all-owner-decisions-unset",
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                file=report_stream,
            )
    except (DecisionPacketError, OSError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

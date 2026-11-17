"""Private retained-media integrity, never review or publication authority."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from hawedit.candidate_publication import _inspect_media, _measurement_claims
from hawedit.candidate_review import (
    REVIEW_SUFFIXES,
    CandidateReviewError,
    _canonical,
    _json,
    _snapshot,
)
from hawedit.captions import find_ffmpeg
from hawedit.clip import Clip
from hawedit.delivery import DeliveryError
from hawedit.edit_plan import CURRENT_PLAN_VERSION, VisualEditPlan
from hawedit.measure import ClipMeasurement, MeasureError
from hawedit.studio_private import PrivateDirectory, StudioStorageError


class CandidateCacheError(RuntimeError):
    """Existing private media cannot be safely reported as a retained candidate."""


@dataclass(frozen=True, slots=True)
class RetainedReviewCandidate:
    """Stored editing metadata and fresh physical evidence, not approval."""

    clip: Clip
    edit_plan: VisualEditPlan
    measurement: ClipMeasurement


def inspect_existing_review_candidate(
    candidate_dir: Path, *, clip: Clip, ffmpeg: Path | None = None
) -> RetainedReviewCandidate:
    """Reopen all members and measure current bytes without repairing prior evidence.

    This checks media, source/clock identity and the expected render request. It does
    not grant signed approval or attest all native runtime dependencies. Publication
    must still independently consume raw review proof.
    """
    try:
        directory = PrivateDirectory(candidate_dir, create=False)
        bindings: dict[str, dict[str, object]] = {}
        documents: dict[str, bytes] = {}
        for suffix in REVIEW_SUFFIXES:
            name = f"{clip.clip_id}.{suffix}"
            binding, data = _snapshot(
                directory,
                name,
                limit=32 * 1024**3 if suffix == "mp4" else 4 * 1024 * 1024,
                capture=suffix in ("json", "measured.json", "edit_plan.json"),
            )
            bindings[suffix], documents[suffix] = binding, data

        stored_doc = _json(documents["json"])
        stored_clip = Clip.from_dict(stored_doc)
        if (
            clip.provenance is None
            or not clip.provenance.render_request_sha256
            or stored_clip.provenance is None
            or stored_clip.provenance.render_request_sha256 != clip.provenance.render_request_sha256
        ):
            raise CandidateCacheError("retained render request binding is missing or changed")
        plan_doc = _json(documents["edit_plan.json"])
        plan = VisualEditPlan.from_dict(plan_doc)
        measured_doc = _json(documents["measured.json"])
        if any(
            type(measured_doc.get(block)) is not dict
            for block in ("file", "video", "audio", "faces", "captions", "tool_metadata")
        ):
            raise CandidateCacheError("retained measurement blocks must be JSON objects")
        stored_measurement = ClipMeasurement.from_dict(measured_doc)
        if (
            _canonical(stored_doc) != _canonical(stored_clip.to_dict())
            or _canonical(plan_doc) != _canonical(plan.to_dict())
            or _canonical(measured_doc) != _canonical(stored_measurement.to_dict())
            or stored_measurement.schema != 1
        ):
            raise CandidateCacheError("retained packet has an unsupported typed schema")
        if (
            not clip.media_sha256
            or stored_clip.clip_id != clip.clip_id
            or stored_clip.media_id != clip.media_id
            or stored_clip.media_sha256 != clip.media_sha256
            or (stored_clip.in_ms, stored_clip.out_ms) != (clip.in_ms, clip.out_ms)
            or plan.version != CURRENT_PLAN_VERSION
            or plan.clip_id != clip.clip_id
            or plan.media_id != clip.media_id
            or plan.media_sha256 != clip.media_sha256
            or (plan.time_mapping.clip_in_ms, plan.time_mapping.clip_out_ms)
            != (clip.in_ms, clip.out_ms)
        ):
            raise CandidateCacheError("retained packet source, candidate or clock binding changed")
        stored_clip.assert_renderable(for_review=True)
        plan.config.assert_valid()
        if (
            stored_measurement.file.sha256 != bindings["mp4"]["sha256"]
            or stored_measurement.file.size_bytes != bindings["mp4"]["size_bytes"]
        ):
            raise CandidateCacheError("retained MP4 differs from its measured byte binding")
        binary = ffmpeg or find_ffmpeg()
        if binary is None:
            raise CandidateCacheError("FFmpeg is required to recheck retained media")
        fresh = _inspect_media(
            directory.path / f"{clip.clip_id}.mp4",
            directory.path / f"{clip.clip_id}.ass",
            binary,
        )
        if _measurement_claims(measured_doc) != _measurement_claims(fresh.to_dict()):
            raise CandidateCacheError("retained measurement differs from freshly decoded media")
        for suffix, before in bindings.items():
            after, _ = _snapshot(
                directory,
                f"{clip.clip_id}.{suffix}",
                limit=32 * 1024**3 if suffix == "mp4" else 4 * 1024 * 1024,
            )
            if after != before:
                raise CandidateCacheError("retained packet changed during inspection")
        directory.verify()
        return RetainedReviewCandidate(stored_clip, plan, fresh)
    except CandidateCacheError:
        raise
    except (
        OSError,
        StudioStorageError,
        CandidateReviewError,
        DeliveryError,
        MeasureError,
        subprocess.SubprocessError,
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        OverflowError,
        RecursionError,
    ) as exc:
        raise CandidateCacheError(
            "retained packet is missing, unsafe, malformed or unmeasurable"
        ) from exc

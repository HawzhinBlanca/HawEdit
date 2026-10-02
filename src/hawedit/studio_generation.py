"""Strict studio request preparation and truthful views of pipeline evidence.

Preparation performs no model work and grants no spending or publication authority.
The durable worker must revalidate runtime/model identities before executing the argv
through durable_workflow's existing shared build_parser/build_and_run path.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Protocol, cast

from hawedit.content_type import resolve_effective_configuration_from_args
from hawedit.events import RunEvent, RunState
from hawedit.measure import ClipMeasurement
from hawedit.pipeline import build_parser
from hawedit.studio_uploads import UploadError, UploadStore
from hawedit.transcripts import validate_media_id
from hawedit.wsl_setup import package_digest

__all__ = [
    "GenerationError",
    "GenerationRequest",
    "PreparedGeneration",
    "ProducerSelection",
    "prepare_generation",
    "project_events",
    "project_generation_result",
]

_SOURCE_ID = re.compile(r"[a-f0-9]{32}\Z")
_CLIENT_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{15,127}\Z")
_STRING_OPTIONS = {"preset", "caption_style", "content_type", "screener", "hook_text"}
_BOOL_OPTIONS = {"hook_banner", "silence_tightening", "keyword_emphasis"}


class GenerationError(ValueError):
    """Contextual request or evidence refusal; never an invented successful outcome."""


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise GenerationError(f"{label} must be an object with string fields")
    return value


def _option_argv(options: Mapping[str, object]) -> list[str]:
    unknown = set(options) - (_STRING_OPTIONS | _BOOL_OPTIONS | {"max_clips"})
    if unknown:
        raise GenerationError(f"Unsupported studio options: {', '.join(sorted(unknown))}")
    argv = [f"--preset={options.get('preset', 'viral')}", "--max-clips=3"]
    for key, value in options.items():
        if key in _STRING_OPTIONS:
            if (
                not isinstance(value, str)
                or not value.strip()
                or len(value) > 240
                or any(ord(char) < 32 for char in value)
            ):
                raise GenerationError(f"{key} must be nonempty text without control characters")
            if key != "preset":
                argv.append(f"--{key.replace('_', '-')}={value}")
        elif key in _BOOL_OPTIONS:
            if type(value) is not bool:
                raise GenerationError(f"{key} must be a boolean")
            if key == "silence_tightening":
                argv.extend(
                    [
                        f"--silence-threshold-ms={250 if value else 0}",
                        "--silence-target-gap-ms=100",
                        "--excise-fillers" if value else "--no-excise-fillers",
                    ]
                )
            else:
                argv.append(f"--{'' if value else 'no-'}{key.replace('_', '-')}")
        else:
            if type(value) is not int or value not in {1, 2, 3, 5}:
                raise GenerationError("max_clips must be one of 1, 2, 3 or 5")
            argv[1] = f"--max-clips={value}"
    return argv


class _ParserErrorPolicy(Protocol):
    exit_on_error: bool


def _parse(argv: Sequence[str]) -> argparse.Namespace:
    parser = build_parser()
    cast(_ParserErrorPolicy, parser).exit_on_error = False
    try:
        return parser.parse_args(list(argv))
    except argparse.ArgumentError as exc:
        raise GenerationError(f"Unsupported studio configuration: {exc}") from exc
    except SystemExit as exc:
        raise GenerationError("Unsupported studio configuration") from exc


@dataclass(frozen=True, slots=True)
class GenerationRequest:
    source_id: str
    client_token: str
    options: tuple[tuple[str, object], ...]

    @classmethod
    def from_payload(cls, payload: object) -> GenerationRequest:
        data = _object(payload, "Generation request")
        if set(data) != {"schema", "source_id", "client_token", "options"}:
            raise GenerationError(
                "Generation requires schema, source_id, client_token and options; "
                "server paths are refused. Upload supported video bytes first."
            )
        if type(data["schema"]) is not int or data["schema"] != 1:
            raise GenerationError("Unsupported generation schema; use schema 1")
        source_id = data["source_id"]
        token = data["client_token"]
        if not isinstance(source_id, str) or not _SOURCE_ID.fullmatch(source_id):
            raise GenerationError("Use a finalized source_id, not a filename or server path")
        if not isinstance(token, str) or not _CLIENT_TOKEN.fullmatch(token):
            raise GenerationError("client_token must be 16-128 ASCII identifier characters")
        options = _object(data["options"], "Studio options")
        _parse(["source.mp4", *_option_argv(options)])
        return cls(source_id, token, tuple(sorted(options.items())))

    def validate_source(self, uploads: UploadStore) -> tuple[Path, dict[str, Any]]:
        try:
            path = uploads.source(self.source_id)
            return path, uploads.describe(self.source_id)
        except UploadError as exc:
            raise GenerationError(str(exc)) from exc


@dataclass(frozen=True, slots=True)
class ProducerSelection:
    """Trusted server-side selection, not browser options or spending approval."""

    provider: str | None = None
    vertex_project: str | None = None
    omni_asr_runtime: str = "auto"
    wsl_distro: str | None = None

    def argv(self) -> list[str]:
        if self.provider not in ("gemini", "vertex"):
            raise GenerationError("Configure an owner-authorized discovery/judge provider")
        if self.provider == "vertex" and not self.vertex_project:
            raise GenerationError("Vertex requires a configured project")
        if self.provider == "gemini" and self.vertex_project is not None:
            raise GenerationError("A Vertex project cannot silently use the Gemini route")
        argv = [
            "--profile=production",
            "--auto-select",
            "--omni-asr",
            f"--omni-asr-runtime={self.omni_asr_runtime}",
            "--diarize",
            "--visual",
            "--timelens",
        ]
        argv.append(
            "--gemini" if self.provider == "gemini" else f"--vertex-project={self.vertex_project}"
        )
        if self.wsl_distro is not None:
            argv.append(f"--wsl-distro={self.wsl_distro}")
        return argv


@dataclass(frozen=True, slots=True)
class PreparedGeneration:
    source_id: str
    source_sha256: str
    client_token: str
    argv: tuple[str, ...]
    configuration_json: str
    content_sha256: str

    @property
    def effective_configuration(self) -> dict[str, Any]:
        configuration = _object(json.loads(self.configuration_json), "Generation configuration")
        return _object(configuration["editorial"], "Effective configuration")


def prepare_generation(
    request: GenerationRequest,
    uploads: UploadStore,
    work_dir: Path,
    producers: ProducerSelection,
) -> PreparedGeneration:
    source_path, source = request.validate_source(uploads)
    argv = [
        str(source_path),
        f"--work-dir={work_dir.resolve()}",
        f"--media-id=src-{request.source_id}",
        *_option_argv(dict(request.options)),
        *producers.argv(),
    ]
    args = _parse(argv)
    effective = asdict(resolve_effective_configuration_from_args(args))
    effective.pop("provenance")
    effective = {
        key: value.value if isinstance(value, Enum) else value for key, value in effective.items()
    }
    configuration = {
        "editorial": effective,
        "max_clips": args.max_clips,
        "hook_text": args.hook_text,
        "screener": args.screener,
        "producers": asdict(producers),
        "pipeline_source_sha256": package_digest(),
    }
    configuration_json = json.dumps(configuration, sort_keys=True, separators=(",", ":"))
    identity = json.dumps(
        {
            "source_id": request.source_id,
            "source_sha256": source["sha256"],
            "configuration": configuration,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return PreparedGeneration(
        request.source_id,
        source["sha256"],
        request.client_token,
        tuple(argv),
        configuration_json,
        hashlib.sha256(identity.encode("utf-8")).hexdigest(),
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _candidate_view(
    root: Path, clip_id: object, media_path: Path, metadata: Mapping[str, Any]
) -> dict[str, Any]:
    view: dict[str, Any] = {
        "clip_id": clip_id,
        "headline": metadata.get("title_ckb"),
        "hook_score": None,
        "duration_s": None,
        "sha256": None,
        "artifact_path": None,
        "state": "failed",
        "error": None,
    }
    try:
        if not isinstance(clip_id, str):
            raise GenerationError("Candidate lacks a clip ID")
        validate_media_id(clip_id)
        media = media_path.resolve()
        measurement_path = media.with_name(f"{clip_id}.measured.json").resolve()
        if not media.is_relative_to(root) or not measurement_path.is_relative_to(root):
            raise GenerationError("Candidate artifact is outside its job")
        with measurement_path.open("rb") as stream:
            data = stream.read(2 * 1024**2 + 1)
        if len(data) > 2 * 1024**2:
            raise GenerationError("Candidate measurement exceeds the record limit")
        measurement = ClipMeasurement.from_json(data.decode("utf-8"))
        if (
            media.stat().st_size != measurement.file.size_bytes
            or _sha256(media) != measurement.file.sha256
        ):
            raise GenerationError("Candidate bytes do not match their measurement")
        if type(measurement.video.duration_ms) is not int or measurement.video.duration_ms <= 0:
            raise GenerationError("Candidate duration is not a valid measurement")
        score = metadata.get("hook_score")
        if (
            isinstance(score, int | float)
            and not isinstance(score, bool)
            and math.isfinite(score)
            and 0 <= score <= 1
        ):
            view["hook_score"] = score
        view.update(
            state="awaiting-review",
            duration_s=measurement.video.duration_ms / 1000,
            sha256=measurement.file.sha256,
            artifact_path=media.relative_to(root).as_posix(),
        )
    except (OSError, ValueError, TypeError, KeyError, OverflowError) as exc:
        view["error"] = f"Candidate evidence refused: {exc}"
    return view


def project_generation_result(report: Mapping[str, Any], work_dir: Path) -> dict[str, Any]:
    """Project review evidence only; a pipeline report cannot authenticate publication."""
    root = work_dir.resolve()
    clips: list[dict[str, Any]] = []
    outcomes: list[dict[str, Any]] = []
    manifest = report.get("episode_manifest")
    if isinstance(manifest, dict):
        items = manifest.get("items", [])
        summaries = manifest.get("clips", [])
        if not isinstance(items, list) or not isinstance(summaries, list):
            raise GenerationError("Episode outcomes and clips must be lists")
        outcomes = [_object(item, "Candidate outcome").copy() for item in items]
        for raw in summaries:
            summary = _object(raw, "Candidate summary")
            clip_id = summary.get("clip_id")
            directory = summary.get("delivery_dir")
            if not isinstance(directory, str):
                raise GenerationError("Candidate summary lacks a scoped delivery directory")
            media = root / directory / f"{clip_id}.mp4"
            clips.append(_candidate_view(root, clip_id, media, summary))
    elif isinstance(report.get("render"), dict) and report["render"].get("path"):
        clip = report.get("clip") or {}
        clip = _object(clip, "Clip report")
        metadata = _object(clip.get("output") or {}, "Clip output").copy()
        editorial = _object(clip.get("editorial") or {}, "Clip editorial verdict")
        metadata["hook_score"] = editorial.get("hook_score")
        path = report["render"]["path"]
        if not isinstance(path, str):
            raise GenerationError("Render path must be text")
        clips.append(_candidate_view(root, clip.get("clip_id"), Path(path), metadata))
    ready = sum(clip["state"] == "awaiting-review" for clip in clips)
    failed = any(item.get("status") == "failed" for item in outcomes) or ready < len(clips)
    return {
        "status": ("partially-completed" if failed else "awaiting-review") if ready else "failed",
        "clips": clips,
        "outcomes": outcomes,
        "publication_verified": False,
        "published_count": 0,
        "no_clip_outcome": not clips,
        "error": None if ready else "No reviewable candidates with verified artifact evidence",
    }


def project_events(events: Sequence[RunEvent], *, attempt: int) -> dict[str, Any]:
    if type(attempt) is not int or attempt < 1:
        raise GenerationError("Event attempt must be a positive integer")
    stages: dict[str, dict[str, Any]] = {}
    previous = 0
    run_id = None
    for event in events:
        if event.sequence <= previous or (run_id is not None and event.run_id != run_id):
            raise GenerationError("Event sequence or run identity is inconsistent")
        previous, run_id = event.sequence, event.run_id
        if event.state is not RunState.BILLED:
            stages[event.stage] = event.to_dict()
    return {
        "attempt": attempt,
        "events": [event.to_dict() for event in events],
        "stages": list(stages.values()),
        "stage_progress": {
            "finished": sum(
                stage["state"] in {"completed", "skipped"} for stage in stages.values()
            ),
            "observed": len(stages),
        },
        "work_progress": None,
    }

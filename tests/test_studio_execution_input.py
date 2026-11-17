"""Actual private upload/outbox rehydration; no model, billing or publication claim."""

from __future__ import annotations

import io
import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

from hawedit import studio_generation
from hawedit.pipeline import build_parser
from hawedit.studio_private import PrivateDirectory, StudioStorageError
from hawedit.studio_submissions import SubmissionStore
from hawedit.studio_uploads import UploadStore
from studio_test_storage import create_private_test_root

if TYPE_CHECKING:
    from hawedit.studio_execution import PreparedStudioExecution

MEDIA = Path(__file__).parent / "fixtures" / "kurdish-speech-3cuts.mp4"
BINDING = "b" * 64
WORKFLOW = "hawedit.studio.producer"


@pytest.fixture(name="tmp_path")
def _private_tmp_path(tmp_path: Path) -> Path:
    return create_private_test_root(tmp_path)


def _state(
    root: Path, options: dict[str, object] | None = None
) -> tuple[UploadStore, SubmissionStore, studio_generation.PreparedGeneration]:
    uploads = UploadStore(root / "uploads")
    data = MEDIA.read_bytes()
    ticket = uploads.begin("episode.mp4", len(data))
    source = uploads.receive(ticket["upload_id"], io.BytesIO(data), len(data))
    request = studio_generation.GenerationRequest.from_payload(
        {
            "schema": 1,
            "source_id": source["source_id"],
            "client_token": "execution-input-token-1",
            "options": options or {},
        }
    )
    prepared = studio_generation.prepare_generation(
        request, uploads, root / "disposable", studio_generation.ProducerSelection("gemini")
    )
    return uploads, SubmissionStore(root / "submissions.sqlite"), prepared


def _prepare(
    uploads: UploadStore, store: SubmissionStore, job_id: str, **changes: object
) -> PreparedStudioExecution:
    from hawedit import studio_execution

    return studio_execution.prepare_studio_execution(
        job_id,
        store,
        uploads,
        producers=cast(
            studio_generation.ProducerSelection,
            changes.get("producers", studio_generation.ProducerSelection("gemini")),
        ),
        execution_binding_sha256=cast(str, changes.get("execution_binding_sha256", BINDING)),
        workflow_name=cast(str, changes.get("workflow_name", WORKFLOW)),
    )


@pytest.mark.parametrize("preset", ["broadcast", "viral", "split"])
@pytest.mark.parametrize("max_clips", [1, 2, 3, 5])
def test_execution_input_preserves_shared_configuration(
    tmp_path: Path, preset: str, max_clips: int
) -> None:
    uploads, store, prepared = _state(
        tmp_path,
        {
            "preset": preset,
            "max_clips": max_clips,
            "caption_style": "rtl_word_highlight",
            "hook_banner": False,
            "keyword_emphasis": True,
            "silence_tightening": False,
            "hook_text": "--stock-decoder",
        },
    )
    job = store.reserve(prepared, BINDING, WORKFLOW)
    result = _prepare(uploads, store, job.job_id)
    args = build_parser().parse_args(result.argv)
    assert args.preset == preset and args.max_clips == max_clips
    assert args.hook_text == "--stock-decoder" and not args.stock_decoder
    assert args.omni_asr and args.diarize and args.visual and args.timelens
    assert args.profile == "production" and args.qc_record is None
    assert args.source == uploads.source(job.source_id)
    assert result.job_id == job.job_id
    assert result.source_sha256 == job.source_sha256
    assert result.configuration_json == job.configuration_json
    assert result.request_sha256 == job.request_sha256
    assert args.work_dir == store.work_dir(job.job_id)
    PrivateDirectory(args.work_dir, create=False).verify()
    assert "client_token" not in asdict(result)
    assert "publication_verified" not in asdict(result)
    assert store.get(job.job_id) == job
    assert not (tmp_path / "disposable").exists()


@pytest.mark.parametrize(
    "options",
    [{}, {"silence_tightening": True, "keyword_emphasis": False, "hook_banner": True}],
)
def test_execution_input_survives_store_reconstruction(
    tmp_path: Path, options: dict[str, object]
) -> None:
    uploads, store, prepared = _state(tmp_path, options)
    job = store.reserve(prepared, BINDING, WORKFLOW)
    store.confirm_dispatch(job.job_id)
    original = _prepare(uploads, store, job.job_id)
    reopened = _prepare(UploadStore(uploads.root), SubmissionStore(store.path), job.job_id)
    assert original == reopened
    assert store.get(job.job_id).dispatch_state == "confirmed"


@pytest.mark.parametrize(
    "argument",
    [
        "--stock-decoder",
        "--profile=preview",
        "--qc-record=foreign.json",
        "--no-visual",
        "--hook-text=changed",
        "--preset=broadcast",
        "--omni-asr-runtime=native",
        "--preset=viral",
        "--silence-threshold-ms=251",
        "--silence-target-gap-ms=99",
        "--excise-fillers",
        "--no-excise-fillers",
    ],
)
def test_execution_input_refuses_unbound_arguments(tmp_path: Path, argument: str) -> None:
    uploads, store, prepared = _state(tmp_path)
    changed = replace(prepared, argv=(*prepared.argv, argument))
    job = store.reserve(changed, BINDING, WORKFLOW)
    before = store.get(job.job_id)
    with pytest.raises(studio_generation.GenerationError):
        _prepare(uploads, store, job.job_id)
    assert store.get(job.job_id) == before
    assert not (tmp_path / "studio-artifacts").exists()
    assert uploads.source(job.source_id).read_bytes() == MEDIA.read_bytes()


@pytest.mark.parametrize("field", ["pipeline_source_sha256", "editorial", "producers"])
def test_execution_input_refuses_configuration_drift(tmp_path: Path, field: str) -> None:
    uploads, store, prepared = _state(tmp_path)
    config = json.loads(prepared.configuration_json)
    config[field] = "a" * 64 if field == "pipeline_source_sha256" else {}
    # A storage-consistent snapshot is descriptive, not execution authority.
    import hashlib

    identity = {
        "source_id": prepared.source_id,
        "source_sha256": prepared.source_sha256,
        "configuration": config,
    }
    request_hash = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    changed = replace(prepared, configuration_json=json.dumps(config), content_sha256=request_hash)
    job = store.reserve(changed, BINDING, WORKFLOW)
    with pytest.raises(studio_generation.GenerationError):
        _prepare(uploads, store, job.job_id)
    assert store.get(job.job_id) == job
    assert not (tmp_path / "studio-artifacts").exists()


def test_execution_input_refuses_changed_source(tmp_path: Path) -> None:
    uploads, store, prepared = _state(tmp_path)
    job = store.reserve(prepared, BINDING, WORKFLOW)
    source = uploads.source(job.source_id)
    source.write_bytes(b"changed-source")
    with pytest.raises(studio_generation.GenerationError, match="changed"):
        _prepare(uploads, store, job.job_id)
    assert source.read_bytes() == b"changed-source"
    assert store.get(job.job_id) == job
    assert not (tmp_path / "studio-artifacts").exists()


@pytest.mark.parametrize("change", ["source", "media_id"])
def test_execution_input_refuses_source_or_media_aliases(tmp_path: Path, change: str) -> None:
    uploads, store, prepared = _state(tmp_path)
    argv = list(prepared.argv)
    if change == "source":
        argv[0] = str(MEDIA.resolve())
    else:
        argv = ["--media-id=foreign-source" if a.startswith("--media-id=") else a for a in argv]
    job = store.reserve(replace(prepared, argv=tuple(argv)), BINDING, WORKFLOW)
    with pytest.raises(studio_generation.GenerationError):
        _prepare(uploads, store, job.job_id)
    assert store.get(job.job_id) == job
    assert not (tmp_path / "studio-artifacts").exists()


@pytest.mark.parametrize("provider", ["gemini", "vertex"])
def test_execution_input_preserves_host_route_and_remaining_options(
    tmp_path: Path, provider: str
) -> None:
    from hawedit.studio_execution import prepare_studio_execution

    uploads, store, original = _state(tmp_path)
    producers = studio_generation.ProducerSelection(
        provider,
        "local-configured-project" if provider == "vertex" else None,
        omni_asr_runtime="wsl",
        wsl_distro="Ubuntu",
    )
    request = studio_generation.GenerationRequest.from_payload(
        {
            "schema": 1,
            "source_id": original.source_id,
            "client_token": "execution-route-token",
            "options": {"content_type": "podcast", "screener": "jev"},
        }
    )
    prepared = studio_generation.prepare_generation(request, uploads, tmp_path / "old", producers)
    job = store.reserve(prepared, BINDING, WORKFLOW)
    result = prepare_studio_execution(
        job.job_id,
        store,
        uploads,
        producers=producers,
        execution_binding_sha256=BINDING,
        workflow_name=WORKFLOW,
    )
    args = build_parser().parse_args(result.argv)
    assert args.gemini is (provider == "gemini")
    assert args.vertex_project == producers.vertex_project
    assert args.screener == "jev" and args.content_type == "podcast"
    assert args.omni_asr_runtime == "wsl" and args.wsl_distro == "Ubuntu"
    assert result.configuration_json == job.configuration_json


@pytest.mark.parametrize(
    "change",
    [
        {"execution_binding_sha256": "c" * 64},
        {"workflow_name": "another.worker"},
        {"producers": studio_generation.ProducerSelection("vertex", "other-project")},
    ],
)
def test_execution_input_refuses_wrong_host_binding(
    tmp_path: Path, change: dict[str, object]
) -> None:
    uploads, store, prepared = _state(tmp_path)
    job = store.reserve(prepared, BINDING, WORKFLOW)
    with pytest.raises(studio_generation.GenerationError):
        _prepare(uploads, store, job.job_id, **change)
    assert store.get(job.job_id) == job
    assert not (tmp_path / "studio-artifacts").exists()


def test_execution_input_refuses_lost_outbox(tmp_path: Path) -> None:
    uploads, store, prepared = _state(tmp_path)
    job = store.reserve(prepared, BINDING, WORKFLOW)
    original = store.path.with_suffix(".preserved")
    store.path.rename(original)
    with pytest.raises(StudioStorageError):
        _prepare(uploads, store, job.job_id)
    assert original.exists() and not store.path.exists()
    assert not (tmp_path / "studio-artifacts").exists()


def test_execution_input_refuses_unsafe_work_directory(tmp_path: Path) -> None:
    uploads, store, prepared = _state(tmp_path)
    job = store.reserve(prepared, BINDING, WORKFLOW)
    foreign = tmp_path / "studio-artifacts"
    foreign.write_bytes(b"preserved foreign file")
    with pytest.raises(StudioStorageError):
        _prepare(uploads, store, job.job_id)
    assert foreign.read_bytes() == b"preserved foreign file"
    assert store.get(job.job_id) == job

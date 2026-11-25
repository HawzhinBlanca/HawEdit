"""Real private job configuration; no model, cloud, retention or authority claim."""

from __future__ import annotations

import io
import json
from dataclasses import asdict, fields, replace
from pathlib import Path
from typing import cast

import pytest

from hawedit.pipeline import build_parser
from hawedit.studio_execution import prepare_studio_execution
from hawedit.studio_generation import (
    GenerationError,
    GenerationRequest,
    ProducerSelection,
    prepare_generation,
)
from hawedit.studio_submissions import SubmissionStore
from hawedit.studio_uploads import UploadStore
from studio_test_storage import create_private_test_root

MEDIA = Path(__file__).parent / "fixtures" / "kurdish-speech-3cuts.mp4"
BINDING = "b" * 64
WORKFLOW = "hawedit.studio.producer"


@pytest.fixture(name="tmp_path")
def _private_tmp_path(tmp_path: Path) -> Path:
    return create_private_test_root(tmp_path)


def _selected() -> ProducerSelection:
    return ProducerSelection(
        "vertex",
        vertex_project="test-project",
        vertex_location="europe-west4",
        confidential=False,
        zero_data_retention=True,
        zdr_confirmed_by="test-operator",
    )


def test_trusted_governance_is_expressible() -> None:
    actual = {field.name for field in fields(ProducerSelection)}
    assert {"confidential", "zero_data_retention", "zdr_confirmed_by", "vertex_location"} <= actual


@pytest.mark.parametrize("confidential", [False, True])
def test_trusted_governance_reaches_shared_parser(confidential: bool) -> None:
    selected = replace(_selected(), confidential=confidential)
    args = build_parser().parse_args(["source.mp4", *selected.argv()])
    assert args.vertex_project == "test-project" and not args.gemini
    assert args.vertex_location == "europe-west4"
    assert args.confidential is confidential
    assert args.zero_data_retention is True
    assert args.zdr_confirmed_by == "test-operator"
    assert args.omni_asr and args.diarize and args.visual and args.timelens
    assert args.profile == "production" and args.auto_select and args.qc_record is None


@pytest.mark.parametrize("field", ["confidential", "zero_data_retention"])
@pytest.mark.parametrize("value", ["false", 0, 1, None])
def test_invalid_trusted_governance_is_refused(field: str, value: object) -> None:
    selection = (
        ProducerSelection("gemini", confidential=cast(bool, value))
        if field == "confidential"
        else ProducerSelection("gemini", zero_data_retention=cast(bool, value))
    )
    with pytest.raises(GenerationError, match=field):
        selection.argv()


@pytest.mark.parametrize("field", ["vertex_location", "zdr_confirmed_by"])
@pytest.mark.parametrize("value", [None, True, 7, "bad\x00text", "x" * 241])
def test_invalid_trusted_governance_text_is_refused(field: str, value: object) -> None:
    with pytest.raises(GenerationError, match=field):
        selected = (
            replace(_selected(), vertex_location=cast(str, value))
            if field == "vertex_location"
            else replace(_selected(), zdr_confirmed_by=cast(str, value))
        )
        selected.argv()


@pytest.mark.parametrize("location", ["", " "])
def test_empty_trusted_vertex_location_is_refused(location: str) -> None:
    with pytest.raises(GenerationError, match="vertex_location"):
        replace(_selected(), vertex_location=location).argv()


def test_confidential_developer_route_never_becomes_vertex() -> None:
    with pytest.raises(GenerationError, match="Developer API"):
        ProducerSelection(
            "gemini",
            confidential=True,
            zero_data_retention=True,
            zdr_confirmed_by="test-operator",
        ).argv()


@pytest.mark.parametrize("changes", [{"zero_data_retention": False}, {"zdr_confirmed_by": " "}])
def test_confidential_vertex_requires_existing_governance(changes: dict[str, object]) -> None:
    selected = replace(
        _selected(),
        confidential=True,
        zero_data_retention=cast(bool, changes.get("zero_data_retention", True)),
        zdr_confirmed_by=cast(str, changes.get("zdr_confirmed_by", "test-operator")),
    )
    with pytest.raises(GenerationError, match="Vertex"):
        selected.argv()


def test_developer_route_refuses_vertex_location() -> None:
    with pytest.raises(GenerationError, match="Vertex"):
        ProducerSelection("gemini", vertex_location="europe-west4").argv()


def test_trusted_confirmation_remains_literal() -> None:
    args = build_parser().parse_args(
        ["source.mp4", *replace(_selected(), zdr_confirmed_by="--stock-decoder").argv()]
    )
    assert args.zdr_confirmed_by == "--stock-decoder" and not args.stock_decoder


@pytest.mark.parametrize("provider", ["gemini", "vertex"])
def test_default_producer_parser_parity(provider: str) -> None:
    selection = ProducerSelection(
        provider, "test-project" if provider == "vertex" else None, "auto", None
    )
    expected = [
        "--profile=production",
        "--auto-select",
        "--omni-asr",
        "--omni-asr-runtime=auto",
        "--diarize",
        "--visual",
        "--timelens",
        "--gemini" if provider == "gemini" else "--vertex-project=test-project",
    ]
    assert selection.argv() == expected
    args = build_parser().parse_args(["source.mp4", *selection.argv()])
    assert args.confidential is False and args.zero_data_retention is False
    assert args.zdr_confirmed_by == "" and args.vertex_location == "global"
    assert args.omni_asr and args.diarize and args.visual and args.timelens


@pytest.mark.parametrize(
    "key",
    [
        "confidential",
        "zero_data_retention",
        "zdr_confirmed_by",
        "vertex_location",
        "provider",
        "vertex_project",
        "execution_authority",
    ],
)
def test_browser_cannot_select_trusted_governance(key: str) -> None:
    with pytest.raises(GenerationError, match="Unsupported studio options"):
        GenerationRequest.from_payload(
            {
                "schema": 1,
                "source_id": "a" * 32,
                "client_token": "test-client-token-1",
                "options": {key: True},
            }
        )


def _upload(root: Path) -> tuple[UploadStore, GenerationRequest]:
    uploads = UploadStore(root / "uploads")
    data = MEDIA.read_bytes()
    ticket = uploads.begin("episode.mp4", len(data))
    source = uploads.receive(ticket["upload_id"], io.BytesIO(data), len(data))
    return uploads, GenerationRequest.from_payload(
        {
            "schema": 1,
            "source_id": source["source_id"],
            "client_token": "trusted-policy-token-1",
            "options": {"preset": "viral", "max_clips": 3},
        }
    )


def test_trusted_governance_is_bound_and_rehydrated(tmp_path: Path) -> None:
    uploads, request = _upload(tmp_path)
    selected = replace(_selected(), confidential=True)
    prepared = prepare_generation(request, uploads, tmp_path / "disposable", selected)
    assert json.loads(prepared.configuration_json)["producers"] == asdict(selected)
    store = SubmissionStore(tmp_path / "submissions.sqlite")
    job = store.reserve(prepared, BINDING, WORKFLOW)
    result = prepare_studio_execution(
        job.job_id,
        SubmissionStore(store.path),
        UploadStore(uploads.root),
        producers=selected,
        execution_binding_sha256=BINDING,
        workflow_name=WORKFLOW,
    )
    assert result.configuration_json == prepared.configuration_json == job.configuration_json
    assert result.request_sha256 == job.request_sha256 == prepared.content_sha256
    assert result.source_sha256 == job.source_sha256 == prepared.source_sha256
    args = build_parser().parse_args(result.argv)
    assert (
        args.vertex_location == selected.vertex_location and args.vertex_project == "test-project"
    )
    assert args.confidential is True and args.zero_data_retention is True
    assert args.zdr_confirmed_by == selected.zdr_confirmed_by
    assert args.qc_record is None and args.profile == "production"
    assert store.get(job.job_id) == job
    assert uploads.source(job.source_id).read_bytes() == MEDIA.read_bytes()
    assert not (tmp_path / "disposable").exists()


@pytest.mark.parametrize(
    "changes",
    [
        {"confidential": True},
        {"zero_data_retention": False},
        {"zdr_confirmed_by": "other-operator"},
        {"vertex_location": "us-central1"},
    ],
)
def test_trusted_governance_drift_refuses_recovery(
    tmp_path: Path, changes: dict[str, object]
) -> None:
    uploads, request = _upload(tmp_path)
    selected = _selected()
    prepared = prepare_generation(request, uploads, tmp_path / "disposable", selected)
    store = SubmissionStore(tmp_path / "submissions.sqlite")
    job = store.reserve(prepared, BINDING, WORKFLOW)
    different = replace(
        selected,
        confidential=cast(bool, changes.get("confidential", selected.confidential)),
        zero_data_retention=cast(
            bool, changes.get("zero_data_retention", selected.zero_data_retention)
        ),
        zdr_confirmed_by=cast(str, changes.get("zdr_confirmed_by", selected.zdr_confirmed_by)),
        vertex_location=cast(str, changes.get("vertex_location", selected.vertex_location)),
    )
    changed = prepare_generation(request, uploads, tmp_path / "other", different)
    assert changed.configuration_json != prepared.configuration_json
    assert changed.content_sha256 != prepared.content_sha256
    with pytest.raises(GenerationError, match="reconstruction"):
        prepare_studio_execution(
            job.job_id,
            store,
            uploads,
            producers=different,
            execution_binding_sha256=BINDING,
            workflow_name=WORKFLOW,
        )
    assert store.get(job.job_id) == job
    assert uploads.source(job.source_id).read_bytes() == MEDIA.read_bytes()
    assert not (tmp_path / "studio-artifacts").exists()
    assert not (tmp_path / "disposable").exists() and not (tmp_path / "other").exists()

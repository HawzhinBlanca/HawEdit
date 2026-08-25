"""The diarization/reframe kit binds real media and never invents human acceptance."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest

import hawedit.diarization_acceptance as acceptance_module
from hawedit.diarization_acceptance import (
    COMMUNITY_MODEL_ID,
    COMMUNITY_REVISION,
    CONTROL_MODEL_ID,
    SIGNATURE_NAMESPACE,
    DiarizationAcceptanceError,
    PreparedDiarizationStudy,
    evaluate_diarization_study,
    main,
    prepare_diarization_study,
)

FIXTURE = Path(__file__).parent / "fixtures" / "kurdish-speech-3cuts.mp4"


def _write_json(path: Path, document: object) -> Path:
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _reference(tmp_path: Path) -> tuple[Path, Path, dict[str, Any]]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    media_root = tmp_path / "media"
    media_root.mkdir()
    shutil.copyfile(FIXTURE, media_root / "conversation.mp4")
    document: dict[str, Any] = {
        "authorized_by": "owner@example.test",
        "consent_basis": "both speakers signed the retained evaluation release",
        "interim": False,
        "items": [
            {
                "duration_ms": 4_162,
                "frame_width": 640,
                "media_id": "conversation-001",
                "media_path": "conversation.mp4",
                "reference_focus_points": [
                    {"at_ms": 500, "center_x": 100, "speaker": "speaker-a"},
                    {"at_ms": 2_500, "center_x": 500, "speaker": "speaker-b"},
                    {"at_ms": 3_500, "center_x": 480, "speaker": "speaker-b"},
                ],
                "reference_turns": [
                    {"end_ms": 2_000, "speaker": "speaker-a", "start_ms": 0},
                    {"end_ms": 4_162, "speaker": "speaker-b", "start_ms": 2_000},
                ],
                "reference_words": [
                    {"end_ms": 900, "start_ms": 100, "w": "سڵاو"},
                    {"end_ms": 1_900, "start_ms": 1_000, "w": "هاوڕێ"},
                    {"end_ms": 2_900, "start_ms": 2_100, "w": "چۆنی"},
                    {"end_ms": 4_000, "start_ms": 3_100, "w": "باشم"},
                ],
            }
        ],
        "media_authorization": "private client media approved for this local study",
        "schema": 1,
        "study_id": "kurdish-speaker-study-001",
        "use_scope": "local diarization and crop evaluation only; no redistribution",
    }
    return _write_json(tmp_path / "reference.json", document), media_root, document


def _prepare(tmp_path: Path) -> tuple[PreparedDiarizationStudy, Path, Path]:
    reference, media_root, _ = _reference(tmp_path)
    result = prepare_diarization_study(
        reference_manifest_path=reference,
        media_root=media_root,
        output_dir=tmp_path / "prepared",
    )
    return result, reference, media_root


def _filled_run(template: Path, *, control: bool = False, fallback: bool = False) -> dict[str, Any]:
    document = json.loads(template.read_text(encoding="utf-8"))
    document.update(
        {
            "checkpoint_manifest_sha256": "a" * 64 if not control else "b" * 64,
            "revision": "c" * 40 if control else COMMUNITY_REVISION,
            "run_at_utc": "2026-08-17T12:00:00Z",
            "run_by": "operator@example.test",
            "runtime_identity": "hawapc01/windows-wsl/python3.12/dual-3090ti",
        }
    )
    item = document["items"][0]
    item["turns"] = [
        {"end_ms": 2_000, "speaker": "hyp-a", "start_ms": 0},
        {"end_ms": 4_162, "speaker": "hyp-b", "start_ms": 2_000},
    ]
    if fallback:
        item.update(
            {
                "fallback_reason": "no face was visible at the reference instants",
                "focus_points": [],
                "mode": "fallback",
            }
        )
    else:
        item.update(
            {
                "fallback_reason": None,
                "focus_points": [
                    {"at_ms": 500, "center_x": 110, "speaker": "hyp-a"},
                    {"at_ms": 2_500, "center_x": 490, "speaker": "hyp-b"},
                    {"at_ms": 3_500, "center_x": 470, "speaker": "hyp-b"},
                ],
                "mode": "speaker_tracked",
            }
        )
    return cast(dict[str, Any], document)


def _key(tmp_path: Path) -> Path:
    key = tmp_path / "owner-key"
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)],
        check=True,
        capture_output=True,
    )
    return key


def _sign(path: Path, key: Path) -> Path:
    subprocess.run(
        [
            "ssh-keygen",
            "-Y",
            "sign",
            "-f",
            str(key),
            "-n",
            SIGNATURE_NAMESPACE,
            str(path),
        ],
        check=True,
        capture_output=True,
    )
    return Path(f"{path}.sig")


def _completed_inputs(tmp_path: Path) -> dict[str, Path]:
    prepared, reference, media_root = _prepare(tmp_path)
    community = _write_json(
        tmp_path / "community.json",
        _filled_run(prepared.community_run_template_path),
    )
    control = _write_json(
        tmp_path / "control.json",
        _filled_run(prepared.control_run_template_path, control=True, fallback=True),
    )
    approval = json.loads(prepared.approval_template_path.read_text(encoding="utf-8"))
    approval.update(
        {
            "approved_at_utc": "2026-08-17T13:00:00Z",
            "community_run_sha256": hashlib.sha256(community.read_bytes()).hexdigest(),
            "control_run_sha256": hashlib.sha256(control.read_bytes()).hexdigest(),
            "crop_reviewed": True,
            "gated_repo_access_accepted": True,
            "media_rights_confirmed": True,
            "statement": "I reviewed the gated licence, source rights, runs, and crop evidence",
        }
    )
    approval_path = _write_json(tmp_path / "approval.json", approval)
    key = _key(tmp_path)
    allowed = tmp_path / "allowed_signers"
    allowed.write_text(
        f'owner@example.test namespaces="{SIGNATURE_NAMESPACE}" '
        f"{Path(f'{key}.pub').read_text(encoding='utf-8').strip()}\n",
        encoding="utf-8",
    )
    return {
        "allowed_signers": allowed,
        "approval": approval_path,
        "approval_signature": _sign(approval_path, key),
        "community": community,
        "control": control,
        "key": key,
        "media_root": media_root,
        "reference": reference,
        "study_manifest": prepared.study_manifest_path,
    }


def _evaluate(
    tmp_path: Path, inputs: dict[str, Path]
) -> acceptance_module.VerifiedDiarizationStudy:
    return evaluate_diarization_study(
        reference_manifest_path=inputs["reference"],
        media_root=inputs["media_root"],
        study_manifest_path=inputs["study_manifest"],
        community_run_path=inputs["community"],
        control_run_path=inputs["control"],
        approval_path=inputs["approval"],
        approval_signature_path=inputs["approval_signature"],
        allowed_signers_path=inputs["allowed_signers"],
        output_dir=tmp_path / "verified",
    )


def _rebind_and_resign(inputs: dict[str, Path]) -> None:
    approval = json.loads(inputs["approval"].read_text(encoding="utf-8"))
    approval["community_run_sha256"] = hashlib.sha256(inputs["community"].read_bytes()).hexdigest()
    approval["control_run_sha256"] = hashlib.sha256(inputs["control"].read_bytes()).hexdigest()
    _write_json(inputs["approval"], approval)
    inputs["approval_signature"].unlink()
    inputs["approval_signature"] = _sign(inputs["approval"], inputs["key"])


def test_prepare_binds_real_video_references_and_unset_templates(tmp_path: Path) -> None:
    prepared, _, _ = _prepare(tmp_path)
    assert {path.name for path in prepared.directory.iterdir()} == {
        "INSTRUCTIONS.txt",
        "approval.template.json",
        "community-run.template.json",
        "control-run.template.json",
        "study-manifest.json",
    }
    manifest = json.loads(prepared.study_manifest_path.read_text(encoding="utf-8"))
    assert manifest["items"][0]["media_sha256"] == hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    community = json.loads(prepared.community_run_template_path.read_text(encoding="utf-8"))
    control = json.loads(prepared.control_run_template_path.read_text(encoding="utf-8"))
    assert community["model_id"] == COMMUNITY_MODEL_ID
    assert community["revision"] == COMMUNITY_REVISION
    assert control["model_id"] == CONTROL_MODEL_ID
    assert control["revision"] is None
    assert community["items"][0]["mode"] is None


def test_signed_runs_publish_raw_metrics_and_explicit_fallback(tmp_path: Path) -> None:
    inputs = _completed_inputs(tmp_path)
    verified = _evaluate(tmp_path, inputs)
    assert {path.name for path in verified.directory.iterdir()} == {
        "ATTRIBUTION.txt",
        "INSTRUCTIONS.txt",
        "diarization-report.json",
    }
    report = json.loads(verified.report_path.read_text(encoding="utf-8"))
    community = report["systems"]["community"]
    control = report["systems"]["control"]
    assert community["der"] == 0.0
    assert community["tracked_items"] == 1
    assert community["fallback_items"] == 0
    assert community["items"][0]["association_error_rate"] == 0.0
    assert community["items"][0]["center_mae_px"] == 10.0
    assert control["tracked_items"] == 0
    assert control["fallback_items"] == 1
    assert control["items"][0]["center_mae_px"] is None
    assert "raw measurements only" in report["acceptance_boundary"]
    assert "CC-BY-4.0" in verified.attribution_path.read_text(encoding="utf-8")


def test_zero_turn_control_is_reported_as_full_miss_not_deleted(tmp_path: Path) -> None:
    inputs = _completed_inputs(tmp_path)
    control = json.loads(inputs["control"].read_text(encoding="utf-8"))
    control["items"][0]["turns"] = []
    _write_json(inputs["control"], control)
    _rebind_and_resign(inputs)
    report = json.loads(_evaluate(tmp_path, inputs).report_path.read_text(encoding="utf-8"))
    control_report = report["systems"]["control"]
    assert control_report["der"] == 1.0
    assert control_report["boundary_mean_abs_error_ms"] is None
    assert control_report["items"][0]["boundary"] is None


def test_control_overlap_is_scored_while_community_overlap_is_refused(tmp_path: Path) -> None:
    inputs = _completed_inputs(tmp_path)
    control = json.loads(inputs["control"].read_text(encoding="utf-8"))
    control["items"][0]["turns"].append({"end_ms": 1_500, "speaker": "overlap", "start_ms": 500})
    _write_json(inputs["control"], control)
    _rebind_and_resign(inputs)
    report = json.loads(_evaluate(tmp_path, inputs).report_path.read_text(encoding="utf-8"))
    assert report["systems"]["control"]["items"][0]["der"]["false_alarm_ms"] == 1_000

    other = _completed_inputs(tmp_path / "community-overlap")
    community = json.loads(other["community"].read_text(encoding="utf-8"))
    community["items"][0]["turns"].append({"end_ms": 1_500, "speaker": "overlap", "start_ms": 500})
    _write_json(other["community"], community)
    with pytest.raises(DiarizationAcceptanceError, match="segments overlap"):
        _evaluate(tmp_path / "community-overlap", other)


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        (lambda doc: doc.update({"interim": True}), "interim"),
        (
            lambda doc: doc["items"][0].update(
                {"reference_turns": [{"end_ms": 4_162, "speaker": "only-one", "start_ms": 0}]}
            ),
            "at least two",
        ),
        (
            lambda doc: doc["items"][0]["reference_focus_points"][0].update(
                {"speaker": "speaker-b"}
            ),
            "active speaker",
        ),
        (
            lambda doc: doc["items"][0].update({"frame_width": 641}),
            "width is 640",
        ),
    ],
)
def test_prepare_refuses_incomplete_or_false_reference_evidence(
    tmp_path: Path, mutation: Any, match: str
) -> None:
    reference, media_root, document = _reference(tmp_path)
    mutation(document)
    _write_json(reference, document)
    with pytest.raises(DiarizationAcceptanceError, match=match):
        prepare_diarization_study(
            reference_manifest_path=reference,
            media_root=media_root,
            output_dir=tmp_path / "refused",
        )


def test_prepare_refuses_linked_or_escaping_media(tmp_path: Path) -> None:
    reference, media_root, document = _reference(tmp_path)
    original = media_root / "conversation.mp4"
    linked = media_root / "linked.mp4"
    os.link(original, linked)
    document["items"][0]["media_path"] = "linked.mp4"
    _write_json(reference, document)
    with pytest.raises(DiarizationAcceptanceError, match="non-hardlinked"):
        prepare_diarization_study(
            reference_manifest_path=reference,
            media_root=media_root,
            output_dir=tmp_path / "linked-output",
        )
    document["items"][0]["media_path"] = "../outside.mp4"
    _write_json(reference, document)
    with pytest.raises(DiarizationAcceptanceError, match="contained relative path"):
        prepare_diarization_study(
            reference_manifest_path=reference,
            media_root=media_root,
            output_dir=tmp_path / "escape-output",
        )


@pytest.mark.parametrize(
    ("path_key", "mutation", "match"),
    [
        (
            "community",
            lambda doc: doc.update({"revision": "d" * 40}),
            "pinned revision",
        ),
        (
            "community",
            lambda doc: doc.update({"licence": "MIT"}),
            "CC-BY-4.0",
        ),
        (
            "control",
            lambda doc: doc.update({"model_id": COMMUNITY_MODEL_ID}),
            "speaker-diarization-3.1",
        ),
        (
            "community",
            lambda doc: doc["items"][0].update({"mode": True}),
            "must be a string",
        ),
    ],
)
def test_evaluate_refuses_wrong_model_receipt_or_coercive_schema(
    tmp_path: Path, path_key: str, mutation: Any, match: str
) -> None:
    inputs = _completed_inputs(tmp_path)
    document = json.loads(inputs[path_key].read_text(encoding="utf-8"))
    mutation(document)
    _write_json(inputs[path_key], document)
    with pytest.raises(DiarizationAcceptanceError, match=match):
        _evaluate(tmp_path, inputs)


def test_speaker_tracked_output_must_match_reference_times_and_its_turns(tmp_path: Path) -> None:
    inputs = _completed_inputs(tmp_path)
    community = json.loads(inputs["community"].read_text(encoding="utf-8"))
    community["items"][0]["focus_points"][0]["at_ms"] = 600
    _write_json(inputs["community"], community)
    _rebind_and_resign(inputs)
    with pytest.raises(DiarizationAcceptanceError, match="exact human-reference focus timestamps"):
        _evaluate(tmp_path, inputs)


@pytest.mark.parametrize(
    "field",
    ["crop_reviewed", "gated_repo_access_accepted", "media_rights_confirmed"],
)
def test_approval_requires_every_human_assertion(tmp_path: Path, field: str) -> None:
    inputs = _completed_inputs(tmp_path)
    approval = json.loads(inputs["approval"].read_text(encoding="utf-8"))
    approval[field] = False
    _write_json(inputs["approval"], approval)
    with pytest.raises(DiarizationAcceptanceError, match=f"{field} must be explicitly true"):
        _evaluate(tmp_path, inputs)


def test_approval_must_follow_both_runs(tmp_path: Path) -> None:
    inputs = _completed_inputs(tmp_path)
    approval = json.loads(inputs["approval"].read_text(encoding="utf-8"))
    approval["approved_at_utc"] = "2026-08-17T11:59:59Z"
    _write_json(inputs["approval"], approval)
    inputs["approval_signature"].unlink()
    inputs["approval_signature"] = _sign(inputs["approval"], inputs["key"])
    with pytest.raises(DiarizationAcceptanceError, match="later than both model runs"):
        _evaluate(tmp_path, inputs)


def test_approval_signature_and_run_digests_bind_exact_bytes(tmp_path: Path) -> None:
    inputs = _completed_inputs(tmp_path)
    community = json.loads(inputs["community"].read_text(encoding="utf-8"))
    community["runtime_identity"] = "different-but-valid-runtime"
    _write_json(inputs["community"], community)
    with pytest.raises(DiarizationAcceptanceError, match="other evidence"):
        _evaluate(tmp_path, inputs)
    inputs = _completed_inputs(tmp_path / "signature")
    approval = json.loads(inputs["approval"].read_text(encoding="utf-8"))
    approval["statement"] = "tampered after signing"
    _write_json(inputs["approval"], approval)
    with pytest.raises(DiarizationAcceptanceError, match="signature verification failed"):
        _evaluate(tmp_path / "signature", inputs)


def test_reference_or_media_drift_is_refused_at_evaluation(tmp_path: Path) -> None:
    inputs = _completed_inputs(tmp_path)
    reference = json.loads(inputs["reference"].read_text(encoding="utf-8"))
    reference["items"][0]["reference_words"][0]["w"] = "گۆڕاو"
    _write_json(inputs["reference"], reference)
    with pytest.raises(DiarizationAcceptanceError, match="does not recompute"):
        _evaluate(tmp_path, inputs)


def test_result_publication_is_write_once(tmp_path: Path) -> None:
    inputs = _completed_inputs(tmp_path)
    _evaluate(tmp_path, inputs)
    with pytest.raises(DiarizationAcceptanceError, match="refusing to overwrite"):
        _evaluate(tmp_path, inputs)


def test_prepare_cli_is_machine_readable_and_refusal_is_bounded(
    tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    reference, media_root, _ = _reference(tmp_path)
    assert (
        main(
            [
                "prepare",
                "--reference-manifest",
                str(reference),
                "--media-root",
                str(media_root),
                "--output-dir",
                str(tmp_path / "cli-prepared"),
            ]
        )
        == 0
    )
    captured = capfd.readouterr()
    assert json.loads(captured.out)["status"] == "prepared"
    assert captured.err == ""
    assert (
        main(
            [
                "prepare",
                "--reference-manifest",
                str(reference),
                "--media-root",
                str(media_root),
                "--output-dir",
                str(tmp_path / "cli-prepared"),
            ]
        )
        == 2
    )
    captured = capfd.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("REFUSED: refusing to overwrite")


def test_prepare_detects_media_change_during_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reference, media_root, _ = _reference(tmp_path)
    original = cast(Callable[[Path], int], acceptance_module.__dict__["probe_duration_ms"])

    def mutate(path: Path) -> int:
        duration = original(path)
        path.write_bytes(path.read_bytes() + b"changed-after-probe")
        return duration

    monkeypatch.setitem(acceptance_module.__dict__, "probe_duration_ms", mutate)
    with pytest.raises(DiarizationAcceptanceError, match="changed while ffprobe"):
        prepare_diarization_study(
            reference_manifest_path=reference,
            media_root=media_root,
            output_dir=tmp_path / "changed-output",
        )

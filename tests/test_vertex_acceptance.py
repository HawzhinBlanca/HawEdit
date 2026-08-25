"""Confidential Vertex acceptance is content-bound, one-shot and human-approved."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import replace
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

import hawedit.vertex_acceptance as acceptance_module
from hawedit.gemini import Governance, VertexGeminiJudge
from hawedit.judge import JudgeFrame, JudgeRequest, JudgeVerdict
from hawedit.vertex_acceptance import (
    SIGNATURE_NAMESPACE,
    PreparedVertexAcceptance,
    VertexAcceptanceError,
    VertexEnvironment,
    main,
    prepare_vertex_acceptance,
    probe_vertex_environment,
    run_vertex_acceptance,
)
from hawedit.windows_security import assert_private_windows_path

FIXTURE = Path(__file__).parent / "fixtures" / "kurdish-speech-3cuts.mp4"


def _write_json(path: Path, document: object) -> Path:
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _private_inputs(tmp_path: Path) -> tuple[Path, Path, dict[str, Any]]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    private = tmp_path / "private"
    private.mkdir()
    shutil.copyfile(FIXTURE, private / "client.mp4")
    transcript = {
        "media_id": "vertex-client-001",
        "source_sha256": "a" * 64,
        "text_ckb": "سڵاو هاوڕێیان ئەمە تاقیکردنەوەیەکی نهێنییە.",
        "words": [
            {"conf": 0.95, "end_ms": 900, "start_ms": 100, "w": "سڵاو"},
            {"conf": 0.94, "end_ms": 1_700, "start_ms": 1_000, "w": "هاوڕێیان"},
        ],
    }
    transcript_path = _write_json(private / "client.transcript.norm.json", transcript)
    policy = private / "retention-policy.txt"
    policy.write_text(
        "contractual Vertex zero-data-retention approval retained by the client\n",
        encoding="utf-8",
    )
    video = private / "client.mp4"
    document: dict[str, Any] = {
        "billing": {
            "billing_account_reference": "billingAccounts/000000-AAAAAA-BBBBBB",
            "billing_enabled": True,
            "confirmed_at_utc": "2026-08-17T09:00:00Z",
            "confirmed_by": "cloud-owner@example.test",
        },
        "environment": {
            "expected_adc_project": "approved-news-project",
            "expected_credential_type": "service_account",
            "expected_principal": "vertex-runner@approved-news-project.iam.gserviceaccount.com",
        },
        "limits": {
            "max_estimated_input_cost_usd": 0.05,
            "max_input_tokens": 25_000,
        },
        "location": "global",
        "media": {
            "authorized_by": "owner@example.test",
            "consent_authorization_basis": "retained client release covers cloud processing",
            "duration_ms": 4_162,
            "licence": "private client media; no redistribution",
            "path": "client.mp4",
            "rights_owner": "Example Kurdish Newsroom",
            "sha256": hashlib.sha256(video.read_bytes()).hexdigest(),
            "use_scope": "one confidential Vertex acceptance request only",
        },
        "model_id": "gemini-2.5-pro",
        "project": "approved-news-project",
        "request": {
            "candidate_id": "vertex-client-001:s0",
            "carried_verbal_score": 0.75,
            "clip_in_ms": 100,
            "clip_out_ms": 1_700,
            "text_ckb": "سڵاو هاوڕێیان",
            "visual_context": ["00:00.100-00:01.700 — two speakers in a studio"],
        },
        "retention": {
            "confirmed_at_utc": "2026-08-17T09:05:00Z",
            "confirmed_by": "privacy-owner@example.test",
            "policy_path": "retention-policy.txt",
            "policy_sha256": hashlib.sha256(policy.read_bytes()).hexdigest(),
            "zero_data_retention": True,
        },
        "schema": 1,
        "study_id": "vertex-confidential-001",
        "transcript": {
            "media_id": "vertex-client-001",
            "path": "client.transcript.norm.json",
            "sha256": hashlib.sha256(transcript_path.read_bytes()).hexdigest(),
        },
    }
    return _write_json(tmp_path / "source.json", document), private, document


def _probe_video(path: Path) -> tuple[int, int]:
    assert path.name == "client.mp4"
    return 4_162, 640


def _prepare(tmp_path: Path) -> tuple[PreparedVertexAcceptance, Path, Path, dict[str, Any]]:
    source, private, document = _private_inputs(tmp_path)
    prepared = prepare_vertex_acceptance(
        source_manifest_path=source,
        private_root=private,
        output_dir=tmp_path / "prepared",
        media_probe=_probe_video,
    )
    return prepared, source, private, document


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


def _approval(tmp_path: Path, prepared: PreparedVertexAcceptance) -> tuple[Path, Path, Path]:
    document = json.loads(prepared.approval_template_path.read_text(encoding="utf-8"))
    document.update(
        {
            "approved_at_utc": "2026-08-17T10:00:00Z",
            "approved_by": "owner@example.test",
            "billing_confirmed": True,
            "media_rights_confirmed": True,
            "one_paid_request_approved": True,
            "statement": "I approve exactly this bounded confidential Vertex acceptance request",
            "zero_data_retention_confirmed": True,
        }
    )
    approval = _write_json(tmp_path / "approval.json", document)
    key = _key(tmp_path)
    allowed = tmp_path / "allowed_signers"
    allowed.write_text(
        f'owner@example.test namespaces="{SIGNATURE_NAMESPACE}" '
        f"{Path(f'{key}.pub').read_text(encoding='utf-8').strip()}\n",
        encoding="utf-8",
    )
    return approval, _sign(approval, key), allowed


def _environment(**overrides: object) -> VertexEnvironment:
    values: dict[str, object] = {
        "access_token": "ya29.secret-access-token",
        "aiplatform_enabled": True,
        "billing_account_reference": "billingAccounts/000000-AAAAAA-BBBBBB",
        "billing_enabled": True,
        "checked_at_utc": "2026-08-17T10:01:00Z",
        "credential_type": "service_account",
        "principal": "vertex-runner@approved-news-project.iam.gserviceaccount.com",
        "project": "approved-news-project",
    }
    values.update(overrides)
    return VertexEnvironment(**values)  # type: ignore[arg-type]


def _frames(*_args: object, **_kwargs: object) -> tuple[JudgeFrame, ...]:
    return (
        JudgeFrame(timestamp_ms=100, mime_type="image/jpeg", data=b"private-frame-one"),
        JudgeFrame(timestamp_ms=1_700, mime_type="image/jpeg", data=b"private-frame-two"),
    )


class _Judge:
    def __init__(self, events: list[str], *, fail: BaseException | None = None) -> None:
        self.events = events
        self.fail = fail
        self.requests: list[JudgeRequest] = []

    def judge_with_count(
        self, request: JudgeRequest, *, max_tokens: int | None = None
    ) -> tuple[int, JudgeVerdict]:
        self.events.append("judge")
        self.requests.append(request)
        assert max_tokens == 25_000
        if self.fail is not None:
            raise self.fail
        return (
            1_234,
            JudgeVerdict(
                candidate_id=request.candidate_id,
                hook_score=0.8,
                self_contained=True,
                payoff_at_ms=1_500,
                meaning_fidelity=0.9,
                misleading_edit_risk=0.1,
                cultural_landing=0.85,
                narrative_role="payoff",
                title_ckb="ناونیشانی نهێنی",
                description_ckb="وەسفی نهێنی",
                hashtags_ckb=("#نهێنی",),
                judge="gemini-2.5-pro",
                clip_in_ms=100,
                clip_out_ms=1_700,
            ),
        )


def _run(
    tmp_path: Path,
    prepared: PreparedVertexAcceptance,
    source: Path,
    private: Path,
    approval: Path,
    signature: Path,
    allowed: Path,
    *,
    environment: VertexEnvironment | None = None,
    judge: _Judge | None = None,
    frames: Callable[..., tuple[JudgeFrame, ...]] = _frames,
) -> tuple[Any, _Judge, list[str]]:
    events: list[str] = []
    selected_judge = judge or _Judge(events)

    def probe(_project: str) -> VertexEnvironment:
        events.append("environment")
        return environment or _environment()

    def judge_factory(
        _project: str, _location: str, _governance: Governance, _token: str
    ) -> _Judge:
        events.append("judge_factory")
        return selected_judge

    def frame_extractor(*args: object, **kwargs: object) -> tuple[JudgeFrame, ...]:
        events.append("frames")
        return frames(*args, **kwargs)

    result = run_vertex_acceptance(
        source_manifest_path=source,
        private_root=private,
        prepared_manifest_path=prepared.manifest_path,
        approval_path=approval,
        approval_signature_path=signature,
        allowed_signers_path=allowed,
        output_dir=tmp_path / "result",
        environment_probe=probe,
        judge_factory=judge_factory,
        frame_extractor=frame_extractor,
        media_probe=_probe_video,
        now_utc=lambda: "2026-08-17T10:02:00Z",
    )
    return result, selected_judge, events


def test_prepare_cli_is_machine_readable_and_transport_free(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source, private, document = _private_inputs(tmp_path)

    assert (
        main(
            [
                "prepare",
                "--source-manifest",
                str(source),
                "--private-root",
                str(private),
                "--output-dir",
                str(tmp_path / "prepared-cli"),
            ]
        )
        == 0
    )

    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert captured.err == ""
    assert report["status"] == "prepared-no-client-content-sent"
    published = Path(report["directory"])
    assert published.is_dir()
    assert document["request"]["text_ckb"] not in captured.out
    assert document["billing"]["billing_account_reference"] not in captured.out


def test_cli_refuses_missing_private_input_without_machine_stdout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        main(
            [
                "prepare",
                "--source-manifest",
                str(tmp_path / "missing.json"),
                "--private-root",
                str(tmp_path),
                "--output-dir",
                str(tmp_path / "prepared"),
            ]
        )
        == 2
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("REFUSED:")


def test_prepare_is_transport_free_and_emits_only_sanitized_templates(tmp_path: Path) -> None:
    prepared, _, _, source = _prepare(tmp_path)

    assert sorted(path.name for path in prepared.directory.iterdir()) == [
        "INSTRUCTIONS.txt",
        "approval.template.json",
        "vertex-acceptance.json",
    ]
    combined = b"".join(path.read_bytes() for path in prepared.directory.iterdir())
    assert source["request"]["text_ckb"].encode() not in combined
    assert source["request"]["visual_context"][0].encode() not in combined
    assert source["billing"]["billing_account_reference"].encode() not in combined
    assert b"retention-policy.txt" not in combined
    manifest = json.loads(prepared.manifest_path.read_text(encoding="utf-8"))
    assert manifest["media_sha256"] == source["media"]["sha256"]
    assert manifest["transcript_sha256"] == source["transcript"]["sha256"]
    assert manifest["request_sha256"]
    if os.name == "nt":
        assert_private_windows_path(prepared.directory, require_protected=True)
    else:
        assert stat.S_IMODE(prepared.directory.stat().st_mode) & 0o077 == 0


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("billing.billing_enabled", "true", "JSON boolean"),
        ("retention.zero_data_retention", False, "must be true"),
        ("limits.max_input_tokens", True, "JSON integer"),
        ("limits.max_input_tokens", 200_000, "below"),
        ("limits.max_estimated_input_cost_usd", -1.0, "must be in"),
        ("limits.max_estimated_input_cost_usd", 0.000001, "must be in"),
    ],
)
def test_prepare_refuses_schema_coercion_and_unbounded_requests(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    source, private, document = _private_inputs(tmp_path)
    parent, child = field.split(".")
    document[parent][child] = value
    _write_json(source, document)

    with pytest.raises(VertexAcceptanceError, match=message):
        prepare_vertex_acceptance(
            source_manifest_path=source,
            private_root=private,
            output_dir=tmp_path / "prepared",
            media_probe=_probe_video,
        )


def test_prepare_refuses_private_path_escape_and_linked_content(tmp_path: Path) -> None:
    source, private, document = _private_inputs(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    document["retention"]["policy_path"] = "../outside.txt"
    document["retention"]["policy_sha256"] = hashlib.sha256(outside.read_bytes()).hexdigest()
    _write_json(source, document)

    with pytest.raises(VertexAcceptanceError, match="contained relative path"):
        prepare_vertex_acceptance(
            source_manifest_path=source,
            private_root=private,
            output_dir=tmp_path / "prepared",
            media_probe=_probe_video,
        )


def test_prepare_requires_request_text_from_the_aligned_clip_words(tmp_path: Path) -> None:
    source, private, document = _private_inputs(tmp_path)
    document["request"]["text_ckb"] = "ئەمە"
    _write_json(source, document)

    with pytest.raises(VertexAcceptanceError, match="aligned words overlapping the clip"):
        prepare_vertex_acceptance(
            source_manifest_path=source,
            private_root=private,
            output_dir=tmp_path / "prepared",
            media_probe=_probe_video,
        )


def test_invalid_transcript_media_identity_is_a_bounded_acceptance_error(tmp_path: Path) -> None:
    source, private, document = _private_inputs(tmp_path)
    transcript_path = private / "client.transcript.norm.json"
    transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
    transcript["media_id"] = "../client"
    _write_json(transcript_path, transcript)
    document["transcript"]["media_id"] = "../client"
    document["transcript"]["sha256"] = hashlib.sha256(transcript_path.read_bytes()).hexdigest()
    _write_json(source, document)

    with pytest.raises(VertexAcceptanceError, match="invalid normalised transcript identity"):
        prepare_vertex_acceptance(
            source_manifest_path=source,
            private_root=private,
            output_dir=tmp_path / "prepared",
            media_probe=_probe_video,
        )

    document["retention"]["policy_path"] = "retention-policy.txt"
    linked = private / "linked-policy.txt"
    linked.hardlink_to(private / "retention-policy.txt")
    document["retention"]["policy_path"] = linked.name
    _write_json(source, document)
    with pytest.raises(VertexAcceptanceError, match="hardlink"):
        prepare_vertex_acceptance(
            source_manifest_path=source,
            private_root=private,
            output_dir=tmp_path / "prepared-two",
            media_probe=_probe_video,
        )


def test_complete_run_preflights_then_makes_one_counted_judgment(tmp_path: Path) -> None:
    prepared, source, private, _ = _prepare(tmp_path)
    approval, signature, allowed = _approval(tmp_path, prepared)

    result, judge, events = _run(tmp_path, prepared, source, private, approval, signature, allowed)

    assert events == ["environment", "frames", "judge_factory", "judge"]
    assert len(judge.requests) == 1
    assert judge.requests[0].text_ckb == "سڵاو هاوڕێیان"
    assert len(judge.requests[0].keyframes) == 2
    evidence = json.loads(result.evidence_path.read_text(encoding="utf-8"))
    assert evidence["request"]["counted_input_tokens"] == 1_234
    assert evidence["request"]["effective_max_input_tokens"] == 25_000
    assert evidence["request"]["paid_generate_attempts"] == 1
    assert evidence["environment"]["billing_enabled"] is True
    assert evidence["verdict"]["hook_score"] == 0.8
    assert result.attempt_path.is_dir()
    assert list(tmp_path.glob(".hawedit-vertex-frames-*")) == []


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"project": "wrong-project"}, "ADC project"),
        ({"credential_type": "authorized_user"}, "credential type"),
        ({"principal": "other@example.test"}, "ADC principal"),
        ({"billing_enabled": False}, "billing is not enabled"),
        ({"aiplatform_enabled": False}, "Vertex AI API is not enabled"),
        ({"billing_account_reference": "billingAccounts/OTHER"}, "billing account"),
    ],
)
def test_live_environment_mismatch_refuses_before_pixels_or_model_transport(
    tmp_path: Path, override: dict[str, object], message: str
) -> None:
    prepared, source, private, _ = _prepare(tmp_path)
    approval, signature, allowed = _approval(tmp_path, prepared)
    judge_events: list[str] = []

    with pytest.raises(VertexAcceptanceError, match=message):
        _run(
            tmp_path,
            prepared,
            source,
            private,
            approval,
            signature,
            allowed,
            environment=_environment(**override),
            judge=_Judge(judge_events),
        )

    assert judge_events == []
    assert not (tmp_path / "result").exists()


def test_false_or_unsigned_human_approval_never_reaches_environment_probe(tmp_path: Path) -> None:
    prepared, source, private, _ = _prepare(tmp_path)
    approval, signature, allowed = _approval(tmp_path, prepared)
    document = json.loads(approval.read_text(encoding="utf-8"))
    document["zero_data_retention_confirmed"] = False
    _write_json(approval, document)

    with pytest.raises(VertexAcceptanceError, match="zero_data_retention_confirmed"):
        _run(tmp_path, prepared, source, private, approval, signature, allowed)

    document["zero_data_retention_confirmed"] = True
    document["statement"] += " changed after signing"
    _write_json(approval, document)
    with pytest.raises(VertexAcceptanceError, match="signature verification failed"):
        _run(tmp_path, prepared, source, private, approval, signature, allowed)


def test_existing_output_refuses_before_cloud_probe_or_private_pixels(tmp_path: Path) -> None:
    prepared, source, private, _ = _prepare(tmp_path)
    approval, signature, allowed = _approval(tmp_path, prepared)
    destination = tmp_path / "result"
    destination.mkdir()
    sentinel = destination / "owned.txt"
    sentinel.write_text("operator-owned", encoding="utf-8")
    events: list[str] = []

    def environment_probe(_project: str) -> VertexEnvironment:
        events.append("environment")
        return _environment()

    def frame_extractor(*_args: object, **_kwargs: object) -> tuple[JudgeFrame, ...]:
        events.append("frames")
        return _frames()

    with pytest.raises(VertexAcceptanceError, match="already exists"):
        run_vertex_acceptance(
            source_manifest_path=source,
            private_root=private,
            prepared_manifest_path=prepared.manifest_path,
            approval_path=approval,
            approval_signature_path=signature,
            allowed_signers_path=allowed,
            output_dir=destination,
            environment_probe=environment_probe,
            frame_extractor=frame_extractor,
            media_probe=_probe_video,
        )

    assert events == []
    assert sentinel.read_text(encoding="utf-8") == "operator-owned"


@pytest.mark.parametrize(
    ("checked_at", "message"),
    [
        ("2026-08-17T09:59:59Z", "predates the signed approval"),
        ("2026-08-17T10:02:01Z", "later than the attempt start"),
    ],
)
def test_environment_timestamp_must_bound_the_attempt_before_transport(
    tmp_path: Path, checked_at: str, message: str
) -> None:
    prepared, source, private, _ = _prepare(tmp_path)
    approval, signature, allowed = _approval(tmp_path, prepared)
    judge_events: list[str] = []

    with pytest.raises(VertexAcceptanceError, match=message):
        _run(
            tmp_path,
            prepared,
            source,
            private,
            approval,
            signature,
            allowed,
            environment=_environment(checked_at_utc=checked_at),
            judge=_Judge(judge_events),
        )

    assert judge_events == []
    assert not (tmp_path / ".result.vertex-attempt").exists()


def test_input_drift_after_preparation_and_signature_is_refused_before_probe(
    tmp_path: Path,
) -> None:
    prepared, source, private, document = _prepare(tmp_path)
    approval, signature, allowed = _approval(tmp_path, prepared)
    document["request"]["visual_context"].append("a changed but valid private observation")
    _write_json(source, document)

    with pytest.raises(VertexAcceptanceError, match="does not recompute"):
        _run(tmp_path, prepared, source, private, approval, signature, allowed)


def test_failed_or_ambiguous_call_leaves_a_durable_no_replay_reservation(tmp_path: Path) -> None:
    prepared, source, private, _ = _prepare(tmp_path)
    approval, signature, allowed = _approval(tmp_path, prepared)
    first_events: list[str] = []

    with pytest.raises(RuntimeError, match="ambiguous after upload"):
        _run(
            tmp_path,
            prepared,
            source,
            private,
            approval,
            signature,
            allowed,
            judge=_Judge(first_events, fail=RuntimeError("ambiguous after upload")),
        )

    attempt = tmp_path / ".result.vertex-attempt"
    assert attempt.is_dir()
    assert not (tmp_path / "result").exists()
    assert list(tmp_path.glob(".hawedit-vertex-frames-*")) == []
    second_events: list[str] = []
    with pytest.raises(VertexAcceptanceError, match="already exists"):
        _run(
            tmp_path,
            prepared,
            source,
            private,
            approval,
            signature,
            allowed,
            judge=_Judge(second_events),
        )
    assert second_events == []


def test_frame_failure_removes_nested_private_pixels_without_masking_primary(
    tmp_path: Path,
) -> None:
    prepared, source, private, _ = _prepare(tmp_path)
    approval, signature, allowed = _approval(tmp_path, prepared)

    def failing_frames(
        _media: Path, _in_ms: int, _out_ms: int, workspace: Path
    ) -> tuple[JudgeFrame, ...]:
        if os.name == "nt":
            assert_private_windows_path(workspace, require_protected=True)
        else:
            assert stat.S_IMODE(workspace.stat().st_mode) & 0o077 == 0
        nested = workspace / "owned-attempt"
        nested.mkdir()
        (nested / "private.jpg").write_bytes(b"confidential pixels")
        raise RuntimeError("frame backend control failure")

    with pytest.raises(RuntimeError, match="frame backend control failure"):
        _run(
            tmp_path,
            prepared,
            source,
            private,
            approval,
            signature,
            allowed,
            frames=failing_frames,
        )

    assert list(tmp_path.glob(".hawedit-vertex-frames-*")) == []
    assert not (tmp_path / ".result.vertex-attempt").exists()


def test_public_evidence_omits_all_client_content_credentials_and_account_names(
    tmp_path: Path,
) -> None:
    prepared, source, private, document = _prepare(tmp_path)
    approval, signature, allowed = _approval(tmp_path, prepared)
    result, _, _ = _run(tmp_path, prepared, source, private, approval, signature, allowed)
    payload = result.evidence_path.read_bytes()

    forbidden = [
        document["request"]["text_ckb"],
        document["request"]["visual_context"][0],
        document["billing"]["billing_account_reference"],
        "ya29.secret-access-token",
        "private-frame-one",
        "private-frame-two",
        "ناونیشانی نهێنی",
        "وەسفی نهێنی",
        "#نهێنی",
        "retention-policy.txt",
    ]
    for secret in forbidden:
        assert str(secret).encode("utf-8") not in payload
    evidence = json.loads(payload)
    assert evidence["content"]["frame_sha256"] == [
        hashlib.sha256(b"private-frame-one").hexdigest(),
        hashlib.sha256(b"private-frame-two").hexdigest(),
    ]
    assert (
        evidence["environment"]["billing_account_sha256"]
        == hashlib.sha256(document["billing"]["billing_account_reference"].encode()).hexdigest()
    )


def test_real_vertex_judge_boundary_performs_one_count_and_one_generate(tmp_path: Path) -> None:
    prepared, source, private, _ = _prepare(tmp_path)
    approval, signature, allowed = _approval(tmp_path, prepared)
    calls: list[tuple[str, Mapping[str, str]]] = []

    def transport(url: str, _body: bytes | None, headers: Mapping[str, str]) -> tuple[int, str]:
        calls.append((url, headers))
        if url.endswith(":countTokens"):
            return 200, json.dumps({"totalTokens": 1_234})
        return 200, json.dumps(
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": json.dumps(
                                        {
                                            "cultural_landing": 0.85,
                                            "description_ckb": "وەسفێک",
                                            "hashtags_ckb": ["#کوردی"],
                                            "hook_score": 0.8,
                                            "meaning_fidelity": 0.9,
                                            "misleading_edit_risk": 0.1,
                                            "narrative_role": "payoff",
                                            "payoff_at_ms": 1_500,
                                            "self_contained": True,
                                            "title_ckb": "ناونیشانێک",
                                        },
                                        ensure_ascii=False,
                                    )
                                }
                            ]
                        }
                    }
                ]
            },
            ensure_ascii=False,
        )

    def factory(
        project: str, location: str, governance: Governance, token: str
    ) -> VertexGeminiJudge:
        return VertexGeminiJudge(
            project,
            location=location,
            governance=governance,
            token_provider=lambda: token,
            transport=transport,
        )

    run_vertex_acceptance(
        source_manifest_path=source,
        private_root=private,
        prepared_manifest_path=prepared.manifest_path,
        approval_path=approval,
        approval_signature_path=signature,
        allowed_signers_path=allowed,
        output_dir=tmp_path / "real-boundary",
        environment_probe=lambda _project: _environment(),
        judge_factory=factory,
        frame_extractor=_frames,
        media_probe=_probe_video,
        now_utc=lambda: "2026-08-17T10:02:00Z",
    )

    assert [url.rsplit(":", 1)[-1] for url, _ in calls] == ["countTokens", "generateContent"]
    assert all(
        headers == {"Authorization": "Bearer ya29.secret-access-token"} for _, headers in calls
    )


def test_environment_value_never_repr_leaks_the_access_token() -> None:
    environment = _environment()
    assert "secret-access-token" not in repr(environment)
    assert replace(environment, billing_enabled=False).billing_enabled is False


def test_default_probe_refreshes_adc_and_checks_billing_plus_vertex_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []

    google = ModuleType("google")
    auth = ModuleType("google.auth")
    exceptions = ModuleType("google.auth.exceptions")
    transport = ModuleType("google.auth.transport")
    requests = ModuleType("google.auth.transport.requests")

    class GoogleAuthError(Exception):
        pass

    class Request:
        pass

    class Credentials:
        __module__ = "google.oauth2.service_account"
        token: str | None = None
        service_account_email = "vertex-runner@approved-news-project.iam.gserviceaccount.com"

        def refresh(self, _request: object) -> None:
            events.append("refresh")
            self.token = "ya29.live-but-test-token"

    auth.default = lambda **_kwargs: (Credentials(), "approved-news-project")  # type: ignore[attr-defined]
    exceptions.GoogleAuthError = GoogleAuthError  # type: ignore[attr-defined]
    requests.Request = Request  # type: ignore[attr-defined]
    google.auth = auth  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.auth", auth)
    monkeypatch.setitem(sys.modules, "google.auth.exceptions", exceptions)
    monkeypatch.setitem(sys.modules, "google.auth.transport", transport)
    monkeypatch.setitem(sys.modules, "google.auth.transport.requests", requests)

    def cloud_get(url: str, token: str) -> dict[str, object]:
        assert token == "ya29.live-but-test-token"
        assert token not in url
        events.append(url)
        if "cloudbilling" in url:
            return {
                "billingAccountName": "billingAccounts/000000-AAAAAA-BBBBBB",
                "billingEnabled": True,
            }
        return {"state": "ENABLED"}

    monkeypatch.setattr(acceptance_module, "_cloud_get_json", cloud_get)

    result = probe_vertex_environment("approved-news-project")

    assert result.project == "approved-news-project"
    assert result.credential_type == "service_account"
    assert result.billing_enabled is True
    assert result.aiplatform_enabled is True
    assert events[0] == "refresh"
    assert len(events) == 3

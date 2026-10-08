"""Host composition probes; synthetic runtime boundaries, real SSH and SQLite.

These tests do not certify GPU/model/security readiness or authorize paid requests.
"""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import pytest

from hawedit.candidate_review import _canonical, _write
from hawedit.environment import HostLock
from hawedit.gemini import API_ROOT, Governance, VertexGeminiJudge
from hawedit.judge import KURDISH_EDITORIAL_JUDGE
from hawedit.models import CheckpointIntegrityReport
from hawedit.studio_authorization import SignedStudioTransport
from hawedit.studio_generation import ProducerSelection
from hawedit.studio_private import PrivateDirectory
from hawedit.workflow_recovery import ExternalReconciliationError
from hawedit.wsl_setup import WslRuntimeProbe, WslRuntimeReceipt, package_digest
from test_studio_authorization import (
    AuthorizationCase,
    ProtocolProbe,
    _replace,
)

pytest_plugins = ("test_studio_authorization",)

SELECTED = (
    "rzgar/qwen3-asr-sorani-kurdish-ckb-v1",
    "pyannote/speaker-diarization-community-1",
    "Qwen3-VL-Embedding-2B",
    "Qwen3-VL-Reranker-2B",
    "MCG-NJU/VideoChat3-4B",
    "MCG-NJU/TimeLens2-4B",
)
PRODUCERS = ProducerSelection("gemini", omni_asr_runtime="wsl", wsl_distro="Ubuntu")


def test_host_module_exposes_no_ready_flag() -> None:
    from hawedit import studio_host

    assert "ready" not in studio_host.__all__
    assert "StudioHostConfiguration" in studio_host.__all__


@pytest.fixture
def observation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    from hawedit import studio_host as host

    root = PrivateDirectory(tmp_path / "host-private")
    policy = root.path / "vex.json"
    _write(root, "vex.json", b'{"synthetic":"not-a-qualified-vex"}')
    calls: list[object] = []
    source = package_digest()
    lock = HostLock(
        root.path / "studio.lock",
        "a" * 64,
        "studio",
        sys.platform,
        (sys.version_info.major, sys.version_info.minor),
        (),
        "test",
        "b" * 64,
        (("test-dependency", "1.0"),),
    )
    receipt = WslRuntimeReceipt(
        root.path / "source",
        source,
        "test-generation",
        root.path / "generation",
        "Ubuntu",
        1000,
        "/home/test",
        "3.12.0",
        {"test-runtime": "1.0"},
        {"test.lock": "c" * 64},
        "/home/test/models",
        100,
        2,
    )
    probe = WslRuntimeProbe(receipt, 3, 100)
    state: dict[str, Any] = {
        "calls": calls,
        "root": root,
        "policy": policy,
        "lock": lock,
        "probe": probe,
        "source": source,
        "configuration": host.StudioHostConfiguration(PRODUCERS, policy, root.path),
    }

    def audit(profile: str) -> HostLock:
        calls.append(("profile", profile))
        result = state["lock"]
        assert isinstance(result, HostLock)
        return result

    def fingerprint(path: Path) -> str:
        calls.append(("champion", path))
        return "d" * 64

    class Store:
        root = state["root"].path / "models"

        def verify_checkpoint(self, model_id: str) -> CheckpointIntegrityReport:
            calls.append(("model", model_id))
            assert model_id in SELECTED
            return CheckpointIntegrityReport(model_id, "test/repository", "e" * 40, 2, 100)

    def live(*, evidence_path: Path, distro: str, vex_path: Path) -> dict[str, object]:
        calls.append(("live", distro, vex_path))
        document: dict[str, object] = {
            "schema": 1,
            "status": "accepted",
            "observed_at": evidence_path.name,
            "runtime": {
                "source_sha256": source,
                "generation": receipt.generation,
                "distro": receipt.distro,
                "uid": receipt.uid,
                "python_version": receipt.python_version,
                "package_count": len(receipt.packages),
                "packages_sha256": hashlib.sha256(_canonical(dict(receipt.packages))).hexdigest(),
                "dependency_locks": dict(receipt.dependency_locks),
                "assets_verified": probe.files_verified,
                "asset_bytes": probe.size_bytes,
                "cuda_device_count": receipt.cuda_device_count,
            },
            "policy": {"sha256": hashlib.sha256(policy.read_bytes()).hexdigest()},
        }
        _write(root, evidence_path.name, _canonical(document))
        state["last_evidence"] = evidence_path
        return document

    monkeypatch.setattr(host, "audit_installed_profile", audit)
    monkeypatch.setattr(host, "resolve_champion_adapter", lambda: root.path / "champion")
    monkeypatch.setattr(host, "adapter_fingerprint", fingerprint)
    monkeypatch.setattr(host, "ModelStore", Store)
    monkeypatch.setattr(host, "probe_wsl_runtime", lambda **kwargs: state["probe"])
    monkeypatch.setattr(host, "run_live_gate", live)
    monkeypatch.setattr(
        host, "assert_devices_available", lambda roles: calls.append(("devices", roles))
    )
    return state


def test_host_admission_composes_selected_producers(observation: dict[str, Any]) -> None:
    from hawedit import studio_host as host

    result = host.capture_studio_deployment(observation["configuration"])
    document = json.loads(result.canonical_json)
    assert result.sha256 == hashlib.sha256(result.canonical_json.encode()).hexdigest()
    assert document["pipeline_source_sha256"] == observation["source"]
    assert document["producers"] == asdict(PRODUCERS)
    assert document["studio_lock"]["sha256"] == observation["lock"].sha256
    assert [item["model_id"] for item in document["models"]] == list(SELECTED)
    assert observation["calls"].count(("profile", "studio")) == 2
    assert [call[1] for call in observation["calls"] if call[0] == "model"] == list(SELECTED) * 2
    assert ("live", "Ubuntu", observation["policy"]) in observation["calls"]
    devices = next(call[1] for call in observation["calls"] if call[0] == "devices")
    assert devices["the Path B reader"] == "cuda:0"
    assert devices["Stage 2 indexing"] == "cuda:1"
    assert devices["TimeLens2"] == "cuda:1"
    assert result.security_evidence_path == observation["last_evidence"]
    assert (
        result.security_evidence_sha256
        == hashlib.sha256(result.security_evidence_path.read_bytes()).hexdigest()
    )
    assert "authorization" not in document and "signature" not in document
    assert "status" not in document and "observed_at" not in document


@pytest.mark.parametrize(
    "runtime,distro", [("auto", "Ubuntu"), ("local", "Ubuntu"), ("wsl", None), ("wsl", "")]
)
def test_host_refuses_implicit_runtime_selection(
    observation: dict[str, Any], runtime: str, distro: str | None
) -> None:
    from hawedit import studio_host as host

    configuration = replace(
        observation["configuration"],
        producers=replace(PRODUCERS, omni_asr_runtime=runtime, wsl_distro=distro),
    )
    with pytest.raises(host.StudioHostError, match="configuration"):
        host.capture_studio_deployment(configuration)
    assert observation["calls"] == []
    assert not list(observation["root"].path.glob("admission-*.json"))


@pytest.mark.parametrize(
    "boundary", ["profile", "champion", "models", "runtime", "devices", "security"]
)
def test_host_admission_preserves_prerequisite_refusal(
    observation: dict[str, Any], monkeypatch: pytest.MonkeyPatch, boundary: str
) -> None:
    from hawedit import studio_host as host

    def refused(*args: object, **kwargs: object) -> Any:
        if boundary == "devices":
            raise SystemExit("synthetic missing device")
        raise RuntimeError("synthetic prerequisite refusal")

    targets = {
        "profile": "audit_installed_profile",
        "champion": "adapter_fingerprint",
        "models": "ModelStore",
        "runtime": "probe_wsl_runtime",
        "devices": "assert_devices_available",
        "security": "run_live_gate",
    }
    monkeypatch.setattr(host, targets[boundary], refused)
    with pytest.raises(host.StudioHostError, match=boundary) as error:
        host.capture_studio_deployment(observation["configuration"])
    assert isinstance(error.value.__cause__, RuntimeError | SystemExit)
    assert observation["policy"].read_bytes() == b'{"synthetic":"not-a-qualified-vex"}'
    assert not list(observation["root"].path.glob("admission-*.json"))


def test_host_deployment_identity_is_stable(observation: dict[str, Any]) -> None:
    from hawedit import studio_host as host

    first = host.capture_studio_deployment(observation["configuration"])
    second = host.capture_studio_deployment(observation["configuration"])
    assert first.sha256 == second.sha256 and first.canonical_json == second.canonical_json
    assert first.security_evidence_path != second.security_evidence_path
    assert first.security_evidence_sha256 != second.security_evidence_sha256


@pytest.mark.parametrize("damage", ["source", "vex", "runtime", "champion", "profile", "report"])
def test_host_admission_refuses_observed_drift(
    observation: dict[str, Any], monkeypatch: pytest.MonkeyPatch, damage: str
) -> None:
    from hawedit import studio_host as host

    original = vars(host)["run_live_gate"]

    def changed(**kwargs: Any) -> dict[str, object]:
        result: dict[str, object] = original(**kwargs)
        if damage == "source":
            monkeypatch.setattr(host, "package_digest", lambda: "f" * 64)
        elif damage == "vex":
            root = observation["root"]
            assert root.remove_owned("vex.json", root.member_identity("vex.json"))
            _write(root, "vex.json", b"changed policy")
        elif damage == "runtime":
            runtime = result["runtime"]
            assert isinstance(runtime, dict)
            result["runtime"] = {**runtime, "uid": 1001}
            path = observation["last_evidence"]
            root = observation["root"]
            assert root.remove_owned(path.name, root.member_identity(path.name))
            _write(root, path.name, _canonical(result))
        elif damage == "champion":
            monkeypatch.setattr(host, "adapter_fingerprint", lambda path: "f" * 64)
        elif damage == "profile":
            observation["lock"] = replace(observation["lock"], sha256="f" * 64)
        else:
            root = observation["root"]
            name = observation["last_evidence"].name
            assert root.remove_owned(name, root.member_identity(name))
            _write(root, name, b'{"status":"changed"}')
        return result

    monkeypatch.setattr(host, "run_live_gate", changed)
    with pytest.raises(host.StudioHostError):
        host.capture_studio_deployment(observation["configuration"])
    assert observation["last_evidence"].exists(), "Retain refused evidence rather than deleting it"


def _signed_host(
    case: AuthorizationCase, observation: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> tuple[Any, Any]:
    from hawedit import studio_host as host

    deployment = host.capture_studio_deployment(observation["configuration"])
    context = replace(case.context, expected_execution_binding_sha256=deployment.sha256)
    case.document["execution_binding_sha256"] = deployment.sha256
    case.sign()
    # Only capture is substituted here: route checks and real OpenSSH remain under test.
    monkeypatch.setattr(host, "capture_studio_deployment", lambda configuration: deployment)
    return deployment, context


@pytest.mark.parametrize(
    "route,confidential",
    [
        (
            "https://aiplatform.googleapis.com/v1/projects/test/locations/global/publishers/google/models/"
            + KURDISH_EDITORIAL_JUDGE,
            False,
        ),
        (API_ROOT + "/models/" + KURDISH_EDITORIAL_JUDGE, True),
    ],
)
def test_host_authorization_requires_exact_route_and_governance(
    authorization_case: AuthorizationCase,
    observation: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    route: str,
    confidential: bool,
) -> None:
    from hawedit import studio_host as host

    case = authorization_case
    _, context = _signed_host(case, observation, monkeypatch)
    case.document["billing"]["model_base_url"] = route
    case.document["governance"]["confidential"] = confidential
    case.sign()
    with pytest.raises((host.StudioHostError, RuntimeError)):
        host.load_studio_host_authorization(observation["configuration"], context)
    assert not (case.root.path / "billing.sqlite").exists()


@pytest.mark.parametrize("location", ["global", "us-central1"])
def test_host_vertex_route_matches_shared_producer(
    authorization_case: AuthorizationCase,
    observation: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    location: str,
) -> None:
    from hawedit import studio_host as host

    case = authorization_case
    producers = replace(
        PRODUCERS, provider="vertex", vertex_project="studio-project", vertex_location=location
    )
    configuration = replace(observation["configuration"], producers=producers)
    observation["configuration"] = configuration
    _, context = _signed_host(case, observation, monkeypatch)
    judge = VertexGeminiJudge("studio-project", location=location, governance=Governance())
    case.document["billing"]["model_base_url"] = judge._url("generateContent").removesuffix(
        ":generateContent"
    )
    case.sign()
    result = host.load_studio_host_authorization(configuration, context)
    assert result.authorization.policy.model_base_url == case.document["billing"]["model_base_url"]
    case.document["billing"]["model_base_url"] = (
        judge._url("generateContent")
        .replace("studio-project", "different-project")
        .removesuffix(":generateContent")
    )
    case.sign()
    with pytest.raises(host.StudioHostError, match="route"):
        host.load_studio_host_authorization(configuration, context)


def test_host_job_binding_includes_raw_proof(
    authorization_case: AuthorizationCase,
    observation: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hawedit import studio_host as host

    case = authorization_case
    deployment, context = _signed_host(case, observation, monkeypatch)
    first = host.load_studio_host_authorization(observation["configuration"], context)
    document = json.loads(first.execution_binding_json)
    assert document["deployment_sha256"] == deployment.sha256
    assert document["owner_document_sha256"] == first.authorization.document_sha256
    assert document["owner_signature_sha256"] == first.authorization.signature_sha256
    assert document["authority_policy_sha256"] == first.authorization.authority_policy_sha256
    assert document["allowed_signers_sha256"] == first.authorization.allowed_signers_sha256
    assert (
        first.execution_binding_sha256
        == hashlib.sha256(first.execution_binding_json.encode()).hexdigest()
    )
    case.document["billing"]["pool_microusd"] += 1
    case.sign()
    second = host.load_studio_host_authorization(observation["configuration"], context)
    assert second.deployment.sha256 == deployment.sha256
    assert second.execution_binding_sha256 != first.execution_binding_sha256


def test_host_transport_reopens_owner_authority(
    authorization_case: AuthorizationCase,
    observation: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hawedit import studio_host as host

    case = authorization_case
    _, context = _signed_host(case, observation, monkeypatch)
    receipt = host.load_studio_host_authorization(observation["configuration"], context)
    case.revoke()
    probe = ProtocolProbe(case)
    with pytest.raises(RuntimeError):
        host.prepare_studio_host_transport(
            observation["configuration"],
            context,
            billing_path=case.root.path / "billing.sqlite",
            job_id="studio-" + "a" * 64,
            expected_execution_binding_sha256=receipt.execution_binding_sha256,
            upstream=probe,
        )
    assert probe.requests == []
    assert not (case.root.path / "billing.sqlite").exists()


def test_host_transport_uses_signed_global_journal(
    authorization_case: AuthorizationCase,
    observation: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hawedit import studio_host as host

    case = authorization_case
    _, context = _signed_host(case, observation, monkeypatch)
    receipt = host.load_studio_host_authorization(observation["configuration"], context)
    probe = ProtocolProbe(case)
    path = case.root.path / "billing.sqlite"
    transport = host.prepare_studio_host_transport(
        observation["configuration"],
        context,
        billing_path=path,
        job_id="studio-" + "a" * 64,
        expected_execution_binding_sha256=receipt.execution_binding_sha256,
        upstream=probe,
    )
    assert transport.authorization_sha256 == receipt.authorization.document_sha256
    assert path.is_file() and probe.requests == []
    result = transport(
        transport.policy.model_base_url + ":generateContent",
        b'{"contents":[{"parts":[{"text":"protocol probe"}]}],"generationConfig":{}}',
        {"X-Probe": "local-only"},
    )
    assert result[0] == 200
    assert [request[0].rsplit(":", 1)[-1] for request in probe.requests] == [
        "countTokens",
        "generateContent",
    ]


def test_host_transport_refuses_binding_drift_before_storage(
    authorization_case: AuthorizationCase,
    observation: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hawedit import studio_host as host

    case = authorization_case
    _, context = _signed_host(case, observation, monkeypatch)
    probe = ProtocolProbe(case)
    with pytest.raises(host.StudioHostError, match="binding"):
        host.prepare_studio_host_transport(
            observation["configuration"],
            context,
            billing_path=case.root.path / "billing.sqlite",
            job_id="studio-" + "a" * 64,
            expected_execution_binding_sha256="0" * 64,
            upstream=probe,
        )
    assert not (case.root.path / "billing.sqlite").exists() and probe.requests == []


def test_host_refuses_vex_drift_during_owner_verification(
    authorization_case: AuthorizationCase,
    observation: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hawedit import studio_host as host

    case = authorization_case
    _, context = _signed_host(case, observation, monkeypatch)
    original = vars(host)["load_studio_authorization"]

    def changed(context: Any) -> Any:
        receipt = original(context)
        _replace(observation["root"], "vex.json", b"changed during owner verification")
        return receipt

    monkeypatch.setattr(host, "load_studio_authorization", changed)
    with pytest.raises(host.StudioHostError, match="drift"):
        host.load_studio_host_authorization(observation["configuration"], context)


def test_host_refuses_trust_drift_during_transport_construction(
    authorization_case: AuthorizationCase,
    observation: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hawedit import studio_host as host

    case = authorization_case
    _, context = _signed_host(case, observation, monkeypatch)
    receipt = host.load_studio_host_authorization(observation["configuration"], context)
    probe = ProtocolProbe(case)

    def changed(*args: Any, **kwargs: Any) -> SignedStudioTransport:
        transport = SignedStudioTransport(*args, **kwargs)
        policy = {**case.authority_policy, "max_authorization_age_seconds": 1800}
        _replace(case.authority, "policy.json", _canonical(policy))
        return transport

    monkeypatch.setattr(host, "SignedStudioTransport", changed)
    with pytest.raises(host.StudioHostError, match="authority changed"):
        host.prepare_studio_host_transport(
            observation["configuration"],
            context,
            billing_path=case.root.path / "billing.sqlite",
            job_id="studio-" + "a" * 64,
            expected_execution_binding_sha256=receipt.execution_binding_sha256,
            upstream=probe,
        )
    assert probe.requests == []


def test_host_transports_share_owner_budget_across_jobs(
    authorization_case: AuthorizationCase,
    observation: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hawedit import studio_host as host

    case = authorization_case
    _, context = _signed_host(case, observation, monkeypatch)
    case.document["billing"]["pool_microusd"] = 200
    case.sign()
    receipt = host.load_studio_host_authorization(observation["configuration"], context)
    probe = ProtocolProbe(case)
    transports = [
        host.prepare_studio_host_transport(
            observation["configuration"],
            context,
            billing_path=case.root.path / "billing.sqlite",
            job_id="studio-" + job * 64,
            expected_execution_binding_sha256=receipt.execution_binding_sha256,
            upstream=probe,
        )
        for job in ("a", "b")
    ]
    payload = b'{"contents":[{"parts":[{"text":"protocol probe"}]}],"generationConfig":{}}'
    route = receipt.authorization.policy.model_base_url + ":generateContent"
    assert transports[0](route, payload, {"X-Probe": "local-only"})[0] == 200
    with pytest.raises(ExternalReconciliationError, match="budget exhausted"):
        transports[1](route, payload, {"X-Probe": "local-only"})
    assert [request[0].rsplit(":", 1)[-1] for request in probe.requests] == [
        "countTokens",
        "generateContent",
        "countTokens",
    ]


def test_host_model_drift_after_security_scan_is_refused(
    observation: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    from hawedit import studio_host as host

    original = vars(host)["run_live_gate"]

    class ChangedStore:
        root = observation["root"].path / "models"

        def verify_checkpoint(self, model_id: str) -> CheckpointIntegrityReport:
            return CheckpointIntegrityReport(model_id, "test/repository", "f" * 40, 2, 100)

    def changed(**kwargs: Any) -> dict[str, object]:
        report: dict[str, object] = original(**kwargs)
        monkeypatch.setattr(host, "ModelStore", ChangedStore)
        return report

    monkeypatch.setattr(host, "run_live_gate", changed)
    with pytest.raises(host.StudioHostError, match="drift"):
        host.capture_studio_deployment(observation["configuration"])


def test_host_confidentiality_mismatch_on_valid_vertex_proof_refuses(
    authorization_case: AuthorizationCase,
    observation: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hawedit import studio_host as host

    case = authorization_case
    producers = replace(PRODUCERS, provider="vertex", vertex_project="studio-project")
    observation["configuration"] = replace(observation["configuration"], producers=producers)
    _, context = _signed_host(case, observation, monkeypatch)
    judge = VertexGeminiJudge("studio-project", governance=Governance())
    case.document["billing"]["model_base_url"] = judge._url("generateContent").removesuffix(
        ":generateContent"
    )
    case.document["governance"]["confidential"] = True
    case.sign()
    with pytest.raises(host.StudioHostError, match="confidentiality"):
        host.load_studio_host_authorization(observation["configuration"], context)
    assert not (case.root.path / "billing.sqlite").exists()

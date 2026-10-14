"""Selected producer admission and raw owner-route composition (D-305).

Descriptions are not capabilities. Every transport preparation repeats admission
and raw proof verification. This does not launch DBOS, enable HTTP, reconcile
effects, certify media tools or authorize publication.
"""

from __future__ import annotations

import hashlib
import json
import sys
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

from hawedit.asr import (
    adapter_fingerprint,
    fused_checkpoint_asset,
    resolve_champion_adapter,
    resolve_champion_checkpoint,
)
from hawedit.candidate_review import _canonical, _json, _read
from hawedit.environment import audit_installed_profile
from hawedit.gemini import API_ROOT, Governance, Transport, VertexGeminiJudge
from hawedit.judge import KURDISH_EDITORIAL_JUDGE
from hawedit.models import ModelStore
from hawedit.pipeline import assert_devices_available, build_parser
from hawedit.studio_authorization import (
    AuthorizationContext,
    ExecutionAuthorization,
    SignedStudioTransport,
    load_studio_authorization,
)
from hawedit.studio_generation import ProducerSelection
from hawedit.studio_private import PrivateDirectory
from hawedit.wsl_setup import package_digest, probe_wsl_runtime
from hawedit.wsl_vex_gate import (
    AUDIT_CONTRACT_SHA256,
    AUDIT_LOCK_SHA256,
    _read_bound,
    run_live_gate,
)

__all__ = [
    "AuthorizedStudioHost",
    "StudioDeployment",
    "StudioHostConfiguration",
    "StudioHostError",
    "capture_studio_deployment",
    "load_studio_host_authorization",
    "prepare_studio_host_transport",
]

_MODELS = (
    "rzgar/qwen3-asr-sorani-kurdish-ckb-v1",
    "pyannote/speaker-diarization-community-1",
    "Qwen3-VL-Embedding-2B",
    "Qwen3-VL-Reranker-2B",
    "MCG-NJU/VideoChat3-4B",
    "MCG-NJU/TimeLens2-4B",
)


class StudioHostError(RuntimeError):
    """Admission refused; original proof/work must remain available for inspection."""


@dataclass(frozen=True, slots=True)
class StudioHostConfiguration:
    """Host selection only. Never populate paths or producers from an HTTP request."""

    producers: ProducerSelection
    vex_path: Path
    evidence_dir: Path


@dataclass(frozen=True, slots=True)
class StudioDeployment:
    """Stable selected deployment description, plus one separate fresh observation."""

    canonical_json: str
    sha256: str
    security_evidence_path: Path
    security_evidence_sha256: str


@dataclass(frozen=True, slots=True)
class AuthorizedStudioHost:
    """Descriptive receipt, not reusable authority or a ready-to-run claim."""

    deployment: StudioDeployment
    authorization: ExecutionAuthorization
    execution_binding_json: str
    execution_binding_sha256: str


def _canonical_evidence_directory(
    original: PrivateDirectory, *, expected: PrivateDirectory | None = None
) -> PrivateDirectory:
    """Resolve packaged aliases only inside a repeatedly verified private identity."""
    original.verify()
    canonical = PrivateDirectory(original.path.resolve(strict=True), create=False)
    original.verify()
    canonical.verify()
    if (
        canonical.identity != original.identity
        or original.path.resolve(strict=True) != canonical.path
    ):
        raise StudioHostError("Studio evidence directory changed during canonicalization")
    if expected is not None:
        expected.verify()
        if canonical.path != expected.path or canonical.identity != expected.identity:
            raise StudioHostError("Studio evidence directory differs from original selection")
    original.verify()
    return canonical


def _studio_champion() -> dict[str, str]:
    """The champion record; a LoRA record is unchanged, a fused one names its kind (D-331)."""
    checkpoint = resolve_champion_checkpoint()
    if checkpoint is not None:
        return {
            "path": str(checkpoint.absolute()),
            "sha256": fused_checkpoint_asset(checkpoint).sha256,
            "kind": "fused",
        }
    champion = resolve_champion_adapter()
    return {"path": str(champion.absolute()), "sha256": adapter_fingerprint(champion)}


def capture_studio_deployment(configuration: StudioHostConfiguration) -> StudioDeployment:
    """Perform actual selected checks; never load a supplied accepted/ready receipt.

    Checkpoint and champion bytes are checked again after the real security audit.
    Actual loaders still need their held-file checks at consumption. Fresh audit
    timestamps/results are retained, not inserted into stable deployment identity.
    """
    stage = "configuration"
    try:
        producers = configuration.producers
        argv = producers.argv()
        if (
            producers.omni_asr_runtime != "wsl"
            or not isinstance(producers.wsl_distro, str)
            or not producers.wsl_distro.strip()
            or len(producers.wsl_distro) > 128
            or any(ord(char) < 32 for char in producers.wsl_distro)
        ):
            raise ValueError("Select explicit wsl and a named distribution for the protected host")
        args = build_parser().parse_args(["admission-only.mp4", *argv])
        original_evidence_dir = PrivateDirectory(configuration.evidence_dir, create=False)
        evidence_dir = _canonical_evidence_directory(original_evidence_dir)
        source = package_digest()
        policy_bytes = _read_bound(configuration.vex_path, limit=1_048_576, label="studio VEX")
        policy_digest = hashlib.sha256(policy_bytes).hexdigest()

        stage = "profile"
        lock = audit_installed_profile("studio")
        stage = "champion"
        champion = _studio_champion()
        stage = "models"
        store = ModelStore()
        models = tuple(store.verify_checkpoint(model_id) for model_id in _MODELS)
        stage = "runtime"
        probe = probe_wsl_runtime(distro=producers.wsl_distro)
        receipt = probe.receipt
        if receipt.source_sha256 != source or receipt.distro != producers.wsl_distro:
            raise ValueError("Selected WSL runtime differs from the current source/distribution")
        runtime = {
            "source_sha256": receipt.source_sha256,
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
        }
        stage = "devices"
        assert_devices_available(
            {
                "the Path B reader": args.visual_device,
                "Stage 2 indexing": args.index_device,
                "TimeLens2": args.timelens_device,
                "diarization": args.diarize_device,
            }
        )
        stage = "security"
        _canonical_evidence_directory(original_evidence_dir, expected=evidence_dir)
        evidence_path = evidence_dir.path / ("admission-" + uuid.uuid4().hex + ".json")
        evidence = run_live_gate(
            evidence_path=evidence_path,
            distro=producers.wsl_distro,
            vex_path=configuration.vex_path,
        )
        _canonical_evidence_directory(original_evidence_dir, expected=evidence_dir)
        raw_evidence = _read(evidence_dir, evidence_path.name, limit=8 * 1024**2)
        observed_runtime = evidence.get("runtime")
        observed_policy = evidence.get("policy")
        if (
            _json(raw_evidence) != evidence
            or evidence.get("status") != "accepted"
            or not isinstance(observed_runtime, dict)
            or any(observed_runtime.get(key) != value for key, value in runtime.items())
            or not isinstance(observed_policy, dict)
            or observed_policy.get("sha256") != policy_digest
        ):
            raise ValueError("Fresh security evidence differs from the selected observation")

        stage = "drift"
        _canonical_evidence_directory(original_evidence_dir, expected=evidence_dir)
        repeated_store = ModelStore()
        if (
            repeated_store.root != store.root
            or tuple(repeated_store.verify_checkpoint(model_id) for model_id in _MODELS) != models
            or _studio_champion() != champion
            or audit_installed_profile("studio") != lock
            or package_digest() != source
            or _read_bound(configuration.vex_path, limit=1_048_576, label="studio VEX")
            != policy_bytes
            or _read(evidence_dir, evidence_path.name, limit=8 * 1024**2) != raw_evidence
        ):
            raise ValueError("Studio admission inputs changed; reconciliation required")
        _canonical_evidence_directory(original_evidence_dir, expected=evidence_dir)
        descriptor = {
            "schema": 1,
            "purpose": "hawedit-studio-deployment-v1",
            "pipeline_source_sha256": source,
            "producers": asdict(producers),
            "studio_lock": {
                "sha256": lock.sha256,
                "contract_sha256": lock.contract_sha256,
                "platform": lock.platform,
                "python_version": list(lock.python_version),
                "requirements": [list(item) for item in lock.requirements],
            },
            "native_interpreter": {"path": sys.executable, "version": sys.version},
            "models_root": str(store.root.absolute()),
            "models": [asdict(model) for model in models],
            "champion": champion,
            "asr_runtime": {
                **runtime,
                "source_root": str(receipt.source_root.absolute()),
                "generation_root": str(receipt.generation_root.absolute()),
                "home": receipt.home,
                "asset_cache": receipt.asset_cache,
            },
            "security": {
                "vex_sha256": policy_digest,
                "audit_contract_sha256": AUDIT_CONTRACT_SHA256,
                "audit_lock_sha256": AUDIT_LOCK_SHA256,
            },
        }
        encoded = _canonical(descriptor)
        return StudioDeployment(
            encoded.decode("utf-8"),
            hashlib.sha256(encoded).hexdigest(),
            evidence_path,
            hashlib.sha256(raw_evidence).hexdigest(),
        )
    except (Exception, SystemExit) as exc:
        raise StudioHostError(f"Studio host {stage} refused; existing work preserved") from exc


def _check_deployment_bindings(
    configuration: StudioHostConfiguration, deployment: StudioDeployment
) -> None:
    descriptor = _json(deployment.canonical_json.encode("utf-8"))
    original_evidence_dir = PrivateDirectory(configuration.evidence_dir, create=False)
    evidence_dir = _canonical_evidence_directory(original_evidence_dir)
    if (
        _canonical(descriptor).decode("utf-8") != deployment.canonical_json
        or hashlib.sha256(deployment.canonical_json.encode("utf-8")).hexdigest()
        != deployment.sha256
        or descriptor["pipeline_source_sha256"] != package_digest()
        or descriptor["producers"] != asdict(configuration.producers)
        or descriptor["security"]["vex_sha256"]
        != hashlib.sha256(
            _read_bound(configuration.vex_path, limit=1_048_576, label="studio VEX")
        ).hexdigest()
        or deployment.security_evidence_path.parent != evidence_dir.path
        or hashlib.sha256(
            _read(evidence_dir, deployment.security_evidence_path.name, limit=8 * 1024**2)
        ).hexdigest()
        != deployment.security_evidence_sha256
    ):
        raise StudioHostError(
            "Studio deployment source/VEX/producer/evidence drift after verification"
        )
    _canonical_evidence_directory(original_evidence_dir, expected=evidence_dir)


def load_studio_host_authorization(
    configuration: StudioHostConfiguration, context: AuthorizationContext
) -> AuthorizedStudioHost:
    """Repeat real admission and raw signature verification, then require route parity."""
    deployment = capture_studio_deployment(configuration)
    if deployment.sha256 != context.expected_execution_binding_sha256:
        raise StudioHostError("Studio deployment binding differs from the configured owner context")
    authorization = load_studio_authorization(context)
    producers = configuration.producers
    if producers.provider == "vertex":
        judge = VertexGeminiJudge(
            producers.vertex_project or "",
            location=producers.vertex_location,
            governance=Governance(
                producers.confidential, producers.zero_data_retention, producers.zdr_confirmed_by
            ),
        )
        route = judge._url("generateContent").removesuffix(":generateContent")
    else:
        route = API_ROOT + "/models/" + KURDISH_EDITORIAL_JUDGE
    governance = json.loads(authorization.governance_json)
    if (
        authorization.policy.model_base_url != route
        or governance["confidential"] is not producers.confidential
    ):
        raise StudioHostError(
            "Signed owner route or confidentiality differs from selected producers"
        )
    _check_deployment_bindings(configuration, deployment)
    binding = _canonical(
        {
            "schema": 1,
            "purpose": "hawedit-studio-job-execution-v1",
            "deployment_sha256": deployment.sha256,
            "owner_document_sha256": authorization.document_sha256,
            "owner_signature_sha256": authorization.signature_sha256,
            "authority_policy_sha256": authorization.authority_policy_sha256,
            "allowed_signers_sha256": authorization.allowed_signers_sha256,
        }
    )
    return AuthorizedStudioHost(
        deployment, authorization, binding.decode("utf-8"), hashlib.sha256(binding).hexdigest()
    )


def prepare_studio_host_transport(
    configuration: StudioHostConfiguration,
    context: AuthorizationContext,
    *,
    billing_path: Path,
    job_id: str,
    expected_execution_binding_sha256: str,
    upstream: Transport,
) -> SignedStudioTransport:
    """Reopen admission/proof before constructing the existing shared-pool transport."""
    host = load_studio_host_authorization(configuration, context)
    if host.execution_binding_sha256 != expected_execution_binding_sha256:
        raise StudioHostError("Immutable job execution binding differs from current owner proof")
    transport = SignedStudioTransport(billing_path, job_id, context, upstream)
    if (
        transport.authorization_sha256 != host.authorization.document_sha256
        or transport.policy != host.authorization.policy
        or load_studio_authorization(context) != host.authorization
    ):
        raise StudioHostError("Owner authority changed during transport construction")
    _check_deployment_bindings(configuration, host.deployment)
    return transport

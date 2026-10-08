"""Real private evidence namespaces; these diagnostics grant no host authority."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from hawedit import studio_host as host
from hawedit.candidate_review import _canonical
from hawedit.studio_generation import ProducerSelection
from hawedit.studio_private import PrivateDirectory, StudioStorageError
from hawedit.wsl_setup import package_digest
from hawedit.wsl_vex_gate import LiveVexGateError, _preflight_new_evidence


def test_host_evidence_canonical_directory_preserves_private_identity(tmp_path: Path) -> None:
    original = PrivateDirectory(tmp_path / "canonical-private")
    canonical = host._canonical_evidence_directory(original)
    assert canonical.path == original.path.resolve(strict=True)
    assert canonical.identity == original.identity
    original.verify()
    canonical.verify()


def test_host_evidence_canonical_preflight_does_not_mint_evidence(tmp_path: Path) -> None:
    original = PrivateDirectory(tmp_path / "preflight-private")
    canonical = host._canonical_evidence_directory(original)
    path = canonical.path / "new-evidence.json"
    _preflight_new_evidence(path)
    assert not path.exists()
    assert not (original.path / path.name).exists()
    assert tuple(original.path.iterdir()) == ()
    original.verify()
    canonical.verify()


def test_host_evidence_canonicalization_refuses_foreign_expectation(tmp_path: Path) -> None:
    original = PrivateDirectory(tmp_path / "selected-private")
    foreign = PrivateDirectory(tmp_path / "foreign-expectation-private")
    with pytest.raises(host.StudioHostError, match="evidence"):
        host._canonical_evidence_directory(original, expected=foreign)
    original.verify()
    foreign.verify()


def test_host_evidence_canonical_preflight_preserves_existing_evidence(tmp_path: Path) -> None:
    original = PrivateDirectory(tmp_path / "existing-private")
    canonical = host._canonical_evidence_directory(original)
    expected = b'{"diagnostic":"not-accepted-security-evidence"}\n'
    with canonical.open_new_file("retained.json") as stream:
        stream.write(expected)
    identity = canonical.member_identity("retained.json")
    with pytest.raises(LiveVexGateError, match="overwrite"):
        _preflight_new_evidence(canonical.path / "retained.json")
    assert canonical.member_identity("retained.json") == identity
    assert (canonical.path / "retained.json").read_bytes() == expected
    original.verify()


def test_host_evidence_canonicalization_refuses_missing_original(tmp_path: Path) -> None:
    original = PrivateDirectory(tmp_path / "missing-private")
    displaced = tmp_path / "retained-missing-private"
    original.path.rename(displaced)
    with pytest.raises(StudioStorageError):
        host._canonical_evidence_directory(original)
    assert displaced.is_dir()
    assert not original.path.exists()


def test_host_evidence_canonicalization_refuses_replaced_original(tmp_path: Path) -> None:
    original = PrivateDirectory(tmp_path / "replaced-private")
    displaced = tmp_path / "retained-replaced-private"
    original.path.rename(displaced)
    replacement = PrivateDirectory(original.path)
    assert replacement.identity != original.identity
    with pytest.raises(StudioStorageError):
        host._canonical_evidence_directory(original)
    assert displaced.is_dir()
    replacement.verify()


def _evidence_binding(
    tmp_path: Path,
) -> tuple[host.StudioHostConfiguration, host.StudioDeployment]:
    original = PrivateDirectory(tmp_path / "binding-private")
    canonical = PrivateDirectory(original.path.resolve(strict=True), create=False)
    policy_bytes = b'{"unit":"not-qualified-vex"}\n'
    evidence_bytes = b'{"unit":"not-security-admission"}\n'
    for name, data in [("policy.json", policy_bytes), ("security.json", evidence_bytes)]:
        with canonical.open_new_file(name) as stream:
            stream.write(data)
    producers = ProducerSelection("gemini", omni_asr_runtime="wsl", wsl_distro="Ubuntu")
    configuration = host.StudioHostConfiguration(
        producers, original.path / "policy.json", original.path
    )
    descriptor = {
        "pipeline_source_sha256": package_digest(),
        "producers": asdict(producers),
        "security": {"vex_sha256": hashlib.sha256(policy_bytes).hexdigest()},
    }
    encoded = _canonical(descriptor).decode("utf-8")
    deployment = host.StudioDeployment(
        encoded,
        hashlib.sha256(encoded.encode()).hexdigest(),
        canonical.path / "security.json",
        hashlib.sha256(evidence_bytes).hexdigest(),
    )
    return configuration, deployment


def test_host_evidence_binding_accepts_actual_canonical_private_parent(tmp_path: Path) -> None:
    configuration, deployment = _evidence_binding(tmp_path)
    host._check_deployment_bindings(configuration, deployment)
    assert deployment.security_evidence_path.parent == configuration.evidence_dir.resolve(
        strict=True
    )


def test_host_evidence_binding_refuses_foreign_private_parent(tmp_path: Path) -> None:
    configuration, deployment = _evidence_binding(tmp_path)
    foreign = PrivateDirectory(tmp_path / "foreign-private")
    with foreign.open_new_file("security.json") as stream:
        stream.write(deployment.security_evidence_path.read_bytes())
    altered = replace(deployment, security_evidence_path=foreign.path / "security.json")
    with pytest.raises(host.StudioHostError, match="drift"):
        host._check_deployment_bindings(configuration, altered)
    assert deployment.security_evidence_path.exists()
    assert altered.security_evidence_path.exists()


def test_host_evidence_binding_refuses_changed_bytes(tmp_path: Path) -> None:
    configuration, deployment = _evidence_binding(tmp_path)
    deployment.security_evidence_path.write_bytes(b'{"unit":"altered-not-admission"}\n')
    with pytest.raises(host.StudioHostError, match="drift"):
        host._check_deployment_bindings(configuration, deployment)
    assert deployment.security_evidence_path.read_bytes() == b'{"unit":"altered-not-admission"}\n'

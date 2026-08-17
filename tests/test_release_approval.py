"""Release approval binds exact evidence but never creates or pushes a tag."""

from __future__ import annotations

import hashlib
import json
import subprocess
import zipfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import pytest

from hawedit.release_approval import (
    PreparedReleaseApproval,
    ReleaseApprovalError,
    prepare_release_approval,
    verify_release_approval,
)

OFFICIAL_REPOSITORY = "HawzhinBlanca/HawEdit"
RELEASE_RUN_ID = 771_245


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


def _project(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "project"
    root.mkdir()
    (root / "evidence").mkdir()
    (root / "pyproject.toml").write_text(
        '[project]\nname = "hawedit"\nversion = "0.1.0"\n', encoding="utf-8"
    )
    (root / "BLOCKED.md").write_text(
        "# Blockers\n\n## #1 — Human labels\n\nOPEN: licensed labels remain absent.\n",
        encoding="utf-8",
    )
    (root / "PROGRESS.md").write_text(
        "# Progress\n\nRelease engineering is built; human quality evidence remains partial.\n",
        encoding="utf-8",
    )
    (root / "evidence" / "versioned-immutable-release.md").write_text(
        "# Immutable release\n\nRollback is forward-only through a new patch version.\n",
        encoding="utf-8",
    )
    _git(root, "init")
    _git(root, "branch", "-M", "main")
    _git(root, "config", "user.email", "release-test@example.invalid")
    _git(root, "config", "user.name", "Release Test")
    _git(root, "add", "pyproject.toml", "BLOCKED.md", "PROGRESS.md", "evidence")
    _git(root, "commit", "-m", "candidate")
    return root, _git(root, "rev-parse", "HEAD")


def _canonical(document: Mapping[str, object]) -> bytes:
    return (json.dumps(document, indent=2, sort_keys=True) + "\n").encode()


def _bundle(tmp_path: Path, revision: str) -> Path:
    release = tmp_path / "release"
    release.mkdir()
    wheel = release / "hawedit-0.1.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(
            "hawedit-0.1.0.dist-info/METADATA",
            "Metadata-Version: 2.4\nName: hawedit\nVersion: 0.1.0\n\n",
        )
    wheel_sha = hashlib.sha256(wheel.read_bytes()).hexdigest()
    sbom = release / f"{wheel.name}.spdx.json"
    sbom.write_bytes(_canonical({"name": "hawedit", "spdxVersion": "SPDX-2.3"}))
    sbom_sha = hashlib.sha256(sbom.read_bytes()).hexdigest()
    provenance = release / "release-provenance.json"
    provenance.write_bytes(
        _canonical(
            {
                "builder": {
                    "backend": "setuptools==84.0.0",
                    "frontend": "pip==26.2.1",
                    "lock": "requirements/release-build.txt",
                    "lock_sha256": "1" * 64,
                    "python": "3.11.15",
                    "requirements": {"pip": "26.2.1", "setuptools": "84.0.0"},
                },
                "distribution": "hawedit",
                "gate": {
                    "branch": "main",
                    "completed_at": "2026-08-17T01:02:03Z",
                    "event": "push",
                    "job_id": 991,
                    "job_url": f"https://github.com/{OFFICIAL_REPOSITORY}/actions/runs/441/job/991",
                    "repository": OFFICIAL_REPOSITORY,
                    "revision": revision,
                    "run_attempt": 1,
                    "run_id": 441,
                    "url": f"https://github.com/{OFFICIAL_REPOSITORY}/actions/runs/441",
                    "workflow": ".github/workflows/gate.yml",
                },
                "revision": revision,
                "sbom": sbom.name,
                "sbom_format": "SPDX-2.3-json",
                "sbom_sha256": sbom_sha,
                "schema": 5,
                "sha256": wheel_sha,
                "size_bytes": wheel.stat().st_size,
                "source_date_epoch": 1_775_000_000,
                "version": "0.1.0",
                "wheel": wheel.name,
            }
        )
    )
    provenance_sha = hashlib.sha256(provenance.read_bytes()).hexdigest()
    (release / "SHA256SUMS").write_text(
        f"{wheel_sha}  {wheel.name}\n"
        f"{sbom_sha}  {sbom.name}\n"
        f"{provenance_sha}  {provenance.name}\n",
        encoding="ascii",
    )
    return release


def _github(revision: str) -> Callable[[str], Mapping[str, object]]:
    def read(url: str) -> Mapping[str, object]:
        if url.endswith(f"/actions/runs/{RELEASE_RUN_ID}"):
            return {
                "conclusion": "success",
                "event": "workflow_run",
                "head_branch": "main",
                "head_repository": {"full_name": OFFICIAL_REPOSITORY},
                "head_sha": revision,
                "id": RELEASE_RUN_ID,
                "path": ".github/workflows/release.yml",
                "run_attempt": 1,
                "status": "completed",
                "updated_at": "2026-08-17T02:03:04Z",
            }
        if url.endswith(f"/actions/runs/{RELEASE_RUN_ID}/jobs?per_page=100"):
            return {
                "jobs": [
                    {"conclusion": "success", "id": 1, "name": "build-release"},
                    {"conclusion": "success", "id": 2, "name": "smoke-release (3.11)"},
                    {"conclusion": "success", "id": 3, "name": "smoke-release (3.12)"},
                    {"conclusion": "success", "id": 4, "name": "attest-release"},
                    {"conclusion": "success", "id": 5, "name": "publish-release"},
                ],
                "total_count": 5,
            }
        raise AssertionError(f"unexpected GitHub URL {url}")

    return read


class _Attestations:
    def __init__(self, *, fail_at: int | None = None) -> None:
        self.commands: list[tuple[str, ...]] = []
        self.fail_at = fail_at

    def __call__(self, command: Sequence[str]) -> str:
        self.commands.append(tuple(command))
        if self.fail_at == len(self.commands):
            raise ReleaseApprovalError("attestation verification failed")
        return json.dumps({"verificationResult": "verified"})


def _prepare(
    tmp_path: Path,
) -> tuple[Path, Path, str, _Attestations, PreparedReleaseApproval]:
    project, revision = _project(tmp_path)
    release = _bundle(tmp_path, revision)
    attestations = _Attestations()
    prepared = prepare_release_approval(
        project_root=project,
        release_dir=release,
        output_dir=tmp_path / "approval-packet",
        release_run_id=RELEASE_RUN_ID,
        github_json=_github(revision),
        attestation_verifier=attestations,
    )
    return project, release, revision, attestations, prepared


def test_prepare_binds_exact_bundle_run_attestations_and_leaves_owner_unset(
    tmp_path: Path,
) -> None:
    project, release, revision, attestations, prepared = _prepare(tmp_path)
    packet = prepared  # retain the public dataclass shape in this end-to-end test
    manifest_bytes = packet.manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    template = json.loads(packet.approval_template_path.read_text(encoding="utf-8"))

    assert project.is_dir() and release.is_dir()
    assert {path.name for path in packet.directory.iterdir()} == {
        "INSTRUCTIONS.txt",
        "owner-approval.template.json",
        "release-approval.json",
        "tag-commands.txt",
    }
    assert manifest["revision"] == revision
    assert manifest["version"] == "0.1.0"
    assert manifest["tag"] == "v0.1.0"
    assert manifest["release_run"]["id"] == RELEASE_RUN_ID
    assert manifest["release_run"]["required_jobs"] == {
        "attest-release": [4],
        "build-release": [1],
        "publish-release": [5],
        "smoke-release (3.11)": [2],
        "smoke-release (3.12)": [3],
    }
    assert set(manifest["payloads"]) == {
        "SHA256SUMS",
        "hawedit-0.1.0-py3-none-any.whl",
        "hawedit-0.1.0-py3-none-any.whl.spdx.json",
        "release-provenance.json",
    }
    assert len(attestations.commands) == 4
    for command in attestations.commands:
        assert command[:3] == ("gh", "attestation", "verify")
        assert "--source-digest" in command and revision in command
        assert "--signer-digest" in command and "--deny-self-hosted-runners" in command
    assert template["packet_manifest_sha256"] == hashlib.sha256(manifest_bytes).hexdigest()
    assert template["approved_at_utc"] is None
    assert template["approved_by"] is None
    assert template["rationale"] is None
    assert template["selected_action"] is None
    assert template["allowed_actions"] == ["approve_exact_tag", "reject_release"]
    assert all(item["acknowledged"] is None for item in template["risk_acknowledgements"])
    assert "git push origin refs/tags/v0.1.0" in packet.tag_commands_path.read_text()
    assert _git(project, "tag", "--list") == ""


@pytest.mark.parametrize("mutation", ["changed", "extra", "hardlink"])
def test_prepare_refuses_untrusted_bundle_before_network(tmp_path: Path, mutation: str) -> None:
    project, revision = _project(tmp_path)
    release = _bundle(tmp_path, revision)
    if mutation == "changed":
        wheel = release / "hawedit-0.1.0-py3-none-any.whl"
        wheel.write_bytes(wheel.read_bytes() + b"changed")
    elif mutation == "extra":
        (release / "unexpected.bin").write_bytes(b"extra")
    else:
        victim = tmp_path / "external"
        victim.write_bytes((release / "release-provenance.json").read_bytes())
        (release / "release-provenance.json").unlink()
        (release / "release-provenance.json").hardlink_to(victim)
    calls = 0

    def no_network(_url: str) -> Mapping[str, object]:
        nonlocal calls
        calls += 1
        raise AssertionError("network must follow local byte validation")

    with pytest.raises(ReleaseApprovalError):
        prepare_release_approval(
            project_root=project,
            release_dir=release,
            output_dir=tmp_path / "packet",
            release_run_id=RELEASE_RUN_ID,
            github_json=no_network,
            attestation_verifier=_Attestations(),
        )
    assert calls == 0


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("head_sha", "0" * 40, "revision"),
        ("head_branch", "feature", "main"),
        ("conclusion", "failure", "successful"),
        ("path", ".github/workflows/other.yml", "workflow"),
    ],
)
def test_prepare_refuses_wrong_hosted_release_identity(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    project, revision = _project(tmp_path)
    release = _bundle(tmp_path, revision)
    healthy = _github(revision)

    def changed(url: str) -> Mapping[str, object]:
        document = dict(healthy(url))
        if url.endswith(f"/actions/runs/{RELEASE_RUN_ID}"):
            document[field] = value
        return document

    with pytest.raises(ReleaseApprovalError, match=message):
        prepare_release_approval(
            project_root=project,
            release_dir=release,
            output_dir=tmp_path / "packet",
            release_run_id=RELEASE_RUN_ID,
            github_json=changed,
            attestation_verifier=_Attestations(),
        )


def test_prepare_refuses_missing_job_or_failed_attestation(tmp_path: Path) -> None:
    project, revision = _project(tmp_path)
    release = _bundle(tmp_path, revision)
    healthy = _github(revision)

    def missing_job(url: str) -> Mapping[str, object]:
        document = dict(healthy(url))
        if url.endswith("/jobs?per_page=100"):
            jobs = document.get("jobs")
            if not isinstance(jobs, list):
                raise AssertionError("healthy fixture lost its jobs array")
            document["jobs"] = jobs[1:]
            document["total_count"] = 4
        return document

    with pytest.raises(ReleaseApprovalError, match="build-release"):
        prepare_release_approval(
            project_root=project,
            release_dir=release,
            output_dir=tmp_path / "missing-job",
            release_run_id=RELEASE_RUN_ID,
            github_json=missing_job,
            attestation_verifier=_Attestations(),
        )
    with pytest.raises(ReleaseApprovalError, match="attestation"):
        prepare_release_approval(
            project_root=project,
            release_dir=release,
            output_dir=tmp_path / "bad-attestation",
            release_run_id=RELEASE_RUN_ID,
            github_json=healthy,
            attestation_verifier=_Attestations(fail_at=3),
        )


def test_packet_is_deterministic_and_never_overwrites(tmp_path: Path) -> None:
    project, revision = _project(tmp_path)
    release = _bundle(tmp_path, revision)
    first = prepare_release_approval(
        project_root=project,
        release_dir=release,
        output_dir=tmp_path / "first",
        release_run_id=RELEASE_RUN_ID,
        github_json=_github(revision),
        attestation_verifier=_Attestations(),
    )
    second = prepare_release_approval(
        project_root=project,
        release_dir=release,
        output_dir=tmp_path / "second",
        release_run_id=RELEASE_RUN_ID,
        github_json=_github(revision),
        attestation_verifier=_Attestations(),
    )
    assert {path.name: path.read_bytes() for path in first.directory.iterdir()} == {
        path.name: path.read_bytes() for path in second.directory.iterdir()
    }
    with pytest.raises(ReleaseApprovalError, match="already exists"):
        prepare_release_approval(
            project_root=project,
            release_dir=release,
            output_dir=first.directory,
            release_run_id=RELEASE_RUN_ID,
            github_json=_github(revision),
            attestation_verifier=_Attestations(),
        )


def test_packet_is_deterministic_across_equivalent_attestation_json(tmp_path: Path) -> None:
    project, revision = _project(tmp_path)
    release = _bundle(tmp_path, revision)

    def compact(_command: Sequence[str]) -> str:
        return '{"z":2,"a":1}'

    def pretty(_command: Sequence[str]) -> str:
        return '{\n  "a": 1,\n  "z": 2\n}\n'

    first = prepare_release_approval(
        project_root=project,
        release_dir=release,
        output_dir=tmp_path / "compact",
        release_run_id=RELEASE_RUN_ID,
        github_json=_github(revision),
        attestation_verifier=compact,
    )
    second = prepare_release_approval(
        project_root=project,
        release_dir=release,
        output_dir=tmp_path / "pretty",
        release_run_id=RELEASE_RUN_ID,
        github_json=_github(revision),
        attestation_verifier=pretty,
    )
    assert {path.name: path.read_bytes() for path in first.directory.iterdir()} == {
        path.name: path.read_bytes() for path in second.directory.iterdir()
    }


def _signed_approval(
    tmp_path: Path, template: Path, *, complete: bool = True
) -> tuple[Path, Path, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    approval = tmp_path / "owner-approval.json"
    document = json.loads(template.read_text(encoding="utf-8"))
    document["approved_at_utc"] = "2026-08-17T03:04:05Z"
    document["approved_by"] = "hawedit-release-owner"
    document["rationale"] = "Exact candidate reviewed for a private single-user release."
    document["selected_action"] = "approve_exact_tag"
    for risk in document["risk_acknowledgements"]:
        risk["acknowledged"] = True
    if not complete:
        document["risk_acknowledgements"][0]["acknowledged"] = None
    approval.write_bytes(_canonical(document))
    key = tmp_path / "owner-key"
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)], check=True)
    allowed = tmp_path / "allowed_signers"
    public_key = (tmp_path / "owner-key.pub").read_text(encoding="ascii").strip()
    allowed.write_text(f"hawedit-release-owner {public_key}\n", encoding="ascii")
    signature = tmp_path / "owner-approval.json.sig"
    subprocess.run(
        [
            "ssh-keygen",
            "-Y",
            "sign",
            "-f",
            str(key),
            "-n",
            "hawedit-release-approval",
            str(approval),
        ],
        check=True,
        capture_output=True,
    )
    Path(f"{approval}.sig").replace(signature)
    return approval, signature, allowed


def test_verify_requires_complete_signed_approval_and_revalidates_everything(
    tmp_path: Path,
) -> None:
    project, release, revision, _, prepared = _prepare(tmp_path)
    approval, signature, allowed = _signed_approval(tmp_path, prepared.approval_template_path)
    authorization = verify_release_approval(
        project_root=project,
        packet_dir=prepared.directory,
        release_dir=release,
        approval_path=approval,
        signature_path=signature,
        allowed_signers_path=allowed,
        github_json=_github(revision),
        attestation_verifier=_Attestations(),
    )

    assert authorization["status"] == "signed-owner-authorization-verified"
    assert authorization["revision"] == revision
    assert authorization["tag"] == "v0.1.0"
    commands = authorization["commands"]
    assert isinstance(commands, list)
    assert commands[-1] == "git push origin refs/tags/v0.1.0"
    assert _git(project, "tag", "--list") == ""

    incomplete, incomplete_signature, incomplete_allowed = _signed_approval(
        tmp_path / "incomplete", prepared.approval_template_path, complete=False
    )
    with pytest.raises(ReleaseApprovalError, match="acknowledge"):
        verify_release_approval(
            project_root=project,
            packet_dir=prepared.directory,
            release_dir=release,
            approval_path=incomplete,
            signature_path=incomplete_signature,
            allowed_signers_path=incomplete_allowed,
            github_json=_github(revision),
            attestation_verifier=_Attestations(),
        )


def test_verify_refuses_changed_bundle_or_signature(tmp_path: Path) -> None:
    project, release, revision, _, prepared = _prepare(tmp_path)
    approval, signature, allowed = _signed_approval(tmp_path, prepared.approval_template_path)
    signature.write_bytes(signature.read_bytes() + b"changed")
    with pytest.raises(ReleaseApprovalError, match="signature"):
        verify_release_approval(
            project_root=project,
            packet_dir=prepared.directory,
            release_dir=release,
            approval_path=approval,
            signature_path=signature,
            allowed_signers_path=allowed,
            github_json=_github(revision),
            attestation_verifier=_Attestations(),
        )


@pytest.mark.parametrize("name", ["INSTRUCTIONS.txt", "tag-commands.txt"])
def test_verify_refuses_changed_human_facing_packet_files(tmp_path: Path, name: str) -> None:
    project, release, revision, _, prepared = _prepare(tmp_path)
    approval, signature, allowed = _signed_approval(tmp_path, prepared.approval_template_path)
    target = prepared.directory / name
    target.write_bytes(target.read_bytes() + b"\nmalicious alternate command\n")

    with pytest.raises(ReleaseApprovalError, match="packet"):
        verify_release_approval(
            project_root=project,
            packet_dir=prepared.directory,
            release_dir=release,
            approval_path=approval,
            signature_path=signature,
            allowed_signers_path=allowed,
            github_json=_github(revision),
            attestation_verifier=_Attestations(),
        )

    approval, signature, allowed = _signed_approval(
        tmp_path / "second-signature", prepared.approval_template_path
    )
    checksum = release / "SHA256SUMS"
    checksum.write_bytes(checksum.read_bytes() + b"changed")
    with pytest.raises(ReleaseApprovalError):
        verify_release_approval(
            project_root=project,
            packet_dir=prepared.directory,
            release_dir=release,
            approval_path=approval,
            signature_path=signature,
            allowed_signers_path=allowed,
            github_json=_github(revision),
            attestation_verifier=_Attestations(),
        )

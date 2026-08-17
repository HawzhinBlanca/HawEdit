"""Human release approval over exact artifacts, without creating or pushing a tag.

The release workflow remains the only builder, attester and publisher.  This module independently
checks its four-file output and hosted identity, writes an explicitly unset owner packet, and later
verifies a detached OpenSSH approval.  Even a valid approval only returns commands for a human to
run; importing or invoking this module cannot mutate Git or GitHub.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from email.parser import BytesParser
from pathlib import Path
from typing import Final
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from hawedit.atomic_fs import rename_directory_noreplace
from hawedit.cli import machine_readable_stdout, program_name, use_utf8_streams

__all__ = [
    "PreparedReleaseApproval",
    "ReleaseApprovalError",
    "prepare_release_approval",
    "verify_release_approval",
]

_SCHEMA: Final = 1
_OFFICIAL_REPOSITORY: Final = "HawzhinBlanca/HawEdit"
_RELEASE_WORKFLOW: Final = ".github/workflows/release.yml"
_GATE_WORKFLOW: Final = ".github/workflows/gate.yml"
_API_ROOT: Final = f"https://api.github.com/repos/{_OFFICIAL_REPOSITORY}"
_REQUIRED_JOBS: Final = (
    "attest-release",
    "build-release",
    "publish-release",
    "smoke-release (3.11)",
    "smoke-release (3.12)",
)
_DOCUMENT_PATHS: Final = (
    "BLOCKED.md",
    "PROGRESS.md",
    "evidence/versioned-immutable-release.md",
)
_MAX_JSON_BYTES: Final = 4 * 1024 * 1024
_MAX_DOCUMENT_BYTES: Final = 16 * 1024 * 1024
_MAX_WHEEL_BYTES: Final = 256 * 1024 * 1024
_MAX_GITHUB_BYTES: Final = 4 * 1024 * 1024
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_HEX_40 = re.compile(r"^[0-9a-f]{40}$")
_SEMVER = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
_CHECKSUM_LINE = re.compile(r"^([0-9a-f]{64})  ([A-Za-z0-9][A-Za-z0-9._+-]*)$")

_RESIDUAL_RISKS: Final = (
    {
        "id": "human-quality-and-rights-evidence-remains-external",
        "description": (
            "A green release proves software and artifact controls, not labelled Sorani accuracy, "
            "editorial quality, client-media rights, gated-model acceptance or contractual ZDR."
        ),
    },
    {
        "id": "native-wsl-build-outputs-not-bit-reproducible",
        "description": (
            "The WSL ASR graph is source-hash/name/version bound, but locally compiled KenLM and "
            "Sox bytes are not bit-reproducibly attested."
        ),
    },
    {
        "id": "immutable-release-rollback-is-forward-only",
        "description": (
            "A published immutable version is never deleted, overwritten or retagged; rollback "
            "requires a reviewed new patch version."
        ),
    },
    {
        "id": "exact-tag-creation-is-the-publication-authorization",
        "description": (
            "Pushing the exact annotated version tag authorizes the existing release workflow to "
            "publish the already attested bytes."
        ),
    },
)


class ReleaseApprovalError(RuntimeError):
    """Release evidence or owner authorization is incomplete or inconsistent."""


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Request,
        fp: object,
        code: int,
        msg: str,
        headers: object,
        newurl: str,
    ) -> None:
        del req, fp, code, msg, headers, newurl
        return None


_GITHUB_OPENER = build_opener(_RejectRedirects)


GitHubJson = Callable[[str], Mapping[str, object]]
AttestationVerifier = Callable[[Sequence[str]], str]


@dataclass(frozen=True, slots=True)
class PreparedReleaseApproval:
    directory: Path
    manifest_path: Path
    approval_template_path: Path
    tag_commands_path: Path


@dataclass(frozen=True, slots=True)
class _FileEvidence:
    path: Path
    sha256: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class _Candidate:
    release_dir: Path
    wheel: _FileEvidence
    sbom: _FileEvidence
    provenance: _FileEvidence
    checksums: _FileEvidence
    provenance_document: dict[str, object]
    revision: str
    version: str
    tag: str


def _canonical_json(document: Mapping[str, object]) -> bytes:
    return (json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode()


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    document: dict[str, object] = {}
    for key, value in pairs:
        if key in document:
            raise ReleaseApprovalError(f"duplicate JSON field {key!r}")
        document[key] = value
    return document


def _strict_object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ReleaseApprovalError(f"{label} must be one JSON object")
    return value


def _exact_keys(document: Mapping[str, object], expected: set[str], label: str) -> None:
    actual = set(document)
    if actual != expected:
        raise ReleaseApprovalError(
            f"{label} fields differ: missing={sorted(expected - actual)!r}, "
            f"unexpected={sorted(actual - expected)!r}"
        )


def _text(document: Mapping[str, object], key: str, label: str) -> str:
    value = document.get(key)
    if (
        not isinstance(value, str)
        or not value
        or value.strip() != value
        or any(character in value for character in "\r\n\0")
    ):
        raise ReleaseApprovalError(f"{label}.{key} must be one nonblank line")
    return value


def _integer(document: Mapping[str, object], key: str, label: str, *, minimum: int = 1) -> int:
    value = document.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ReleaseApprovalError(f"{label}.{key} must be an integer >= {minimum}")
    return value


def _identity(info: os.stat_result) -> tuple[int, int, int, int, int]:
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_nlink)


def _is_reparse(info: os.stat_result) -> bool:
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(getattr(info, "st_file_attributes", 0) & reparse)


def _regular_file(path: Path, label: str) -> os.stat_result:
    try:
        info = os.lstat(path)
    except OSError as exc:
        raise ReleaseApprovalError(f"cannot inspect {label} {path}: {exc}") from exc
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode) or _is_reparse(info):
        raise ReleaseApprovalError(f"{label} must be one real regular file: {path}")
    if info.st_nlink != 1:
        raise ReleaseApprovalError(f"{label} must not be hardlinked: {path}")
    return info


def _read_bound(path: Path, label: str, *, max_bytes: int) -> bytes:
    before_path = _regular_file(path, label)
    if before_path.st_size > max_bytes:
        raise ReleaseApprovalError(f"{label} exceeds the {max_bytes}-byte limit")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ReleaseApprovalError(f"cannot open {label} {path}: {exc}") from exc
    try:
        before_fd = os.fstat(descriptor)
        if _identity(before_fd) != _identity(before_path):
            raise ReleaseApprovalError(f"{label} changed while opening: {path}")
        chunks: list[bytes] = []
        total = 0
        while chunk := os.read(descriptor, min(1024 * 1024, max_bytes + 1 - total)):
            chunks.append(chunk)
            total += len(chunk)
            if total > max_bytes:
                raise ReleaseApprovalError(f"{label} exceeds the {max_bytes}-byte limit")
        after_fd = os.fstat(descriptor)
        if (
            _identity(after_fd) != _identity(before_fd)
            or after_fd.st_ctime_ns != before_fd.st_ctime_ns
        ):
            raise ReleaseApprovalError(f"{label} changed while reading: {path}")
    finally:
        os.close(descriptor)
    after_path = _regular_file(path, label)
    if (
        _identity(after_path) != _identity(before_path)
        or after_path.st_ctime_ns != before_path.st_ctime_ns
    ):
        raise ReleaseApprovalError(f"{label} path changed while reading: {path}")
    return b"".join(chunks)


def _digest(path: Path, label: str) -> _FileEvidence:
    before_path = _regular_file(path, label)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ReleaseApprovalError(f"cannot open {label} {path}: {exc}") from exc
    digest = hashlib.sha256()
    try:
        before_fd = os.fstat(descriptor)
        if _identity(before_fd) != _identity(before_path):
            raise ReleaseApprovalError(f"{label} changed while opening: {path}")
        while chunk := os.read(descriptor, 1024 * 1024):
            digest.update(chunk)
        after_fd = os.fstat(descriptor)
        if (
            _identity(after_fd) != _identity(before_fd)
            or after_fd.st_ctime_ns != before_fd.st_ctime_ns
        ):
            raise ReleaseApprovalError(f"{label} changed while hashing: {path}")
    finally:
        os.close(descriptor)
    after_path = _regular_file(path, label)
    if (
        _identity(after_path) != _identity(before_path)
        or after_path.st_ctime_ns != before_path.st_ctime_ns
    ):
        raise ReleaseApprovalError(f"{label} path changed while hashing: {path}")
    return _FileEvidence(path=path, sha256=digest.hexdigest(), size_bytes=before_path.st_size)


def _json_file(path: Path, label: str) -> tuple[dict[str, object], bytes]:
    payload = _read_bound(path, label, max_bytes=_MAX_JSON_BYTES)
    try:
        value = json.loads(payload.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReleaseApprovalError(f"{label} is not strict UTF-8 JSON: {exc}") from exc
    return _strict_object(value, label), payload


def _real_directory(path: Path, label: str) -> Path:
    absolute = Path(os.path.abspath(path))
    try:
        info = os.lstat(absolute)
    except OSError as exc:
        raise ReleaseApprovalError(f"cannot inspect {label} {absolute}: {exc}") from exc
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or _is_reparse(info):
        raise ReleaseApprovalError(f"{label} must be one real directory: {absolute}")
    return absolute


def _git(root: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, timeout=30, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ReleaseApprovalError(f"cannot inspect candidate Git checkout: {exc}") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().replace("\n", " ")[:512]
        raise ReleaseApprovalError(f"cannot inspect candidate Git checkout: {detail}")
    return result.stdout.strip()


def _project_identity(project_root: Path, revision: str, version: str) -> dict[str, object]:
    root = _real_directory(project_root, "candidate project root")
    if _git(root, "status", "--porcelain", "--untracked-files=all"):
        raise ReleaseApprovalError("candidate project checkout must be clean")
    if _git(root, "rev-parse", "HEAD") != revision:
        raise ReleaseApprovalError("candidate checkout HEAD does not match release revision")
    if _git(root, "branch", "--show-current") != "main":
        raise ReleaseApprovalError("candidate checkout must be on protected main")
    pyproject = _read_bound(
        root / "pyproject.toml", "candidate pyproject", max_bytes=_MAX_JSON_BYTES
    )
    try:
        pyproject_document = tomllib.loads(pyproject.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ReleaseApprovalError("candidate pyproject is not valid UTF-8 TOML") from exc
    project = pyproject_document.get("project")
    if not isinstance(project, dict):
        raise ReleaseApprovalError("candidate pyproject must contain one [project] table")
    if project.get("name") != "hawedit" or project.get("version") != version:
        raise ReleaseApprovalError("candidate pyproject version does not match the release")
    documents: dict[str, object] = {}
    for relative in _DOCUMENT_PATHS:
        payload = _read_bound(
            root / relative, f"candidate document {relative}", max_bytes=_MAX_DOCUMENT_BYTES
        )
        documents[relative] = {
            "sha256": hashlib.sha256(payload).hexdigest(),
            "size_bytes": len(payload),
        }
    return {"documents": documents, "root_revision": revision}


def _wheel_identity(expected: _FileEvidence) -> tuple[str, str]:
    payload = _read_bound(expected.path, "release wheel", max_bytes=_MAX_WHEEL_BYTES)
    measured_sha256 = hashlib.sha256(payload).hexdigest()
    if len(payload) != expected.size_bytes or measured_sha256 != expected.sha256:
        raise ReleaseApprovalError("release wheel changed after its measured identity was captured")
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            names = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
            if len(names) != 1:
                raise ReleaseApprovalError("release wheel must contain exactly one METADATA file")
            metadata = BytesParser().parsebytes(archive.read(names[0]))
    except (OSError, KeyError, zipfile.BadZipFile) as exc:
        raise ReleaseApprovalError(f"release wheel is not a valid wheel archive: {exc}") from exc
    name = str(metadata.get("Name", "")).strip()
    version = str(metadata.get("Version", "")).strip()
    if name != "hawedit" or not _SEMVER.fullmatch(version):
        raise ReleaseApprovalError("release wheel must be HawEdit with strict MAJOR.MINOR.PATCH")
    return name, version


def _parse_checksums(payload: bytes) -> dict[str, str]:
    try:
        text = payload.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ReleaseApprovalError("SHA256SUMS must be ASCII") from exc
    lines = text.splitlines()
    if len(lines) != 3 or not text.endswith("\n"):
        raise ReleaseApprovalError("SHA256SUMS must contain exactly three newline-terminated rows")
    parsed: dict[str, str] = {}
    for line in lines:
        match = _CHECKSUM_LINE.fullmatch(line)
        if match is None or match.group(2) in parsed:
            raise ReleaseApprovalError("SHA256SUMS has malformed or duplicate entries")
        parsed[match.group(2)] = match.group(1)
    return parsed


def _validate_gate(gate_value: object, revision: str) -> dict[str, object]:
    gate = _strict_object(gate_value, "release provenance gate")
    expected = {
        "branch",
        "completed_at",
        "event",
        "job_id",
        "job_url",
        "repository",
        "revision",
        "run_attempt",
        "run_id",
        "url",
        "workflow",
    }
    _exact_keys(gate, expected, "release provenance gate")
    required_text = {
        "branch": "main",
        "event": "push",
        "repository": _OFFICIAL_REPOSITORY,
        "revision": revision,
        "workflow": _GATE_WORKFLOW,
    }
    for field, required in required_text.items():
        if _text(gate, field, "release provenance gate") != required:
            raise ReleaseApprovalError(f"release provenance gate {field} is not {required!r}")
    for field in ("completed_at", "job_url", "url"):
        _text(gate, field, "release provenance gate")
    _integer(gate, "job_id", "release provenance gate")
    _integer(gate, "run_attempt", "release provenance gate")
    _integer(gate, "run_id", "release provenance gate")
    return gate


def _candidate(release_dir: Path) -> _Candidate:
    root = _real_directory(release_dir, "release artifact directory")
    try:
        entries = tuple(root.iterdir())
    except OSError as exc:
        raise ReleaseApprovalError(f"cannot enumerate release artifact directory: {exc}") from exc
    wheel_paths = [path for path in entries if path.name.endswith(".whl")]
    if len(wheel_paths) != 1:
        raise ReleaseApprovalError("release artifact must contain exactly one wheel")
    wheel_path = wheel_paths[0]
    expected_names = {
        wheel_path.name,
        f"{wheel_path.name}.spdx.json",
        "release-provenance.json",
        "SHA256SUMS",
    }
    actual_names = {path.name for path in entries}
    if actual_names != expected_names:
        missing = sorted(expected_names - actual_names)
        unexpected = sorted(actual_names - expected_names)
        raise ReleaseApprovalError(
            f"release artifact file set differs: missing={missing!r}, unexpected={unexpected!r}"
        )
    checksums = _digest(root / "SHA256SUMS", "release checksum manifest")
    checksum_rows = _parse_checksums(
        _read_bound(root / "SHA256SUMS", "release checksum manifest", max_bytes=16 * 1024)
    )
    if set(checksum_rows) != expected_names - {"SHA256SUMS"}:
        raise ReleaseApprovalError("SHA256SUMS names do not match the release payload set")
    wheel = _digest(wheel_path, "release wheel")
    sbom = _digest(root / f"{wheel_path.name}.spdx.json", "release SBOM")
    provenance = _digest(root / "release-provenance.json", "release provenance")
    evidence = {item.path.name: item for item in (wheel, sbom, provenance)}
    for name, expected in checksum_rows.items():
        if evidence[name].sha256 != expected:
            raise ReleaseApprovalError(f"release checksum mismatch for {name}")
    document, _ = _json_file(provenance.path, "release provenance")
    top_fields = {
        "builder",
        "distribution",
        "gate",
        "revision",
        "sbom",
        "sbom_format",
        "sbom_sha256",
        "schema",
        "sha256",
        "size_bytes",
        "source_date_epoch",
        "version",
        "wheel",
    }
    _exact_keys(document, top_fields, "release provenance")
    if _integer(document, "schema", "release provenance") != 5:
        raise ReleaseApprovalError("release provenance schema must be 5")
    if _text(document, "distribution", "release provenance") != "hawedit":
        raise ReleaseApprovalError("release provenance distribution must be hawedit")
    revision = _text(document, "revision", "release provenance")
    if not _HEX_40.fullmatch(revision):
        raise ReleaseApprovalError("release provenance revision must be one lowercase Git SHA")
    version = _text(document, "version", "release provenance")
    if not _SEMVER.fullmatch(version):
        raise ReleaseApprovalError("release provenance version must be strict MAJOR.MINOR.PATCH")
    if _text(document, "wheel", "release provenance") != wheel.path.name:
        raise ReleaseApprovalError("release provenance wheel name does not match the bundle")
    if _text(document, "sbom", "release provenance") != sbom.path.name:
        raise ReleaseApprovalError("release provenance SBOM name does not match the bundle")
    expected_values: tuple[tuple[str, object], ...] = (
        ("sha256", wheel.sha256),
        ("size_bytes", wheel.size_bytes),
        ("sbom_format", "SPDX-2.3-json"),
        ("sbom_sha256", sbom.sha256),
    )
    for field, expected_value in expected_values:
        if document.get(field) != expected_value:
            raise ReleaseApprovalError(f"release provenance {field} does not match the bundle")
    _integer(document, "source_date_epoch", "release provenance")
    _strict_object(document.get("builder"), "release provenance builder")
    _validate_gate(document.get("gate"), revision)
    wheel_distribution, wheel_version = _wheel_identity(wheel)
    if wheel_distribution != "hawedit" or wheel_version != version:
        raise ReleaseApprovalError("wheel METADATA does not match release provenance")
    return _Candidate(
        release_dir=root,
        wheel=wheel,
        sbom=sbom,
        provenance=provenance,
        checksums=checksums,
        provenance_document=document,
        revision=revision,
        version=version,
        tag=f"v{version}",
    )


def _github_json(url: str) -> Mapping[str, object]:
    if not url.startswith(f"{_API_ROOT}/"):
        raise ReleaseApprovalError("refusing a GitHub API URL outside the official repository")
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "hawedit-release-approval"}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, headers=headers, method="GET")
    try:
        with _GITHUB_OPENER.open(request, timeout=30) as response:
            if response.geturl() != url:
                raise ReleaseApprovalError("GitHub API redirect refused")
            payload = response.read(_MAX_GITHUB_BYTES + 1)
    except HTTPError as exc:
        if 300 <= exc.code < 400:
            raise ReleaseApprovalError("GitHub API redirect refused") from exc
        raise ReleaseApprovalError(
            f"GitHub API refused release evidence with HTTP {exc.code}"
        ) from exc
    except (OSError, URLError) as exc:
        raise ReleaseApprovalError(f"GitHub API release-evidence lookup failed: {exc}") from exc
    if len(payload) > _MAX_GITHUB_BYTES:
        raise ReleaseApprovalError("GitHub API release evidence exceeded the response limit")
    try:
        value = json.loads(payload.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReleaseApprovalError("GitHub API returned invalid release evidence") from exc
    return _strict_object(value, "GitHub API release evidence")


def _hosted_release(
    revision: str, release_run_id: int, github_json: GitHubJson
) -> dict[str, object]:
    if isinstance(release_run_id, bool) or release_run_id <= 0:
        raise ReleaseApprovalError("release run id must be a positive integer")
    run = dict(github_json(f"{_API_ROOT}/actions/runs/{release_run_id}"))
    if _integer(run, "id", "release workflow run") != release_run_id:
        raise ReleaseApprovalError("release workflow run id does not match the requested run")
    expected_text = {
        "status": "completed",
        "conclusion": "success",
        "event": "workflow_run",
        "head_branch": "main",
        "head_sha": revision,
        "path": _RELEASE_WORKFLOW,
    }
    for field, expected in expected_text.items():
        if _text(run, field, "release workflow run") != expected:
            description = "successful" if field == "conclusion" else expected
            field_description = "revision" if field == "head_sha" else field
            raise ReleaseApprovalError(
                f"release workflow run {field_description} does not match required {description!r}"
            )
    repository = _strict_object(run.get("head_repository"), "release head repository")
    if _text(repository, "full_name", "release head repository") != _OFFICIAL_REPOSITORY:
        raise ReleaseApprovalError("release run is not from the official repository")
    attempt = _integer(run, "run_attempt", "release workflow run")
    completed_at = _text(run, "updated_at", "release workflow run")
    jobs_response = dict(
        github_json(f"{_API_ROOT}/actions/runs/{release_run_id}/jobs?per_page=100")
    )
    jobs = jobs_response.get("jobs")
    if not isinstance(jobs, list) or any(not isinstance(job, dict) for job in jobs):
        raise ReleaseApprovalError("release workflow jobs response must contain a JSON array")
    if _integer(jobs_response, "total_count", "release workflow jobs", minimum=0) != len(jobs):
        raise ReleaseApprovalError("release workflow jobs response is truncated")
    by_name: dict[str, list[int]] = {}
    for raw in jobs:
        job = _strict_object(raw, "release workflow job")
        name = _text(job, "name", "release workflow job")
        if name not in _REQUIRED_JOBS:
            raise ReleaseApprovalError(f"unexpected release workflow job {name!r}")
        if _text(job, "conclusion", "release workflow job") != "success":
            raise ReleaseApprovalError(f"release workflow job {name!r} was not successful")
        by_name.setdefault(name, []).append(_integer(job, "id", "release workflow job"))
    if set(by_name) != set(_REQUIRED_JOBS) or any(len(ids) != 1 for ids in by_name.values()):
        missing = sorted(set(_REQUIRED_JOBS) - set(by_name))
        duplicates = sorted(name for name, ids in by_name.items() if len(ids) != 1)
        raise ReleaseApprovalError(
            f"release workflow required jobs differ: missing={missing!r}, duplicates={duplicates!r}"
        )
    return {
        "attempt": attempt,
        "completed_at": completed_at,
        "id": release_run_id,
        "required_jobs": {name: by_name[name] for name in sorted(by_name)},
        "url": f"https://github.com/{_OFFICIAL_REPOSITORY}/actions/runs/{release_run_id}",
    }


def _attestation_command(path: Path, revision: str) -> tuple[str, ...]:
    return (
        "gh",
        "attestation",
        "verify",
        str(path),
        "--repo",
        _OFFICIAL_REPOSITORY,
        "--signer-workflow",
        f"{_OFFICIAL_REPOSITORY}/{_RELEASE_WORKFLOW}",
        "--source-ref",
        "refs/heads/main",
        "--source-digest",
        revision,
        "--signer-digest",
        revision,
        "--deny-self-hosted-runners",
        "--format",
        "json",
    )


def _verify_attestation(command: Sequence[str]) -> str:
    environment = os.environ.copy()
    environment.update({"GH_PAGER": "cat", "NO_COLOR": "1"})
    try:
        result = subprocess.run(
            list(command),
            capture_output=True,
            text=True,
            errors="replace",
            timeout=60,
            check=False,
            env=environment,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ReleaseApprovalError(f"attestation verification failed: {exc}") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().replace("\n", " ")[:512]
        raise ReleaseApprovalError(f"attestation verification failed: {detail}")
    return result.stdout


def _attestations(
    candidate: _Candidate, verifier: AttestationVerifier
) -> tuple[dict[str, object], ...]:
    evidence: list[dict[str, object]] = []
    for item in sorted(
        (candidate.wheel, candidate.sbom, candidate.provenance, candidate.checksums),
        key=lambda value: value.path.name,
    ):
        command = _attestation_command(item.path, candidate.revision)
        try:
            output = verifier(command)
        except ReleaseApprovalError:
            raise
        except (OSError, subprocess.SubprocessError) as exc:
            raise ReleaseApprovalError(
                f"attestation verification failed for {item.path.name}"
            ) from exc
        try:
            parsed = json.loads(output)
        except json.JSONDecodeError as exc:
            raise ReleaseApprovalError(
                f"attestation verifier returned non-JSON evidence for {item.path.name}"
            ) from exc
        if parsed in ({}, [], None, False):
            raise ReleaseApprovalError(
                f"attestation verifier returned empty evidence for {item.path.name}"
            )
        canonical_evidence = json.dumps(
            parsed, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
        display = list(command)
        display[3] = f"$RELEASE_DIR/{item.path.name}"
        evidence.append(
            {
                "command": display,
                "output_sha256": hashlib.sha256(canonical_evidence).hexdigest(),
                "payload": item.path.name,
            }
        )
    return tuple(evidence)


def _commands(revision: str, version: str, tag: str) -> tuple[str, ...]:
    return (
        "git fetch origin main --tags",
        f'test "$(git rev-parse origin/main^{{commit}})" = "{revision}"',
        f'git tag -a {tag} {revision} -m "HawEdit {version} approved release"',
        f"git push origin refs/tags/{tag}",
    )


def _instructions() -> bytes:
    return (
        b"HAWEDIT RELEASE APPROVAL - UNSET\n\n"
        b"Review release-approval.json, the exact four payloads, all residual risks and the "
        b"forward-only rollback. Fill owner-approval.template.json without changing candidate "
        b"identity fields, sign its canonical bytes with OpenSSH namespace "
        b"hawedit-release-approval, then run the verify command. The verifier prints commands; "
        b"it never creates or pushes a tag.\n"
    )


def _approval_template(
    *, candidate: _Candidate, manifest_bytes: bytes, release_run_id: int
) -> dict[str, object]:
    return {
        "allowed_actions": ["approve_exact_tag", "reject_release"],
        "approved_at_utc": None,
        "approved_by": None,
        "packet_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "rationale": None,
        "release_run_id": release_run_id,
        "revision": candidate.revision,
        "risk_acknowledgements": [
            {"acknowledged": None, "id": risk["id"]} for risk in _RESIDUAL_RISKS
        ],
        "schema": _SCHEMA,
        "selected_action": None,
        "tag": candidate.tag,
        "version": candidate.version,
    }


def _tag_commands(candidate: _Candidate) -> bytes:
    return (
        "\n".join(_commands(candidate.revision, candidate.version, candidate.tag)) + "\n"
    ).encode("utf-8")


def _manifest(
    *,
    project: dict[str, object],
    candidate: _Candidate,
    release_run: dict[str, object],
    attestations: tuple[dict[str, object], ...],
) -> dict[str, object]:
    payloads = {
        item.path.name: {"sha256": item.sha256, "size_bytes": item.size_bytes}
        for item in (candidate.wheel, candidate.sbom, candidate.provenance, candidate.checksums)
    }
    return {
        "acceptance_boundary": (
            "verified candidate evidence and commands only; no tag, push or release approval exists"
        ),
        "attestations": list(attestations),
        "commands": list(_commands(candidate.revision, candidate.version, candidate.tag)),
        "gate": candidate.provenance_document["gate"],
        "payloads": payloads,
        "project": project,
        "release_run": release_run,
        "residual_risks": list(_RESIDUAL_RISKS),
        "revision": candidate.revision,
        "rollback": (
            "Forward-only: keep immutable prior releases and publish a reviewed new patch version; "
            "never delete, overwrite, move or reuse a production tag."
        ),
        "schema": _SCHEMA,
        "tag": candidate.tag,
        "version": candidate.version,
    }


def _write(path: Path, payload: bytes) -> None:
    try:
        with path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as exc:
        raise ReleaseApprovalError(f"cannot stage release approval file {path}: {exc}") from exc


def _publish(output_dir: Path, payloads: Mapping[str, bytes]) -> Path:
    destination = Path(os.path.abspath(output_dir))
    parent = _real_directory(destination.parent, "release approval parent")
    parent_identity = os.lstat(parent)
    if os.path.lexists(destination):
        raise ReleaseApprovalError(f"release approval output already exists at {destination}")
    try:
        staging = Path(
            tempfile.mkdtemp(prefix=f".{destination.name}.", suffix=".staging", dir=parent)
        )
    except OSError as exc:
        raise ReleaseApprovalError("cannot create release approval staging directory") from exc
    try:
        for name in sorted(payloads):
            _write(staging / name, payloads[name])
        if {path.name for path in staging.iterdir()} != set(payloads):
            raise ReleaseApprovalError("release approval staging file set changed")
        current_parent = os.lstat(parent)
        if (current_parent.st_dev, current_parent.st_ino) != (
            parent_identity.st_dev,
            parent_identity.st_ino,
        ):
            raise ReleaseApprovalError("release approval parent changed during publication")
        rename_directory_noreplace(staging, destination)
        published_parent = os.lstat(parent)
        if (published_parent.st_dev, published_parent.st_ino) != (
            parent_identity.st_dev,
            parent_identity.st_ino,
        ):
            raise ReleaseApprovalError("release approval parent changed during publication")
    except BaseException as primary:
        if staging.exists():
            try:
                shutil.rmtree(staging)
            except OSError as cleanup:
                primary.add_note(f"release approval staging cleanup also failed: {cleanup}")
        if isinstance(primary, FileExistsError):
            raise ReleaseApprovalError(
                f"release approval output already exists at {destination}"
            ) from primary
        if isinstance(primary, OSError):
            raise ReleaseApprovalError(
                f"cannot publish release approval {destination}"
            ) from primary
        raise
    return destination


def prepare_release_approval(
    *,
    project_root: Path,
    release_dir: Path,
    output_dir: Path,
    release_run_id: int,
    github_json: GitHubJson = _github_json,
    attestation_verifier: AttestationVerifier = _verify_attestation,
) -> PreparedReleaseApproval:
    """Verify one exact candidate and publish a packet with every owner field unset."""
    candidate = _candidate(release_dir)
    project = _project_identity(project_root, candidate.revision, candidate.version)
    release_run = _hosted_release(candidate.revision, release_run_id, github_json)
    attestations = _attestations(candidate, attestation_verifier)
    manifest = _manifest(
        project=project,
        candidate=candidate,
        release_run=release_run,
        attestations=attestations,
    )
    manifest_bytes = _canonical_json(manifest)
    template = _approval_template(
        candidate=candidate, manifest_bytes=manifest_bytes, release_run_id=release_run_id
    )
    payloads = {
        "INSTRUCTIONS.txt": _instructions(),
        "owner-approval.template.json": _canonical_json(template),
        "release-approval.json": manifest_bytes,
        "tag-commands.txt": _tag_commands(candidate),
    }
    directory = _publish(output_dir, payloads)
    return PreparedReleaseApproval(
        directory=directory,
        manifest_path=directory / "release-approval.json",
        approval_template_path=directory / "owner-approval.template.json",
        tag_commands_path=directory / "tag-commands.txt",
    )


def _parse_utc(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ReleaseApprovalError(f"{field} must be an RFC3339 UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ReleaseApprovalError(f"{field} is not a valid RFC3339 timestamp") from exc
    if parsed.utcoffset() != UTC.utcoffset(parsed):
        raise ReleaseApprovalError(f"{field} must be UTC")
    if parsed > datetime.now(UTC):
        raise ReleaseApprovalError(f"{field} must not be in the future")
    return value


def _verify_signature(
    *,
    approval_path: Path,
    approval_bytes: bytes,
    signature_path: Path,
    allowed_signers_path: Path,
    principal: str,
    ssh_keygen: str,
) -> tuple[str, str, str]:
    signature = _read_bound(signature_path, "release approval signature", max_bytes=1024 * 1024)
    allowed = _read_bound(allowed_signers_path, "release allowed signers", max_bytes=1024 * 1024)
    try:
        signature_text = signature.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ReleaseApprovalError(
            "release approval signature is not canonical OpenSSH ASCII"
        ) from exc
    if (
        re.fullmatch(
            r"-----BEGIN SSH SIGNATURE-----\n(?:[A-Za-z0-9+/=]+\n)+"
            r"-----END SSH SIGNATURE-----\n",
            signature_text,
        )
        is None
    ):
        raise ReleaseApprovalError("release approval signature is not canonical OpenSSH armor")
    try:
        result = subprocess.run(
            [
                ssh_keygen,
                "-Y",
                "verify",
                "-f",
                str(allowed_signers_path),
                "-I",
                principal,
                "-n",
                "hawedit-release-approval",
                "-s",
                str(signature_path),
            ],
            input=approval_bytes,
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ReleaseApprovalError(
            f"release approval signature verification failed: {exc}"
        ) from exc
    if result.returncode != 0:
        raise ReleaseApprovalError("release approval signature verification failed")
    return (
        hashlib.sha256(approval_bytes).hexdigest(),
        hashlib.sha256(signature).hexdigest(),
        hashlib.sha256(allowed).hexdigest(),
    )


def verify_release_approval(
    *,
    project_root: Path,
    packet_dir: Path,
    release_dir: Path,
    approval_path: Path,
    signature_path: Path,
    allowed_signers_path: Path,
    github_json: GitHubJson = _github_json,
    attestation_verifier: AttestationVerifier = _verify_attestation,
    ssh_keygen: str = "ssh-keygen",
) -> dict[str, object]:
    """Verify signed human approval and return commands without performing them."""
    packet_root = _real_directory(packet_dir, "release approval packet")
    expected_packet = {
        "INSTRUCTIONS.txt",
        "owner-approval.template.json",
        "release-approval.json",
        "tag-commands.txt",
    }
    if {path.name for path in packet_root.iterdir()} != expected_packet:
        raise ReleaseApprovalError("release approval packet file set changed")
    manifest, manifest_bytes = _json_file(
        packet_root / "release-approval.json", "release approval manifest"
    )
    candidate = _candidate(release_dir)
    project = _project_identity(project_root, candidate.revision, candidate.version)
    release_run_id = _integer(
        _strict_object(manifest.get("release_run"), "release approval run"),
        "id",
        "release approval run",
    )
    release_run = _hosted_release(candidate.revision, release_run_id, github_json)
    attestations = _attestations(candidate, attestation_verifier)
    expected_manifest = _manifest(
        project=project,
        candidate=candidate,
        release_run=release_run,
        attestations=attestations,
    )
    if manifest_bytes != _canonical_json(expected_manifest):
        raise ReleaseApprovalError("release approval manifest no longer matches current evidence")
    template, template_bytes = _json_file(
        packet_root / "owner-approval.template.json", "release owner template"
    )
    expected_template = _approval_template(
        candidate=candidate, manifest_bytes=manifest_bytes, release_run_id=release_run_id
    )
    if template_bytes != _canonical_json(expected_template):
        raise ReleaseApprovalError("release owner template no longer matches the verified packet")
    instructions = _read_bound(
        packet_root / "INSTRUCTIONS.txt", "release approval instructions", max_bytes=64 * 1024
    )
    if instructions != _instructions():
        raise ReleaseApprovalError("release approval packet instructions changed")
    tag_commands = _read_bound(
        packet_root / "tag-commands.txt", "release tag commands", max_bytes=64 * 1024
    )
    if tag_commands != _tag_commands(candidate):
        raise ReleaseApprovalError("release approval packet tag commands changed")
    approval, approval_bytes = _json_file(approval_path, "release owner approval")
    if set(approval) != set(template):
        raise ReleaseApprovalError("release owner approval fields differ from the template")
    fixed_fields = {
        "allowed_actions",
        "packet_manifest_sha256",
        "release_run_id",
        "revision",
        "schema",
        "tag",
        "version",
    }
    for field in fixed_fields:
        if approval.get(field) != template.get(field):
            raise ReleaseApprovalError(f"release owner approval changed fixed field {field}")
    if approval.get("packet_manifest_sha256") != hashlib.sha256(manifest_bytes).hexdigest():
        raise ReleaseApprovalError("release owner approval names the wrong packet manifest")
    principal = _text(approval, "approved_by", "release owner approval")
    _parse_utc(approval.get("approved_at_utc"), "release owner approval.approved_at_utc")
    _text(approval, "rationale", "release owner approval")
    action = _text(approval, "selected_action", "release owner approval")
    if approval.get("allowed_actions") != ["approve_exact_tag", "reject_release"] or action not in {
        "approve_exact_tag",
        "reject_release",
    }:
        raise ReleaseApprovalError("release owner approval selected an unsupported action")
    acknowledgements = approval.get("risk_acknowledgements")
    expected_ids = [risk["id"] for risk in _RESIDUAL_RISKS]
    if not isinstance(acknowledgements, list) or len(acknowledgements) != len(expected_ids):
        raise ReleaseApprovalError("release owner must acknowledge every residual risk")
    measured_ids: list[object] = []
    for raw in acknowledgements:
        item = _strict_object(raw, "release risk acknowledgement")
        _exact_keys(item, {"acknowledged", "id"}, "release risk acknowledgement")
        measured_ids.append(item.get("id"))
        if item.get("acknowledged") is not True:
            raise ReleaseApprovalError("release owner must acknowledge every residual risk")
    if measured_ids != expected_ids:
        raise ReleaseApprovalError("release owner risk acknowledgement identities changed")
    approval_sha, signature_sha, allowed_sha = _verify_signature(
        approval_path=approval_path,
        approval_bytes=approval_bytes,
        signature_path=signature_path,
        allowed_signers_path=allowed_signers_path,
        principal=principal,
        ssh_keygen=ssh_keygen,
    )
    commands = list(_commands(candidate.revision, candidate.version, candidate.tag))
    return {
        "allowed_signers_sha256": allowed_sha,
        "approval_sha256": approval_sha,
        "approved_at_utc": approval["approved_at_utc"],
        "approved_by": principal,
        "commands": commands if action == "approve_exact_tag" else [],
        "packet_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "revision": candidate.revision,
        "signature_sha256": signature_sha,
        "status": (
            "signed-owner-authorization-verified"
            if action == "approve_exact_tag"
            else "signed-owner-rejection-verified"
        ),
        "tag": candidate.tag,
        "version": candidate.version,
    }


def main(argv: Sequence[str] | None = None) -> int:
    use_utf8_streams()
    parser = argparse.ArgumentParser(
        prog=program_name("hawedit.release_approval"),
        description="Prepare or verify exact HawEdit release-owner approval without mutating Git",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare", help="verify artifacts and emit an unset packet")
    prepare.add_argument("--project-root", type=Path, required=True)
    prepare.add_argument("--release-dir", type=Path, required=True)
    prepare.add_argument("--output-dir", type=Path, required=True)
    prepare.add_argument("--release-run-id", type=int, required=True)
    verify = subparsers.add_parser("verify", help="verify the completed signed owner approval")
    verify.add_argument("--project-root", type=Path, required=True)
    verify.add_argument("--packet-dir", type=Path, required=True)
    verify.add_argument("--release-dir", type=Path, required=True)
    verify.add_argument("--approval", type=Path, required=True)
    verify.add_argument("--signature", type=Path, required=True)
    verify.add_argument("--allowed-signers", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        with machine_readable_stdout() as report_stream:
            if args.command == "prepare":
                prepared = prepare_release_approval(
                    project_root=args.project_root,
                    release_dir=args.release_dir,
                    output_dir=args.output_dir,
                    release_run_id=args.release_run_id,
                )
                document: dict[str, object] = {
                    "approval_template": str(prepared.approval_template_path),
                    "directory": str(prepared.directory),
                    "manifest": str(prepared.manifest_path),
                    "status": "prepared-owner-approval-unset",
                    "tag_commands": str(prepared.tag_commands_path),
                }
            else:
                document = verify_release_approval(
                    project_root=args.project_root,
                    packet_dir=args.packet_dir,
                    release_dir=args.release_dir,
                    approval_path=args.approval,
                    signature_path=args.signature,
                    allowed_signers_path=args.allowed_signers,
                )
            print(json.dumps(document, ensure_ascii=False, sort_keys=True), file=report_stream)
    except (ReleaseApprovalError, OSError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Build and publish a reproducible HawEdit wheel from one clean Git revision.

A successful ``pip wheel`` exit is not release evidence. This command requires an explicit,
successful canonical GitHub gate run for the exact clean ``main`` revision, derives
``SOURCE_DATE_EPOCH`` from that commit, builds twice in independent directories, requires the
wheel bytes to have the same SHA-256, inspects the archive for HawEdit's runtime data, and only
then atomically publishes a directory containing the wheel, an SPDX 2.3 SBOM, ``SHA256SUMS`` and
stable provenance JSON.

The output directory is write-once. Re-running against an existing release refuses instead of
replacing an artifact that may already have been distributed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from email.parser import BytesParser
from pathlib import Path, PurePosixPath
from typing import Final, cast
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from hawedit.cli import use_utf8_streams

__all__ = ["ReleaseArtifact", "ReleaseError", "build_reproducible_wheel", "main"]

_REQUIRED_WHEEL_MEMBERS: Final = (
    "hawedit/release.py",
    "share/hawedit/assets/fonts/NotoNaskhArabic-Regular.ttf",
    "share/hawedit/assets/fonts/OFL.txt",
    "share/hawedit/models/sources.json",
    "share/hawedit/models/revisions.json",
    "share/hawedit/models/integrity.json",
    "share/hawedit/requirements/host-base-linux-py311.txt",
    "share/hawedit/requirements/host-base-linux-py312.txt",
    "share/hawedit/requirements/host-base-windows-py311.txt",
    "share/hawedit/requirements/host-base-windows-py312.txt",
    "share/hawedit/requirements/host-models-linux-py311.txt",
    "share/hawedit/requirements/host-models-linux-py312.txt",
    "share/hawedit/requirements/host-models-windows-py311.txt",
    "share/hawedit/requirements/host-models-windows-py312.txt",
    "share/hawedit/requirements/host-gpu-windows-py311.txt",
    "share/hawedit/security/wsl-asr-vex.json",
    "share/hawedit/scripts/fetch-ffmpeg.sh",
)
_REQUIREMENT_NAME: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*")
_EXACT_REQUIREMENT_VERSION: Final = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]*(?:\[[^]]+\])?\s*==\s*([^,;\s*]+)(?:\s*;.*)?$"
)
_LOCKED_REQUIREMENT: Final = re.compile(
    r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s]+)\s+--hash=sha256:([0-9a-f]{64})$"
)
_BUILD_LOCK: Final = Path("requirements/release-build.txt")
_GITHUB_REPOSITORY: Final = "HawzhinBlanca/HawEdit"
_GATE_WORKFLOW: Final = ".github/workflows/gate.yml"
_GATE_JOB: Final = "gate"
_GATE_BRANCH: Final = "main"
_GITHUB_API: Final = f"https://api.github.com/repos/{_GITHUB_REPOSITORY}"
_MAX_GITHUB_RESPONSE_BYTES: Final = 2_000_000
_REQUIRED_GATE_STEPS: Final = (
    "install",
    "fetch the pinned ffmpeg (libass + HarfBuzz + FriBidi)",
    "gate",
    "the golden render must have run, not skipped",
    "Stage 0 must have run against real media, not skipped",
    "the pipeline must run over real media and refuse to claim completeness",
    "the gate must have left fresh test evidence",
    "the test-count floor must not have been ratcheted by this run",
)


class _RejectRedirects(HTTPRedirectHandler):
    """Never forward a release credential to a redirect target."""

    def redirect_request(self, *_args: object, **_kwargs: object) -> None:
        return None


_GITHUB_OPENER: Final = build_opener(_RejectRedirects())


class ReleaseError(RuntimeError):
    """The source or artifact is not strong enough to publish as a release."""


@dataclass(frozen=True, slots=True)
class ReleaseArtifact:
    output_dir: Path
    wheel: Path
    checksum_file: Path
    provenance_file: Path
    sbom_file: Path
    revision: str
    source_date_epoch: int
    sha256: str
    sbom_sha256: str
    provenance_sha256: str
    gate_run_id: int
    gate_run_url: str
    size_bytes: int
    build_python: str
    build_frontend: str
    build_backend: str
    build_lock_sha256: str
    distribution: str
    version: str

    def to_dict(self) -> dict[str, str | int]:
        return {
            "output_dir": str(self.output_dir),
            "wheel": str(self.wheel),
            "checksum_file": str(self.checksum_file),
            "provenance_file": str(self.provenance_file),
            "sbom_file": str(self.sbom_file),
            "revision": self.revision,
            "source_date_epoch": self.source_date_epoch,
            "sha256": self.sha256,
            "sbom_sha256": self.sbom_sha256,
            "provenance_sha256": self.provenance_sha256,
            "gate_run_id": self.gate_run_id,
            "gate_run_url": self.gate_run_url,
            "size_bytes": self.size_bytes,
            "build_python": self.build_python,
            "build_frontend": self.build_frontend,
            "build_backend": self.build_backend,
            "build_lock_sha256": self.build_lock_sha256,
            "distribution": self.distribution,
            "version": self.version,
        }


@dataclass(frozen=True, slots=True)
class _BuildIdentity:
    python: str
    frontend: str
    backend: str
    requirements: tuple[tuple[str, str], ...]
    lock_path: str
    lock_sha256: str

    def to_dict(self) -> dict[str, str | dict[str, str]]:
        return {
            "python": self.python,
            "frontend": self.frontend,
            "backend": self.backend,
            "requirements": dict(self.requirements),
            "lock": self.lock_path,
            "lock_sha256": self.lock_sha256,
        }


@dataclass(frozen=True, slots=True)
class _GateIdentity:
    repository: str
    workflow: str
    run_id: int
    run_attempt: int
    event: str
    branch: str
    revision: str
    url: str
    completed_at: str
    job_id: int
    job_url: str

    def to_dict(self) -> dict[str, str | int]:
        return {
            "repository": self.repository,
            "workflow": self.workflow,
            "run_id": self.run_id,
            "run_attempt": self.run_attempt,
            "event": self.event,
            "branch": self.branch,
            "revision": self.revision,
            "status": "completed",
            "conclusion": "success",
            "url": self.url,
            "completed_at": self.completed_at,
            "job": _GATE_JOB,
            "job_id": self.job_id,
            "job_url": self.job_url,
        }


def _run(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> str:
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise ReleaseError(f"could not run {command[0]!r}: {exc}") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[-2_000:]
        raise ReleaseError(
            f"command failed with exit {result.returncode}: {' '.join(command)}\n{detail}"
        )
    return result.stdout.strip()


def _github_json(url: str) -> dict[str, object]:
    """Read one bounded GitHub API object without making ``gh`` a runtime dependency."""
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "hawedit-release",
    }
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, headers=headers)
    try:
        with _GITHUB_OPENER.open(request, timeout=30) as response:
            payload = response.read(_MAX_GITHUB_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        raise ReleaseError(
            f"GitHub rejected gate evidence lookup with HTTP {exc.code}; "
            "check --gate-run-id and GITHUB_TOKEN"
        ) from exc
    except (OSError, URLError) as exc:
        raise ReleaseError(f"could not read gate evidence from GitHub: {exc}") from exc
    if len(payload) > _MAX_GITHUB_RESPONSE_BYTES:
        raise ReleaseError("GitHub gate evidence exceeded the 2 MB response limit")
    try:
        parsed: object = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReleaseError("GitHub returned malformed JSON for the gate evidence") from exc
    if not isinstance(parsed, dict):
        raise ReleaseError("GitHub gate evidence is not a JSON object")
    return cast(dict[str, object], parsed)


def _object_field(value: object, *, context: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ReleaseError(f"GitHub gate evidence has invalid {context}")
    return cast(dict[str, object], value)


def _text_field(source: dict[str, object], key: str, *, context: str) -> str:
    value = source.get(key)
    if not isinstance(value, str) or not value:
        raise ReleaseError(f"GitHub gate evidence has invalid {context}.{key}")
    return value


def _int_field(source: dict[str, object], key: str, *, context: str) -> int:
    value = source.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ReleaseError(f"GitHub gate evidence has invalid {context}.{key}")
    return value


def _verify_gate_run(revision: str, gate_run_id: int | None) -> _GateIdentity:
    """Require one official, completed canonical gate for this exact main-branch revision."""
    if isinstance(gate_run_id, bool) or not isinstance(gate_run_id, int) or gate_run_id <= 0:
        raise ReleaseError(
            "an explicit positive --gate-run-id is required; a clean commit is not proof it passed"
        )

    run_url = f"{_GITHUB_API}/actions/runs/{gate_run_id}"
    run = _github_json(run_url)
    if _int_field(run, "id", context="run") != gate_run_id:
        raise ReleaseError("GitHub returned a different gate run id than requested")
    repository = _object_field(run.get("repository"), context="run.repository")
    head_repository = _object_field(run.get("head_repository"), context="run.head_repository")
    if _text_field(repository, "full_name", context="run.repository") != _GITHUB_REPOSITORY:
        raise ReleaseError("gate run is not owned by the official HawEdit repository")
    if (
        _text_field(head_repository, "full_name", context="run.head_repository")
        != _GITHUB_REPOSITORY
    ):
        raise ReleaseError("gate run tested a fork rather than the official HawEdit repository")
    if _text_field(run, "path", context="run") != _GATE_WORKFLOW:
        raise ReleaseError(f"gate run did not use {_GATE_WORKFLOW}")
    if _text_field(run, "event", context="run") != "push":
        raise ReleaseError("release gate must be the push run, not a manual or pull-request run")
    branch = _text_field(run, "head_branch", context="run")
    if branch != _GATE_BRANCH:
        raise ReleaseError(f"release gate ran on {branch!r}, not {_GATE_BRANCH!r}")
    head_sha = _text_field(run, "head_sha", context="run")
    if head_sha != revision:
        raise ReleaseError(f"gate run tested {head_sha}, but the release source is {revision}")
    if _text_field(run, "status", context="run") != "completed":
        raise ReleaseError("gate run has not completed")
    if _text_field(run, "conclusion", context="run") != "success":
        raise ReleaseError("gate run did not conclude successfully")
    attempt = _int_field(run, "run_attempt", context="run")
    run_page = f"https://github.com/{_GITHUB_REPOSITORY}/actions/runs/{gate_run_id}"

    jobs = _github_json(f"{run_url}/jobs?per_page=100")
    raw_jobs = jobs.get("jobs")
    if isinstance(raw_jobs, str | bytes) or not isinstance(raw_jobs, list):
        raise ReleaseError("GitHub gate evidence has invalid jobs")
    total_jobs = _int_field(jobs, "total_count", context="jobs")
    if total_jobs != len(raw_jobs):
        raise ReleaseError(
            f"gate run reports {total_jobs} jobs but returned {len(raw_jobs)}; "
            "refusing incomplete paginated evidence"
        )
    job_objects = [
        _object_field(job, context=f"jobs[{index}]") for index, job in enumerate(raw_jobs)
    ]
    gate_jobs = [job for job in job_objects if _text_field(job, "name", context="job") == _GATE_JOB]
    if len(gate_jobs) != 1:
        raise ReleaseError(f"gate run contains {len(gate_jobs)} {_GATE_JOB!r} jobs; expected one")
    job = gate_jobs[0]
    if _text_field(job, "head_sha", context="job") != revision:
        raise ReleaseError("gate job revision does not match the release source")
    if _int_field(job, "run_attempt", context="job") != attempt:
        raise ReleaseError("gate job belongs to a different run attempt")
    if _text_field(job, "status", context="job") != "completed":
        raise ReleaseError("gate job has not completed")
    if _text_field(job, "conclusion", context="job") != "success":
        raise ReleaseError("gate job did not conclude successfully")

    raw_steps = job.get("steps")
    if isinstance(raw_steps, str | bytes) or not isinstance(raw_steps, list):
        raise ReleaseError("GitHub gate evidence has invalid job steps")
    steps: dict[str, list[dict[str, object]]] = {}
    for index, raw_step in enumerate(raw_steps):
        step = _object_field(raw_step, context=f"job.steps[{index}]")
        name = _text_field(step, "name", context=f"job.steps[{index}]")
        steps.setdefault(name, []).append(step)
    missing = [name for name in _REQUIRED_GATE_STEPS if name not in steps]
    if missing:
        raise ReleaseError("gate job omitted required step(s): " + ", ".join(missing))
    for name in _REQUIRED_GATE_STEPS:
        matches = steps[name]
        if len(matches) != 1:
            raise ReleaseError(f"gate job contains duplicate required step {name!r}")
        step = matches[0]
        if _text_field(step, "status", context=f"step {name!r}") != "completed":
            raise ReleaseError(f"required gate step {name!r} did not complete")
        if _text_field(step, "conclusion", context=f"step {name!r}") != "success":
            raise ReleaseError(f"required gate step {name!r} did not succeed")

    job_id = _int_field(job, "id", context="job")
    job_page = f"{run_page}/job/{job_id}"
    return _GateIdentity(
        repository=_GITHUB_REPOSITORY,
        workflow=_GATE_WORKFLOW,
        run_id=gate_run_id,
        run_attempt=attempt,
        event="push",
        branch=branch,
        revision=revision,
        url=run_page,
        completed_at=_text_field(job, "completed_at", context="job"),
        job_id=job_id,
        job_url=job_page,
    )


def _extract_git_archive(archive: Path, destination: Path, revision: str) -> None:
    """Extract only contained regular files/directories on every supported Python 3.11+."""
    root = destination.resolve()
    try:
        with tarfile.open(archive, mode="r:") as source:
            for member in source:
                relative = PurePosixPath(member.name)
                if (
                    not relative.parts
                    or relative.is_absolute()
                    or ".." in relative.parts
                    or "\\" in member.name
                ):
                    raise ReleaseError(
                        f"Git archive for {revision} contains unsafe path {member.name!r}"
                    )
                target = destination.joinpath(*relative.parts).resolve()
                if not target.is_relative_to(root):
                    raise ReleaseError(
                        f"Git archive for {revision} escapes its source root: {member.name!r}"
                    )
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                if not member.isreg():
                    raise ReleaseError(
                        f"Git archive for {revision} contains unsupported link/special member "
                        f"{member.name!r}"
                    )
                target.parent.mkdir(parents=True, exist_ok=True)
                incoming = source.extractfile(member)
                if incoming is None:
                    raise ReleaseError(f"Git archive for {revision} could not read {member.name!r}")
                with incoming, target.open("xb") as output:
                    shutil.copyfileobj(incoming, output, length=1024 * 1024)
                os.chmod(target, member.mode & 0o777)
                os.utime(target, (member.mtime, member.mtime))
    except ReleaseError:
        raise
    except (OSError, tarfile.TarError) as exc:
        raise ReleaseError(
            f"could not extract immutable source revision {revision}: {exc}"
        ) from exc


def _snapshot_source(project_root: Path, revision: str, destination: Path) -> None:
    """Export one immutable Git commit; never let live worktree bytes enter a wheel."""
    destination.mkdir(parents=True)
    archive = destination.parent / f".{destination.name}.tar"
    _run(
        [
            "git",
            "--no-replace-objects",
            "archive",
            "--format=tar",
            "--output",
            str(archive),
            revision,
        ],
        cwd=project_root,
    )
    try:
        _extract_git_archive(archive, destination, revision)
    finally:
        archive.unlink(missing_ok=True)
    if not (destination / "pyproject.toml").is_file():
        raise ReleaseError(f"Git archive for {revision} did not contain pyproject.toml")


def _source_identity(project_root: Path) -> tuple[str, int]:
    if not (project_root / "pyproject.toml").is_file():
        raise ReleaseError(f"no pyproject.toml at release root {project_root}")

    top = Path(_run(["git", "rev-parse", "--show-toplevel"], cwd=project_root)).resolve()
    if top != project_root:
        raise ReleaseError(
            f"release root {project_root} is not the Git root {top}; build the whole checkout"
        )

    dirty = _run(["git", "status", "--porcelain=v1", "--untracked-files=all"], cwd=project_root)
    if dirty:
        paths = ", ".join(line[3:] for line in dirty.splitlines()[:8])
        raise ReleaseError(
            f"refusing to release a dirty checkout ({paths}); commit explicit source paths first"
        )

    revision = _run(["git", "rev-parse", "--verify", "HEAD"], cwd=project_root)
    epoch_text = _run(["git", "show", "-s", "--format=%ct", "HEAD"], cwd=project_root)
    try:
        epoch = int(epoch_text)
    except ValueError as exc:
        raise ReleaseError(f"Git returned an invalid commit timestamp {epoch_text!r}") from exc
    if epoch < 315_532_800:  # ZIP timestamps cannot precede 1980-01-01.
        raise ReleaseError(f"commit timestamp {epoch} predates the wheel/ZIP timestamp range")
    return revision, epoch


def _locked_build_contract(project_root: Path) -> tuple[Path, tuple[tuple[str, str], ...], str]:
    """Require exact build pins and a hash for every release-builder package."""
    pyproject_path = project_root / "pyproject.toml"
    lock_path = project_root / _BUILD_LOCK
    if not lock_path.is_file():
        raise ReleaseError(f"release builder lock is missing: {lock_path}")
    try:
        project = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
        build_system = project["build-system"]
        raw_requires = build_system["requires"]
        backend = build_system["build-backend"]
    except (OSError, KeyError, TypeError, tomllib.TOMLDecodeError) as exc:
        raise ReleaseError(
            f"could not read the build-system contract from {pyproject_path}"
        ) from exc
    if not isinstance(build_system, dict) or not isinstance(raw_requires, list):
        raise ReleaseError("pyproject build-system must contain a requirements list")
    if not isinstance(backend, str) or not backend.strip():
        raise ReleaseError("pyproject build-system must name its build backend")

    declared: dict[str, str] = {}
    for requirement in raw_requires:
        if not isinstance(requirement, str):
            raise ReleaseError("every build-system requirement must be a string")
        match = _EXACT_REQUIREMENT_VERSION.fullmatch(requirement)
        if match is None:
            raise ReleaseError(
                f"release build requirement {requirement!r} is not exactly pinned; "
                "two builds under one ambient backend are not reproducibility evidence"
            )
        name = _requirement_name(requirement)
        normalized = _pypi_name(name)
        if normalized in declared:
            raise ReleaseError(f"duplicate build-system requirement {name!r}")
        declared[normalized] = match.group(1)

    locked: dict[str, str] = {}
    try:
        lock_lines = lock_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ReleaseError(f"could not read release builder lock {lock_path}: {exc}") from exc
    for line_number, raw_line in enumerate(lock_lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = _LOCKED_REQUIREMENT.fullmatch(line)
        if match is None:
            raise ReleaseError(
                f"{lock_path}:{line_number} must be one exact package and one SHA-256 hash"
            )
        name = _pypi_name(match.group(1))
        if name in locked:
            raise ReleaseError(f"duplicate release builder requirement {name!r}")
        locked[name] = match.group(2)
    if "pip" not in locked:
        raise ReleaseError("release builder lock must pin the pip build frontend")
    for name, version in declared.items():
        if locked.get(name) != version:
            raise ReleaseError(
                f"build-system requires {name}=={version}, but the release lock has "
                f"{name}=={locked.get(name)!s}"
            )
    backend_package = _pypi_name(backend.split(".", 1)[0])
    if backend_package not in declared:
        raise ReleaseError(
            f"build backend {backend!r} is not represented by an exact build-system requirement"
        )
    return lock_path, tuple(sorted(locked.items())), backend


def _create_locked_builder(
    project_root: Path, temporary_root: Path, bootstrap_python: Path
) -> tuple[Path, _BuildIdentity]:
    lock_path, requirements, backend_module = _locked_build_contract(project_root)
    _run([str(bootstrap_python), "-m", "venv", str(temporary_root)], cwd=project_root)
    builder_python = (
        temporary_root / "Scripts" / "python.exe"
        if os.name == "nt"
        else temporary_root / "bin" / "python"
    )
    if not builder_python.is_file():
        raise ReleaseError(f"builder venv did not create {builder_python}")
    install_env = os.environ.copy()
    install_env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    _run(
        [
            str(builder_python),
            "-m",
            "pip",
            "install",
            "--require-hashes",
            "--only-binary=:all:",
            "--no-deps",
            "--no-cache-dir",
            "-r",
            str(lock_path),
        ],
        cwd=project_root,
        env=install_env,
    )
    package_names = [name for name, _version in requirements]
    identity_script = (
        "import importlib.metadata as m, json, platform; "
        f"names={package_names!r}; "
        "print(json.dumps({'python': platform.python_version(), "
        "'packages': {name: m.version(name) for name in names}}, sort_keys=True))"
    )
    try:
        measured = json.loads(_run([str(builder_python), "-c", identity_script], cwd=project_root))
        measured_python = measured["python"]
        measured_packages = measured["packages"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ReleaseError("could not measure the locked release builder identity") from exc
    expected = dict(requirements)
    if measured_packages != expected:
        raise ReleaseError(
            f"locked builder resolved {measured_packages!r}, expected exactly {expected!r}"
        )
    backend_name = _pypi_name(backend_module.split(".", 1)[0])
    lock_relative = lock_path.relative_to(project_root).as_posix()
    return builder_python, _BuildIdentity(
        python=str(measured_python),
        frontend=f"pip=={expected['pip']}",
        backend=f"{backend_name}=={expected[backend_name]}",
        requirements=requirements,
        lock_path=lock_relative,
        lock_sha256=_sha256(lock_path),
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _build_once(project_root: Path, destination: Path, python: Path, epoch: int) -> Path:
    destination.mkdir()
    env = os.environ.copy()
    env.update(
        {
            "SOURCE_DATE_EPOCH": str(epoch),
            "PYTHONHASHSEED": "0",
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        }
    )
    _run(
        [
            str(python),
            "-m",
            "pip",
            "wheel",
            str(project_root),
            "--no-deps",
            "--no-build-isolation",
            "--no-cache-dir",
            "--wheel-dir",
            str(destination),
        ],
        cwd=project_root,
        env=env,
    )
    wheels = tuple(destination.glob("*.whl"))
    if len(wheels) != 1:
        raise ReleaseError(
            f"one source tree must produce exactly one wheel, found {len(wheels)} in {destination}"
        )
    return wheels[0]


def _validate_hawedit_wheel(wheel: Path) -> None:
    try:
        with zipfile.ZipFile(wheel) as archive:
            corrupt = archive.testzip()
            names = tuple(archive.namelist())
    except (OSError, zipfile.BadZipFile) as exc:
        raise ReleaseError(f"built wheel is not a readable ZIP archive: {wheel}") from exc
    if corrupt is not None:
        raise ReleaseError(f"built wheel contains a corrupt member: {corrupt}")
    if not any(name.endswith(".dist-info/METADATA") for name in names):
        raise ReleaseError("built wheel has no .dist-info/METADATA")
    missing = [
        required
        for required in _REQUIRED_WHEEL_MEMBERS
        if not any(name.endswith(required) for name in names)
    ]
    if missing:
        raise ReleaseError("built wheel is missing runtime files: " + ", ".join(missing))


def _wheel_metadata(wheel: Path) -> tuple[str, str, tuple[str, ...]]:
    try:
        with zipfile.ZipFile(wheel) as archive:
            members = tuple(
                name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
            )
            if len(members) != 1:
                raise ReleaseError(
                    f"built wheel must contain exactly one METADATA member, found {len(members)}"
                )
            message = BytesParser().parsebytes(archive.read(members[0]))
    except (OSError, zipfile.BadZipFile, KeyError) as exc:
        raise ReleaseError(f"could not read wheel metadata from {wheel}: {exc}") from exc
    name = str(message.get("Name", "")).strip()
    version = str(message.get("Version", "")).strip()
    if not name or not version:
        raise ReleaseError("built wheel METADATA must name the distribution and version")
    requirements = tuple(
        sorted(
            {str(value).strip() for value in cast(list[str], message.get_all("Requires-Dist", []))}
        )
    )
    if any(not requirement for requirement in requirements):
        raise ReleaseError("built wheel METADATA contains an empty Requires-Dist value")
    return name, version, requirements


def _project_identity(project_root: Path) -> tuple[str, str]:
    """Read the distribution identity the exact source revision authorizes."""
    path = project_root / "pyproject.toml"
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise ReleaseError(f"could not read release project identity from {path}: {exc}") from exc
    project = raw.get("project")
    if not isinstance(project, dict):
        raise ReleaseError("pyproject.toml must contain one [project] table")
    name = project.get("name")
    version = project.get("version")
    if not isinstance(name, str) or not name.strip() or name != name.strip():
        raise ReleaseError("pyproject.toml [project].name must be one nonblank trimmed string")
    if not isinstance(version, str) or not version.strip() or version != version.strip():
        raise ReleaseError("pyproject.toml [project].version must be one nonblank trimmed string")
    return name, version


def _wheel_filename_identity(wheel: Path) -> tuple[str, str]:
    """Return the distribution/version encoded by a PEP 427 wheel filename."""
    if not wheel.name.endswith(".whl"):
        raise ReleaseError(f"built artifact is not named as a wheel: {wheel.name}")
    stem = wheel.name.removesuffix(".whl")
    fields = stem.rsplit("-", 3)
    if len(fields) != 4 or any(not field for field in fields):
        raise ReleaseError(f"built wheel has a malformed filename: {wheel.name}")
    identity = fields[0].split("-")
    if len(identity) not in (2, 3) or any(not field for field in identity):
        raise ReleaseError(f"built wheel has a malformed distribution/version: {wheel.name}")
    return identity[0], identity[1]


def _assert_release_identity(project_root: Path, wheel: Path) -> tuple[str, str]:
    """Bind source, filename and METADATA to one distribution name and version."""
    expected_name, expected_version = _project_identity(project_root)
    metadata_name, metadata_version, _ = _wheel_metadata(wheel)
    filename_name, filename_version = _wheel_filename_identity(wheel)
    if _pypi_name(metadata_name) != _pypi_name(expected_name):
        raise ReleaseError(
            f"wheel METADATA name {metadata_name!r} does not match pyproject name {expected_name!r}"
        )
    if metadata_version != expected_version:
        raise ReleaseError(
            f"wheel METADATA version {metadata_version!r} does not match pyproject version "
            f"{expected_version!r}"
        )
    if _pypi_name(filename_name) != _pypi_name(metadata_name):
        raise ReleaseError(
            f"wheel filename distribution {filename_name!r} does not match METADATA name "
            f"{metadata_name!r}"
        )
    if filename_version != metadata_version:
        raise ReleaseError(
            f"wheel filename version {filename_version!r} does not match METADATA version "
            f"{metadata_version!r}"
        )
    return metadata_name, metadata_version


def _wheel_member_bytes(wheel: Path, suffix: str) -> bytes:
    try:
        with zipfile.ZipFile(wheel) as archive:
            matches = tuple(name for name in archive.namelist() if name.endswith(suffix))
            if len(matches) != 1:
                raise ReleaseError(
                    f"built wheel must contain exactly one {suffix}, found {len(matches)}"
                )
            return archive.read(matches[0])
    except (OSError, zipfile.BadZipFile, KeyError) as exc:
        raise ReleaseError(f"could not read {suffix} from {wheel}: {exc}") from exc


def _requirement_name(requirement: str) -> str:
    match = _REQUIREMENT_NAME.match(requirement)
    if match is None:
        raise ReleaseError(f"wheel METADATA contains an invalid requirement {requirement!r}")
    return match.group(0)


def _spdx_id(requirement: str) -> str:
    name = re.sub(r"[^A-Za-z0-9.-]", "-", _requirement_name(requirement))
    digest = hashlib.sha256(requirement.encode()).hexdigest()[:12]
    return f"SPDXRef-Dependency-{name}-{digest}"


def _pypi_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _exact_requirement_version(requirement: str) -> str | None:
    match = _EXACT_REQUIREMENT_VERSION.match(requirement)
    return match.group(1) if match is not None else None


def _spdx_sbom(
    wheel: Path,
    *,
    revision: str,
    epoch: int,
    wheel_sha256: str,
) -> bytes:
    """Describe the wheel and its declared, unbundled requirements without inventing versions."""
    name, version, requirements = _wheel_metadata(wheel)
    font_bytes = _wheel_member_bytes(
        wheel, "share/hawedit/assets/fonts/NotoNaskhArabic-Regular.ttf"
    )
    root_id = "SPDXRef-Package-HawEdit"
    font_id = "SPDXRef-Package-NotoNaskhArabic"
    packages: list[dict[str, object]] = [
        {
            "SPDXID": root_id,
            "name": name,
            "versionInfo": version,
            "packageFileName": wheel.name,
            "downloadLocation": "NOASSERTION",
            "filesAnalyzed": False,
            "checksums": [{"algorithm": "SHA256", "checksumValue": wheel_sha256}],
            "licenseConcluded": "NOASSERTION",
            "licenseDeclared": "NOASSERTION",
            "copyrightText": "NOASSERTION",
            "primaryPackagePurpose": "APPLICATION",
            "externalRefs": [
                {
                    "referenceCategory": "PACKAGE-MANAGER",
                    "referenceType": "purl",
                    "referenceLocator": f"pkg:pypi/{_pypi_name(name)}@{version}",
                }
            ],
        },
        {
            "SPDXID": font_id,
            "name": "Noto Naskh Arabic",
            "packageFileName": "share/hawedit/assets/fonts/NotoNaskhArabic-Regular.ttf",
            "downloadLocation": "NOASSERTION",
            "filesAnalyzed": False,
            "checksums": [
                {
                    "algorithm": "SHA256",
                    "checksumValue": hashlib.sha256(font_bytes).hexdigest(),
                }
            ],
            "licenseConcluded": "OFL-1.1",
            "licenseDeclared": "OFL-1.1",
            "copyrightText": "NOASSERTION",
            "primaryPackagePurpose": "FILE",
            "comment": (
                "Third-party font bundled inside the HawEdit wheel. Its OFL-1.1 license text "
                "is shipped beside the font."
            ),
        },
    ]
    relationships: list[dict[str, str]] = [
        {
            "spdxElementId": "SPDXRef-DOCUMENT",
            "relationshipType": "DESCRIBES",
            "relatedSpdxElement": root_id,
        }
    ]
    relationships.append(
        {
            "spdxElementId": root_id,
            "relationshipType": "CONTAINS",
            "relatedSpdxElement": font_id,
        }
    )
    for requirement in requirements:
        dependency_id = _spdx_id(requirement)
        dependency_name = _requirement_name(requirement)
        exact_version = _exact_requirement_version(requirement)
        purl = f"pkg:pypi/{_pypi_name(dependency_name)}"
        dependency: dict[str, object] = {
            "SPDXID": dependency_id,
            "name": dependency_name,
            "downloadLocation": "NOASSERTION",
            "filesAnalyzed": False,
            "licenseConcluded": "NOASSERTION",
            "licenseDeclared": "NOASSERTION",
            "copyrightText": "NOASSERTION",
            "comment": (
                f"Declared by wheel METADATA as {requirement!r}. This wheel does not bundle "
                "or resolve that dependency, so no installed checksum is asserted."
            ),
            "externalRefs": [
                {
                    "referenceCategory": "PACKAGE-MANAGER",
                    "referenceType": "purl",
                    "referenceLocator": (
                        f"{purl}@{exact_version}" if exact_version is not None else purl
                    ),
                }
            ],
        }
        if exact_version is not None:
            dependency["versionInfo"] = exact_version
        packages.append(dependency)
        optional = "extra ==" in requirement or "extra==" in requirement
        relationships.append(
            {
                "spdxElementId": dependency_id if optional else root_id,
                "relationshipType": "OPTIONAL_DEPENDENCY_OF" if optional else "DEPENDS_ON",
                "relatedSpdxElement": root_id if optional else dependency_id,
                "comment": requirement,
            }
        )

    created = datetime.fromtimestamp(epoch, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    document = {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": f"{name}-{version}-{revision[:12]}",
        "documentNamespace": (
            f"https://github.com/HawzhinBlanca/HawEdit/spdx/{revision}/{wheel_sha256}"
        ),
        "creationInfo": {
            "created": created,
            "creators": [f"Tool: hawedit-release-{version}"],
            "comment": (
                "Generated from the reproducible wheel's exact bytes and METADATA. Declared "
                "dependencies are not a resolved environment graph; external model assets are "
                "recorded separately in HawEdit's pinned model manifests."
            ),
        },
        "documentDescribes": [root_id],
        "packages": packages,
        "relationships": relationships,
    }
    return (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _copy_synced(source: Path, destination: Path) -> None:
    with source.open("rb") as incoming, destination.open("xb") as outgoing:
        shutil.copyfileobj(incoming, outgoing, length=1024 * 1024)
        outgoing.flush()
        os.fsync(outgoing.fileno())


def _write_synced(payload: bytes, destination: Path) -> None:
    with destination.open("xb") as output:
        output.write(payload)
        output.flush()
        os.fsync(output.fileno())


def _publish_directory(staging: Path, output: Path) -> None:
    if os.path.lexists(output):
        raise ReleaseError(f"refusing to overwrite release directory {output}")
    try:
        # Staging is a sibling, so the rename is one-filesystem and atomic. A populated winner
        # cannot be replaced by os.rename on POSIX or Windows.
        os.rename(staging, output)
    except OSError as exc:
        if os.path.lexists(output):
            raise ReleaseError(
                f"refusing to overwrite release directory {output}; another build published it"
            ) from exc
        raise ReleaseError(
            f"could not atomically publish release directory {output}: {exc}"
        ) from exc


def build_reproducible_wheel(
    project_root: Path,
    output_dir: Path | None = None,
    *,
    python: Path = Path(sys.executable),
    gate_run_id: int | None = None,
) -> ReleaseArtifact:
    """Verify exact-SHA CI, then build twice and publish byte-identical wheels."""
    root = project_root.resolve()
    revision, epoch = _source_identity(root)
    output = (
        output_dir.resolve()
        if output_dir is not None
        else root / "dist" / f"hawedit-{revision[:12]}"
    )
    if output == root or output.is_relative_to(root / ".git"):
        raise ReleaseError(f"unsafe release output directory {output}")
    if os.path.lexists(output):
        raise ReleaseError(f"refusing to overwrite release directory {output}")
    gate = _verify_gate_run(revision, gate_run_id)
    output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="hawedit-wheel-build-") as temporary:
        temporary_root = Path(temporary)
        first_source = temporary_root / "source-first"
        second_source = temporary_root / "source-second"
        _snapshot_source(root, revision, first_source)
        _snapshot_source(root, revision, second_source)
        builder_python, builder = _create_locked_builder(
            first_source, temporary_root / "builder", python.resolve()
        )
        first = _build_once(first_source, temporary_root / "first", builder_python, epoch)
        second = _build_once(second_source, temporary_root / "second", builder_python, epoch)
        first_digest = _sha256(first)
        second_digest = _sha256(second)
        if first.name != second.name or first_digest != second_digest:
            raise ReleaseError(
                "wheel build is not reproducible: "
                f"{first.name} {first_digest} != {second.name} {second_digest}"
            )
        _validate_hawedit_wheel(first)
        distribution, version = _assert_release_identity(first_source, first)

        # Refuse if HEAD or the worktree changed while the two builds were running.
        if _source_identity(root) != (revision, epoch):
            raise ReleaseError("source revision changed during the release build")

        staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
        try:
            staged_wheel = staging / first.name
            _copy_synced(first, staged_wheel)
            size = staged_wheel.stat().st_size
            checksum_name = "SHA256SUMS"
            provenance_name = "release-provenance.json"
            sbom_name = f"{first.name}.spdx.json"
            sbom_payload = _spdx_sbom(
                staged_wheel,
                revision=revision,
                epoch=epoch,
                wheel_sha256=first_digest,
            )
            sbom_digest = hashlib.sha256(sbom_payload).hexdigest()
            provenance = {
                "schema": 5,
                "revision": revision,
                "source_date_epoch": epoch,
                "distribution": distribution,
                "version": version,
                "gate": gate.to_dict(),
                "builder": builder.to_dict(),
                "wheel": first.name,
                "sha256": first_digest,
                "size_bytes": size,
                "sbom": sbom_name,
                "sbom_format": "SPDX-2.3-json",
                "sbom_sha256": sbom_digest,
            }
            provenance_payload = (json.dumps(provenance, indent=2, sort_keys=True) + "\n").encode()
            provenance_digest = hashlib.sha256(provenance_payload).hexdigest()
            _write_synced(sbom_payload, staging / sbom_name)
            _write_synced(provenance_payload, staging / provenance_name)
            _write_synced(
                (
                    f"{first_digest}  {first.name}\n"
                    f"{sbom_digest}  {sbom_name}\n"
                    f"{provenance_digest}  {provenance_name}\n"
                ).encode(),
                staging / checksum_name,
            )
            _publish_directory(staging, output)
        finally:
            if staging.exists():
                shutil.rmtree(staging)

    return ReleaseArtifact(
        output_dir=output,
        wheel=output / first.name,
        checksum_file=output / "SHA256SUMS",
        provenance_file=output / "release-provenance.json",
        sbom_file=output / sbom_name,
        revision=revision,
        source_date_epoch=epoch,
        sha256=first_digest,
        sbom_sha256=sbom_digest,
        provenance_sha256=provenance_digest,
        gate_run_id=gate.run_id,
        gate_run_url=gate.url,
        size_bytes=size,
        build_python=builder.python,
        build_frontend=builder.frontend,
        build_backend=builder.backend,
        build_lock_sha256=builder.lock_sha256,
        distribution=distribution,
        version=version,
    )


def main(argv: list[str] | None = None) -> int:
    use_utf8_streams()
    parser = argparse.ArgumentParser(
        description=(
            "verify an exact successful main-branch gate run, then build HawEdit twice and "
            "publish only a byte-reproducible wheel"
        )
    )
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--gate-run-id",
        type=int,
        required=True,
        help="GitHub Actions run id for this exact main-branch revision",
    )
    args = parser.parse_args(argv)
    try:
        artifact = build_reproducible_wheel(
            args.project_root, args.output_dir, gate_run_id=args.gate_run_id
        )
    except ReleaseError as exc:
        parser.exit(1, f"REFUSED: {exc}\n")
    print(json.dumps(artifact.to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through the installed entry point
    raise SystemExit(main())

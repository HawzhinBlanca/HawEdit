"""Live, fail-closed vulnerability boundary for the canonical WSL OmniASR runtime.

This command is intentionally separate from the offline :mod:`hawedit.vex` evaluator.  It first
validates the current source-fingerprinted receipt and live package inventory, runs exactly
``pip-audit==2.10.1`` against that environment through a hash-locked scanner environment, then
revalidates the receipt and hashes all canonical model assets before accepting the VEX policy.
Only a complete success publishes a new, non-overwriting evidence artifact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import threading
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Final

from hawedit.cli import program_name, use_utf8_streams
from hawedit.omni_assets import OMNI_ASSETS
from hawedit.vex import (
    AssetIdentity,
    RuntimeIdentity,
    VexError,
    _default_vex_path,
    evaluate,
    parse_pip_audit_json,
    parse_vex_json,
)
from hawedit.wsl_audit_locks import (
    AUDIT_DISTRIBUTIONS as AUDIT_DISTRIBUTIONS,
)
from hawedit.wsl_audit_locks import (
    AUDIT_LOCK_SHA256 as AUDIT_LOCK_SHA256,
)
from hawedit.wsl_audit_locks import (
    AUDIT_REQUIREMENTS as AUDIT_REQUIREMENTS,
)
from hawedit.wsl_setup import (
    WslRuntimeError,
    WslRuntimeReceipt,
    default_wsl_runtime,
    default_wsl_source,
    load_wsl_runtime_receipt,
    probe_wsl_runtime,
    wsl_path,
)

PIP_AUDIT_VERSION: Final = "2.10.1"
OSV_ENDPOINT: Final = "https://api.osv.dev/v1/query"
PYPI_INDEX: Final = "https://pypi.org/simple"
_REPORT_LIMIT: Final = 16_777_216
_STDERR_LIMIT: Final = 65_536
_SMALL_OUTPUT_LIMIT: Final = 8_192
_EVIDENCE_LIMIT: Final = 32_000_000
_TOOL_VERSION = re.compile(r"pip-audit ([0-9]+\.[0-9]+\.[0-9]+)\r?\n?\Z")
_UV_VERSION = re.compile(r"uv ([0-9]+\.[0-9]+\.[0-9]+)[^\r\n]*\r?\n?\Z")
_WSL_TEMP = re.compile(r"/tmp/hawedit-wsl-audit\.[A-Za-z0-9]{10}\n\Z")

_AUDIT_OPTIONS: Final = (
    "--strict",
    "--vulnerability-service",
    "osv",
    "--osv-url",
    OSV_ENDPOINT,
    "--format",
    "json",
    "--aliases",
    "on",
    "--desc",
    "off",
    "--progress-spinner",
    "off",
    "--timeout",
    "30",
)
AUDIT_CONTRACT_SHA256: Final = hashlib.sha256(
    json.dumps(
        {
            "audit_options": _AUDIT_OPTIONS,
            "index": PYPI_INDEX,
            "pip_audit": PIP_AUDIT_VERSION,
            "scanner_lock_sha256": AUDIT_LOCK_SHA256,
            "service": "osv",
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
).hexdigest()


class LiveVexGateError(RuntimeError):
    """The live audit could not produce accepted, identity-bound evidence."""


@dataclass(frozen=True)
class ProcessOutput:
    returncode: int
    stdout: bytes
    stderr: bytes


def _wsl_prefix(distro: str, executable: str) -> list[str]:
    return [executable, "--distribution", distro, "--exec"]


def _run_bounded(
    command: list[str],
    *,
    timeout_seconds: int,
    stdout_limit: int,
    stderr_limit: int,
) -> ProcessOutput:
    """Run without a shell while capping both captured streams during execution."""
    if timeout_seconds <= 0:
        raise LiveVexGateError("process timeout must be positive")
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError as exc:
        raise LiveVexGateError(f"cannot start WSL audit process: {exc}") from exc
    stdout_stream = process.stdout
    stderr_stream = process.stderr
    if stdout_stream is None or stderr_stream is None:  # defensive for alternate Popen objects
        process.kill()
        raise LiveVexGateError("audit process did not expose both output streams")

    outputs: dict[str, bytearray] = {"stdout": bytearray(), "stderr": bytearray()}
    overflow: list[str] = []
    reader_errors: list[BaseException] = []
    lock = threading.Lock()

    def consume(name: str, limit: int) -> None:
        stream = stdout_stream if name == "stdout" else stderr_stream
        try:
            while True:
                chunk = stream.read(65_536)
                if not chunk:
                    return
                with lock:
                    if len(outputs[name]) + len(chunk) > limit:
                        overflow.append(name)
                        process.kill()
                        return
                    outputs[name].extend(chunk)
        except BaseException as exc:  # pragma: no cover - defensive OS stream failure
            with lock:
                reader_errors.append(exc)
            process.kill()

    readers = [
        threading.Thread(target=consume, args=("stdout", stdout_limit), daemon=True),
        threading.Thread(target=consume, args=("stderr", stderr_limit), daemon=True),
    ]
    for reader in readers:
        reader.start()
    try:
        returncode = process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        process.kill()
        process.wait()
        for reader in readers:
            reader.join()
        raise LiveVexGateError(f"WSL audit process exceeded {timeout_seconds} seconds") from exc
    for reader in readers:
        reader.join()
    if reader_errors:
        raise LiveVexGateError(f"cannot read WSL audit process output: {reader_errors[0]}")
    if overflow:
        label = "/".join(sorted(set(overflow)))
        raise LiveVexGateError(f"WSL audit process exceeded its {label} output limit")
    return ProcessOutput(returncode, bytes(outputs["stdout"]), bytes(outputs["stderr"]))


def _safe_posix_home(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if (
        not path.is_absolute()
        or ".." in path.parts
        or any(ord(character) < 32 for character in value)
    ):
        raise LiveVexGateError(f"WSL receipt has an unsafe home path: {value!r}")
    return path


def _find_uv(
    receipt: WslRuntimeReceipt,
    *,
    executable: str,
    timeout_seconds: int,
) -> str:
    home = _safe_posix_home(receipt.home)
    candidates = (
        str(home / ".local" / "bin" / "uv"),
        "/usr/local/bin/uv",
        "/usr/bin/uv",
        "/bin/uv",
    )
    for candidate in candidates:
        result = _run_bounded(
            [*_wsl_prefix(receipt.distro, executable), "test", "-x", candidate],
            timeout_seconds=min(timeout_seconds, 30),
            stdout_limit=_SMALL_OUTPUT_LIMIT,
            stderr_limit=_SMALL_OUTPUT_LIMIT,
        )
        if result.returncode == 0 and not result.stdout:
            return candidate
    raise LiveVexGateError(
        "the validated WSL user has no executable uv in the reviewed system locations; "
        "install uv for that user before running the live VEX gate"
    )


def _verify_uv(
    receipt: WslRuntimeReceipt,
    *,
    uv: str,
    executable: str,
    timeout_seconds: int,
) -> str:
    uv_result = _run_bounded(
        [*_wsl_prefix(receipt.distro, executable), uv, "--version"],
        timeout_seconds=min(timeout_seconds, 60),
        stdout_limit=_SMALL_OUTPUT_LIMIT,
        stderr_limit=_SMALL_OUTPUT_LIMIT,
    )
    try:
        uv_text = uv_result.stdout.decode("utf-8")
    except UnicodeError as exc:
        raise LiveVexGateError("uv emitted a non-UTF-8 version") from exc
    uv_match = _UV_VERSION.fullmatch(uv_text)
    if uv_result.returncode != 0 or uv_match is None:
        raise LiveVexGateError("cannot verify the WSL uv runner version")

    return uv_match.group(1)


_SCANNER_IDENTITY_SCRIPT: Final = (
    "import importlib.metadata as m,json;"
    "n=lambda s:s.lower().replace('_','-').replace('.','-');"
    "print(json.dumps(dict(sorted((n(d.metadata['Name']),d.version) for d in m.distributions())),"
    "sort_keys=True,separators=(',',':')))"
)
_WRITE_EXCLUSIVE_SCRIPT: Final = (
    "import os,sys;"
    "p=sys.argv[1];b=bytes.fromhex(sys.argv[2]);"
    "f=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);"
    "os.write(f,b);os.fsync(f);os.close(f)"
)


def _scanner_identity(payload: bytes) -> dict[str, str]:
    try:
        value: object = json.loads(payload.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise LiveVexGateError("scanner environment emitted an invalid identity") from exc
    if type(value) is not dict or any(
        type(name) is not str or type(version) is not str for name, version in value.items()
    ):
        raise LiveVexGateError("scanner environment emitted an invalid identity")
    return {str(name): str(version) for name, version in value.items()}


def _run_hash_locked_audit(
    receipt: WslRuntimeReceipt,
    *,
    uv: str,
    runtime_python: str,
    site_packages: str,
    executable: str,
    timeout_seconds: int,
) -> tuple[str, str, ProcessOutput, str]:
    """Create an ephemeral scanner from reviewed wheels, verify it, and audit the runtime."""
    uv_version = _verify_uv(receipt, uv=uv, executable=executable, timeout_seconds=timeout_seconds)
    prefix = _wsl_prefix(receipt.distro, executable)
    created = _run_bounded(
        [
            *prefix,
            "/usr/bin/mktemp",
            "--directory",
            "--tmpdir=/tmp",
            "hawedit-wsl-audit.XXXXXXXXXX",
        ],
        timeout_seconds=min(timeout_seconds, 60),
        stdout_limit=_SMALL_OUTPUT_LIMIT,
        stderr_limit=_STDERR_LIMIT,
    )
    try:
        temporary = created.stdout.decode("ascii")
    except UnicodeError as exc:
        raise LiveVexGateError("WSL mktemp emitted a non-ASCII path") from exc
    if created.returncode != 0 or _WSL_TEMP.fullmatch(temporary) is None:
        raise LiveVexGateError("cannot create a private WSL scanner directory")
    temporary = temporary.rstrip("\n")
    requirements = f"{temporary}/requirements.txt"
    scanner = f"{temporary}/scanner"
    scanner_python = f"{scanner}/bin/python"
    scanner_executable = f"{scanner}/bin/pip-audit"
    write = _run_bounded(
        [
            *prefix,
            runtime_python,
            "-I",
            "-c",
            _WRITE_EXCLUSIVE_SCRIPT,
            requirements,
            (AUDIT_REQUIREMENTS + "\n").encode("utf-8").hex(),
        ],
        timeout_seconds=min(timeout_seconds, 60),
        stdout_limit=_SMALL_OUTPUT_LIMIT,
        stderr_limit=_STDERR_LIMIT,
    )
    if write.returncode != 0 or write.stdout:
        raise LiveVexGateError(
            "cannot materialize the reviewed scanner lock in private WSL storage"
        )
    active_error: BaseException | None = None
    try:
        common_env = [
            "env",
            "UV_NO_CONFIG=1",
            "UV_NO_ENV_FILE=1",
            "UV_KEYRING_PROVIDER=disabled",
            "UV_PYTHON_DOWNLOADS=never",
            "UV_NO_PROGRESS=1",
            f"UV_CACHE_DIR={temporary}/cache",
        ]
        return _execute_hash_locked_scanner(
            prefix=prefix,
            common_env=common_env,
            uv=uv,
            runtime_python=runtime_python,
            scanner=scanner,
            scanner_python=scanner_python,
            scanner_executable=scanner_executable,
            requirements=requirements,
            site_packages=site_packages,
            uv_version=uv_version,
            timeout_seconds=timeout_seconds,
        )
    except BaseException as exc:
        active_error = exc
        raise
    finally:
        try:
            cleanup = _run_bounded(
                [*prefix, "/usr/bin/rm", "-rf", "--", temporary],
                timeout_seconds=min(timeout_seconds, 60),
                stdout_limit=_SMALL_OUTPUT_LIMIT,
                stderr_limit=_STDERR_LIMIT,
            )
            if cleanup.returncode != 0 and active_error is None:
                detail = cleanup.stderr.decode("utf-8", "replace")[-1_200:]
                raise LiveVexGateError(f"cannot remove ephemeral scanner: {detail or 'no detail'}")
        except LiveVexGateError:
            if active_error is None:
                raise


def _execute_hash_locked_scanner(
    *,
    prefix: list[str],
    common_env: list[str],
    uv: str,
    runtime_python: str,
    scanner: str,
    scanner_python: str,
    scanner_executable: str,
    requirements: str,
    site_packages: str,
    uv_version: str,
    timeout_seconds: int,
) -> tuple[str, str, ProcessOutput, str]:
    create = _run_bounded(
        [
            *prefix,
            *common_env,
            uv,
            "venv",
            "--no-project",
            "--python",
            runtime_python,
            "--no-python-downloads",
            "--no-config",
            "--no-progress",
            scanner,
        ],
        timeout_seconds=timeout_seconds,
        stdout_limit=_SMALL_OUTPUT_LIMIT,
        stderr_limit=_STDERR_LIMIT,
    )
    if create.returncode != 0:
        detail = create.stderr.decode("utf-8", "replace")[-1_200:]
        raise LiveVexGateError(f"cannot create scanner environment: {detail or 'no detail'}")
    install = _run_bounded(
        [
            *prefix,
            *common_env,
            uv,
            "pip",
            "install",
            "--python",
            scanner_python,
            "--require-hashes",
            "--only-binary",
            ":all:",
            "--no-deps",
            "--no-sources",
            "--default-index",
            PYPI_INDEX,
            "--index-strategy",
            "first-index",
            "--keyring-provider",
            "disabled",
            "--no-python-downloads",
            "--no-config",
            "--no-progress",
            "--link-mode",
            "copy",
            "-r",
            requirements,
        ],
        timeout_seconds=timeout_seconds,
        stdout_limit=_SMALL_OUTPUT_LIMIT,
        stderr_limit=_STDERR_LIMIT,
    )
    if install.returncode != 0:
        detail = install.stderr.decode("utf-8", "replace")[-1_200:]
        raise LiveVexGateError(f"cannot install hash-locked scanner: {detail or 'no detail'}")
    identity_result = _run_bounded(
        [*prefix, scanner_python, "-I", "-c", _SCANNER_IDENTITY_SCRIPT],
        timeout_seconds=min(timeout_seconds, 60),
        stdout_limit=_SMALL_OUTPUT_LIMIT,
        stderr_limit=_STDERR_LIMIT,
    )
    identity = _scanner_identity(identity_result.stdout)
    if identity_result.returncode != 0 or identity != dict(AUDIT_DISTRIBUTIONS):
        raise LiveVexGateError("installed scanner identity drifted from its reviewed hash lock")
    identity_sha256 = _mapping_digest(identity)
    version_result = _run_bounded(
        [*prefix, scanner_executable, "--version"],
        timeout_seconds=min(timeout_seconds, 60),
        stdout_limit=_SMALL_OUTPUT_LIMIT,
        stderr_limit=_STDERR_LIMIT,
    )
    try:
        version_text = version_result.stdout.decode("utf-8")
    except UnicodeError as exc:
        raise LiveVexGateError("pip-audit emitted a non-UTF-8 version") from exc
    match = _TOOL_VERSION.fullmatch(version_text)
    if version_result.returncode != 0 or match is None:
        raise LiveVexGateError("cannot verify the pinned pip-audit version")
    if match.group(1) != PIP_AUDIT_VERSION:
        raise LiveVexGateError(
            f"pip-audit version drifted: expected {PIP_AUDIT_VERSION}, got {match.group(1)}"
        )
    audit = _run_bounded(
        [*prefix, scanner_executable, *_AUDIT_OPTIONS, "--path", site_packages],
        timeout_seconds=timeout_seconds,
        stdout_limit=_REPORT_LIMIT,
        stderr_limit=_STDERR_LIMIT,
    )
    return uv_version, match.group(1), audit, identity_sha256


def _read_bound(path: Path, *, limit: int, label: str) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise LiveVexGateError(f"cannot open {label} {path}: {exc}") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise LiveVexGateError(f"{label} must be a regular file: {path}")
        if before.st_size > limit:
            raise LiveVexGateError(f"{label} exceeds the {limit}-byte limit")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(65_536, limit + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            if total > limit:
                raise LiveVexGateError(f"{label} exceeds the {limit}-byte limit")
            chunks.append(chunk)
        after = os.fstat(descriptor)
    except OSError as exc:
        raise LiveVexGateError(f"cannot read {label} {path}: {exc}") from exc
    finally:
        os.close(descriptor)
    identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    if identity != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        raise LiveVexGateError(f"{label} changed while it was read")
    try:
        pathname = os.stat(path, follow_symlinks=False)
    except OSError as exc:
        raise LiveVexGateError(f"cannot revalidate {label} {path}: {exc}") from exc
    if (pathname.st_dev, pathname.st_ino) != (after.st_dev, after.st_ino):
        raise LiveVexGateError(f"{label} pathname changed while it was read")
    return b"".join(chunks)


def _runtime_identity(receipt: WslRuntimeReceipt) -> RuntimeIdentity:
    return RuntimeIdentity(
        receipt.source_sha256,
        receipt.python_version,
        dict(sorted(receipt.packages.items())),
        receipt.dependency_locks["build_sha256"],
        receipt.dependency_locks["runtime_sha256"],
        tuple(sorted(AssetIdentity(asset.name, asset.size, asset.sha256) for asset in OMNI_ASSETS)),
    )


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def _mapping_digest(value: Mapping[str, str]) -> str:
    return hashlib.sha256(_canonical_bytes(dict(sorted(value.items())))).hexdigest()


def _evidence_target(path: Path) -> Path:
    target = path.absolute()
    parent = target.parent
    try:
        if os.path.normcase(os.path.realpath(parent)) != os.path.normcase(str(parent)):
            raise LiveVexGateError(f"evidence parent must not traverse links: {parent}")
        metadata = os.stat(parent, follow_symlinks=False)
    except LiveVexGateError:
        raise
    except OSError as exc:
        raise LiveVexGateError(f"cannot inspect evidence parent {parent}: {exc}") from exc
    if not stat.S_ISDIR(metadata.st_mode):
        raise LiveVexGateError(f"evidence parent is not a directory: {parent}")
    return target


def _preflight_new_evidence(path: Path) -> None:
    target = _evidence_target(path)
    if os.path.lexists(target):
        raise LiveVexGateError(f"refusing to overwrite existing evidence: {target}")


def _publish_new_evidence(path: Path, document: Mapping[str, object]) -> None:
    encoded = _canonical_bytes(document) + b"\n"
    if len(encoded) > _EVIDENCE_LIMIT:
        raise LiveVexGateError(f"evidence exceeds the {_EVIDENCE_LIMIT}-byte limit")
    target = _evidence_target(path)
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(target, flags, 0o600)
    except FileExistsError as exc:
        raise LiveVexGateError(f"refusing to overwrite existing evidence: {target}") from exc
    except OSError as exc:
        raise LiveVexGateError(f"cannot create evidence {target}: {exc}") from exc
    created = os.fstat(descriptor)
    try:
        offset = 0
        while offset < len(encoded):
            offset += os.write(descriptor, encoded[offset:])
        os.fsync(descriptor)
    except OSError as exc:
        os.close(descriptor)
        descriptor = -1
        try:
            current = os.stat(target, follow_symlinks=False)
            if (current.st_dev, current.st_ino) == (created.st_dev, created.st_ino):
                os.unlink(target)
        except OSError:
            pass
        raise LiveVexGateError(f"cannot publish complete evidence {target}: {exc}") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _same_receipt(before: WslRuntimeReceipt, after: WslRuntimeReceipt) -> bool:
    return asdict(before) == asdict(after)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def run_live_gate(
    *,
    evidence_path: Path,
    runtime_root: Path | None = None,
    package_source: Path | None = None,
    distro: str | None = None,
    executable: str = "wsl.exe",
    vex_path: Path | None = None,
    timeout_seconds: int = 300,
) -> dict[str, object]:
    """Run the complete live boundary and publish one immutable success artifact."""
    if not 1 <= timeout_seconds <= 1_800:
        raise LiveVexGateError("timeout_seconds must be between 1 and 1800")
    _preflight_new_evidence(evidence_path)
    source = (package_source or Path(__file__).resolve().parent).resolve()
    runtime = (runtime_root or default_wsl_runtime(source)).absolute()
    policy_path = (vex_path or _default_vex_path()).resolve()

    try:
        before = load_wsl_runtime_receipt(
            distro=distro,
            runtime_root=runtime,
            package_source=source,
            executable=executable,
        )
    except WslRuntimeError as exc:
        raise LiveVexGateError(
            f"canonical WSL receipt/live identity is unavailable: {exc}"
        ) from exc
    marker = default_wsl_source(source, runtime) / ".ready"
    receipt_bytes = _read_bound(marker, limit=2_097_152, label="canonical WSL receipt")
    vex_bytes_before = _read_bound(policy_path, limit=1_048_576, label="WSL ASR VEX policy")
    try:
        policy = parse_vex_json(vex_bytes_before)
    except VexError as exc:
        raise LiveVexGateError(f"WSL ASR VEX policy is invalid: {exc}") from exc

    translated_environment = wsl_path(before.generation_root, before.distro, executable)
    python_minor = ".".join(before.python_version.split(".")[:2])
    if re.fullmatch(r"3\.12", python_minor) is None:
        raise LiveVexGateError(f"unexpected WSL runtime Python: {before.python_version!r}")
    runtime_python = f"{translated_environment}/bin/python"
    site_packages = f"{translated_environment}/lib/python{python_minor}/site-packages"
    uv = _find_uv(before, executable=executable, timeout_seconds=timeout_seconds)
    uv_version, audit_version, audit, scanner_packages_sha256 = _run_hash_locked_audit(
        before,
        uv=uv,
        runtime_python=runtime_python,
        site_packages=site_packages,
        executable=executable,
        timeout_seconds=timeout_seconds,
    )
    if audit.returncode not in (0, 1):
        detail = audit.stderr.decode("utf-8", "replace")[-1_200:]
        raise LiveVexGateError(
            f"pip-audit failed with exit code {audit.returncode}: {detail or 'no detail'}"
        )
    try:
        findings, audited_packages, audit_document = parse_pip_audit_json(audit.stdout)
    except VexError as exc:
        raise LiveVexGateError(f"pip-audit emitted invalid 2.10.1 JSON: {exc}") from exc

    try:
        final_probe = probe_wsl_runtime(
            distro=distro,
            runtime_root=runtime,
            package_source=source,
            executable=executable,
        )
    except WslRuntimeError as exc:
        raise LiveVexGateError(f"post-audit WSL runtime verification failed: {exc}") from exc
    if not _same_receipt(before, final_probe.receipt):
        raise LiveVexGateError("canonical WSL receipt/live identity changed during the audit")
    if _read_bound(marker, limit=2_097_152, label="canonical WSL receipt") != receipt_bytes:
        raise LiveVexGateError("canonical WSL receipt bytes changed during the audit")
    if _read_bound(policy_path, limit=1_048_576, label="WSL ASR VEX policy") != vex_bytes_before:
        raise LiveVexGateError("WSL ASR VEX policy bytes changed during the audit")

    observed_at = _utc_now()
    try:
        result = evaluate(
            policy,
            _runtime_identity(final_probe.receipt),
            findings,
            audited_packages,
            as_of=observed_at.date(),
        )
    except VexError as exc:
        raise LiveVexGateError(f"live WSL ASR vulnerability policy refused: {exc}") from exc

    canonical_report = _canonical_bytes(audit_document)
    evidence: dict[str, object] = {
        "schema": 1,
        "status": "accepted",
        "observed_at": observed_at.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "audit_contract_sha256": AUDIT_CONTRACT_SHA256,
        "audit_tool": {
            "name": "pip-audit",
            "version": audit_version,
            "runner": uv,
            "runner_version": uv_version,
            "service": "osv",
            "endpoint": OSV_ENDPOINT,
            "exit_code": audit.returncode,
            "lock_sha256": AUDIT_LOCK_SHA256,
            "package_count": len(AUDIT_DISTRIBUTIONS),
            "packages_sha256": scanner_packages_sha256,
            "stderr_sha256": hashlib.sha256(audit.stderr).hexdigest(),
        },
        "runtime": {
            "source_sha256": final_probe.receipt.source_sha256,
            "generation": final_probe.receipt.generation,
            "distro": final_probe.receipt.distro,
            "uid": final_probe.receipt.uid,
            "python_version": final_probe.receipt.python_version,
            "package_count": len(final_probe.receipt.packages),
            "packages_sha256": _mapping_digest(final_probe.receipt.packages),
            "dependency_locks": dict(sorted(final_probe.receipt.dependency_locks.items())),
            "receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
            "assets_verified": final_probe.files_verified,
            "asset_bytes": final_probe.size_bytes,
            "cuda_device_count": final_probe.receipt.cuda_device_count,
        },
        "policy": {
            "sha256": hashlib.sha256(vex_bytes_before).hexdigest(),
            "reviewed": policy.reviewed.isoformat(),
            "expires": policy.expires.isoformat(),
            "dispositions": len(policy.dispositions),
        },
        "audit": {
            "sha256": hashlib.sha256(canonical_report).hexdigest(),
            "dependencies": len(audited_packages),
            "findings": len(findings),
            "report": audit_document,
        },
        "evaluation": {
            "findings": result.finding_count,
            "dispositions": result.disposition_count,
            "matched_dispositions": result.matched_dispositions,
        },
    }
    _publish_new_evidence(evidence_path, evidence)
    return evidence


def main(argv: list[str] | None = None) -> int:
    use_utf8_streams()
    parser = argparse.ArgumentParser(
        prog=program_name("hawedit.wsl_vex_gate"),
        description="Run and evidence the live WSL OmniASR vulnerability gate",
    )
    parser.add_argument("--evidence", required=True, type=Path, help="new success artifact path")
    parser.add_argument("--runtime-root", type=Path, help="canonical host WSL runtime root")
    parser.add_argument("--package-source", type=Path, help="current hawedit package directory")
    parser.add_argument("--distro", type=str, help="required WSL distribution")
    parser.add_argument("--wsl-executable", default="wsl.exe", help="WSL executable")
    parser.add_argument("--vex", type=Path, help="reviewed VEX policy")
    parser.add_argument("--timeout-seconds", type=int, default=300)
    args = parser.parse_args(argv)
    try:
        evidence = run_live_gate(
            evidence_path=args.evidence,
            runtime_root=args.runtime_root,
            package_source=args.package_source,
            distro=args.distro,
            executable=args.wsl_executable,
            vex_path=args.vex,
            timeout_seconds=args.timeout_seconds,
        )
    except (LiveVexGateError, OSError, RuntimeError) as exc:
        print(f"WSL ASR LIVE VEX REFUSED: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "evidence": str(args.evidence.absolute()),
                "findings": evidence["evaluation"],
                "status": "accepted",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through main()
    raise SystemExit(main())

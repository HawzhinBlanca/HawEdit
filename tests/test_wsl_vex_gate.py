from __future__ import annotations

import json
import sys
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from hawedit import wsl_vex_gate as gate
from hawedit.wsl_setup import (
    WslRuntimeError,
    WslRuntimeProbe,
    WslRuntimeReceipt,
    default_wsl_source,
)

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "security" / "wsl-asr-vex.json"


def _policy() -> dict[str, Any]:
    value: object = json.loads(POLICY.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _audit_report() -> dict[str, object]:
    policy = _policy()
    applicability = policy["applicability"]
    assert isinstance(applicability, dict)
    package_versions = applicability["packages"]
    assert isinstance(package_versions, dict)
    packages: dict[str, dict[str, object]] = {
        name: {"name": name, "version": version, "vulns": []}
        for name, version in package_versions.items()
    }
    dispositions = policy["dispositions"]
    assert isinstance(dispositions, list)
    for disposition in dispositions:
        assert isinstance(disposition, dict)
        package = disposition["package"]
        advisory_ids = disposition["advisory_ids"]
        assert isinstance(package, str)
        assert isinstance(advisory_ids, list)
        primary, *aliases = advisory_ids
        vulnerabilities = packages[package]["vulns"]
        assert isinstance(vulnerabilities, list)
        vulnerabilities.append({"id": primary, "fix_versions": [], "aliases": aliases})
    return {
        "dependencies": [packages[name] for name in sorted(packages)],
        "fixes": [],
    }


def _receipt(tmp_path: Path) -> WslRuntimeReceipt:
    applicability = _policy()["applicability"]
    assert isinstance(applicability, dict)
    packages = applicability["packages"]
    locks = {
        "build_sha256": applicability["build_lock_sha256"],
        "runtime_sha256": applicability["runtime_lock_sha256"],
    }
    assert isinstance(packages, dict)
    assert all(
        isinstance(name, str) and isinstance(version, str) for name, version in packages.items()
    )
    assert all(isinstance(value, str) for value in locks.values())
    return WslRuntimeReceipt(
        source_root=tmp_path / "snapshot",
        source_sha256=str(applicability["source_sha256"]),
        generation="Ubuntu-generation",
        generation_root=tmp_path / "venvs" / "Ubuntu-generation" / "environment",
        distro="Ubuntu",
        uid=1000,
        home="/home/ai",
        python_version="3.12.13",
        packages={str(name): str(version) for name, version in packages.items()},
        dependency_locks={name: str(value) for name, value in locks.items()},
        asset_cache="/home/ai/.cache/fairseq2/assets",
        asset_bytes=43_546_500_168,
        cuda_device_count=2,
    )


def _source_and_marker(tmp_path: Path) -> tuple[Path, Path, Path]:
    source = tmp_path / "package" / "hawedit"
    source.mkdir(parents=True)
    (source / "__init__.py").write_text("__version__ = 'test'\n", encoding="utf-8")
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    marker = default_wsl_source(source, runtime) / ".ready"
    marker.parent.mkdir(parents=True)
    marker.write_bytes(b'{"canonical":"receipt"}\n')
    return source, runtime, marker


def _install_success_mocks(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    audit_stdout: bytes | None = None,
    audit_returncode: int = 1,
    audit_version: str = "2.10.1",
    scanner_identity: dict[str, str] | None = None,
    final_receipt: WslRuntimeReceipt | None = None,
) -> tuple[Path, Path, WslRuntimeReceipt, list[list[str]]]:
    source, runtime, _marker = _source_and_marker(tmp_path)
    receipt = _receipt(tmp_path)
    commands: list[list[str]] = []
    report = json.dumps(_audit_report()).encode("utf-8") if audit_stdout is None else audit_stdout

    monkeypatch.setattr(gate, "load_wsl_runtime_receipt", lambda **_kwargs: receipt)
    monkeypatch.setattr(
        gate,
        "probe_wsl_runtime",
        lambda **_kwargs: WslRuntimeProbe(final_receipt or receipt, 3, 43_546_500_168),
    )
    monkeypatch.setattr(
        gate,
        "wsl_path",
        lambda path, *_args: (
            "/runtime/environment" if path == receipt.generation_root else "/audit-work"
        ),
    )
    monkeypatch.setattr(gate, "_find_uv", lambda *_args, **_kwargs: "/home/ai/.local/bin/uv")
    monkeypatch.setattr(gate, "_utc_now", lambda: datetime(2026, 8, 9, 12, 0, tzinfo=UTC))

    def run(command: list[str], **_kwargs: object) -> gate.ProcessOutput:
        commands.append(command)
        if command[-1] == "--version" and command[-2] == "/home/ai/.local/bin/uv":
            return gate.ProcessOutput(0, b"uv 0.11.15 (x86_64-unknown-linux-gnu)\n", b"")
        if command[-1] == "--version":
            return gate.ProcessOutput(0, f"pip-audit {audit_version}\n".encode(), b"")
        if "/usr/bin/mktemp" in command:
            return gate.ProcessOutput(0, b"/tmp/hawedit-wsl-audit.A1b2C3d4E5\n", b"")
        if gate._WRITE_EXCLUSIVE_SCRIPT in command:
            return gate.ProcessOutput(0, b"", b"")
        if "venv" in command or ("pip" in command and "install" in command):
            return gate.ProcessOutput(0, b"", b"")
        if gate._SCANNER_IDENTITY_SCRIPT in command:
            return gate.ProcessOutput(
                0,
                json.dumps(
                    dict(gate.AUDIT_DISTRIBUTIONS) if scanner_identity is None else scanner_identity
                ).encode("utf-8")
                + b"\n",
                b"",
            )
        if "/usr/bin/rm" in command:
            return gate.ProcessOutput(0, b"", b"")
        return gate.ProcessOutput(audit_returncode, report, b"Found reviewed vulnerabilities\n")

    monkeypatch.setattr(gate, "_run_bounded", run)
    return source, runtime, receipt, commands


def test_live_gate_runs_exact_pinned_contract_and_publishes_bound_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, runtime, receipt, commands = _install_success_mocks(monkeypatch, tmp_path)
    evidence_path = tmp_path / "live-vex.json"
    result = gate.run_live_gate(
        evidence_path=evidence_path,
        runtime_root=runtime,
        package_source=source,
        distro="Ubuntu",
        vex_path=POLICY,
    )

    assert len(commands) == 9
    assert all(
        command[:4] == ["wsl.exe", "--distribution", "Ubuntu", "--exec"] for command in commands
    )
    write_command = commands[2]
    assert bytes.fromhex(write_command[-1]) == (gate.AUDIT_REQUIREMENTS + "\n").encode("utf-8")
    install_command = commands[4]
    assert "--require-hashes" in install_command
    assert install_command[install_command.index("--only-binary") + 1] == ":all:"
    assert "--no-deps" in install_command
    assert "--no-sources" in install_command
    assert install_command[install_command.index("--link-mode") + 1] == "copy"
    audit_command = commands[-2]
    assert audit_command[4] == "/tmp/hawedit-wsl-audit.A1b2C3d4E5/scanner/bin/pip-audit"
    assert audit_command[
        audit_command.index("--vulnerability-service") : audit_command.index(
            "--vulnerability-service"
        )
        + 2
    ] == ["--vulnerability-service", "osv"]
    assert audit_command[audit_command.index("--osv-url") + 1] == gate.OSV_ENDPOINT
    assert audit_command[audit_command.index("--path") + 1].endswith(
        "/lib/python3.12/site-packages"
    )
    assert "--ignore-vuln" not in audit_command
    assert "--fix" not in audit_command

    persisted = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert persisted == result
    assert persisted["audit_contract_sha256"] == gate.AUDIT_CONTRACT_SHA256
    assert persisted["audit_tool"]["version"] == "2.10.1"
    assert persisted["audit_tool"]["lock_sha256"] == gate.AUDIT_LOCK_SHA256
    assert persisted["audit_tool"]["package_count"] == len(gate.AUDIT_DISTRIBUTIONS)
    assert persisted["runtime"]["source_sha256"] == receipt.source_sha256
    assert persisted["runtime"]["asset_bytes"] == 43_546_500_168
    assert persisted["audit"]["dependencies"] == 3
    assert persisted["audit"]["findings"] == 12
    assert persisted["evaluation"]["matched_dispositions"] == 12
    assert persisted["audit"]["report"] == _audit_report()


def test_live_gate_uses_the_same_environment_runtime_root_as_setup_and_stage_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, runtime, receipt, _commands = _install_success_mocks(monkeypatch, tmp_path)
    monkeypatch.setenv("HAWEDIT_WSL_RUNTIME", str(runtime))
    receipt_calls: list[dict[str, object]] = []

    def load_receipt(**kwargs: object) -> WslRuntimeReceipt:
        receipt_calls.append(kwargs)
        return receipt

    monkeypatch.setattr(gate, "load_wsl_runtime_receipt", load_receipt)

    gate.run_live_gate(
        evidence_path=tmp_path / "environment-root-evidence.json",
        package_source=source,
        distro="Ubuntu",
        vex_path=POLICY,
    )

    assert receipt_calls[0]["runtime_root"] == runtime


def test_missing_current_receipt_fails_before_tools_or_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, runtime, _marker = _source_and_marker(tmp_path)
    called = False

    def missing(**_kwargs: object) -> WslRuntimeReceipt:
        raise WslRuntimeError("current fingerprint has no .ready receipt")

    def should_not_run(*_args: object, **_kwargs: object) -> gate.ProcessOutput:
        nonlocal called
        called = True
        raise AssertionError("tool must not run")

    monkeypatch.setattr(gate, "load_wsl_runtime_receipt", missing)
    monkeypatch.setattr(gate, "_run_bounded", should_not_run)
    evidence = tmp_path / "missing.json"
    with pytest.raises(gate.LiveVexGateError, match="receipt/live identity is unavailable"):
        gate.run_live_gate(
            evidence_path=evidence,
            runtime_root=runtime,
            package_source=source,
            vex_path=POLICY,
        )
    assert called is False
    assert not evidence.exists()


def test_wrong_pip_audit_version_is_refused_before_audit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, runtime, _receipt_value, commands = _install_success_mocks(
        monkeypatch, tmp_path, audit_version="2.10.2"
    )
    evidence = tmp_path / "wrong-tool.json"
    with pytest.raises(gate.LiveVexGateError, match="version drifted"):
        gate.run_live_gate(
            evidence_path=evidence,
            runtime_root=runtime,
            package_source=source,
            vex_path=POLICY,
        )
    assert len(commands) == 8
    assert not evidence.exists()


def test_scanner_inventory_drift_is_refused_before_audit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, runtime, _receipt_value, commands = _install_success_mocks(
        monkeypatch, tmp_path, scanner_identity={"pip-audit": "2.10.1"}
    )
    evidence = tmp_path / "wrong-scanner.json"
    with pytest.raises(gate.LiveVexGateError, match="scanner identity drifted"):
        gate.run_live_gate(
            evidence_path=evidence,
            runtime_root=runtime,
            package_source=source,
            vex_path=POLICY,
        )
    assert len(commands) == 7
    assert not evidence.exists()


def test_policy_aba_swap_evaluates_captured_bytes_without_reopening(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, runtime, _receipt_value, _commands = _install_success_mocks(monkeypatch, tmp_path)
    policy_copy = tmp_path / "policy.json"
    original_policy = POLICY.read_bytes()
    policy_copy.write_bytes(original_policy)
    original_read = gate._read_bound
    policy_reads = 0

    def read_bound(path: Path, *, limit: int, label: str) -> bytes:
        nonlocal policy_reads
        if path == policy_copy:
            policy_reads += 1
            if policy_reads == 2:
                policy_copy.write_bytes(original_policy)
        payload = original_read(path, limit=limit, label=label)
        if path == policy_copy and policy_reads == 1:
            policy_copy.write_bytes(b"{}")
        return payload

    monkeypatch.setattr(gate, "_read_bound", read_bound)
    evidence = tmp_path / "aba.json"
    gate.run_live_gate(
        evidence_path=evidence,
        runtime_root=runtime,
        package_source=source,
        vex_path=policy_copy,
    )
    assert policy_reads == 2
    assert evidence.is_file()


def test_audit_operational_failure_cannot_publish_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, runtime, _receipt_value, commands = _install_success_mocks(
        monkeypatch, tmp_path, audit_returncode=2
    )
    evidence = tmp_path / "audit-failed.json"
    with pytest.raises(gate.LiveVexGateError, match="exit code 2"):
        gate.run_live_gate(
            evidence_path=evidence,
            runtime_root=runtime,
            package_source=source,
            vex_path=POLICY,
        )
    assert len(commands) == 9
    assert not evidence.exists()


@pytest.mark.parametrize(
    "payload",
    [b"[]", b'{"dependencies": [], "fixes": [true]}', b"not-json"],
)
def test_malformed_or_mutating_audit_report_cannot_publish_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, payload: bytes
) -> None:
    source, runtime, _receipt_value, _commands = _install_success_mocks(
        monkeypatch, tmp_path, audit_stdout=payload
    )
    evidence = tmp_path / "bad-report.json"
    with pytest.raises(gate.LiveVexGateError, match="invalid 2.10.1 JSON"):
        gate.run_live_gate(
            evidence_path=evidence,
            runtime_root=runtime,
            package_source=source,
            vex_path=POLICY,
        )
    assert not evidence.exists()


def test_post_audit_receipt_drift_cannot_publish_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt = _receipt(tmp_path)
    changed = replace(receipt, generation="changed-after-audit")
    source, runtime, _receipt_value, _commands = _install_success_mocks(
        monkeypatch, tmp_path, final_receipt=changed
    )
    evidence = tmp_path / "drift.json"
    with pytest.raises(gate.LiveVexGateError, match="changed during the audit"):
        gate.run_live_gate(
            evidence_path=evidence,
            runtime_root=runtime,
            package_source=source,
            vex_path=POLICY,
        )
    assert not evidence.exists()


def test_existing_evidence_refuses_before_expensive_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, runtime, _marker = _source_and_marker(tmp_path)
    evidence = tmp_path / "exists.json"
    evidence.write_text("operator evidence", encoding="utf-8")
    monkeypatch.setattr(
        gate,
        "load_wsl_runtime_receipt",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("must fail before receipt")),
    )
    with pytest.raises(gate.LiveVexGateError, match="overwrite"):
        gate.run_live_gate(
            evidence_path=evidence,
            runtime_root=runtime,
            package_source=source,
            vex_path=POLICY,
        )
    assert evidence.read_text(encoding="utf-8") == "operator evidence"


def test_find_uv_uses_only_reviewed_absolute_candidates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt = _receipt(tmp_path)
    requested: list[list[str]] = []

    def run(command: list[str], **_kwargs: object) -> gate.ProcessOutput:
        requested.append(command)
        candidate = command[-1]
        return gate.ProcessOutput(0 if candidate == "/usr/local/bin/uv" else 1, b"", b"")

    monkeypatch.setattr(gate, "_run_bounded", run)
    assert gate._find_uv(receipt, executable="wsl.exe", timeout_seconds=30) == "/usr/local/bin/uv"
    assert [command[-1] for command in requested] == [
        "/home/ai/.local/bin/uv",
        "/usr/local/bin/uv",
    ]
    assert all("bash" not in command and "sh" not in command for command in requested)


def test_bounded_process_kills_excess_output() -> None:
    with pytest.raises(gate.LiveVexGateError, match="stdout output limit"):
        gate._run_bounded(
            [sys.executable, "-c", "import sys; sys.stdout.write('x' * 200000)"],
            timeout_seconds=30,
            stdout_limit=1_024,
            stderr_limit=1_024,
        )


def test_main_normalizes_live_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        gate,
        "run_live_gate",
        lambda **_kwargs: (_ for _ in ()).throw(gate.LiveVexGateError("receipt absent")),
    )
    assert gate.main(["--evidence", str(tmp_path / "evidence.json")]) == 1
    assert "WSL ASR LIVE VEX REFUSED: receipt absent" in capsys.readouterr().err

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from hawedit.omni_assets import OMNI_ASSETS
from hawedit.vex import (
    VexError,
    evaluate,
    load_pip_audit,
    load_runtime_identity,
    load_vex,
    main,
)
from hawedit.wsl_asr_locks import BUILD_LOCK_SHA256, RUNTIME_LOCK_SHA256
from hawedit.wsl_setup import package_digest

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "security" / "wsl-asr-vex.json"


def _policy_payload() -> dict[str, Any]:
    value: object = json.loads(POLICY.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _audit_payload(policy: dict[str, Any] | None = None) -> dict[str, object]:
    selected = _policy_payload() if policy is None else policy
    applicability = selected["applicability"]
    assert isinstance(applicability, dict)
    packages = applicability["packages"]
    assert isinstance(packages, dict)
    dependencies: dict[str, dict[str, object]] = {
        name: {"name": name, "version": version, "vulns": []} for name, version in packages.items()
    }
    dispositions = selected["dispositions"]
    assert isinstance(dispositions, list)
    for disposition in dispositions:
        assert isinstance(disposition, dict)
        package = disposition["package"]
        ids = disposition["advisory_ids"]
        assert isinstance(package, str)
        assert isinstance(ids, list)
        primary, *aliases = ids
        vulns = dependencies[package]["vulns"]
        assert isinstance(vulns, list)
        vulns.append(
            {
                "id": primary,
                "fix_versions": [],
                "aliases": aliases,
                "description": "fixture",
            }
        )
    return {
        "dependencies": [dependencies[name] for name in sorted(dependencies)],
        "fixes": [],
    }


def _audit_dependencies(audit: dict[str, object]) -> list[dict[str, object]]:
    dependencies = audit["dependencies"]
    assert isinstance(dependencies, list)
    assert all(isinstance(dependency, dict) for dependency in dependencies)
    return dependencies


def _receipt_payload(policy: dict[str, Any] | None = None) -> dict[str, object]:
    selected = _policy_payload() if policy is None else policy
    applicability = selected["applicability"]
    assert isinstance(applicability, dict)
    assets = applicability["assets"]
    assert isinstance(assets, list)
    return {
        "schema": 2,
        "source_sha256": applicability["source_sha256"],
        "source_directory": "source",
        "source_snapshot": "snapshot",
        "generation": "Ubuntu-generation",
        "environment_sha256": "2" * 64,
        "requested_distro": "Ubuntu",
        "runtime": {
            "schema": 2,
            "distro": "Ubuntu",
            "uid": 1000,
            "home": "/home/operator",
            "python": "/runtime/bin/python",
            "python_version": "3.12.13",
            "packages": applicability["packages"],
            "dependency_locks": {
                "build_sha256": applicability["build_lock_sha256"],
                "runtime_sha256": applicability["runtime_lock_sha256"],
            },
            "cuda_device_count": 2,
            "asset_cache": "/home/operator/.cache/fairseq2/assets",
            "assets": [dict(asset, path=f"/cache/{index}") for index, asset in enumerate(assets)],
        },
    }


def _write_json(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _evaluate_fixture(tmp_path: Path, policy: dict[str, Any] | None = None) -> None:
    selected = _policy_payload() if policy is None else policy
    policy_path = _write_json(tmp_path / "vex.json", selected)
    audit_path = _write_json(tmp_path / "audit.json", _audit_payload(selected))
    receipt_path = _write_json(tmp_path / "receipt.json", _receipt_payload(selected))
    findings, packages = load_pip_audit(audit_path)
    result = evaluate(
        load_vex(policy_path),
        load_runtime_identity(receipt_path),
        findings,
        packages,
        as_of=date(2026, 8, 9),
    )
    assert result.finding_count == 12
    assert result.disposition_count == 12
    assert result.matched_dispositions == 12


def test_checked_in_policy_binds_current_lock_and_assets_and_closes_report(tmp_path: Path) -> None:
    policy = load_vex(POLICY)
    assert policy.source_sha256 == package_digest(ROOT / "src" / "hawedit")
    assert policy.build_lock_sha256 == BUILD_LOCK_SHA256
    assert policy.runtime_lock_sha256 == RUNTIME_LOCK_SHA256
    assert {(asset.name, asset.size, asset.sha256) for asset in policy.assets} == {
        (asset.name, asset.size, asset.sha256) for asset in OMNI_ASSETS
    }
    _evaluate_fixture(tmp_path)


def test_reviewed_source_snapshot_drift_is_refused(tmp_path: Path) -> None:
    receipt = _receipt_payload()
    receipt["source_sha256"] = "f" * 64
    findings, packages = load_pip_audit(_write_json(tmp_path / "audit.json", _audit_payload()))
    with pytest.raises(VexError, match="source snapshot digest drifted"):
        evaluate(
            load_vex(POLICY),
            load_runtime_identity(_write_json(tmp_path / "receipt.json", receipt)),
            findings,
            packages,
            as_of=date(2026, 8, 9),
        )


def test_unknown_new_advisory_is_refused(tmp_path: Path) -> None:
    policy = _policy_payload()
    audit = _audit_payload(policy)
    torch = next(
        dependency for dependency in _audit_dependencies(audit) if dependency["name"] == "torch"
    )
    vulns = torch["vulns"]
    assert isinstance(vulns, list)
    vulns.append({"id": "CVE-2026-99999", "fix_versions": [], "aliases": [], "description": "new"})
    findings, packages = load_pip_audit(_write_json(tmp_path / "audit.json", audit))
    with pytest.raises(VexError, match="CVE-2026-99999.*0 applicable"):
        evaluate(
            load_vex(POLICY),
            load_runtime_identity(_write_json(tmp_path / "receipt.json", _receipt_payload(policy))),
            findings,
            packages,
            as_of=date(2026, 8, 9),
        )


def test_unknown_alias_on_known_advisory_is_refused(tmp_path: Path) -> None:
    audit = _audit_payload()
    vulns = _audit_dependencies(audit)[1]["vulns"]
    assert isinstance(vulns, list)
    assert isinstance(vulns[0], dict)
    aliases = vulns[0]["aliases"]
    assert isinstance(aliases, list)
    aliases.append("CVE-2026-99998")
    findings, packages = load_pip_audit(_write_json(tmp_path / "audit.json", audit))
    with pytest.raises(VexError, match="CVE-2026-99998.*0 applicable"):
        evaluate(
            load_vex(POLICY),
            load_runtime_identity(_write_json(tmp_path / "receipt.json", _receipt_payload())),
            findings,
            packages,
            as_of=date(2026, 8, 9),
        )


def test_expired_vex_is_refused_even_when_every_finding_matches(tmp_path: Path) -> None:
    policy = _policy_payload()
    policy["reviewed"] = "2026-07-08"
    policy["expires"] = "2026-08-08"
    policy_path = _write_json(tmp_path / "vex.json", policy)
    audit_path = _write_json(tmp_path / "audit.json", _audit_payload(policy))
    receipt_path = _write_json(tmp_path / "receipt.json", _receipt_payload(policy))
    findings, packages = load_pip_audit(audit_path)
    with pytest.raises(VexError, match="expired on 2026-08-08"):
        evaluate(
            load_vex(policy_path),
            load_runtime_identity(receipt_path),
            findings,
            packages,
            as_of=date(2026, 8, 9),
        )


@pytest.mark.parametrize("lock_name", ["build_sha256", "runtime_sha256"])
def test_observed_lock_drift_is_refused(tmp_path: Path, lock_name: str) -> None:
    receipt = _receipt_payload()
    runtime = receipt["runtime"]
    assert isinstance(runtime, dict)
    locks = runtime["dependency_locks"]
    assert isinstance(locks, dict)
    locks[lock_name] = "0" * 64
    findings, packages = load_pip_audit(_write_json(tmp_path / "audit.json", _audit_payload()))
    with pytest.raises(VexError, match="lock digest drifted"):
        evaluate(
            load_vex(POLICY),
            load_runtime_identity(_write_json(tmp_path / "receipt.json", receipt)),
            findings,
            packages,
            as_of=date(2026, 8, 9),
        )


def test_observed_asset_drift_is_refused(tmp_path: Path) -> None:
    receipt = _receipt_payload()
    runtime = receipt["runtime"]
    assert isinstance(runtime, dict)
    assets = runtime["assets"]
    assert isinstance(assets, list)
    assert isinstance(assets[0], dict)
    assets[0]["sha256"] = "0" * 64
    findings, packages = load_pip_audit(_write_json(tmp_path / "audit.json", _audit_payload()))
    with pytest.raises(VexError, match="asset byte identities drifted"):
        evaluate(
            load_vex(POLICY),
            load_runtime_identity(_write_json(tmp_path / "receipt.json", receipt)),
            findings,
            packages,
            as_of=date(2026, 8, 9),
        )


def test_truncated_audit_inventory_is_refused(tmp_path: Path) -> None:
    receipt = _receipt_payload()
    runtime = receipt["runtime"]
    assert isinstance(runtime, dict)
    packages = runtime["packages"]
    assert isinstance(packages, dict)
    packages["certifi"] = "2026.7.22"
    findings, audited = load_pip_audit(_write_json(tmp_path / "audit.json", _audit_payload()))
    with pytest.raises(VexError, match="inventory drifted.*certifi"):
        evaluate(
            load_vex(POLICY),
            load_runtime_identity(_write_json(tmp_path / "receipt.json", receipt)),
            findings,
            audited,
            as_of=date(2026, 8, 9),
        )


def test_alias_emitted_as_primary_still_matches_one_disposition(tmp_path: Path) -> None:
    audit = _audit_payload()
    first_vuln = _audit_dependencies(audit)[1]["vulns"]
    assert isinstance(first_vuln, list)
    assert isinstance(first_vuln[0], dict)
    primary = first_vuln[0]["id"]
    aliases = first_vuln[0]["aliases"]
    assert isinstance(primary, str)
    assert isinstance(aliases, list)
    first_vuln[0]["id"] = aliases[0]
    first_vuln[0]["aliases"] = [primary, *aliases[1:]]
    findings, packages = load_pip_audit(_write_json(tmp_path / "audit.json", audit))
    result = evaluate(
        load_vex(POLICY),
        load_runtime_identity(_write_json(tmp_path / "receipt.json", _receipt_payload())),
        findings,
        packages,
        as_of=date(2026, 8, 9),
    )
    assert result.matched_dispositions == 12


def test_duplicate_alias_across_dispositions_is_refused(tmp_path: Path) -> None:
    policy = _policy_payload()
    dispositions = policy["dispositions"]
    assert isinstance(dispositions, list)
    assert isinstance(dispositions[0], dict)
    assert isinstance(dispositions[1], dict)
    first_ids = dispositions[0]["advisory_ids"]
    second_ids = dispositions[1]["advisory_ids"]
    assert isinstance(first_ids, list)
    assert isinstance(second_ids, list)
    second_ids.append(first_ids[0])
    with pytest.raises(VexError, match="multiple dispositions"):
        load_vex(_write_json(tmp_path / "vex.json", policy))


def test_duplicate_primary_advisory_in_audit_is_refused(tmp_path: Path) -> None:
    audit = _audit_payload()
    vulns = _audit_dependencies(audit)[1]["vulns"]
    assert isinstance(vulns, list)
    vulns.append(dict(vulns[0]))
    with pytest.raises(VexError, match="repeats primary advisory"):
        load_pip_audit(_write_json(tmp_path / "audit.json", audit))


def test_captured_pip_audit_2_10_1_schema_is_accepted(tmp_path: Path) -> None:
    """Captured from pinned pip-audit 2.10.1 with OSV, aliases on, descriptions off."""
    report = {
        "dependencies": [
            {
                "name": "torch",
                "version": "2.8.0",
                "vulns": [
                    {
                        "id": "PYSEC-2026-2286",
                        "fix_versions": ["2.10.0"],
                        "aliases": [
                            "GHSA-63cw-57p8-fm3p",
                            "PYSEC-2026-1856",
                            "CVE-2026-24747",
                            "BIT-pytorch-2026-24747",
                        ],
                    }
                ],
            }
        ],
        "fixes": [],
    }
    findings, packages = load_pip_audit(_write_json(tmp_path / "captured.json", report))
    assert packages == {"torch": "2.8.0"}
    assert len(findings) == 1
    assert findings[0].primary_id == "PYSEC-2026-2286"
    assert "CVE-2026-24747" in findings[0].aliases


@pytest.mark.parametrize("fixes", [{}, True, [{"name": "torch"}]])
def test_audit_only_report_requires_an_empty_fixes_array(tmp_path: Path, fixes: object) -> None:
    report = _audit_payload()
    report["fixes"] = fixes
    with pytest.raises(VexError, match="fixes"):
        load_pip_audit(_write_json(tmp_path / "fixes.json", report))


def test_removed_advisory_makes_the_disposition_visibly_stale(tmp_path: Path) -> None:
    audit = _audit_payload()
    vulns = _audit_dependencies(audit)[1]["vulns"]
    assert isinstance(vulns, list)
    vulns.pop()
    findings, packages = load_pip_audit(_write_json(tmp_path / "audit.json", audit))
    with pytest.raises(VexError, match="stale dispositions"):
        evaluate(
            load_vex(POLICY),
            load_runtime_identity(_write_json(tmp_path / "receipt.json", _receipt_payload())),
            findings,
            packages,
            as_of=date(2026, 8, 9),
        )


@pytest.mark.parametrize(
    ("loader", "payload", "message"),
    [
        (load_vex, [], "VEX document must be an object"),
        (load_pip_audit, [], "pip-audit report must be an object"),
        (load_runtime_identity, [], "WSL runtime receipt must be an object"),
    ],
)
def test_malformed_top_level_is_refused(
    tmp_path: Path, loader: Any, payload: object, message: str
) -> None:
    with pytest.raises(VexError, match=message):
        loader(_write_json(tmp_path / "input.json", payload))


def test_boolean_schema_and_size_are_not_coerced(tmp_path: Path) -> None:
    policy = _policy_payload()
    policy["schema"] = True
    with pytest.raises(VexError, match="not a boolean"):
        load_vex(_write_json(tmp_path / "bool-schema.json", policy))

    receipt = _receipt_payload()
    runtime = receipt["runtime"]
    assert isinstance(runtime, dict)
    assets = runtime["assets"]
    assert isinstance(assets, list)
    assert isinstance(assets[0], dict)
    assets[0]["size"] = True
    with pytest.raises(VexError, match="not a boolean"):
        load_runtime_identity(_write_json(tmp_path / "bool-size.json", receipt))


def test_duplicate_json_key_unknown_status_and_missing_controls_are_refused(
    tmp_path: Path,
) -> None:
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"schema": 1, "schema": 1}', encoding="utf-8")
    with pytest.raises(VexError, match="duplicate JSON key 'schema'"):
        load_vex(duplicate)

    policy = _policy_payload()
    dispositions = policy["dispositions"]
    assert isinstance(dispositions, list)
    assert isinstance(dispositions[0], dict)
    dispositions[0]["status"] = "mitigated"
    with pytest.raises(VexError, match="unknown or unresolved status"):
        load_vex(_write_json(tmp_path / "status.json", policy))

    policy = _policy_payload()
    dispositions = policy["dispositions"]
    assert isinstance(dispositions, list)
    assert isinstance(dispositions[0], dict)
    dispositions[0]["controls"] = []
    with pytest.raises(VexError, match="controls must not be empty"):
        load_vex(_write_json(tmp_path / "controls.json", policy))


def test_cli_accepts_closed_fixture_and_refuses_unknown_advisory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    receipt = _write_json(tmp_path / "receipt.json", _receipt_payload())
    report = _write_json(tmp_path / "audit.json", _audit_payload())
    assert (
        main(
            [
                "--vex",
                str(POLICY),
                "--receipt",
                str(receipt),
                "--report",
                str(report),
                "--as-of",
                "2026-08-09",
            ]
        )
        == 0
    )
    assert '"status": "accepted"' in capsys.readouterr().out

    audit = _audit_payload()
    torch = next(
        dependency for dependency in _audit_dependencies(audit) if dependency["name"] == "torch"
    )
    vulns = torch["vulns"]
    assert isinstance(vulns, list)
    vulns.append({"id": "CVE-2026-99999", "fix_versions": [], "aliases": []})
    _write_json(report, audit)
    assert (
        main(
            [
                "--vex",
                str(POLICY),
                "--receipt",
                str(receipt),
                "--report",
                str(report),
                "--as-of",
                "2026-08-09",
            ]
        )
        == 1
    )
    assert "CVE-2026-99999" in capsys.readouterr().err


def test_default_policy_resolves_authenticated_installed_data_outside_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hawedit import vex as vex_module

    fake_module = tmp_path / "target" / "hawedit" / "vex.py"
    fake_module.parent.mkdir(parents=True)
    fake_module.write_text("", encoding="utf-8")
    installed = tmp_path / "target" / "share" / "hawedit" / "security" / POLICY.name
    installed.parent.mkdir(parents=True)
    installed.write_bytes(POLICY.read_bytes())
    requested: list[str] = []

    def resolve(relative: str) -> Path:
        requested.append(relative)
        return installed

    monkeypatch.setattr(vex_module, "__file__", str(fake_module))
    monkeypatch.setattr(vex_module, "resolve_installed_hawedit_data", resolve)

    assert vex_module._default_vex_path() == installed
    assert requested == ["share/hawedit/security/wsl-asr-vex.json"]

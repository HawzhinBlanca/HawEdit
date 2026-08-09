"""Strict VEX gate for the isolated WSL OmniASR dependency graph.

The gate consumes pip-audit's JSON output and the already-published WSL runtime receipt.  A
finding is accepted only when one reviewed disposition covers one of its emitted IDs or aliases,
the disposition has not expired, and the receipt still has the exact lock and model-byte identity
that was reviewed.  Dispositions which the current report no longer emits are rejected as stale
so removals and advisory re-keying receive a human review instead of silently accumulating.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Final, cast

from hawedit.environment import EnvironmentAuditError, resolve_installed_hawedit_data

_VEX_LIMIT: Final = 1_048_576
_REPORT_LIMIT: Final = 16_777_216
_RECEIPT_LIMIT: Final = 2_097_152
_SHA256: Final = re.compile(r"[0-9a-f]{64}")
_PACKAGE: Final = re.compile(r"[a-z0-9]+(?:[-_.][a-z0-9]+)*")
_ADVISORY: Final = re.compile(
    r"(?:CVE-[0-9]{4}-[0-9]{4,}|GHSA-[0-9a-z]{4}-[0-9a-z]{4}-[0-9a-z]{4}|"
    r"PYSEC-[0-9]{4}-[0-9]+|BIT-[a-z0-9-]+)",
    re.IGNORECASE,
)
_STATUSES: Final = frozenset({"affected", "not_affected", "fixed"})


class VexError(RuntimeError):
    """The audit, receipt, or VEX policy is malformed or does not close the findings."""


@dataclass(frozen=True, order=True)
class AssetIdentity:
    name: str
    size: int
    sha256: str


@dataclass(frozen=True)
class RuntimeIdentity:
    source_sha256: str
    python_version: str
    packages: dict[str, str]
    build_lock_sha256: str
    runtime_lock_sha256: str
    assets: tuple[AssetIdentity, ...]


@dataclass(frozen=True)
class Finding:
    package: str
    version: str
    primary_id: str
    aliases: tuple[str, ...]

    @property
    def identifiers(self) -> frozenset[str]:
        return frozenset((self.primary_id, *self.aliases))


@dataclass(frozen=True)
class Disposition:
    advisory_ids: frozenset[str]
    package: str
    version: str
    status: str
    justification: str
    controls: tuple[str, ...]
    sources: tuple[str, ...]


@dataclass(frozen=True)
class VexDocument:
    reviewed: date
    expires: date
    python: str
    source_sha256: str
    packages: dict[str, str]
    build_lock_sha256: str
    runtime_lock_sha256: str
    assets: tuple[AssetIdentity, ...]
    dispositions: tuple[Disposition, ...]


@dataclass(frozen=True)
class Evaluation:
    finding_count: int
    disposition_count: int
    matched_dispositions: int


def _duplicate_safe_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise VexError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _load_bytes(path: Path, *, limit: int, label: str) -> bytes:
    try:
        if path.is_symlink() or not path.is_file():
            raise VexError(f"{label} is not one regular file: {path}")
        size = path.stat().st_size
        if size > limit:
            raise VexError(f"{label} exceeds the {limit}-byte input limit")
        return path.read_bytes()
    except VexError:
        raise
    except OSError as exc:
        raise VexError(f"cannot read {label}: {exc}") from exc


def _load_json(path: Path, *, limit: int, label: str) -> object:
    try:
        return json.loads(
            _load_bytes(path, limit=limit, label=label).decode("utf-8"),
            object_pairs_hook=_duplicate_safe_object,
        )
    except VexError:
        raise
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise VexError(f"cannot decode {label}: {exc}") from exc


def _object(value: object, label: str) -> dict[str, object]:
    if type(value) is not dict:
        raise VexError(f"{label} must be an object")
    return cast(dict[str, object], value)


def _list(value: object, label: str) -> list[object]:
    if type(value) is not list:
        raise VexError(f"{label} must be an array")
    return cast(list[object], value)


def _string(value: object, label: str) -> str:
    if type(value) is not str or not value.strip() or value != value.strip():
        raise VexError(f"{label} must be one non-empty, trimmed string")
    assert isinstance(value, str)
    return value


def _integer(value: object, label: str) -> int:
    if type(value) is not int:
        raise VexError(f"{label} must be an integer, not a boolean or coercible value")
    assert isinstance(value, int)
    return value


def _keys(value: dict[str, object], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        raise VexError(
            f"{label} keys drifted: missing={sorted(expected - actual)!r}, "
            f"unknown={sorted(actual - expected)!r}"
        )


def _digest(value: object, label: str) -> str:
    digest = _string(value, label)
    if _SHA256.fullmatch(digest) is None:
        raise VexError(f"{label} must be a lowercase SHA-256 digest")
    return digest


def _day(value: object, label: str) -> date:
    raw = _string(value, label)
    try:
        parsed = date.fromisoformat(raw)
    except ValueError as exc:
        raise VexError(f"{label} must be an ISO calendar date") from exc
    if parsed.isoformat() != raw:
        raise VexError(f"{label} must use canonical YYYY-MM-DD form")
    return parsed


def _package_name(value: object, label: str) -> str:
    name = _string(value, label)
    if name != name.lower() or _PACKAGE.fullmatch(name) is None:
        raise VexError(f"{label} must be one normalized lowercase distribution name")
    return name.replace("_", "-").replace(".", "-")


def _advisory_id(value: object, label: str) -> str:
    identifier = _string(value, label).upper()
    if _ADVISORY.fullmatch(identifier) is None:
        raise VexError(f"{label} is not a supported CVE/GHSA/PYSEC/BIT advisory ID")
    return identifier


def _strings(value: object, label: str) -> tuple[str, ...]:
    result = tuple(
        _string(item, f"{label}[{index}]") for index, item in enumerate(_list(value, label))
    )
    if not result:
        raise VexError(f"{label} must not be empty")
    if len(set(result)) != len(result):
        raise VexError(f"{label} contains a duplicate")
    return result


def _parse_assets(value: object, label: str, *, with_path: bool) -> tuple[AssetIdentity, ...]:
    result: list[AssetIdentity] = []
    seen: set[str] = set()
    expected_keys = {"name", "size", "sha256", "path"} if with_path else {"name", "size", "sha256"}
    for index, item in enumerate(_list(value, label)):
        raw = _object(item, f"{label}[{index}]")
        _keys(raw, expected_keys, f"{label}[{index}]")
        name = _string(raw["name"], f"{label}[{index}].name")
        if name in seen:
            raise VexError(f"{label} repeats asset {name!r}")
        seen.add(name)
        size = _integer(raw["size"], f"{label}[{index}].size")
        if size <= 0:
            raise VexError(f"{label}[{index}].size must be positive")
        digest = _digest(raw["sha256"], f"{label}[{index}].sha256")
        if with_path:
            _string(raw["path"], f"{label}[{index}].path")
        result.append(AssetIdentity(name, size, digest))
    if not result:
        raise VexError(f"{label} must not be empty")
    return tuple(sorted(result))


def _parse_vex(raw_value: object) -> VexDocument:
    raw = _object(raw_value, "VEX document")
    _keys(
        raw,
        {"schema", "product", "reviewed", "expires", "applicability", "dispositions"},
        "VEX document",
    )
    if _integer(raw["schema"], "VEX schema") != 1:
        raise VexError("VEX schema must be exactly 1")
    if _string(raw["product"], "VEX product") != "hawedit-wsl-asr":
        raise VexError("VEX product must be exactly 'hawedit-wsl-asr'")
    reviewed = _day(raw["reviewed"], "VEX reviewed")
    expires = _day(raw["expires"], "VEX expires")
    if expires <= reviewed:
        raise VexError("VEX expires must be later than VEX reviewed")

    applicability = _object(raw["applicability"], "VEX applicability")
    _keys(
        applicability,
        {
            "python",
            "source_sha256",
            "packages",
            "build_lock_sha256",
            "runtime_lock_sha256",
            "assets",
        },
        "VEX applicability",
    )
    python = _string(applicability["python"], "VEX applicability.python")
    if re.fullmatch(r"[0-9]+\.[0-9]+", python) is None:
        raise VexError("VEX applicability.python must be an exact major.minor version")
    raw_packages = _object(applicability["packages"], "VEX applicability.packages")
    if not raw_packages:
        raise VexError("VEX applicability.packages must not be empty")
    packages: dict[str, str] = {}
    for raw_name, raw_version in raw_packages.items():
        name = _package_name(raw_name, "VEX package name")
        if name in packages:
            raise VexError(f"VEX applicability repeats normalized package {name!r}")
        packages[name] = _string(raw_version, f"VEX package {name} version")

    dispositions: list[Disposition] = []
    claimed_ids: set[str] = set()
    for index, item in enumerate(_list(raw["dispositions"], "VEX dispositions")):
        value = _object(item, f"VEX dispositions[{index}]")
        _keys(
            value,
            {
                "advisory_ids",
                "package",
                "version",
                "status",
                "justification",
                "controls",
                "sources",
            },
            f"VEX dispositions[{index}]",
        )
        ids = frozenset(
            _advisory_id(raw_id, f"VEX dispositions[{index}].advisory_ids")
            for raw_id in _list(value["advisory_ids"], f"VEX dispositions[{index}].advisory_ids")
        )
        if not ids:
            raise VexError(f"VEX dispositions[{index}].advisory_ids must not be empty")
        if len(ids) != len(_list(value["advisory_ids"], "advisory IDs")):
            raise VexError(f"VEX dispositions[{index}] repeats an advisory ID or alias")
        overlap = claimed_ids & ids
        if overlap:
            raise VexError(
                f"VEX advisory IDs/aliases occur in multiple dispositions: {sorted(overlap)!r}"
            )
        claimed_ids.update(ids)
        package = _package_name(value["package"], f"VEX dispositions[{index}].package")
        version = _string(value["version"], f"VEX dispositions[{index}].version")
        if packages.get(package) != version:
            raise VexError(f"VEX disposition {index} is outside its package applicability")
        status = _string(value["status"], f"VEX dispositions[{index}].status")
        if status not in _STATUSES:
            raise VexError(f"VEX disposition {index} has unknown or unresolved status {status!r}")
        controls = _strings(value["controls"], f"VEX dispositions[{index}].controls")
        sources = _strings(value["sources"], f"VEX dispositions[{index}].sources")
        if any(not source.startswith("https://") for source in sources):
            raise VexError(f"VEX disposition {index} sources must all be HTTPS URLs")
        dispositions.append(
            Disposition(
                ids,
                package,
                version,
                status,
                _string(value["justification"], f"VEX dispositions[{index}].justification"),
                controls,
                sources,
            )
        )
    if not dispositions:
        raise VexError("VEX dispositions must not be empty")
    return VexDocument(
        reviewed,
        expires,
        python,
        _digest(applicability["source_sha256"], "VEX source snapshot"),
        dict(sorted(packages.items())),
        _digest(applicability["build_lock_sha256"], "VEX build lock"),
        _digest(applicability["runtime_lock_sha256"], "VEX runtime lock"),
        _parse_assets(applicability["assets"], "VEX applicability.assets", with_path=False),
        tuple(dispositions),
    )


def parse_vex_json(payload: bytes) -> VexDocument:
    """Parse one bounded VEX byte snapshot without reopening a mutable pathname."""
    if len(payload) > _VEX_LIMIT:
        raise VexError(f"VEX document exceeds the {_VEX_LIMIT}-byte input limit")
    try:
        raw = json.loads(payload.decode("utf-8"), object_pairs_hook=_duplicate_safe_object)
    except VexError:
        raise
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise VexError(f"cannot decode VEX document: {exc}") from exc
    return _parse_vex(raw)


def load_vex(path: Path) -> VexDocument:
    """Load the intentionally narrow HawEdit WSL-ASR VEX schema."""
    return parse_vex_json(_load_bytes(path, limit=_VEX_LIMIT, label="VEX document"))


def load_runtime_identity(path: Path) -> RuntimeIdentity:
    """Extract the observed identity from a canonical ``.ready`` WSL receipt."""
    raw = _object(
        _load_json(path, limit=_RECEIPT_LIMIT, label="WSL runtime receipt"),
        "WSL runtime receipt",
    )
    _keys(
        raw,
        {
            "schema",
            "source_sha256",
            "source_directory",
            "source_snapshot",
            "generation",
            "environment_sha256",
            "requested_distro",
            "runtime",
        },
        "WSL runtime receipt",
    )
    if _integer(raw["schema"], "WSL runtime receipt.schema") != 2:
        raise VexError("WSL runtime receipt.schema must be exactly 2")
    _digest(raw["source_sha256"], "WSL runtime receipt.source_sha256")
    _digest(raw["environment_sha256"], "WSL runtime receipt.environment_sha256")
    for field in ("source_directory", "source_snapshot", "generation"):
        _string(raw[field], f"WSL runtime receipt.{field}")
    if type(raw["requested_distro"]) is not str:
        raise VexError("WSL runtime receipt.requested_distro must be a string")
    runtime = _object(raw["runtime"], "WSL runtime receipt.runtime")
    _keys(
        runtime,
        {
            "schema",
            "distro",
            "uid",
            "home",
            "python",
            "python_version",
            "packages",
            "dependency_locks",
            "cuda_device_count",
            "asset_cache",
            "assets",
        },
        "WSL runtime receipt.runtime",
    )
    if _integer(runtime["schema"], "WSL runtime receipt.runtime.schema") != 2:
        raise VexError("WSL runtime receipt.runtime.schema must be exactly 2")
    if _integer(runtime["uid"], "WSL runtime receipt.runtime.uid") < 0:
        raise VexError("WSL runtime receipt.runtime.uid must not be negative")
    if _integer(runtime["cuda_device_count"], "WSL runtime receipt.runtime.cuda_device_count") < 2:
        raise VexError("WSL runtime receipt must prove at least two CUDA devices")
    for field in ("distro", "home", "python", "asset_cache"):
        _string(runtime[field], f"WSL runtime receipt.runtime.{field}")
    packages_value = _object(runtime["packages"], "WSL runtime receipt.runtime.packages")
    packages: dict[str, str] = {}
    for raw_name, raw_version in packages_value.items():
        name = _package_name(raw_name, "WSL runtime package name")
        if name in packages:
            raise VexError(f"WSL receipt repeats normalized package {name!r}")
        packages[name] = _string(raw_version, f"WSL runtime package {name} version")
    locks = _object(runtime["dependency_locks"], "WSL runtime receipt.dependency_locks")
    _keys(locks, {"build_sha256", "runtime_sha256"}, "WSL runtime receipt.dependency_locks")
    return RuntimeIdentity(
        _digest(raw["source_sha256"], "WSL runtime receipt.source_sha256"),
        _string(runtime["python_version"], "WSL runtime receipt.runtime.python_version"),
        dict(sorted(packages.items())),
        _digest(locks["build_sha256"], "WSL runtime build lock"),
        _digest(locks["runtime_sha256"], "WSL runtime dependency lock"),
        _parse_assets(runtime["assets"], "WSL runtime receipt.runtime.assets", with_path=True),
    )


def _parse_pip_audit(raw: object) -> tuple[tuple[Finding, ...], dict[str, str]]:
    document = _object(raw, "pip-audit report")
    _keys(document, {"dependencies", "fixes"}, "pip-audit report")
    applied_fixes = _list(document["fixes"], "pip-audit report.fixes")
    if applied_fixes:
        raise VexError("pip-audit report.fixes must be empty for a non-mutating audit")
    dependencies = _list(document["dependencies"], "pip-audit report.dependencies")
    findings: list[Finding] = []
    packages: dict[str, str] = {}
    primary_findings: dict[tuple[str, str], Finding] = {}
    for dep_index, item in enumerate(dependencies):
        label = f"pip-audit report.dependencies[{dep_index}]"
        dependency = _object(item, label)
        _keys(dependency, {"name", "version", "vulns"}, label)
        name = _package_name(dependency["name"], f"{label}.name")
        version = _string(dependency["version"], f"{label}.version")
        if name in packages:
            raise VexError(f"pip-audit report repeats normalized dependency {name!r}")
        packages[name] = version
        for vuln_index, raw_vuln in enumerate(_list(dependency["vulns"], f"{label}.vulns")):
            vuln = _object(raw_vuln, f"pip-audit vulnerability {dep_index}:{vuln_index}")
            required = {"id", "fix_versions", "aliases"}
            if not required <= set(vuln) or set(vuln) - (required | {"description"}):
                raise VexError(
                    f"pip-audit vulnerability {dep_index}:{vuln_index} has missing or unknown keys"
                )
            primary = _advisory_id(vuln["id"], "pip-audit vulnerability ID")
            aliases = tuple(
                _advisory_id(alias, "pip-audit vulnerability alias")
                for alias in _list(vuln["aliases"], "pip-audit vulnerability aliases")
            )
            if primary in aliases or len(set(aliases)) != len(aliases):
                raise VexError(f"pip-audit vulnerability {primary} repeats an ID or alias")
            fix_versions = tuple(
                _string(version, "pip-audit vulnerability fix version")
                for version in _list(vuln["fix_versions"], "pip-audit vulnerability fix_versions")
            )
            if len(fix_versions) != len(set(fix_versions)):
                raise VexError(f"pip-audit vulnerability {primary} repeats a fix version")
            if "description" in vuln and type(vuln["description"]) is not str:
                raise VexError("pip-audit vulnerability description must be a string")
            key = (name, primary)
            finding = Finding(name, version, primary, tuple(sorted(aliases)))
            previous = primary_findings.get(key)
            if previous is not None:
                if previous != finding:
                    raise VexError(
                        f"pip-audit report gives conflicting identities for advisory "
                        f"{primary} on {name}"
                    )
                # OSV can emit one row per affected range, with different fix_versions, while
                # retaining the same primary/alias identity. Fix versions do not determine VEX
                # coverage; the raw report stays digest-bound in the live evidence.
                continue
            primary_findings[key] = finding
            findings.append(finding)
    return tuple(findings), dict(sorted(packages.items()))


def parse_pip_audit_json(
    payload: bytes,
) -> tuple[tuple[Finding, ...], dict[str, str], dict[str, object]]:
    """Parse bounded pip-audit 2.10.1 JSON bytes and retain the validated document."""
    if len(payload) > _REPORT_LIMIT:
        raise VexError(f"pip-audit report exceeds the {_REPORT_LIMIT}-byte input limit")
    try:
        raw = json.loads(payload.decode("utf-8"), object_pairs_hook=_duplicate_safe_object)
    except VexError:
        raise
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise VexError(f"cannot decode pip-audit report: {exc}") from exc
    findings, packages = _parse_pip_audit(raw)
    return findings, packages, _object(raw, "pip-audit report")


def load_pip_audit(path: Path) -> tuple[tuple[Finding, ...], dict[str, str]]:
    """Parse pip-audit 2.10.1's ``dependencies``/``fixes`` JSON object."""
    return _parse_pip_audit(_load_json(path, limit=_REPORT_LIMIT, label="pip-audit report"))


def evaluate(
    vex: VexDocument,
    identity: RuntimeIdentity,
    findings: tuple[Finding, ...],
    audited_packages: dict[str, str],
    *,
    as_of: date | None = None,
) -> Evaluation:
    """Refuse identity drift, unknown findings, expired policy, and stale dispositions."""
    today = date.today() if as_of is None else as_of
    failures: list[str] = []
    if today < vex.reviewed:
        failures.append(f"VEX review date {vex.reviewed.isoformat()} is in the future")
    if today > vex.expires:
        failures.append(f"VEX expired on {vex.expires.isoformat()}")
    if ".".join(identity.python_version.split(".")[:2]) != vex.python:
        failures.append(f"Python identity drift: {identity.python_version!r} != {vex.python!r}")
    if identity.source_sha256 != vex.source_sha256:
        failures.append("HawEdit source snapshot digest drifted")
    if identity.build_lock_sha256 != vex.build_lock_sha256:
        failures.append("WSL ASR build lock digest drifted")
    if identity.runtime_lock_sha256 != vex.runtime_lock_sha256:
        failures.append("WSL ASR runtime lock digest drifted")
    if identity.assets != vex.assets:
        failures.append("OmniASR asset byte identities drifted")
    if audited_packages != identity.packages:
        missing = sorted(set(identity.packages) - set(audited_packages))
        extra = sorted(set(audited_packages) - set(identity.packages))
        changed = sorted(
            package
            for package in set(identity.packages) & set(audited_packages)
            if identity.packages[package] != audited_packages[package]
        )
        failures.append(
            f"pip-audit inventory drifted from the WSL receipt: "
            f"missing={missing!r}, extra={extra!r}, changed={changed!r}"
        )
    for package, expected_version in vex.packages.items():
        if identity.packages.get(package) != expected_version:
            failures.append(f"runtime package drift: {package} != {expected_version}")
        if audited_packages.get(package) != expected_version:
            failures.append(f"pip-audit did not audit {package}=={expected_version}")

    matched: set[int] = set()
    for finding in findings:
        candidates = [
            index
            for index, disposition in enumerate(vex.dispositions)
            if disposition.package == finding.package
            and disposition.version == finding.version
            and finding.identifiers <= disposition.advisory_ids
        ]
        if len(candidates) != 1:
            label = "/".join(sorted(finding.identifiers))
            failures.append(
                f"{finding.package}=={finding.version} finding {label} has "
                f"{len(candidates)} applicable dispositions"
            )
        else:
            matched.add(candidates[0])

    stale = [
        "/".join(sorted(disposition.advisory_ids))
        for index, disposition in enumerate(vex.dispositions)
        if index not in matched
    ]
    if stale:
        failures.append(f"VEX has stale dispositions not emitted by this audit: {stale!r}")
    if failures:
        raise VexError("; ".join(failures))
    return Evaluation(len(findings), len(vex.dispositions), len(matched))


def _default_vex_path() -> Path:
    checkout = Path(__file__).resolve().parents[2] / "security" / "wsl-asr-vex.json"
    if checkout.is_file():
        return checkout
    try:
        return resolve_installed_hawedit_data("share/hawedit/security/wsl-asr-vex.json")
    except EnvironmentAuditError as exc:
        raise VexError(f"cannot authenticate the installed WSL ASR VEX policy: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Enforce HawEdit's WSL OmniASR VEX policy")
    parser.add_argument("--report", required=True, type=Path, help="pip-audit 2.10 JSON report")
    parser.add_argument("--receipt", required=True, type=Path, help="canonical WSL .ready receipt")
    parser.add_argument(
        "--vex", type=Path, help="reviewed VEX file (defaults to authenticated package data)"
    )
    parser.add_argument("--as-of", type=str, help="override evaluation date (tests/replay only)")
    args = parser.parse_args(argv)
    try:
        as_of = _day(args.as_of, "--as-of") if args.as_of is not None else None
        vex = load_vex(args.vex if args.vex is not None else _default_vex_path())
        identity = load_runtime_identity(args.receipt)
        findings, packages = load_pip_audit(args.report)
        result = evaluate(vex, identity, findings, packages, as_of=as_of)
    except VexError as exc:
        print(f"WSL ASR VEX REFUSED: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "dispositions": result.disposition_count,
                "findings": result.finding_count,
                "matched_dispositions": result.matched_dispositions,
                "status": "accepted",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through main()
    raise SystemExit(main())

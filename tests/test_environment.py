"""The canonical gate must prove which project and dependency metadata it is running."""

from __future__ import annotations

import base64
import hashlib
import importlib.metadata as metadata
import json
import os
import platform
import re
import sys
from pathlib import Path

import pytest

from hawedit.environment import (
    EnvironmentAuditError,
    _audit_environment,
    audit_installed_profile,
    dependency_contract_digest,
    resolve_installed_hawedit_data,
    resolve_installed_host_lock,
    validate_host_lock,
)

TEST_LOCK_HASHES: dict[str, str] = {}
ROOT = Path(__file__).resolve().parents[1]


class _Distribution(metadata.Distribution):
    def __init__(
        self,
        root: Path,
        *,
        direct_url: dict[str, object] | None,
        metadata_path: Path | None = None,
        name: str = "hawedit",
        located_files: dict[str, Path] | None = None,
        requirements: tuple[str, ...] = ("fonttools==4.60.2", "klpt==0.1.7"),
        requires_python: str = ">=3.11,<3.13",
        version: str = "0.1.0",
    ) -> None:
        self.root = root
        self._path = metadata_path or root / f"{name}-{version}.dist-info"
        self._direct_url = direct_url
        self._located_files = located_files
        self._record_text: str | None = None
        requires = "".join(f"Requires-Dist: {item}\n" for item in requirements)
        self._metadata = (
            "Metadata-Version: 2.4\n"
            f"Name: {name}\n"
            f"Version: {version}\n"
            f"Requires-Python: {requires_python}\n"
            f"{requires}\n"
        )

    def read_text(self, filename: str) -> str | None:
        if filename == "METADATA":
            return self._metadata
        if filename == "direct_url.json" and self._direct_url is not None:
            return json.dumps(self._direct_url)
        if filename == "RECORD" and self._located_files is not None:
            if self._record_text is not None:
                return self._record_text
            rows = []
            for relative, path in self._located_files.items():
                content = path.read_bytes()
                digest = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=")
                rows.append(f"{relative},sha256={digest.decode('ascii')},{len(content)}")
            return "\n".join(rows) + "\n"
        return None

    def locate_file(self, path: str | os.PathLike[str]) -> Path:
        if self._located_files is not None:
            located = self._located_files.get(os.fspath(path).replace("\\", "/"))
            if located is not None:
                return located
        return self.root / path

    @property
    def files(self) -> list[metadata.PackagePath] | None:
        if self._located_files is None:
            return None
        entries: list[metadata.PackagePath] = []
        for relative in self._located_files:
            entry = metadata.PackagePath(relative)
            entry.dist = self
            entries.append(entry)
        return entries


def _write_project(root: Path) -> None:
    (root / "requirements").mkdir(exist_ok=True)
    (root / "requirements" / "release-build.txt").write_text(
        "pip==26.2.1 --hash=sha256:" + "a" * 64 + "\n",
        encoding="utf-8",
    )
    (root / "pyproject.toml").write_text(
        """
[project]
name = "hawedit"
version = "0.1.0"
requires-python = ">=3.11,<3.13"
dependencies = ["fonttools==4.60.2", "klpt==0.1.7"]

[project.optional-dependencies]
dev = ["pytest==9.1.1"]
media = ["torch==2.13.0"]
models = ["huggingface-hub==0.36.2"]
asr = [
    "torch==2.8.0; platform_system != 'Windows'",
    "torchaudio==2.8.0; platform_system != 'Windows'",
    "qwen-asr==0.0.6; platform_system != 'Windows'",
]
markers = [
    "active-marker==1.2.3; python_version >= '3.11'",
    "inactive-marker==9.9.9; python_version < '3.11'",
]
bad-marker = ["floating>=1.0; python_version >= '3.11'"]
""".strip(),
        encoding="utf-8",
    )


def _editable(root: Path) -> dict[str, object]:
    return {"dir_info": {"editable": True}, "url": root.resolve().as_uri()}


def _write_lock(
    root: Path,
    *,
    extras: tuple[str, ...] = (),
    packages: tuple[tuple[str, str], ...] = (
        ("fonttools", "4.60.2"),
        ("klpt", "0.1.7"),
    ),
    platform_name: str = "linux",
    python: str = "3.11",
) -> Path:
    scope = {(): "base", ("dev", "media"): "gate", ("models",): "models"}[extras]
    path = root / "requirements" / f"host-{scope}-{platform_name}-py{python.replace('.', '')}.txt"
    lines = [
        "# hawedit-lock-version: 1",
        f"# scope: {scope}",
        f"# target-platform: {platform_name}",
        f"# target-python: {python}",
        f"# extras: {','.join(extras) or '-'}",
        "# project-version: 0.1.0",
        f"# contract-sha256: {dependency_contract_digest(root, extras)}",
        "# resolver: uv==0.11.26",
        "# exclude-newer: 2026-08-09T00:00:00Z",
        "--extra-index-url https://download.pytorch.org/whl/cpu",
        "--only-binary=:all:",
    ]
    lines.extend(
        f"{name}=={version} --hash=sha256:{index:064x}"
        for index, (name, version) in enumerate(packages, 1)
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    TEST_LOCK_HASHES[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return path


def _audit(
    root: Path | None,
    distribution: _Distribution,
    versions: dict[str, str],
    *,
    extras: tuple[str, ...] = (),
    python_version: tuple[int, int] = (3, 11),
) -> None:
    _audit_environment(
        root,
        extras,
        python_version=python_version,
        distributions=(distribution,),
        version_getter=versions.__getitem__,
    )


def test_clean_editable_gate_environment_is_accepted(tmp_path: Path) -> None:
    _write_project(tmp_path)
    distribution = _Distribution(tmp_path, direct_url=_editable(tmp_path))
    companion = _Distribution(
        tmp_path,
        direct_url=None,
        metadata_path=tmp_path / "src" / "hawedit.egg-info",
    )
    report = _audit_environment(
        tmp_path,
        ("dev", "media"),
        python_version=(3, 12),
        distributions=(distribution, companion),
        version_getter={
            "fonttools": "4.60.2",
            "klpt": "0.1.7",
            "pytest": "9.1.1",
            "torch": "2.13.0+cpu",
        }.__getitem__,
    )
    assert report.project_root == tmp_path.resolve()
    assert report.python_version == (3, 12)
    assert ("torch", "2.13.0+cpu") in report.checked_requirements


def test_unsupported_interpreter_is_refused(tmp_path: Path) -> None:
    _write_project(tmp_path)
    distribution = _Distribution(tmp_path, direct_url=_editable(tmp_path))
    with pytest.raises(EnvironmentAuditError, match=r"Python 3\.13 is unsupported"):
        _audit(
            tmp_path,
            distribution,
            {"fonttools": "4.60.2", "klpt": "0.1.7"},
            python_version=(3, 13),
        )


def test_installed_metadata_may_canonically_reorder_python_bounds(tmp_path: Path) -> None:
    distribution = _Distribution(
        tmp_path,
        direct_url=None,
        requires_python="<3.13, >=3.11",
    )
    _audit(
        None,
        distribution,
        {"fonttools": "4.60.2", "klpt": "0.1.7"},
        python_version=(3, 12),
    )


@pytest.mark.parametrize(
    "requires_python",
    (">=3.11", ">=3.11,<=3.12", ">=3.11,>=3.12", ">=3.11,<3.13,!=3.12"),
)
def test_installed_metadata_refuses_ambiguous_python_bounds(
    tmp_path: Path, requires_python: str
) -> None:
    distribution = _Distribution(
        tmp_path,
        direct_url=None,
        requires_python=requires_python,
    )
    with pytest.raises(EnvironmentAuditError, match="unsupported Requires-Python form"):
        _audit(
            None,
            distribution,
            {"fonttools": "4.60.2", "klpt": "0.1.7"},
            python_version=(3, 12),
        )


@pytest.mark.parametrize("count", [0, 2])
def test_zero_or_duplicate_hawedit_distributions_are_refused(tmp_path: Path, count: int) -> None:
    _write_project(tmp_path)
    distributions = tuple(
        _Distribution(tmp_path / str(index), direct_url=_editable(tmp_path))
        for index in range(count)
    )
    with pytest.raises(
        EnvironmentAuditError,
        match=rf"exactly one authoritative editable HawEdit .dist-info; found {count}",
    ):
        _audit_environment(
            tmp_path,
            (),
            python_version=(3, 11),
            distributions=distributions,
            version_getter={"fonttools": "4.60.2", "klpt": "0.1.7"}.__getitem__,
        )


def test_editable_install_from_another_checkout_is_refused(tmp_path: Path) -> None:
    current = tmp_path / "current"
    other = tmp_path / "other"
    current.mkdir()
    other.mkdir()
    _write_project(current)
    distribution = _Distribution(other, direct_url=_editable(other))
    with pytest.raises(EnvironmentAuditError, match="not current checkout"):
        _audit(
            current,
            distribution,
            {"fonttools": "4.60.2", "klpt": "0.1.7"},
        )


def test_source_gate_refuses_a_non_editable_install(tmp_path: Path) -> None:
    _write_project(tmp_path)
    distribution = _Distribution(tmp_path, direct_url=None)
    with pytest.raises(EnvironmentAuditError, match="authoritative editable HawEdit .dist-info"):
        _audit(
            tmp_path,
            distribution,
            {"fonttools": "4.60.2", "klpt": "0.1.7"},
        )


@pytest.mark.parametrize(
    ("versions", "message"),
    [
        ({"fonttools": "4.55.3", "klpt": "0.1.7"}, "fonttools drifted"),
        ({"fonttools": "4.60.2"}, "klpt==0.1.7 is not installed"),
    ],
)
def test_declared_direct_dependency_drift_is_refused(
    tmp_path: Path, versions: dict[str, str], message: str
) -> None:
    _write_project(tmp_path)
    distribution = _Distribution(tmp_path, direct_url=_editable(tmp_path))
    with pytest.raises(EnvironmentAuditError, match=message):
        _audit(tmp_path, distribution, versions)


def test_active_markers_are_checked_and_false_markers_are_skipped(tmp_path: Path) -> None:
    _write_project(tmp_path)
    distribution = _Distribution(tmp_path, direct_url=_editable(tmp_path))
    versions = {
        "fonttools": "4.60.2",
        "klpt": "0.1.7",
        "active-marker": "1.2.3",
    }
    _audit(tmp_path, distribution, versions, extras=("markers",))


def test_real_asr_platform_markers_match_the_audited_platform(tmp_path: Path) -> None:
    _write_project(tmp_path)
    distribution = _Distribution(tmp_path, direct_url=_editable(tmp_path))
    versions = {"fonttools": "4.60.2", "klpt": "0.1.7"}
    if platform.system() != "Windows":
        versions.update({"torch": "2.8.0", "torchaudio": "2.8.0", "qwen-asr": "0.0.6"})
    _audit(tmp_path, distribution, versions, extras=("asr",))


def test_active_marked_requirement_must_still_be_an_exact_pin(tmp_path: Path) -> None:
    _write_project(tmp_path)
    distribution = _Distribution(tmp_path, direct_url=_editable(tmp_path))
    with pytest.raises(EnvironmentAuditError, match="active direct requirement is not an exact"):
        _audit(
            tmp_path,
            distribution,
            {"fonttools": "4.60.2", "klpt": "0.1.7"},
            extras=("bad-marker",),
        )


def test_unexpected_third_or_stale_metadata_record_is_refused(tmp_path: Path) -> None:
    _write_project(tmp_path)
    distribution = _Distribution(tmp_path, direct_url=_editable(tmp_path))
    companion = _Distribution(
        tmp_path,
        direct_url=None,
        metadata_path=tmp_path / "src" / "hawedit.egg-info",
    )
    stale = _Distribution(
        tmp_path,
        direct_url=None,
        metadata_path=tmp_path / "other-checkout" / "hawedit.egg-info",
    )
    with pytest.raises(EnvironmentAuditError, match="unexpected HawEdit metadata records"):
        _audit_environment(
            tmp_path,
            (),
            python_version=(3, 11),
            distributions=(distribution, companion, stale),
            version_getter={"fonttools": "4.60.2", "klpt": "0.1.7"}.__getitem__,
        )


def test_clean_non_editable_wheel_context_is_supported(tmp_path: Path) -> None:
    distribution = _Distribution(tmp_path, direct_url=None)
    report = _audit_environment(
        None,
        (),
        python_version=(3, 11),
        distributions=(distribution,),
        version_getter={"fonttools": "4.60.2", "klpt": "0.1.7"}.__getitem__,
    )
    assert report.project_root is None
    assert report.checked_requirements == (("fonttools", "4.60.2"), ("klpt", "0.1.7"))


def test_target_lock_binds_the_complete_installed_environment(tmp_path: Path) -> None:
    _write_project(tmp_path)
    lock = _write_lock(tmp_path)
    hawedit = _Distribution(tmp_path, direct_url=_editable(tmp_path))
    installed = (
        hawedit,
        _Distribution(tmp_path, direct_url=None, name="fonttools", version="4.60.2"),
        _Distribution(tmp_path, direct_url=None, name="klpt", version="0.1.7"),
    )
    report = _audit_environment(
        tmp_path,
        (),
        python_version=(3, 11),
        distributions=(hawedit,),
        version_getter={"fonttools": "4.60.2", "klpt": "0.1.7"}.__getitem__,
        lock_path=lock,
        installed_distributions=installed,
        platform_name="Linux",
        _lock_hashes=TEST_LOCK_HASHES,
    )
    assert report.lock_sha256 is not None
    assert report.locked_requirements == (("fonttools", "4.60.2"), ("klpt", "0.1.7"))


@pytest.mark.parametrize(
    ("installed", "message"),
    [
        (
            (("fonttools", "4.60.2"),),
            "missing=\\['klpt'\\]",
        ),
        (
            (("fonttools", "4.60.2"), ("klpt", "0.1.7"), ("surprise", "1")),
            "unexpected=\\['surprise'\\]",
        ),
        (
            (("fonttools", "4.0"), ("klpt", "0.1.7")),
            "drifted=\\['fonttools==4.0",
        ),
    ],
)
def test_lock_refuses_missing_unexpected_or_drifted_distributions(
    tmp_path: Path, installed: tuple[tuple[str, str], ...], message: str
) -> None:
    _write_project(tmp_path)
    lock = _write_lock(tmp_path)
    hawedit = _Distribution(tmp_path, direct_url=_editable(tmp_path))
    inventory = (
        hawedit,
        *(
            _Distribution(tmp_path, direct_url=None, name=name, version=version)
            for name, version in installed
        ),
    )
    with pytest.raises(EnvironmentAuditError, match=message):
        _audit_environment(
            tmp_path,
            (),
            python_version=(3, 11),
            distributions=(hawedit,),
            version_getter={"fonttools": "4.60.2", "klpt": "0.1.7"}.__getitem__,
            lock_path=lock,
            installed_distributions=inventory,
            platform_name="linux",
            _lock_hashes=TEST_LOCK_HASHES,
        )


def test_lock_target_and_contract_drift_are_refused_before_install(tmp_path: Path) -> None:
    _write_project(tmp_path)
    lock = _write_lock(tmp_path)
    with pytest.raises(EnvironmentAuditError, match="targets linux"):
        validate_host_lock(
            lock,
            project_root=tmp_path,
            extras=(),
            python_version=(3, 11),
            platform_name="Windows",
            _lock_hashes=TEST_LOCK_HASHES,
        )
    with lock.open("a", encoding="utf-8") as stream:
        stream.write("unhashed==1.0\n")
    with pytest.raises(EnvironmentAuditError, match="bytes do not match trusted SHA-256"):
        validate_host_lock(
            lock,
            project_root=tmp_path,
            extras=(),
            python_version=(3, 11),
            platform_name="Linux",
            _lock_hashes=TEST_LOCK_HASHES,
        )

    lock = _write_lock(tmp_path)
    project = tmp_path / "pyproject.toml"
    project.write_text(
        project.read_text(encoding="utf-8").replace("fonttools==4.60.2", "fonttools==4.60.3"),
        encoding="utf-8",
    )
    with pytest.raises(EnvironmentAuditError, match="lock is stale"):
        validate_host_lock(
            lock,
            project_root=tmp_path,
            extras=(),
            python_version=(3, 11),
            platform_name="Linux",
            _lock_hashes=TEST_LOCK_HASHES,
        )


def test_packaged_models_lock_is_resolved_and_runtime_drift_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    system = platform.system().lower()
    python = f"{sys.version_info.major}.{sys.version_info.minor}"
    source = ROOT / "requirements" / f"host-models-{system}-py{python.replace('.', '')}.txt"
    locked = validate_host_lock(
        source,
        project_root=ROOT,
        extras=("models",),
        python_version=(sys.version_info.major, sys.version_info.minor),
        platform_name=platform.system(),
    )
    packages = locked.requirements
    data_root = tmp_path / "target-style-install"
    packaged = data_root / "share" / "hawedit" / "requirements" / source.name
    packaged.parent.mkdir(parents=True)
    packaged.write_bytes(source.read_bytes())
    record_name = f"../../../share/hawedit/requirements/{source.name}"

    hawedit = _Distribution(
        tmp_path,
        direct_url={"archive_info": {}, "url": (tmp_path / "hawedit.whl").as_uri()},
        located_files={record_name: packaged},
        requirements=(
            "fonttools==4.60.2",
            "klpt==0.1.7",
            'huggingface-hub==0.36.2; extra == "models"',
        ),
    )
    inventory = [
        hawedit,
        *(
            _Distribution(tmp_path, direct_url=None, name=name, version=version)
            for name, version in packages
        ),
        _Distribution(tmp_path, direct_url=None, name="unrelated", version="9.0"),
    ]
    hawedit_records = [hawedit]

    def distributions(*, name: str | None = None) -> tuple[metadata.Distribution, ...]:
        return tuple(hawedit_records) if name == "hawedit" else tuple(inventory)

    monkeypatch.setattr(metadata, "distributions", distributions)
    assert resolve_installed_host_lock("models") == packaged.resolve()
    assert (
        resolve_installed_hawedit_data(f"share/hawedit/requirements/{source.name}")
        == packaged.resolve()
    )
    original = packaged.read_bytes()
    hawedit._record_text = hawedit.read_text("RECORD")
    packaged.write_bytes(original + b"hostile")
    with pytest.raises(EnvironmentAuditError, match="does not match RECORD SHA-256"):
        resolve_installed_hawedit_data(f"share/hawedit/requirements/{source.name}")
    packaged.write_bytes(original)
    hawedit._record_text = None

    valid_record = hawedit.read_text("RECORD")
    assert valid_record is not None
    hawedit._record_text = valid_record.replace(
        record_name, f"hostile/../share/hawedit/requirements/{source.name}"
    )
    with pytest.raises(EnvironmentAuditError, match="unsafe data path"):
        resolve_installed_hawedit_data(f"share/hawedit/requirements/{source.name}")
    hawedit._record_text = None

    duplicate_name = f"share/hawedit/requirements/{source.name}"
    assert hawedit._located_files is not None
    hawedit._located_files[duplicate_name] = packaged
    with pytest.raises(EnvironmentAuditError, match="exactly one.*found 2"):
        resolve_installed_hawedit_data(duplicate_name)
    del hawedit._located_files[duplicate_name]
    for hostile_path in (
        source.name,
        f"/share/hawedit/requirements/{source.name}",
        f"share/hawedit/../requirements/{source.name}",
        f"share\\hawedit\\requirements\\{source.name}",
    ):
        with pytest.raises(EnvironmentAuditError, match="path must"):
            resolve_installed_hawedit_data(hostile_path)
    assert audit_installed_profile("models").scope == "models"

    drift_name, _version = packages[0]
    inventory[1] = _Distribution(tmp_path, direct_url=None, name=drift_name, version="0")
    with pytest.raises(EnvironmentAuditError, match=rf"drifted=.*{re.escape(drift_name)}==0"):
        audit_installed_profile("models")

    inventory[1] = _Distribution(
        tmp_path, direct_url=None, name=packages[0][0], version=packages[0][1]
    )
    hawedit_records.clear()
    with pytest.raises(EnvironmentAuditError, match="metadata is missing"):
        audit_installed_profile("models")

    hostile = _Distribution(
        tmp_path / "hostile",
        direct_url=None,
        requirements=("huggingface-hub==9.9.9",),
    )
    hawedit_records.extend((hawedit, hostile))
    with pytest.raises(EnvironmentAuditError, match="exactly one HawEdit wheel.*found 2"):
        audit_installed_profile("models")

    hawedit_records[:] = [hawedit]
    packaged.write_bytes(packaged.read_bytes().replace(b"certifi==", b"certifx==", 1))
    with pytest.raises(EnvironmentAuditError, match="bytes do not match trusted SHA-256"):
        audit_installed_profile("models")

"""The canonical gate must prove which project and dependency metadata it is running."""

from __future__ import annotations

import importlib.metadata as metadata
import json
import os
import platform
from pathlib import Path

import pytest

from hawedit.environment import EnvironmentAuditError, _audit_environment


class _Distribution(metadata.Distribution):
    def __init__(
        self,
        root: Path,
        *,
        direct_url: dict[str, object] | None,
        metadata_path: Path | None = None,
        requirements: tuple[str, ...] = ("fonttools==4.60.2", "klpt==0.1.7"),
        version: str = "0.1.0",
    ) -> None:
        self.root = root
        self._path = metadata_path or root / f"hawedit-{version}.dist-info"
        self._direct_url = direct_url
        requires = "".join(f"Requires-Dist: {item}\n" for item in requirements)
        self._metadata = (
            "Metadata-Version: 2.4\n"
            "Name: hawedit\n"
            f"Version: {version}\n"
            "Requires-Python: >=3.11,<3.13\n"
            f"{requires}\n"
        )

    def read_text(self, filename: str) -> str | None:
        if filename == "METADATA":
            return self._metadata
        if filename == "direct_url.json" and self._direct_url is not None:
            return json.dumps(self._direct_url)
        return None

    def locate_file(self, path: str | os.PathLike[str]) -> Path:
        return self.root / path


def _write_project(root: Path) -> None:
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

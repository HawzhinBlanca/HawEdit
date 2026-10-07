"""Exact studio host metadata/refusals, not installed GPU or inference evidence."""

from __future__ import annotations

import hashlib
import importlib.metadata as metadata
import importlib.util
import re
import sys
import tomllib
from pathlib import Path
from types import ModuleType, SimpleNamespace
from urllib.parse import urlsplit
from urllib.request import Request

import pytest

from hawedit import environment
from hawedit.environment import EnvironmentAuditError, validate_host_lock
from hawedit.release import _REQUIRED_WHEEL_MEMBERS
from test_environment import _Distribution

ROOT = Path(__file__).resolve().parents[1]
EXTRAS = ("media", "gpu", "models", "diarization", "agentic", "cloud")
LOCK_NAME = "host-studio-windows-py311.txt"
CODEC_URL = (
    "https://download.pytorch.org/whl/cu130/torchcodec-0.15.0%2Bcu130-cp311-cp311-win_amd64.whl"
)
CODEC_SHA = "4e0fb3eed8f1fe020d82a82c1e16fe43701e48cc04ac1bdfa693fd4f7a1c1c3d"


def _generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "studio_profile_lock_test", ROOT / "scripts" / "lock_host_dependencies.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _graph(root: Path, url: str = CODEC_URL, digest: str = CODEC_SHA) -> Path:
    path = root / "pylock.origin.toml"
    path.write_text(
        'lock-version = "1.0"\ncreated-by = "uv"\n[[packages]]\n'
        'name = "torchcodec"\nversion = "0.15.0+cu130"\n[[packages.wheels]]\n'
        f'url = "{url}"\n[packages.wheels.hashes]\nsha256 = "{digest}"\n',
        encoding="utf-8",
    )
    return path


def _fixture(root: Path) -> Path:
    (root / "requirements").mkdir()
    (root / "pyproject.toml").write_bytes((ROOT / "pyproject.toml").read_bytes())
    (root / "requirements" / "release-build.txt").write_bytes(
        (ROOT / "requirements" / "release-build.txt").read_bytes()
    )
    path = root / "requirements" / LOCK_NAME
    path.write_bytes((ROOT / "requirements" / LOCK_NAME).read_bytes())
    return path


def test_studio_profile_binds_all_production_extras_and_cuda() -> None:
    assert environment._PROFILE_EXTRAS.get("studio") == EXTRAS
    lock = validate_host_lock(
        ROOT / "requirements" / LOCK_NAME,
        project_root=ROOT,
        extras=EXTRAS,
        python_version=(3, 11),
        platform_name="Windows",
    )
    packages = dict(lock.requirements)
    assert lock.scope == "studio"
    assert packages["torch"] == "2.13.0+cu130"
    assert packages["torchvision"] == "0.28.0+cu130"
    assert packages["torchaudio"] == "2.11.0+cu130"
    assert packages["torchcodec"] == "0.15.0+cu130"
    assert packages["numpy"] == "2.2.2"
    assert packages["pyannote-audio"] == "4.0.7"
    assert packages["dbos"] == "2.29.0"
    assert packages["huggingface-hub"] == "0.36.2"
    assert packages["google-auth"] == "2.56.3"
    assert not {"fairseq2", "omnilingual-asr", "pytest", "ruff", "mypy"} & packages.keys()


def test_studio_numpy_pin_satisfies_declared_diarization() -> None:
    optional = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "optional-dependencies"
    ]
    assert "numpy==2.2.2" in optional["media"]
    assert "pyannote.audio==4.0.7" in optional["diarization"]
    assert "torch==2.8.0; platform_system != 'Windows'" in optional["asr"]
    assert "torchaudio==2.8.0; platform_system != 'Windows'" in optional["asr"]


def test_wheel_requires_studio_profile_lock() -> None:
    assert f"share/hawedit/requirements/{LOCK_NAME}" in _REQUIRED_WHEEL_MEMBERS
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert (
        f"requirements/{LOCK_NAME}"
        in project["tool"]["setuptools"]["data-files"]["share/hawedit/requirements"]
    )


def test_studio_profile_has_one_exact_hash_per_package() -> None:
    text = (ROOT / "requirements" / LOCK_NAME).read_text(encoding="utf-8")
    entries = re.findall(r"^([\w.-]+)==(\S+) --hash=sha256:([0-9a-f]{64})$", text, re.M)
    urls = [
        line.removeprefix("# selected wheel ")
        for line in text.splitlines()
        if line.startswith("# selected wheel ")
    ]
    assert len(entries) == len(urls) == 133
    assert len({name for name, _version, _digest in entries}) == len(entries)
    for url in urls:
        parsed = urlsplit(url)
        assert parsed.scheme == "https"
        assert parsed.hostname in {
            "files.pythonhosted.org",
            "download-r2.pytorch.org",
            "download.pytorch.org",
        }
        assert parsed.path.endswith(".whl")


def test_wheel_exporter_accepts_official_torchcodec_origin(tmp_path: Path) -> None:
    module = _generator()
    target = module.Target("studio", "windows", "x86_64-pc-windows-msvc", "3.11", EXTRAS, "cu130")
    rendered = module._render(target, _graph(tmp_path))
    assert CODEC_URL in rendered
    assert f"torchcodec==0.15.0+cu130 --hash=sha256:{CODEC_SHA}" in rendered


@pytest.mark.parametrize("digest", ["z" * 64, "A" * 64, "a" * 63, "a" * 65])
def test_wheel_exporter_refuses_nonhex_sha256(tmp_path: Path, digest: str) -> None:
    module = _generator()
    target = module.Target("base", "windows", "x86_64-pc-windows-msvc", "3.11", (), "cpu")
    with pytest.raises(SystemExit, match="invalid wheel SHA-256"):
        module._render(target, _graph(tmp_path, "https://files.pythonhosted.org/codec.whl", digest))


@pytest.mark.parametrize(
    "url",
    [
        "http://download.pytorch.org/codec.whl",
        "https://download.pytorch.org.attacker.example/codec.whl",
        "https://attacker.example/download.pytorch.org/codec.whl",
        "https://127.0.0.1/codec.whl",
        "https://user:secret@download.pytorch.org/codec.whl",
        "https://download.pytorch.org:444/codec.whl",
    ],
)
def test_wheel_exporter_refuses_untrusted_origin_and_redirect(tmp_path: Path, url: str) -> None:
    module = _generator()
    target = module.Target("base", "windows", "x86_64-pc-windows-msvc", "3.11", (), "cpu")
    with pytest.raises(SystemExit, match="HTTPS|untrusted"):
        module._render(target, _graph(tmp_path, url))
    with pytest.raises(SystemExit, match="HTTPS|untrusted"):
        module._download_wheel_sha256(url)
    handler = module._OfficialWheelRedirects()
    with pytest.raises(SystemExit, match="HTTPS|untrusted"):
        handler.redirect_request(Request(CODEC_URL), None, 302, "redirect", {}, url)


@pytest.mark.parametrize("system,version", [("Linux", (3, 11)), ("Windows", (3, 12))])
def test_studio_profile_refuses_unmeasured_host_targets(
    monkeypatch: pytest.MonkeyPatch, system: str, version: tuple[int, int]
) -> None:
    monkeypatch.setattr(environment, "platform", SimpleNamespace(system=lambda: system))
    monkeypatch.setattr(
        environment,
        "sys",
        SimpleNamespace(version_info=SimpleNamespace(major=version[0], minor=version[1])),
    )
    with pytest.raises(EnvironmentAuditError, match="studio.*Windows.*3.11"):
        environment._host_lock_name("studio")


@pytest.mark.parametrize(
    "change", ["bytes", "backend", "options", "contract", "cpu-wheel", "target"]
)
def test_studio_profile_refuses_target_backend_and_contract_drift(
    tmp_path: Path, change: str
) -> None:
    path = _fixture(tmp_path)
    trusted = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()}
    text = path.read_text(encoding="utf-8")
    edits = {
        "bytes": text + "# changed bytes\n",
        "backend": text.replace("# torch-backend: cu130", "# torch-backend: cpu"),
        "options": text.replace(
            "--index-url https://download.pytorch.org/whl/cu130",
            "--index-url https://attacker.example",
        ),
        "cpu-wheel": text.replace("torch==2.13.0+cu130", "torch==2.13.0+cpu"),
        "target": text.replace("# target-platform: windows", "# target-platform: linux"),
    }
    if change == "contract":
        project = tmp_path / "pyproject.toml"
        project.write_text(
            project.read_text(encoding="utf-8").replace("numpy==2.2.2", "numpy==2.2.3"),
            encoding="utf-8",
        )
    else:
        path.write_text(edits[change], encoding="utf-8")
        if change != "bytes":
            trusted[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    reason = {
        "bytes": "trusted SHA-256",
        "backend": "torch-backend cu130",
        "options": "unsafe or incomplete",
        "contract": "lock is stale",
        "cpu-wheel": "cu130 wheel",
        "target": "targets linux",
    }[change]
    with pytest.raises(EnvironmentAuditError, match=reason):
        validate_host_lock(
            path,
            project_root=tmp_path,
            extras=EXTRAS,
            python_version=(3, 11),
            platform_name="Windows",
            _lock_hashes=trusted,
        )


def test_installed_studio_profile_refuses_missing_or_drifted_dependencies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = ROOT / "requirements" / LOCK_NAME
    locked = validate_host_lock(
        source, project_root=ROOT, extras=EXTRAS, python_version=(3, 11), platform_name="Windows"
    )
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    packaged = tmp_path / LOCK_NAME
    packaged.write_bytes(source.read_bytes())
    record_name = f"../../../share/hawedit/requirements/{LOCK_NAME}"
    requirements = tuple(project["dependencies"]) + tuple(
        f'{requirement}; extra == "{extra}"'
        for extra in EXTRAS
        for requirement in project["optional-dependencies"][extra]
    )
    hawedit = _Distribution(
        tmp_path,
        direct_url=None,
        located_files={record_name: packaged},
        requirements=requirements,
        version=project["version"],
    )
    inventory = [
        hawedit,
        *(
            _Distribution(tmp_path, direct_url=None, name=name, version=version)
            for name, version in locked.requirements
        ),
    ]
    monkeypatch.setattr(
        metadata,
        "distributions",
        lambda *, name=None: (hawedit,) if name == "hawedit" else tuple(inventory),
    )
    monkeypatch.setattr(environment, "platform", SimpleNamespace(system=lambda: "Windows"))
    monkeypatch.setattr(
        environment, "sys", SimpleNamespace(version_info=SimpleNamespace(major=3, minor=11))
    )
    assert environment.audit_installed_profile("studio").path == packaged.resolve()
    item = next(
        i for i, distribution in enumerate(inventory) if distribution.metadata["Name"] == "numpy"
    )
    original = inventory[item]
    inventory[item] = _Distribution(tmp_path, direct_url=None, name="numpy", version="2.2.1")
    with pytest.raises(EnvironmentAuditError, match="drifted=.*numpy"):
        environment.audit_installed_profile("studio")
    inventory.pop(item)
    with pytest.raises(EnvironmentAuditError, match="missing=.*numpy"):
        environment.audit_installed_profile("studio")
    inventory.insert(item, original)
    hawedit._record_text = hawedit.read_text("RECORD")
    packaged.write_bytes(packaged.read_bytes() + b"# changed packaged lock\n")
    with pytest.raises(EnvironmentAuditError, match="does not match RECORD SHA-256"):
        environment.audit_installed_profile("studio")

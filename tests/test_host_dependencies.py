"""The host installer must consume exact target wheels, not a fresh resolver decision."""

from __future__ import annotations

import platform as platform_module
import re
import subprocess
import sys
from pathlib import Path

from hawedit.environment import dependency_contract_digest, validate_host_lock

ROOT = Path(__file__).resolve().parents[1]
LOCKS = ROOT / "requirements"
REQUIREMENT = re.compile(
    r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s;\\]+) --hash=sha256:([0-9a-f]{64})$"
)


def _lock(scope: str, platform: str, python: str) -> Path:
    return LOCKS / f"host-{scope}-{platform}-py{python.replace('.', '')}.txt"


def _packages(path: Path) -> dict[str, tuple[str, str]]:
    packages: dict[str, tuple[str, str]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = REQUIREMENT.fullmatch(line)
        if match:
            name, version, digest = match.groups()
            packages[name] = (version, digest)
    return packages


def test_all_supported_host_targets_have_valid_semantically_bound_locks() -> None:
    found: set[Path] = set()
    cpu_profiles = (("base", ()), ("gate", ("dev", "media")), ("models", ("models",)))
    for scope, extras in cpu_profiles:
        for platform in ("linux", "windows"):
            for python in ("3.11", "3.12"):
                path = _lock(scope, platform, python)
                found.add(path)
                major, minor = map(int, python.split("."))
                lock = validate_host_lock(
                    path,
                    project_root=ROOT,
                    extras=extras,
                    python_version=(major, minor),
                    platform_name=platform,
                )
                assert lock.contract_sha256 == dependency_contract_digest(ROOT, extras)
                assert lock.requirements
    gpu_path = _lock("gpu", "windows", "3.11")
    found.add(gpu_path)
    gpu = validate_host_lock(
        gpu_path,
        project_root=ROOT,
        extras=("media", "gpu"),
        python_version=(3, 11),
        platform_name="windows",
    )
    assert gpu.contract_sha256 == dependency_contract_digest(ROOT, ("media", "gpu"))
    assert found == set(LOCKS.glob("host-*.txt"))


def test_each_lock_selects_one_binary_hash_per_exact_package() -> None:
    for path in sorted(LOCKS.glob("host-*.txt")):
        lines = path.read_text(encoding="utf-8").splitlines()
        requirements = [line for line in lines if REQUIREMENT.fullmatch(line)]
        selected_wheels = [line for line in lines if line.startswith("# selected wheel https://")]
        assert requirements
        assert len(requirements) == len(selected_wheels)
        names: set[str] = set()
        for line in requirements:
            match = REQUIREMENT.fullmatch(line)
            assert match is not None
            names.add(match.group(1))
        assert len(requirements) == len(names)
        assert all(
            "files.pythonhosted.org/" in line or "download-r2.pytorch.org/" in line
            for line in selected_wheels
        )
        assert not any(".tar.gz" in line or ".zip" in line for line in selected_wheels)


def test_base_and_gate_scopes_are_minimal_and_platform_specific() -> None:
    for platform in ("linux", "windows"):
        for python in ("3.11", "3.12"):
            base = _packages(_lock("base", platform, python))
            gate = _packages(_lock("gate", platform, python))
            assert set(base) == {"chunspell", "fonttools", "klpt", "pip", "setuptools"}
            assert base.items() <= gate.items()
            assert gate["torch"][0] == "2.13.0+cpu"
            assert not any(name.startswith("nvidia-") for name in gate)
            if platform == "windows":
                assert {"colorama", "pyreadline3"} <= gate.keys()
            else:
                assert "colorama" not in gate
                assert "pyreadline3" not in gate


def test_models_profile_is_minimal_production_provisioning_not_the_gate() -> None:
    for platform in ("linux", "windows"):
        for python in ("3.11", "3.12"):
            base = _packages(_lock("base", platform, python))
            models = _packages(_lock("models", platform, python))
            assert base.items() <= models.items()
            assert models["huggingface-hub"][0] == "0.36.2"
            assert "pytest" not in models
            assert "torch" not in models
            assert "opencv-python-headless" not in models


def test_gpu_profile_is_the_one_measured_windows_cuda_target() -> None:
    path = _lock("gpu", "windows", "3.11")
    packages = _packages(path)
    assert len(packages) == 46
    assert packages["torch"][0] == "2.13.0+cu130"
    assert packages["torchvision"][0] == "0.28.0+cu130"
    assert packages["torchaudio"][0] == "2.11.0+cu130"
    assert packages["transformers"][0] == "4.57.6"
    assert packages["accelerate"][0] == "1.14.0"
    assert packages["pillow"][0] == "12.3.0"
    assert not {"pytest", "ruff", "mypy", "google-auth"} & packages.keys()
    text = path.read_text(encoding="utf-8")
    assert "# torch-backend: cu130" in text
    assert "--index-url https://download.pytorch.org/whl/cu130" in text
    assert "--extra-index-url https://pypi.org/simple" in text
    assert "/whl/cu130/torch-2.13.0%2Bcu130-cp311-cp311-win_amd64.whl" in text
    assert not _lock("gpu", "linux", "3.11").exists()
    assert not _lock("gpu", "windows", "3.12").exists()


def test_installer_and_gate_fail_closed_around_the_selected_lock() -> None:
    installer = (ROOT / "scripts" / "install-host.sh").read_text(encoding="utf-8")
    validation = '"$python" -I "$here/src/hawedit/environment.py"'
    install = '"$python" -m pip install'
    assert installer.index(validation) < installer.index(install)
    for flag in ("--require-hashes", "--only-binary=:all:", "--no-deps", "--no-build-isolation"):
        assert flag in installer
    assert "pip install --upgrade" not in installer
    assert '"$scope" != models' in installer
    assert "extras=(--extra media --extra gpu)" in installer
    assert '"$python" -I -m hawedit.gpu_runtime' in installer

    setup = (ROOT / "scripts" / "setup.sh").read_text(encoding="utf-8")
    assert 'bash scripts/install-host.sh "$VENV_PY" gate' in setup
    assert "pip install --upgrade" not in setup
    gate = (ROOT / "scripts" / "verify.sh").read_text(encoding="utf-8")
    assert "host-gate-${_lock_identity}.txt" in gate
    assert '--extra media --lock "$HOST_LOCK"' in gate


def test_source_lock_preflight_bootstraps_before_hawedit_is_importable() -> None:
    target_platform = platform_module.system().lower()
    major, minor = sys.version_info[:2]
    lock = _lock("base", target_platform, f"{major}.{minor}")
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            str(ROOT / "src" / "hawedit" / "environment.py"),
            "--validate-lock-only",
            "--project-root",
            str(ROOT),
            "--lock",
            str(lock),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "hawedit-environment-ok"


def test_ci_and_release_smoke_consume_locks_without_dependency_resolution() -> None:
    gate = (ROOT / ".github" / "workflows" / "gate.yml").read_text(encoding="utf-8")
    assert gate.count("bash scripts/install-host.sh .venv/bin/python gate") == 2
    assert "pip install --upgrade" not in gate
    assert "-e '.[dev,media]'" not in gate

    release = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert '--no-index --no-deps "${wheels[0]}"' in release
    assert "-m hawedit.environment --show-lock base" in release
    assert "--require-hashes --only-binary=:all:" in release
    assert '-m hawedit.environment --lock "$lock"' in release
    assert "hawedit-fetch-models" in release

    gpu = (ROOT / ".github" / "workflows" / "gpu-readiness.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch:" in gpu
    assert "runs-on: [self-hosted, Windows, X64, hawedit-gpu]" in gpu
    assert 'python-version: "3.11"' in gpu
    assert 'scripts/install-host.sh "$venv/Scripts/python.exe" gpu' in gpu
    assert "continue-on-error" not in gpu
    assert "pull_request:" not in gpu
    assert "push:" not in gpu


def test_generator_pins_the_resolver_cutoff_and_rejects_non_wheels() -> None:
    generator = (ROOT / "scripts" / "lock_host_dependencies.py").read_text(encoding="utf-8")
    assert 'UV_VERSION: Final = "0.11.26"' in generator
    assert 'EXCLUDE_NEWER: Final = "2026-08-09T00:00:00Z"' in generator
    assert '"--only-binary=:all:"' in generator
    assert '"cu130"' in generator
    assert "_download_wheel_sha256" in generator
    assert "MAX_HASH_DOWNLOAD_BYTES" in generator
    assert "urlsplit(response.geturl())" in generator
    assert "wheels[0]" in generator

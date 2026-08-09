"""Provision the wheel-safe WSL2 runtime for canonical OmniASR on Windows.

The official fairseq2 native extension is not published for Windows. HawEdit therefore keeps a
Linux runtime in the user's local application-data directory. Only HawEdit's pure Python package
is copied into a source-fingerprinted snapshot; native dependencies live in one shared Linux venv
inside WSL2. Upgrading the host package therefore cannot silently execute an older worker and
does not duplicate the multi-gigabyte environment.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
from pathlib import Path

__all__ = [
    "default_wsl_runtime",
    "default_wsl_source",
    "package_fingerprint",
    "provision_wsl_runtime",
    "wsl_path",
]


def package_fingerprint(package_dir: Path | None = None) -> str:
    """Stable identity of the pure-Python worker source copied into WSL's shared mount."""
    source = package_dir or Path(__file__).resolve().parent
    digest = hashlib.sha256()
    files = sorted(source.glob("*.py"), key=lambda path: path.name)
    if not files:
        raise RuntimeError(f"no HawEdit Python modules found at {source}")
    for path in files:
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()[:16]


def default_wsl_runtime(package_dir: Path | None = None) -> Path:
    """Stable host path shared with WSL; never inside a wheel's site-packages."""
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "HawEdit" / "wsl-asr"


def default_wsl_source(package_dir: Path | None = None, runtime_root: Path | None = None) -> Path:
    """Fingerprint-specific Python source; the multi-GB Linux venv remains shared."""
    return (runtime_root or default_wsl_runtime()) / "sources" / package_fingerprint(package_dir)


def _prefix(distro: str | None, executable: str = "wsl.exe") -> list[str]:
    prefix = [executable]
    if distro:
        prefix.extend(("--distribution", distro))
    prefix.append("--")
    return prefix


def wsl_path(path: Path, distro: str | None = None, executable: str = "wsl.exe") -> str:
    """Translate without the backslash-loss bug in ``wsl.exe`` argument forwarding."""
    result = subprocess.run(
        [*_prefix(distro, executable), "wslpath", "-a", "-u", path.resolve().as_posix()],
        capture_output=True,
        check=False,
    )
    value = result.stdout.decode("utf-8", "replace").strip()
    if result.returncode != 0 or not value:
        error = result.stderr.decode("utf-8", "replace")[-600:]
        raise RuntimeError(f"WSL could not translate {path}: {error or 'no path returned'}")
    return value


_FONTOOLS_VERSION = "4.60.2"

_SETUP_SCRIPT = r"""
set -euo pipefail
venv="$HAWEDIT_WSL_RUNTIME/venv"
if command -v uv >/dev/null 2>&1; then
  if [[ ! -x "$venv/bin/python" ]]; then
    uv venv --python 3.12 "$venv"
  fi
  uv pip install --python "$venv/bin/python" \
    'torch==2.8.0' 'torchaudio==2.8.0' \
    'omnilingual-asr==0.2.0' 'qwen-asr==0.0.6' 'klpt==0.1.7' \
    'fonttools==__FONTOOLS_VERSION__'
elif command -v python3.12 >/dev/null 2>&1; then
  if [[ ! -x "$venv/bin/python" ]]; then
    python3.12 -m venv "$venv"
  fi
  "$venv/bin/python" -m pip install --upgrade pip
  "$venv/bin/python" -m pip install \
    'torch==2.8.0' 'torchaudio==2.8.0' \
    'omnilingual-asr==0.2.0' 'qwen-asr==0.0.6' 'klpt==0.1.7' \
    'fonttools==__FONTOOLS_VERSION__'
else
  printf '%s\n' 'Install uv or Python 3.12 inside WSL2.' >&2
  exit 1
fi
PYTHONPATH="$HAWEDIT_WSL_SOURCE" "$venv/bin/python" - <<'PY'
import torch
import torchaudio
from hawedit.asr_worker import run_request
from omnilingual_asr.models.inference.pipeline import ASRInferencePipeline
from qwen_asr import Qwen3ASRModel

torch_version = torch.__version__.split("+", 1)[0]
torchaudio_version = torchaudio.__version__.split("+", 1)[0]
if torch_version != "2.8.0" or torchaudio_version != "2.8.0":
    raise SystemExit(
        f"Stage 1 requires matched torch/torchaudio 2.8.0, got "
        f"{torch_version}/{torchaudio_version}"
    )
del run_request, ASRInferencePipeline, Qwen3ASRModel, torchaudio
if not torch.cuda.is_available():
    raise SystemExit("OmniASR installed, but CUDA is not visible inside WSL2")
if torch.cuda.device_count() < 2:
    raise SystemExit("HawEdit OmniASR needs two visible GPUs (LLM cuda:0, CTC cuda:1)")
print(f"OmniASR import OK; CUDA GPUs visible: {torch.cuda.device_count()}")
PY
""".replace("__FONTOOLS_VERSION__", _FONTOOLS_VERSION).strip()


def provision_wsl_runtime(
    *,
    distro: str | None = None,
    runtime_root: Path | None = None,
    package_source: Path | None = None,
    platform_name: str | None = None,
) -> Path:
    """Install/update one fingerprinted runtime and return its host-side path."""
    if (platform_name or os.name) != "nt":
        raise RuntimeError("the WSL2 OmniASR setup command is only for Windows hosts")
    source = (package_source or Path(__file__).resolve().parent).resolve()
    runtime = runtime_root or default_wsl_runtime(source)
    source_root = default_wsl_source(source, runtime)
    ready = source_root / ".ready"
    if ready.is_file():
        return runtime

    target = source_root / "hawedit"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        source,
        target,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    translated = wsl_path(runtime, distro)
    translated_source = wsl_path(source_root, distro)
    result = subprocess.run(
        [
            *_prefix(distro),
            "env",
            f"HAWEDIT_WSL_RUNTIME={translated}",
            f"HAWEDIT_WSL_SOURCE={translated_source}",
            "bash",
            "-l",
            "-s",
        ],
        input=_SETUP_SCRIPT.encode("utf-8"),
        capture_output=False,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"OmniASR WSL2 setup failed with exit code {result.returncode}")
    with ready.open("x", encoding="ascii", newline="\n") as stream:
        stream.write("ready\n")
    return runtime


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Provision HawEdit's official OmniASR runtime inside WSL2"
    )
    parser.add_argument("--distribution", help="optional WSL distribution name")
    args = parser.parse_args(argv)
    runtime = provision_wsl_runtime(distro=args.distribution)
    print(f"READY: OmniASR WSL2 runtime at {runtime}")
    return 0


if __name__ == "__main__":  # pragma: no cover - console entry point
    raise SystemExit(main())

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

from hawedit.cli import program_name, use_utf8_streams

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
    """Every `wsl.exe` invocation this project makes, built once.

    `--exec`, not `--`. `--` only ends option parsing: the command line still goes through the
    distribution's default shell, which expands `$VAR` references before the `bash -lc` script
    ever sees them and runs with a PATH that omits `~/.local/bin`. Measured 2026-08-09 on
    hawapc01, the same probe under both spellings:

        wsl.exe --      env HAWEDIT_WSL_RUNTIME=/tmp/x bash -lc …
            -> RUNTIME=[UNSET]  uv=none  python3.12=none
        wsl.exe --exec  env HAWEDIT_WSL_RUNTIME=/tmp/x bash -lc …
            -> RUNTIME=[/tmp/x]  uv=~/.local/bin/uv  python3.12=~/.local/bin/python3.12

    So the runtime root arrived empty, `uv venv --python 3.12 ""` failed with uv's own "a value
    is required for '[PATH]'", and `hawedit-asr-setup` could not provision anything — which is
    why M1.4 recorded the runtime as absent here. The ASR worker call had the same bug in a
    second copy of this function: its `PYTHONPATH=` would have arrived empty too, so Stage 1
    would have failed on an unimportable `hawedit.asr_worker` even after a successful install.
    One prefix now, used by both. D-102.
    """
    prefix = [executable]
    if distro:
        prefix.extend(("--distribution", distro))
    prefix.append("--exec")
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


_SETUP_SCRIPT = r"""
set -euo pipefail
venv="$HAWEDIT_WSL_RUNTIME/venv"
if command -v uv >/dev/null 2>&1; then
  if [[ ! -x "$venv/bin/python" ]]; then
    uv venv --python 3.12 "$venv"
  fi
  uv pip install --python "$venv/bin/python" \
    'omnilingual-asr==0.2.0' 'klpt==0.1.7' 'fonttools==4.55.3' 'peft==0.19.1'
elif command -v python3.12 >/dev/null 2>&1; then
  if [[ ! -x "$venv/bin/python" ]]; then
    python3.12 -m venv "$venv"
  fi
  "$venv/bin/python" -m pip install --upgrade pip
  "$venv/bin/python" -m pip install \
    'omnilingual-asr==0.2.0' 'klpt==0.1.7' 'fonttools==4.55.3' 'peft==0.19.1'
else
  printf '%s\n' 'Install uv or Python 3.12 inside WSL2.' >&2
  exit 1
fi
PYTHONPATH="$HAWEDIT_WSL_SOURCE" "$venv/bin/python" - <<'PY'
import torch
from hawedit.asr_worker import run_request
from omnilingual_asr.models.inference.pipeline import ASRInferencePipeline

# `--omni-asr-adapter` loads a PEFT bundle inside this venv. It was missing here and the
# adapter path would have raised ImportError *after* Stage 0 and 545 WAV cuts. Pinned to the
# version `adapter_config.json` records as having written the bundle — read, not chosen.
from peft import PeftModel

del run_request, ASRInferencePipeline, PeftModel
if not torch.cuda.is_available():
    raise SystemExit("OmniASR installed, but CUDA is not visible inside WSL2")
if torch.cuda.device_count() < 2:
    raise SystemExit("HawEdit OmniASR needs two visible GPUs (LLM cuda:0, CTC cuda:1)")
print(f"OmniASR import OK; CUDA GPUs visible: {torch.cuda.device_count()}")
PY
""".strip()


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
            "-lc",
            _SETUP_SCRIPT,
        ],
        capture_output=False,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"OmniASR WSL2 setup failed with exit code {result.returncode}")
    with ready.open("x", encoding="ascii", newline="\n") as stream:
        stream.write("ready\n")
    return runtime


def main(argv: list[str] | None = None) -> int:
    use_utf8_streams()
    parser = argparse.ArgumentParser(
        prog=program_name("hawedit.wsl_setup"),
        description="Provision HawEdit's official OmniASR runtime inside WSL2",
    )
    parser.add_argument("--distribution", help="optional WSL distribution name")
    args = parser.parse_args(argv)
    runtime = provision_wsl_runtime(distro=args.distribution)
    print(f"READY: OmniASR WSL2 runtime at {runtime}")
    return 0


if __name__ == "__main__":  # pragma: no cover - console entry point
    raise SystemExit(main())

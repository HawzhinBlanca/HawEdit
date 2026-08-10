"""Installed/source FFmpeg provisioning entry point with authenticated script resolution."""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final

from hawedit.captions import MissingRtlStack, assert_rtl_stack, ffprobe_for, find_ffmpeg
from hawedit.cli import program_name, use_utf8_streams
from hawedit.environment import EnvironmentAuditError, resolve_installed_hawedit_data

__all__ = ["FfmpegSetupError", "default_ffmpeg_dir", "main"]

_SOURCE_ROOT: Final = Path(__file__).resolve().parents[2]
_SCRIPT_DATA_PATH: Final = "share/hawedit/scripts/fetch-ffmpeg.sh"
_PROBE_TIMEOUT_SECONDS: Final = 15


class FfmpegSetupError(RuntimeError):
    """FFmpeg cannot be verified or safely provisioned in this runtime."""


def default_ffmpeg_dir(
    environ: Mapping[str, str] | None = None,
    *,
    system: str | None = None,
    home: Path | None = None,
) -> Path:
    """Return the per-user installed-wheel FFmpeg cache without creating it."""

    values = os.environ if environ is None else environ
    if configured := values.get("HAWEDIT_FFMPEG_DIR"):
        path = Path(configured).expanduser()
        if not path.is_absolute():
            raise FfmpegSetupError("HAWEDIT_FFMPEG_DIR must be an absolute path")
        return path

    platform_name = platform.system() if system is None else system
    user_home = Path.home() if home is None else home
    if platform_name == "Windows":
        root = Path(values.get("LOCALAPPDATA", user_home / "AppData" / "Local"))
    elif platform_name == "Darwin":
        root = user_home / "Library" / "Caches"
    else:
        root = Path(values.get("XDG_CACHE_HOME", user_home / ".cache"))
    return root / "hawedit" / "ffmpeg"


def _provisioning_context(source_root: Path = _SOURCE_ROOT) -> tuple[Path, Path]:
    source_script = source_root / "scripts" / "fetch-ffmpeg.sh"
    if source_script.is_file():
        return source_script, source_root / ".ffmpeg"
    try:
        installed_script = resolve_installed_hawedit_data(_SCRIPT_DATA_PATH)
    except EnvironmentAuditError as exc:
        raise FfmpegSetupError(
            f"cannot authenticate the installed FFmpeg provisioner: {exc}"
        ) from exc
    return installed_script, default_ffmpeg_dir()


def _run(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=_PROBE_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise FfmpegSetupError(f"cannot execute {command[0]!r}: {exc}") from exc


def _verified_existing() -> Path | None:
    binary = find_ffmpeg()
    if binary is None:
        return None
    build = _run((str(binary), "-hide_banner", "-buildconf"))
    if build.returncode != 0:
        raise FfmpegSetupError(f"ffmpeg at {binary} cannot report its build configuration")

    linked_libraries = ""
    if platform.system() == "Linux" and (ldd := shutil.which("ldd")):
        linked = _run((ldd, str(binary)))
        if linked.returncode == 0:
            linked_libraries = linked.stdout
    try:
        assert_rtl_stack(build.stdout + build.stderr, linked_libraries)
    except MissingRtlStack as exc:
        raise FfmpegSetupError(f"ffmpeg at {binary} failed the Kurdish RTL check: {exc}") from exc

    probe = ffprobe_for(binary)
    if not probe.is_file():
        raise FfmpegSetupError(f"ffprobe is missing beside ffmpeg at {binary}")
    probed = _run((str(probe), "-hide_banner", "-version"))
    if probed.returncode != 0:
        raise FfmpegSetupError(f"ffprobe beside {binary} cannot execute")
    return binary


def _find_bash() -> Path:
    candidates: list[Path] = []
    if configured := os.environ.get("HAWEDIT_BASH"):
        candidates.append(Path(configured))
    if os.name == "nt":
        if git := shutil.which("git"):
            candidates.append(Path(git).resolve().parent.parent / "bin" / "bash.exe")
        if program_files := os.environ.get("PROGRAMFILES"):
            candidates.append(Path(program_files) / "Git" / "bin" / "bash.exe")
        if local_app_data := os.environ.get("LOCALAPPDATA"):
            candidates.append(Path(local_app_data) / "Programs" / "Git" / "bin" / "bash.exe")
    elif found := shutil.which("bash"):
        candidates.append(Path(found))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FfmpegSetupError("Bash is required to provision the pinned Linux FFmpeg archive")


def _run_provisioner(script: Path, install_dir: Path) -> int:
    bash = _find_bash()
    environment = os.environ.copy()
    # Git Bash accepts forward-slash drive paths; POSIX receives the same spelling unchanged.
    environment["HAWEDIT_FFMPEG_DIR"] = install_dir.as_posix()
    try:
        result = subprocess.run(
            (str(bash), "--noprofile", "--norc", str(script)),
            env=environment,
            timeout=None,
            check=False,
        )
    except OSError as exc:
        raise FfmpegSetupError(
            f"cannot launch the authenticated FFmpeg provisioner: {exc}"
        ) from exc
    return int(result.returncode)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=program_name("hawedit.ffmpeg_setup"),
        description="Verify or provision HawEdit's Kurdish-capable FFmpeg runtime.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the active ffmpeg/ffprobe pair without downloading anything",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    use_utf8_streams()
    args = _parser().parse_args(argv)
    try:
        active = _verified_existing()
    except FfmpegSetupError as exc:
        if os.environ.get("HAWEDIT_FFMPEG") or args.check:
            print(f"REFUSED: {exc}", file=sys.stderr)
            return 1
        print(f"repairing invalid ffmpeg: {exc}", file=sys.stderr)
        active = None
    if active is not None:
        print(f"hawedit-ffmpeg-ok: {active}")
        return 0
    if args.check:
        print("REFUSED: no ffmpeg is available; run hawedit-ffmpeg-setup", file=sys.stderr)
        return 1
    if platform.system() != "Linux":
        remedy = (
            "winget install Gyan.FFmpeg"
            if platform.system() == "Windows"
            else "brew install ffmpeg"
        )
        print(
            "REFUSED: automatic download is Linux-only. Install the platform build first with "
            f"`{remedy}`, then rerun hawedit-ffmpeg-setup.",
            file=sys.stderr,
        )
        return 1
    try:
        script, install_dir = _provisioning_context()
        result = _run_provisioner(script, install_dir)
        if result != 0:
            return result
        active = _verified_existing()
    except FfmpegSetupError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    if active is None:
        print(
            "REFUSED: provisioner returned success but ffmpeg is still undiscoverable",
            file=sys.stderr,
        )
        return 1
    print(f"hawedit-ffmpeg-ok: {active}")
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through the console entry point
    raise SystemExit(main())

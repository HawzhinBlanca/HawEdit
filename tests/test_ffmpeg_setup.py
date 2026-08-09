"""Installed-wheel FFmpeg setup is executable, authenticated, and automatically discoverable."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from hawedit import ffmpeg_setup
from hawedit.captions import find_ffmpeg
from hawedit.ffmpeg_setup import FfmpegSetupError, default_ffmpeg_dir, main


def test_default_install_directory_is_platform_user_state(tmp_path: Path) -> None:
    assert (
        default_ffmpeg_dir(
            {"LOCALAPPDATA": str(tmp_path / "local")}, system="Windows", home=tmp_path
        )
        == tmp_path / "local" / "hawedit" / "ffmpeg"
    )
    assert (
        default_ffmpeg_dir(
            {"XDG_CACHE_HOME": str(tmp_path / "cache")}, system="Linux", home=tmp_path
        )
        == tmp_path / "cache" / "hawedit" / "ffmpeg"
    )
    assert default_ffmpeg_dir({}, system="Darwin", home=tmp_path) == (
        tmp_path / "Library" / "Caches" / "hawedit" / "ffmpeg"
    )


def test_relative_install_override_is_refused() -> None:
    with pytest.raises(FfmpegSetupError, match="absolute path"):
        default_ffmpeg_dir({"HAWEDIT_FFMPEG_DIR": "relative/ffmpeg"})


def test_source_context_uses_the_checkout_script_and_checkout_generation(tmp_path: Path) -> None:
    script = tmp_path / "scripts" / "fetch-ffmpeg.sh"
    script.parent.mkdir()
    script.write_text("#!/usr/bin/env bash\n", encoding="utf-8")

    assert ffmpeg_setup._provisioning_context(tmp_path) == (script, tmp_path / ".ffmpeg")


def test_wheel_context_authenticates_the_recorded_script(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installed = tmp_path / "share" / "hawedit" / "scripts" / "fetch-ffmpeg.sh"
    installed.parent.mkdir(parents=True)
    installed.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    monkeypatch.setattr(ffmpeg_setup, "resolve_installed_hawedit_data", lambda _path: installed)
    monkeypatch.setattr(ffmpeg_setup, "default_ffmpeg_dir", lambda: tmp_path / "cache")

    assert ffmpeg_setup._provisioning_context(tmp_path / "no-source") == (
        installed,
        tmp_path / "cache",
    )


def test_binary_probe_requires_rtl_and_its_matching_ffprobe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = tmp_path / "ffmpeg"
    probe = tmp_path / "ffprobe"
    binary.write_bytes(b"fixture")
    probe.write_bytes(b"fixture")
    monkeypatch.setattr(ffmpeg_setup, "find_ffmpeg", lambda: binary)
    monkeypatch.setattr(ffmpeg_setup, "ffprobe_for", lambda _binary: probe)
    monkeypatch.setattr("platform.system", lambda: "Windows")

    def run(command: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
        if command[0] == str(binary):
            output = "configuration: --enable-libass --enable-libharfbuzz --enable-libfribidi"
        else:
            output = "ffprobe fixture"
        return subprocess.CompletedProcess(command, 0, output, "")

    monkeypatch.setattr(ffmpeg_setup, "_run", run)
    assert ffmpeg_setup._verified_existing() == binary

    probe.unlink()
    with pytest.raises(FfmpegSetupError, match="ffprobe is missing"):
        ffmpeg_setup._verified_existing()


def test_existing_verified_pair_returns_without_running_a_provisioner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    binary = tmp_path / "ffmpeg"
    monkeypatch.setattr(ffmpeg_setup, "_verified_existing", lambda: binary)
    monkeypatch.setattr(
        ffmpeg_setup,
        "_run_provisioner",
        lambda *_args: pytest.fail("a verified pair must not trigger provisioning"),
    )

    assert main([]) == 0
    assert f"hawedit-ffmpeg-ok: {binary}" in capsys.readouterr().out


def test_linux_missing_pair_runs_authenticated_provisioner_then_rechecks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    active = tmp_path / "cache" / "ffmpeg"
    answers = iter((None, active))
    observed: list[tuple[Path, Path]] = []
    script = tmp_path / "fetch-ffmpeg.sh"
    target = tmp_path / "cache"
    monkeypatch.setattr(ffmpeg_setup, "_verified_existing", lambda: next(answers))
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr(ffmpeg_setup, "_provisioning_context", lambda: (script, target))

    def provision(selected: Path, destination: Path) -> int:
        observed.append((selected, destination))
        return 0

    monkeypatch.setattr(ffmpeg_setup, "_run_provisioner", provision)

    assert main([]) == 0
    assert observed == [(script, target)]


def test_check_mode_and_non_linux_missing_pair_never_download(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(ffmpeg_setup, "_verified_existing", lambda: None)
    monkeypatch.setattr(
        ffmpeg_setup,
        "_run_provisioner",
        lambda *_args: pytest.fail("refusal paths must not download"),
    )
    assert main(["--check"]) == 1
    assert "no ffmpeg is available" in capsys.readouterr().err

    monkeypatch.setattr("platform.system", lambda: "Windows")
    assert main([]) == 1
    assert "winget install Gyan.FFmpeg" in capsys.readouterr().err


def test_find_ffmpeg_discovers_the_installed_user_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install = tmp_path / "installed"
    install.mkdir()
    binary = install / "ffmpeg"
    binary.write_bytes(b"launcher")
    monkeypatch.delenv("HAWEDIT_FFMPEG", raising=False)
    monkeypatch.setenv("HAWEDIT_FFMPEG_DIR", str(install))
    monkeypatch.setattr("shutil.which", lambda _name: None)

    assert find_ffmpeg() == binary

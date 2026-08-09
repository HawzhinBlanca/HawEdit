"""Supply-chain guards on scripts that download executable/model bytes."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _bash() -> Path:
    candidates: list[Path] = []
    if configured := os.environ.get("HAWEDIT_BASH"):
        candidates.append(Path(configured))
    if git := shutil.which("git"):
        candidates.append(Path(git).resolve().parent.parent / "bin" / "bash.exe")
    if program_files := os.environ.get("PROGRAMFILES"):
        candidates.append(Path(program_files) / "Git" / "bin" / "bash.exe")
    if sys.platform != "win32" and (found := shutil.which("bash")):
        candidates.append(Path(found))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise AssertionError("the canonical gate requires Bash, but no usable Bash was found")


def _write_executable(path: Path, body: str) -> None:
    path.write_text("#!/usr/bin/env bash\nset -euo pipefail\n" + body, encoding="utf-8")
    path.chmod(0o755)


def _link_directory(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=True)
        return
    except OSError:
        if sys.platform != "win32":
            raise
    created = subprocess.run(
        ["cmd", "/d", "/c", "mklink", "/J", str(link), str(target)],
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert created.returncode == 0, created.stderr or created.stdout


def _ffmpeg_fixture(
    tmp_path: Path, *, staged_pair_is_valid: bool = True
) -> tuple[Path, dict[str, str]]:
    project = tmp_path / "project"
    scripts = project / "scripts"
    scripts.mkdir(parents=True)
    shutil.copy2(ROOT / "scripts" / "fetch-ffmpeg.sh", scripts / "fetch-ffmpeg.sh")
    shutil.copy2(ROOT / "scripts" / "verify-sha256.sh", scripts / "verify-sha256.sh")
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()

    _write_executable(fake_bin / "uname", 'printf "%s\\n" Linux\n')
    _write_executable(fake_bin / "flock", "exit 0\n")
    # Prevent a real PATH ffmpeg from satisfying the preflight.
    _write_executable(
        fake_bin / "ffmpeg", 'printf "%s\\n" "configuration: no RTL libraries"\nexit 1\n'
    )
    _write_executable(
        fake_bin / "curl",
        """
output=
while (($#)); do
  if [[ "$1" == "-o" ]]; then output="$2"; shift 2; else shift; fi
done
[[ -n "$output" ]]
printf 'authenticated fixture archive' >"$output"
printf '%s\n' "$output" >"$FFMPEG_TEST_CURL_OUTPUT"
""",
    )
    _write_executable(
        fake_bin / "sha256sum",
        """
if [[ "${1:-}" == "--check" && $# -eq 2 ]]; then
  exit "${FFMPEG_TEST_HASH_STATUS:-0}"
fi
if [[ $# -eq 1 && "$1" == */linux.zip ]]; then
  printf '%s  %s\n' 'ca75b05e887c7a97676632f673031875847be83daa9794298fed9cef8cac14ad' "$1"
  exit 0
fi
exec /usr/bin/sha256sum "$@"
""",
    )
    buildconf = (
        "configuration: --enable-libass --enable-libharfbuzz --enable-libfribidi"
        if staged_pair_is_valid
        else "configuration: --enable-libass"
    )
    _write_executable(
        fake_bin / "unzip",
        f"""
destination=
while (($#)); do
  if [[ "$1" == "-d" ]]; then destination="$2"; shift 2; else shift; fi
done
mkdir -p "$destination/bin"
cat >"$destination/bin/ffmpeg" <<'FFMPEG'
#!/usr/bin/env bash
if [[ "$*" == *-buildconf* ]]; then
  printf '%s\\n' '{buildconf}'
else
  printf '%s\\n' 'ffmpeg fixture'
fi
FFMPEG
cat >"$destination/bin/ffprobe" <<'FFPROBE'
#!/usr/bin/env bash
printf '%s\\n' 'ffprobe fixture'
FFPROBE
chmod 700 "$destination/bin/ffmpeg" "$destination/bin/ffprobe"
""",
    )

    curl_output = tmp_path / "curl-output.txt"
    env = os.environ.copy()
    env.update(
        {
            "FFMPEG_TEST_CURL_OUTPUT": str(curl_output),
            "FFMPEG_TEST_FAKE_BIN": str(fake_bin),
            "HAWEDIT_FFMPEG": "",
        }
    )
    return project, env


def _run_ffmpeg_fetch(project: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    script = (project / "scripts" / "fetch-ffmpeg.sh").as_posix()
    return subprocess.run(
        [
            str(_bash()),
            "--noprofile",
            "--norc",
            "-c",
            'fake_bin="$(cd "$1" && pwd -P)"; export PATH="$fake_bin:$PATH"; exec "$2"',
            "hawedit-ffmpeg-test",
            env["FFMPEG_TEST_FAKE_BIN"],
            script,
        ],
        cwd=project,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )


def test_ffmpeg_fetch_uses_an_immutable_commit_and_lfs_digest_before_unpacking() -> None:
    script = (ROOT / "scripts" / "fetch-ffmpeg.sh").read_text(encoding="utf-8")
    commit = re.search(r'^ffmpeg_bins_commit="([0-9a-f]{40})"$', script, re.MULTILINE)
    digest = re.search(r'^linux_zip_sha256="([0-9a-f]{64})"$', script, re.MULTILINE)
    assert commit is not None
    assert digest is not None
    assert "ffmpeg_bins/main/" not in script
    assert "${ffmpeg_bins_commit}/v8.0/linux.zip" in script
    assert script.index("verify-sha256.sh") < script.index("unzip -q")
    assert "curl --fail" in script and "--proto '=https'" in script


def test_ffmpeg_fetch_repairs_a_corrupt_install_through_a_private_generation(
    tmp_path: Path,
) -> None:
    project, env = _ffmpeg_fixture(tmp_path)
    install = project / ".ffmpeg"
    install.mkdir()
    old = install / "ffmpeg"
    _write_executable(old, 'printf "%s\\n" "configuration: corrupt"\nexit 1\n')
    _write_executable(install / "ffprobe", "exit 1\n")

    result = _run_ffmpeg_fetch(project, env)

    assert result.returncode == 0, result.stderr
    assert "libass + HarfBuzz + FriBidi: present" in result.stdout
    assert old.read_text(encoding="utf-8").startswith("#!/usr/bin/env bash\nset -euo pipefail")
    assert "generations/" in old.read_text(encoding="utf-8")
    generations = tuple((install / "generations").iterdir())
    assert len(generations) == 1
    assert (generations[0] / "ffmpeg").is_file()
    assert (generations[0] / "SHA256SUMS").is_file()
    attempts = tuple(path for path in install.glob(".fetch.*") if path.name != ".fetch.lock")
    assert not attempts, "private attempts must be removed after publication"
    assert (install / ".fetch.lock").is_file(), "the stable kernel-lock inode is retained"

    curl_output = Path((tmp_path / "curl-output.txt").read_text(encoding="utf-8").strip())
    assert curl_output.name == "linux.zip"
    assert ".fetch." in curl_output.parent.as_posix(), "curl wrote to a predictable shared path"

    # Reuse is a hash check, not a second download.
    (tmp_path / "curl-output.txt").unlink()
    second = _run_ffmpeg_fetch(project, env)
    assert second.returncode == 0, second.stderr
    assert "generation and hashes verified" in second.stdout
    assert not (tmp_path / "curl-output.txt").exists()


def test_ffmpeg_fetch_repairs_a_capable_but_byte_modified_generation(tmp_path: Path) -> None:
    project, env = _ffmpeg_fixture(tmp_path)
    first = _run_ffmpeg_fetch(project, env)
    assert first.returncode == 0, first.stderr
    install = project / ".ffmpeg"
    first_generation = next((install / "generations").iterdir())
    with (first_generation / "ffmpeg").open("a", encoding="utf-8") as stream:
        stream.write("\n# unreceipted mutation that preserves executable behaviour\n")
    (tmp_path / "curl-output.txt").unlink()

    second = _run_ffmpeg_fetch(project, env)

    assert second.returncode == 0, second.stderr
    assert "receipt or bytes are invalid; repairing" in second.stderr
    assert (tmp_path / "curl-output.txt").is_file(), "the modified generation was trusted"
    assert len(tuple((install / "generations").iterdir())) == 2


def test_ffmpeg_fetch_never_publishes_a_pair_that_fails_staged_verification(
    tmp_path: Path,
) -> None:
    project, env = _ffmpeg_fixture(tmp_path, staged_pair_is_valid=False)
    install = project / ".ffmpeg"
    install.mkdir()
    old = install / "ffmpeg"
    old_bytes = b"#!/usr/bin/env bash\nexit 1\n"
    old.write_bytes(old_bytes)
    old.chmod(0o755)

    result = _run_ffmpeg_fetch(project, env)

    assert result.returncode == 1
    assert "nothing was published" in result.stderr
    assert old.read_bytes() == old_bytes
    assert not (install / "generations").exists()
    attempts = tuple(path for path in install.glob(".fetch.*") if path.name != ".fetch.lock")
    assert not attempts
    assert (install / ".fetch.lock").is_file()


def test_ffmpeg_publication_replaces_a_hardlink_without_touching_its_victim(tmp_path: Path) -> None:
    project, env = _ffmpeg_fixture(tmp_path)
    install = project / ".ffmpeg"
    install.mkdir()
    victim = tmp_path / "victim"
    victim.write_bytes(b"DO NOT MODIFY")
    os.link(victim, install / "ffmpeg")
    (install / "ffmpeg").chmod(0o755)

    result = _run_ffmpeg_fetch(project, env)

    assert result.returncode == 0, result.stderr
    assert victim.read_bytes() == b"DO NOT MODIFY"
    assert os.stat(victim).st_nlink == 1
    assert "generations/" in (install / "ffmpeg").read_text(encoding="utf-8")


def test_ffmpeg_fetch_refuses_a_non_directory_install_root_before_curl(tmp_path: Path) -> None:
    project, env = _ffmpeg_fixture(tmp_path)
    (project / ".ffmpeg").write_bytes(b"external-looking target")

    result = _run_ffmpeg_fetch(project, env)

    assert result.returncode == 1
    assert "exists and is not a directory" in result.stderr
    assert not (tmp_path / "curl-output.txt").exists()


def test_ffmpeg_fetch_refuses_a_linked_install_root_without_touching_its_target(
    tmp_path: Path,
) -> None:
    project, env = _ffmpeg_fixture(tmp_path)
    victim = tmp_path / "external-directory"
    victim.mkdir()
    marker = victim / "marker"
    marker.write_bytes(b"KEEP")
    _link_directory(project / ".ffmpeg", victim)

    result = _run_ffmpeg_fetch(project, env)

    assert result.returncode == 1
    assert "symbolic link" in result.stderr or "resolves outside" in result.stderr
    assert marker.read_bytes() == b"KEEP"
    assert tuple(victim.iterdir()) == (marker,)
    assert not (tmp_path / "curl-output.txt").exists()


def test_ffmpeg_fetch_refuses_a_non_regular_lock_without_truncating_it(tmp_path: Path) -> None:
    project, env = _ffmpeg_fixture(tmp_path)
    lock = project / ".ffmpeg" / ".fetch.lock"
    lock.mkdir(parents=True)

    result = _run_ffmpeg_fetch(project, env)

    assert result.returncode == 1
    assert "is not a regular lock file" in result.stderr
    assert lock.is_dir(), "a process that did not acquire the lock must not replace it"
    assert not (tmp_path / "curl-output.txt").exists()


def test_ffmpeg_fetch_refuses_a_hardlinked_lock_without_touching_its_victim(tmp_path: Path) -> None:
    project, env = _ffmpeg_fixture(tmp_path)
    install = project / ".ffmpeg"
    install.mkdir()
    victim = tmp_path / "lock-victim"
    victim.write_bytes(b"LOCK VICTIM")
    os.link(victim, install / ".fetch.lock")

    result = _run_ffmpeg_fetch(project, env)

    assert result.returncode == 1
    assert "must be one owner-controlled regular file" in result.stderr
    assert victim.read_bytes() == b"LOCK VICTIM"
    assert os.stat(victim).st_nlink == 2
    assert not (tmp_path / "curl-output.txt").exists()


def test_model_fetch_passes_a_full_revision_and_pins_its_download_client() -> None:
    implementation = (ROOT / "src" / "hawedit" / "model_fetch.py").read_text(encoding="utf-8")
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "repo_id=item.repository" in implementation
    assert "revision=item.revision" in implementation
    assert 'DOWNLOAD_CLIENT_VERSION: Final = "0.36.2"' in implementation
    assert '"huggingface-hub==0.36.2"' in project


def test_model_fetch_uses_one_models_root_and_failures_survive_the_status_report() -> None:
    script = (ROOT / "scripts" / "fetch-models.sh").read_text(encoding="utf-8")
    implementation = (ROOT / "src" / "hawedit" / "model_fetch.py").read_text(encoding="utf-8")
    assert 'exec "$PY" -m hawedit.model_fetch "$@"' in script
    assert "ModelStore(root=args.models_dir)" in implementation
    assert "HAWEDIT_MODELS" not in script
    assert "status_ok = _print_status(store)" in implementation
    assert "return int(failures or not status_ok)" in implementation


def test_model_fetch_stages_verifies_locks_and_atomically_publishes() -> None:
    implementation = (ROOT / "src" / "hawedit" / "model_fetch.py").read_text(encoding="utf-8")
    assert "checkpoint_publish_lock(destination)" in implementation
    assert ".download-{revision}" in implementation
    assert ".resume-{item.revision}" in implementation
    assert "tempfile.mkdtemp(" in implementation
    assert "resume_download=True" in implementation
    assert "metadata.st_nlink != 1" in implementation
    assert "stat.S_IMODE(root_before.st_mode) & 0o077" in implementation
    assert implementation.index("validate_private_stage(resume)") < implementation.index(
        "download("
    )
    assert implementation.index("validate_private_stage(staging)") < implementation.index(
        "download("
    )
    assert implementation.index(
        "store.verify_checkpoint(item.entry.model_id, staging)"
    ) < implementation.index("_publish_checkpoint_directory(staging, destination)")
    assert "existing final checkpoint is invalid and was preserved" in implementation


def test_every_remote_github_action_is_pinned_to_a_full_commit() -> None:
    workflows = tuple((ROOT / ".github" / "workflows").glob("*.yml"))
    assert workflows
    uses: list[tuple[Path, str]] = []
    for workflow in workflows:
        for line in workflow.read_text(encoding="utf-8").splitlines():
            match = re.search(r"\buses:\s*([^\s#]+)", line)
            if match and not match.group(1).startswith(("./", "docker://")):
                uses.append((workflow, match.group(1)))
    assert uses
    for workflow, action in uses:
        assert re.fullmatch(r"[^@\s]+@[0-9a-f]{40}", action), (
            f"{workflow}: remote action {action!r} is not pinned to a full commit"
        )


def test_gate_uses_the_audited_node24_action_commits() -> None:
    """A full SHA can still identify an action whose retired Node runtime is being emulated."""
    workflow = (ROOT / ".github" / "workflows" / "gate.yml").read_text(encoding="utf-8")
    expected = {
        "actions/checkout": ("3d3c42e5aac5ba805825da76410c181273ba90b1", "v7.0.1"),
        "actions/setup-python": ("5fda3b95a4ea91299a34e894583c3862153e4b97", "v7.0.0"),
    }
    for action, (commit, release) in expected.items():
        assert f"uses: {action}@{commit} # {release}" in workflow

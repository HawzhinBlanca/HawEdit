"""Supply-chain guards on scripts that download executable/model bytes."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_ffmpeg_fetch_uses_an_immutable_commit_and_lfs_digest_before_unpacking() -> None:
    script = (ROOT / "scripts" / "fetch-ffmpeg.sh").read_text(encoding="utf-8")
    commit = re.search(r'^ffmpeg_bins_commit="([0-9a-f]{40})"$', script, re.MULTILINE)
    digest = re.search(r'^linux_zip_sha256="([0-9a-f]{64})"$', script, re.MULTILINE)
    assert commit is not None
    assert digest is not None
    assert "ffmpeg_bins/main/" not in script
    assert "${ffmpeg_bins_commit}/v8.0/linux.zip" in script
    assert script.index("sha256sum --check") < script.index("unzip -oq")
    assert "curl --fail" in script and "--proto '=https'" in script


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

"""Release artifacts are reproducible, complete and atomically published."""

from __future__ import annotations

import hashlib
import io
import json
import subprocess
import sys
import tarfile
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import cast
from urllib.error import URLError

import pytest

import hawedit.release as release_module
from hawedit.release import (
    LocalWheelArtifact,
    ReleaseError,
    _assert_release_identity,
    _extract_git_archive,
    _github_json,
    _locked_build_contract,
    _publish_directory,
    _spdx_sbom,
    _verify_gate_run,
    build_local_reproducible_wheel,
    build_reproducible_wheel,
)

RELEASE_BUILD_LOCK = """\
pip==26.2.1 --hash=sha256:71138adf1f4ca900cdb7d289c21b7494329f2332b6d85f0e1c42108c0384ed3e
setuptools==84.0.0 --hash=sha256:51a52592b3b99e102b609654876bd65f19f999935166d1352678931132b0c670
"""
ROOT = Path(__file__).resolve().parents[1]
GATE_RUN_ID = 42_424_242
GATE_JOB_ID = 91_919_191
EXPECTED_GATE_STEPS = (
    "install",
    "fetch the pinned ffmpeg (libass + HarfBuzz + FriBidi)",
    "gate",
    "the golden render must have run, not skipped",
    "Stage 0 must have run against real media, not skipped",
    "the pipeline must run over real media and refuse to claim completeness",
    "the gate must have left fresh test evidence",
    "the test-count floor must not have been ratcheted by this run",
)


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def _git_bytes(root: Path, *args: str) -> bytes:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, check=True)
    return result.stdout


def test_git_archive_preserves_authenticated_text_member_bytes(tmp_path: Path) -> None:
    """Windows archive export must not rewrite committed lock or license bytes."""
    attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "*.txt text eol=lf" in attributes

    tracked = tuple(
        path for path in _git_bytes(ROOT, "ls-files", "-z", "*.txt").split(b"\0") if path
    )
    assert tracked
    archive_path = tmp_path / "source.tar"
    subprocess.run(
        [
            "git",
            "-c",
            "core.autocrlf=true",
            "archive",
            "--worktree-attributes",
            "--format=tar",
            f"--output={archive_path}",
            "HEAD",
            "--",
            *(path.decode("utf-8") for path in tracked),
        ],
        cwd=ROOT,
        check=True,
    )
    with tarfile.open(archive_path, mode="r:") as archive:
        for encoded_path in tracked:
            path = encoded_path.decode("utf-8")
            member = archive.extractfile(path)
            assert member is not None, f"Git archive omitted {path}"
            blob = _git_bytes(ROOT, "show", f"HEAD:{path}")
            assert member.read() == blob, f"Git archive rewrote committed bytes for {path}"


def _release_source(root: Path) -> Path:
    """A tiny clean Git package with HawEdit's release-critical wheel members."""
    project = root / "project"
    (project / "src" / "hawedit").mkdir(parents=True)
    (project / "assets" / "fonts").mkdir(parents=True)
    (project / "models").mkdir()
    (project / "requirements").mkdir()
    (project / "scripts").mkdir()
    (project / "src" / "hawedit" / "__init__.py").write_text("", encoding="utf-8")
    (project / "src" / "hawedit" / "release.py").write_text(
        '"""release fixture"""\n', encoding="utf-8"
    )
    (project / "assets" / "fonts" / "NotoNaskhArabic-Regular.ttf").write_bytes(b"font")
    (project / "assets" / "fonts" / "OFL.txt").write_text("OFL", encoding="utf-8")
    (project / "models" / "sources.json").write_text("{}\n", encoding="utf-8")
    (project / "models" / "revisions.json").write_text("{}\n", encoding="utf-8")
    (project / "models" / "integrity.json").write_text(
        '{"schema":1,"models":{}}\n', encoding="utf-8"
    )
    (project / "requirements" / "release-build.txt").write_text(
        RELEASE_BUILD_LOCK, encoding="utf-8"
    )
    for target in (
        "host-base-linux-py311.txt",
        "host-base-linux-py312.txt",
        "host-base-windows-py311.txt",
        "host-base-windows-py312.txt",
        "host-models-linux-py311.txt",
        "host-models-linux-py312.txt",
        "host-models-windows-py311.txt",
        "host-models-windows-py312.txt",
        "host-gpu-windows-py311.txt",
    ):
        (project / "requirements" / target).write_text("# fixture lock\n", encoding="utf-8")
    (project / "security").mkdir()
    (project / "security" / "wsl-asr-vex.json").write_text("{}\n", encoding="utf-8")
    (project / "scripts" / "fetch-ffmpeg.sh").write_text(
        "#!/usr/bin/env bash\nexit 0\n", encoding="utf-8"
    )
    (project / ".gitignore").write_text("/build/\n/dist/\n*.egg-info/\n", encoding="utf-8")
    (project / "pyproject.toml").write_text(
        """[build-system]
requires = ["setuptools==84.0.0"]
build-backend = "setuptools.build_meta"

[project]
name = "hawedit-release-fixture"
version = "1.0.0"
dependencies = ["base-dep==2.3.4"]

[project.optional-dependencies]
feature = ["optional-dep>=5"]

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools.data-files]
"share/hawedit/assets/fonts" = [
    "assets/fonts/NotoNaskhArabic-Regular.ttf",
    "assets/fonts/OFL.txt",
]
"share/hawedit/models" = [
    "models/sources.json",
    "models/revisions.json",
    "models/integrity.json",
]
"share/hawedit/requirements" = [
    "requirements/host-base-linux-py311.txt",
    "requirements/host-base-linux-py312.txt",
    "requirements/host-base-windows-py311.txt",
    "requirements/host-base-windows-py312.txt",
    "requirements/host-models-linux-py311.txt",
    "requirements/host-models-linux-py312.txt",
    "requirements/host-models-windows-py311.txt",
    "requirements/host-models-windows-py312.txt",
    "requirements/host-gpu-windows-py311.txt",
]
"share/hawedit/security" = ["security/wsl-asr-vex.json"]
"share/hawedit/scripts" = ["scripts/fetch-ffmpeg.sh"]
""",
        encoding="utf-8",
    )
    _git(project, "init", "--quiet")
    _git(project, "add", "--", ".")
    _git(
        project,
        "-c",
        "user.name=HawEdit Test",
        "-c",
        "user.email=test@hawedit.invalid",
        "commit",
        "--quiet",
        "-m",
        "fixture",
    )
    return project


def _successful_gate_responses(revision: str) -> tuple[dict[str, object], dict[str, object]]:
    run_page = f"https://github.com/HawzhinBlanca/HawEdit/actions/runs/{GATE_RUN_ID}"
    run: dict[str, object] = {
        "id": GATE_RUN_ID,
        "repository": {"full_name": "HawzhinBlanca/HawEdit"},
        "head_repository": {"full_name": "HawzhinBlanca/HawEdit"},
        "path": ".github/workflows/gate.yml",
        "event": "push",
        "head_branch": "main",
        "head_sha": revision,
        "status": "completed",
        "conclusion": "success",
        "run_attempt": 1,
        "html_url": run_page,
    }
    steps = [
        {"name": name, "status": "completed", "conclusion": "success"}
        for name in EXPECTED_GATE_STEPS
    ]
    jobs: dict[str, object] = {
        "total_count": 1,
        "jobs": [
            {
                "id": GATE_JOB_ID,
                "name": "gate",
                "head_sha": revision,
                "status": "completed",
                "conclusion": "success",
                "run_attempt": 1,
                "html_url": f"{run_page}/job/{GATE_JOB_ID}",
                "completed_at": "2026-08-09T04:32:54Z",
                "steps": steps,
            }
        ],
    }
    return run, jobs


def _stub_gate_api(
    monkeypatch: pytest.MonkeyPatch,
    run: dict[str, object],
    jobs: dict[str, object],
) -> None:
    def response(url: str) -> dict[str, object]:
        expected = f"https://api.github.com/repos/HawzhinBlanca/HawEdit/actions/runs/{GATE_RUN_ID}"
        if url == expected:
            return run
        if url == f"{expected}/jobs?per_page=100":
            return jobs
        raise AssertionError(f"unexpected GitHub API URL {url}")

    monkeypatch.setattr(release_module, "_github_json", response)


def test_release_builds_twice_and_publishes_verified_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _release_source(tmp_path)
    destination = tmp_path / "published"
    revision = _git(project, "rev-parse", "HEAD")
    run, jobs = _successful_gate_responses(revision)
    _stub_gate_api(monkeypatch, run, jobs)
    identity_calls: list[tuple[Path, Path]] = []
    original_identity_check = release_module._assert_release_identity

    def record_identity(project_root: Path, wheel: Path) -> tuple[str, str]:
        identity_calls.append((project_root, wheel))
        return original_identity_check(project_root, wheel)

    monkeypatch.setattr(release_module, "_assert_release_identity", record_identity)

    artifact = build_reproducible_wheel(
        project,
        destination,
        python=Path(sys.executable),
        gate_run_id=GATE_RUN_ID,
    )

    assert artifact.output_dir == destination
    assert artifact.wheel.is_file()
    assert artifact.distribution == "hawedit-release-fixture"
    assert artifact.version == "1.0.0"
    assert len(identity_calls) == 1
    assert identity_calls[0][0].name == "source-first"
    assert artifact.checksum_file.read_text(encoding="utf-8") == (
        f"{artifact.sha256}  {artifact.wheel.name}\n"
        f"{artifact.sbom_sha256}  {artifact.sbom_file.name}\n"
        f"{artifact.provenance_sha256}  {artifact.provenance_file.name}\n"
    )
    provenance = json.loads(artifact.provenance_file.read_text(encoding="utf-8"))
    assert provenance == {
        "schema": 5,
        "revision": revision,
        "source_date_epoch": artifact.source_date_epoch,
        "distribution": "hawedit-release-fixture",
        "version": "1.0.0",
        "gate": {
            "repository": "HawzhinBlanca/HawEdit",
            "workflow": ".github/workflows/gate.yml",
            "run_id": GATE_RUN_ID,
            "run_attempt": 1,
            "event": "push",
            "branch": "main",
            "revision": revision,
            "status": "completed",
            "conclusion": "success",
            "url": f"https://github.com/HawzhinBlanca/HawEdit/actions/runs/{GATE_RUN_ID}",
            "completed_at": "2026-08-09T04:32:54Z",
            "job": "gate",
            "job_id": GATE_JOB_ID,
            "job_url": (
                f"https://github.com/HawzhinBlanca/HawEdit/actions/runs/{GATE_RUN_ID}"
                f"/job/{GATE_JOB_ID}"
            ),
        },
        "builder": {
            "python": artifact.build_python,
            "frontend": "pip==26.2.1",
            "backend": "setuptools==84.0.0",
            "requirements": {"pip": "26.2.1", "setuptools": "84.0.0"},
            "lock": "requirements/release-build.txt",
            "lock_sha256": artifact.build_lock_sha256,
        },
        "wheel": artifact.wheel.name,
        "sha256": artifact.sha256,
        "size_bytes": artifact.size_bytes,
        "sbom": artifact.sbom_file.name,
        "sbom_format": "SPDX-2.3-json",
        "sbom_sha256": artifact.sbom_sha256,
    }
    sbom = json.loads(artifact.sbom_file.read_text(encoding="utf-8"))
    assert sbom["spdxVersion"] == "SPDX-2.3"
    assert sbom["dataLicense"] == "CC0-1.0"
    assert sbom["documentDescribes"] == ["SPDXRef-Package-HawEdit"]
    assert sbom["documentNamespace"].endswith(f"/{artifact.revision}/{artifact.sha256}")
    packages = {package["name"]: package for package in sbom["packages"]}
    assert set(packages) == {
        "hawedit-release-fixture",
        "Noto Naskh Arabic",
        "base-dep",
        "optional-dep",
    }
    assert packages["hawedit-release-fixture"]["checksums"] == [
        {"algorithm": "SHA256", "checksumValue": artifact.sha256}
    ]
    assert packages["base-dep"]["versionInfo"] == "2.3.4"
    assert "versionInfo" not in packages["optional-dep"]
    relationships = {
        (
            relationship["spdxElementId"],
            relationship["relationshipType"],
            relationship["relatedSpdxElement"],
        )
        for relationship in sbom["relationships"]
    }
    root = "SPDXRef-Package-HawEdit"
    font_id = packages["Noto Naskh Arabic"]["SPDXID"]
    base_id = packages["base-dep"]["SPDXID"]
    optional_id = packages["optional-dep"]["SPDXID"]
    assert ("SPDXRef-DOCUMENT", "DESCRIBES", root) in relationships
    assert (root, "CONTAINS", font_id) in relationships
    assert (root, "DEPENDS_ON", base_id) in relationships
    assert (optional_id, "OPTIONAL_DEPENDENCY_OF", root) in relationships
    assert packages["Noto Naskh Arabic"]["checksums"] == [
        {"algorithm": "SHA256", "checksumValue": hashlib.sha256(b"font").hexdigest()}
    ]
    expected_sbom = _spdx_sbom(
        artifact.wheel,
        revision=artifact.revision,
        epoch=artifact.source_date_epoch,
        wheel_sha256=artifact.sha256,
    )
    assert artifact.sbom_file.read_bytes() == expected_sbom
    assert expected_sbom == _spdx_sbom(
        artifact.wheel,
        revision=artifact.revision,
        epoch=artifact.source_date_epoch,
        wheel_sha256=artifact.sha256,
    )
    assert {path.name for path in destination.iterdir()} == {
        artifact.wheel.name,
        artifact.sbom_file.name,
        "SHA256SUMS",
        "release-provenance.json",
    }
    with zipfile.ZipFile(artifact.wheel) as wheel:
        assert wheel.testzip() is None
        wheel_metadata = wheel.read("hawedit_release_fixture-1.0.0.dist-info/WHEEL").decode()
        assert "Generator: setuptools (84.0.0)" in wheel_metadata
        assert any(name.endswith("share/hawedit/models/sources.json") for name in wheel.namelist())
        assert any(
            name.endswith("share/hawedit/models/revisions.json") for name in wheel.namelist()
        )
        assert any(
            name.endswith("share/hawedit/models/integrity.json") for name in wheel.namelist()
        )
        for target in (
            "host-base-linux-py311.txt",
            "host-base-linux-py312.txt",
            "host-base-windows-py311.txt",
            "host-base-windows-py312.txt",
            "host-models-linux-py311.txt",
            "host-models-linux-py312.txt",
            "host-models-windows-py311.txt",
            "host-models-windows-py312.txt",
            "host-gpu-windows-py311.txt",
        ):
            assert any(
                name.endswith(f"share/hawedit/requirements/{target}") for name in wheel.namelist()
            )
        assert any(
            name.endswith("share/hawedit/security/wsl-asr-vex.json") for name in wheel.namelist()
        )
        assert any(
            name.endswith("share/hawedit/scripts/fetch-ffmpeg.sh") for name in wheel.namelist()
        )

    with pytest.raises(ReleaseError, match="refusing to overwrite"):
        build_reproducible_wheel(
            project,
            destination,
            python=Path(sys.executable),
            gate_run_id=GATE_RUN_ID,
        )


def _identity_fixture(
    root: Path,
    *,
    project_name: str = "hawedit",
    project_version: str = "1.2.3",
    metadata_name: str = "hawedit",
    metadata_version: str = "1.2.3",
    filename_name: str = "hawedit",
    filename_version: str = "1.2.3",
) -> tuple[Path, Path]:
    project = root / "project"
    project.mkdir()
    (project / "pyproject.toml").write_text(
        f'[project]\nname = "{project_name}"\nversion = "{project_version}"\n',
        encoding="utf-8",
    )
    wheel = root / f"{filename_name}-{filename_version}-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(
            f"{filename_name}-{filename_version}.dist-info/METADATA",
            f"Metadata-Version: 2.4\nName: {metadata_name}\nVersion: {metadata_version}\n\n",
        )
    return project, wheel


@pytest.mark.parametrize(
    ("changed", "message"),
    [
        ({"metadata_name": "hawedit-impostor"}, "METADATA name"),
        ({"metadata_version": "9.9.9"}, "METADATA version"),
        ({"filename_name": "hawedit_impostor"}, "filename distribution"),
        ({"filename_version": "9.9.9"}, "filename version"),
    ],
)
def test_release_identity_refuses_source_metadata_or_filename_drift(
    tmp_path: Path, changed: dict[str, str], message: str
) -> None:
    project, wheel = _identity_fixture(tmp_path, **changed)
    with pytest.raises(ReleaseError, match=message):
        _assert_release_identity(project, wheel)


def test_release_identity_accepts_pep503_name_spelling_only(tmp_path: Path) -> None:
    project, wheel = _identity_fixture(
        tmp_path,
        project_name="HawEdit.Release_Fixture",
        metadata_name="hawedit-release-fixture",
        filename_name="hawedit_release_fixture",
    )
    assert _assert_release_identity(project, wheel) == ("hawedit-release-fixture", "1.2.3")


def test_release_main_reserves_stdout_for_its_json_document(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class FakeArtifact:
        def to_dict(self) -> dict[str, str]:
            return {"distribution": "hawedit", "version": "1.2.3"}

    def noisy_build(*_args: object, **_kwargs: object) -> FakeArtifact:
        print("dependency noise")
        return FakeArtifact()

    monkeypatch.setattr(release_module, "build_reproducible_wheel", noisy_build)

    assert release_module.main(["--project-root", str(tmp_path), "--gate-run-id", "1"]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"distribution": "hawedit", "version": "1.2.3"}
    assert captured.err == "dependency noise\n"


def test_release_refuses_to_build_without_an_explicit_gate_run(tmp_path: Path) -> None:
    project = _release_source(tmp_path)
    destination = tmp_path / "uncreated" / "untested-release"

    with pytest.raises(ReleaseError, match="explicit positive --gate-run-id"):
        build_reproducible_wheel(project, destination, python=Path(sys.executable))

    assert not destination.exists()
    assert not destination.parent.exists()


def test_release_gate_contract_is_bound_to_the_canonical_workflow() -> None:
    workflow = (ROOT / ".github" / "workflows" / "gate.yml").read_text(encoding="utf-8")

    assert release_module._GITHUB_REPOSITORY == "HawzhinBlanca/HawEdit"
    assert release_module._GATE_WORKFLOW == ".github/workflows/gate.yml"
    assert release_module._GATE_JOB == "gate"
    assert release_module._GATE_BRANCH == "main"
    assert release_module._REQUIRED_GATE_STEPS == EXPECTED_GATE_STEPS
    assert "push:\n    branches: [main]" in workflow
    assert "\n  gate:\n" in workflow
    assert "continue-on-error" not in workflow
    for step in EXPECTED_GATE_STEPS:
        assert f"- name: {step}" in workflow


@pytest.mark.parametrize(
    ("case", "message"),
    (
        ("repository", "official HawEdit repository"),
        ("fork", "tested a fork"),
        ("run_id", "different gate run id"),
        ("workflow", "did not use"),
        ("event", "must be the push run"),
        ("branch", "not 'main'"),
        ("revision", "but the release source is"),
        ("run_status", "has not completed"),
        ("run_conclusion", "did not conclude successfully"),
        ("job", "expected one"),
        ("job_revision", "revision does not match"),
        ("job_status", "job has not completed"),
        ("job_conclusion", "gate job did not conclude successfully"),
        ("attempt", "different run attempt"),
        ("pagination", "incomplete paginated evidence"),
        ("missing_step", "omitted required step"),
        ("failed_step", "did not succeed"),
        ("duplicate_step", "duplicate required step"),
    ),
)
def test_release_rejects_gate_evidence_that_is_not_the_exact_canonical_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
    message: str,
) -> None:
    project = _release_source(tmp_path)
    revision = _git(project, "rev-parse", "HEAD")
    run, jobs = _successful_gate_responses(revision)
    job = cast(list[dict[str, object]], jobs["jobs"])[0]
    steps = cast(list[dict[str, object]], job["steps"])
    if case == "repository":
        cast(dict[str, object], run["repository"])["full_name"] = "attacker/HawEdit"
    elif case == "fork":
        cast(dict[str, object], run["head_repository"])["full_name"] = "attacker/HawEdit"
    elif case == "run_id":
        run["id"] = GATE_RUN_ID + 1
    elif case == "workflow":
        run["path"] = ".github/workflows/noop.yml"
    elif case == "event":
        run["event"] = "workflow_dispatch"
    elif case == "branch":
        run["head_branch"] = "feature"
    elif case == "revision":
        run["head_sha"] = "0" * 40
    elif case == "run_status":
        run["status"] = "in_progress"
    elif case == "run_conclusion":
        run["conclusion"] = "failure"
    elif case == "job":
        job["name"] = "not-the-gate"
    elif case == "job_revision":
        job["head_sha"] = "0" * 40
    elif case == "job_status":
        job["status"] = "in_progress"
    elif case == "job_conclusion":
        job["conclusion"] = "failure"
    elif case == "attempt":
        job["run_attempt"] = 2
    elif case == "pagination":
        jobs["total_count"] = 2
    elif case == "missing_step":
        steps.pop()
    elif case == "failed_step":
        steps[0]["conclusion"] = "skipped"
    elif case == "duplicate_step":
        steps.append(dict(steps[0]))
    else:  # pragma: no cover - the parameter table is exhaustive
        raise AssertionError(case)
    _stub_gate_api(monkeypatch, run, jobs)

    with pytest.raises(ReleaseError, match=message):
        _verify_gate_run(revision, GATE_RUN_ID)


def test_exact_canonical_gate_evidence_is_bound_to_the_release_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _release_source(tmp_path)
    revision = _git(project, "rev-parse", "HEAD")
    run, jobs = _successful_gate_responses(revision)
    job = cast(list[dict[str, object]], jobs["jobs"])[0]
    steps = cast(list[dict[str, object]], job["steps"])
    steps.extend(
        (
            {"name": "unrelated cleanup", "status": "completed", "conclusion": "success"},
            {"name": "unrelated cleanup", "status": "completed", "conclusion": "success"},
        )
    )
    _stub_gate_api(monkeypatch, run, jobs)

    gate = _verify_gate_run(revision, GATE_RUN_ID)

    assert gate.revision == revision
    assert gate.run_id == GATE_RUN_ID
    assert gate.branch == "main"
    assert gate.job_id == GATE_JOB_ID


def test_gate_lookup_network_failure_is_a_release_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def offline(*_args: object, **_kwargs: object) -> object:
        raise URLError("offline")

    monkeypatch.setattr(release_module._GITHUB_OPENER, "open", offline)

    with pytest.raises(ReleaseError, match="could not read gate evidence"):
        _github_json(
            f"https://api.github.com/repos/HawzhinBlanca/HawEdit/actions/runs/{GATE_RUN_ID}"
        )


def test_gate_lookup_never_forwards_the_token_to_a_redirect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target_authorization: list[str | None] = []

    class Target(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            target_authorization.append(self.headers.get("Authorization"))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, _format: str, *_args: object) -> None:
            return

    target = ThreadingHTTPServer(("127.0.0.1", 0), Target)
    target_port = target.server_address[1]

    class Redirect(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{target_port}/stolen")
            self.end_headers()

        def log_message(self, _format: str, *_args: object) -> None:
            return

    source = ThreadingHTTPServer(("127.0.0.1", 0), Redirect)
    source_port = source.server_address[1]
    threads = [
        threading.Thread(target=target.serve_forever, daemon=True),
        threading.Thread(target=source.serve_forever, daemon=True),
    ]
    for thread in threads:
        thread.start()
    monkeypatch.setenv("GITHUB_TOKEN", "must-not-cross-hosts")
    try:
        with pytest.raises(ReleaseError, match="HTTP 302"):
            _github_json(f"http://127.0.0.1:{source_port}/gate")
    finally:
        source.shutdown()
        target.shutdown()
        source.server_close()
        target.server_close()
        for thread in threads:
            thread.join(timeout=2)

    assert target_authorization == []


def test_invalid_remote_gate_is_refused_before_builder_or_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _release_source(tmp_path)
    revision = _git(project, "rev-parse", "HEAD")
    run, jobs = _successful_gate_responses(revision)
    run["event"] = "workflow_dispatch"
    _stub_gate_api(monkeypatch, run, jobs)
    builder_calls = 0

    def forbidden_builder(*_args: object, **_kwargs: object) -> object:
        nonlocal builder_calls
        builder_calls += 1
        raise AssertionError("builder ran before gate refusal")

    monkeypatch.setattr(release_module, "_create_locked_builder", forbidden_builder)
    destination = tmp_path / "uncreated" / "bad-gate"

    with pytest.raises(ReleaseError, match="must be the push run"):
        build_reproducible_wheel(
            project,
            destination,
            python=Path(sys.executable),
            gate_run_id=GATE_RUN_ID,
        )

    assert builder_calls == 0
    assert not destination.parent.exists()


def test_release_builds_from_the_gated_git_object_not_live_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _release_source(tmp_path)
    revision = _git(project, "rev-parse", "HEAD")
    run, jobs = _successful_gate_responses(revision)
    _stub_gate_api(monkeypatch, run, jobs)
    live_source = project / "src" / "hawedit" / "release.py"
    committed = live_source.read_bytes()
    observed: list[tuple[Path, bytes]] = []
    builder = release_module._BuildIdentity(
        python=sys.version.split()[0],
        frontend="pip==26.2.1",
        backend="setuptools==84.0.0",
        requirements=(("pip", "26.2.1"), ("setuptools", "84.0.0")),
        lock_path="requirements/release-build.txt",
        lock_sha256="f" * 64,
    )

    def fake_builder(
        source_root: Path, _destination: Path, python: Path
    ) -> tuple[Path, release_module._BuildIdentity]:
        assert source_root != project
        return python, builder

    def fake_build_once(source_root: Path, destination: Path, _python: Path, _epoch: int) -> Path:
        if not observed:
            live_source.write_bytes(b'raise RuntimeError("tampered live tree")\n')
            (source_root / "generated-by-first-build.txt").write_text("state", encoding="utf-8")
        else:
            assert not (source_root / "generated-by-first-build.txt").exists()
        observed.append(
            (source_root, (source_root / "src" / "hawedit" / "release.py").read_bytes())
        )
        destination.mkdir(parents=True)
        wheel = destination / "hawedit_fixture-1.0.0-py3-none-any.whl"
        wheel.write_bytes(b"identical committed wheel")
        if len(observed) == 2:
            live_source.write_bytes(committed)
        return wheel

    def fake_sbom(_wheel: Path, *, revision: str, epoch: int, wheel_sha256: str) -> bytes:
        assert revision and epoch > 0 and len(wheel_sha256) == 64
        return b"{}\n"

    monkeypatch.setattr(release_module, "_create_locked_builder", fake_builder)
    monkeypatch.setattr(release_module, "_build_once", fake_build_once)
    monkeypatch.setattr(release_module, "_validate_hawedit_wheel", lambda _wheel: None)
    monkeypatch.setattr(
        release_module,
        "_assert_release_identity",
        lambda _source, _wheel: ("hawedit-fixture", "1.0.0"),
    )
    monkeypatch.setattr(release_module, "_spdx_sbom", fake_sbom)
    destination = tmp_path / "published-from-snapshot"
    try:
        artifact = build_reproducible_wheel(
            project,
            destination,
            python=Path(sys.executable),
            gate_run_id=GATE_RUN_ID,
        )
    finally:
        live_source.write_bytes(committed)

    assert len(observed) == 2
    assert all(source_root != project for source_root, _payload in observed)
    assert observed[0][0] != observed[1][0]
    assert all(payload == committed for _source_root, payload in observed)
    assert artifact.wheel.read_bytes() == b"identical committed wheel"
    assert not _git(project, "status", "--porcelain")


def test_local_wheel_uses_locked_builder_and_independent_git_snapshots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _release_source(tmp_path)
    committed = (project / "src" / "hawedit" / "release.py").read_bytes()
    sources: list[Path] = []
    builder_sources: list[Path] = []
    builder = release_module._BuildIdentity(
        python="3.12.10",
        frontend="pip==26.2.1",
        backend="setuptools==84.0.0",
        requirements=(("pip", "26.2.1"), ("setuptools", "84.0.0")),
        lock_path="requirements/release-build.txt",
        lock_sha256="a" * 64,
    )

    def fake_builder(
        source_root: Path, _destination: Path, python: Path
    ) -> tuple[Path, release_module._BuildIdentity]:
        builder_sources.append(source_root)
        return python, builder

    def fake_build(source_root: Path, destination: Path, _python: Path, _epoch: int) -> Path:
        assert (source_root / "src" / "hawedit" / "release.py").read_bytes() == committed
        if not sources:
            (source_root / "first-build-state").write_text("must not leak", encoding="utf-8")
        else:
            assert not (source_root / "first-build-state").exists()
        sources.append(source_root)
        destination.mkdir()
        wheel = destination / "hawedit_release_fixture-1.0.0-py3-none-any.whl"
        wheel.write_bytes(b"same committed candidate")
        return wheel

    monkeypatch.setattr(release_module, "_create_locked_builder", fake_builder)
    monkeypatch.setattr(release_module, "_build_once", fake_build)
    monkeypatch.setattr(release_module, "_validate_hawedit_wheel", lambda _wheel: None)
    monkeypatch.setattr(
        release_module,
        "_assert_release_identity",
        lambda _source, _wheel: ("hawedit-release-fixture", "1.0.0"),
    )
    monkeypatch.setattr(
        release_module,
        "_verify_gate_run",
        lambda *_args, **_kwargs: pytest.fail("a local candidate must not claim CI evidence"),
    )

    destination = tmp_path / "local-candidate"
    artifact = build_local_reproducible_wheel(project, destination, python=Path(sys.executable))

    assert isinstance(artifact, LocalWheelArtifact)
    assert builder_sources == [sources[0]]
    assert len(sources) == 2
    assert sources[0] != sources[1]
    assert all(source != project for source in sources)
    assert artifact.wheel.read_bytes() == b"same committed candidate"
    assert artifact.build_frontend == "pip==26.2.1"
    assert artifact.build_backend == "setuptools==84.0.0"
    assert artifact.build_lock_sha256 == "a" * 64
    assert tuple(destination.iterdir()) == (artifact.wheel,)

    with pytest.raises(ReleaseError, match="refusing to overwrite"):
        build_local_reproducible_wheel(project, destination, python=Path(sys.executable))


def test_local_wheel_refuses_dirty_source_before_builder_or_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _release_source(tmp_path)
    (project / "untracked-secret.txt").write_text("not committed", encoding="utf-8")
    destination = tmp_path / "must-not-exist" / "local"

    monkeypatch.setattr(
        release_module,
        "_build_reproducible_candidate",
        lambda *_args, **_kwargs: pytest.fail("dirty source reached the builder"),
    )

    with pytest.raises(ReleaseError, match="dirty checkout.*untracked-secret"):
        build_local_reproducible_wheel(project, destination, python=Path(sys.executable))

    assert not destination.parent.exists()


@pytest.mark.parametrize("member_kind", ("traversal", "symlink"))
def test_source_archive_extraction_refuses_escaping_or_link_members(
    tmp_path: Path, member_kind: str
) -> None:
    archive = tmp_path / "hostile.tar"
    with tarfile.open(archive, mode="w:") as output:
        if member_kind == "traversal":
            member = tarfile.TarInfo("../escaped.py")
            payload = b"escaped"
            member.size = len(payload)
            output.addfile(member, io.BytesIO(payload))
        else:
            member = tarfile.TarInfo("linked.py")
            member.type = tarfile.SYMTYPE
            member.linkname = "../escaped.py"
            output.addfile(member)
    destination = tmp_path / "source"
    destination.mkdir()

    with pytest.raises(ReleaseError, match="unsafe path|unsupported link"):
        _extract_git_archive(archive, destination, "a" * 40)

    assert not (tmp_path / "escaped.py").exists()
    assert not (destination / "linked.py").exists()


def test_release_refuses_an_unpinned_or_drifting_build_backend(tmp_path: Path) -> None:
    project = _release_source(tmp_path)
    pyproject = project / "pyproject.toml"
    original = pyproject.read_text(encoding="utf-8")

    pyproject.write_text(original.replace("setuptools==84.0.0", "setuptools>=68"), encoding="utf-8")
    with pytest.raises(ReleaseError, match="not exactly pinned"):
        _locked_build_contract(project)

    pyproject.write_text(
        original.replace("setuptools==84.0.0", "setuptools==83.0.0"), encoding="utf-8"
    )
    with pytest.raises(ReleaseError, match="release lock has setuptools==84.0.0"):
        _locked_build_contract(project)


def test_project_release_builder_is_exactly_pinned_and_officially_hashed() -> None:
    lock_path, requirements, backend = _locked_build_contract(ROOT)
    assert backend == "setuptools.build_meta"
    assert dict(requirements) == {"pip": "26.2.1", "setuptools": "84.0.0"}
    lock = lock_path.read_text(encoding="utf-8")
    assert "71138adf1f4ca900cdb7d289c21b7494329f2332b6d85f0e1c42108c0384ed3e" in lock
    assert "51a52592b3b99e102b609654876bd65f19f999935166d1352678931132b0c670" in lock


def test_release_refuses_uncommitted_or_untracked_source(tmp_path: Path) -> None:
    project = _release_source(tmp_path)
    (project / "untracked-client-change.txt").write_text("not reviewed", encoding="utf-8")

    with pytest.raises(ReleaseError, match="dirty checkout.*untracked-client-change"):
        build_reproducible_wheel(project, tmp_path / "must-not-exist", python=Path(sys.executable))

    assert not (tmp_path / "must-not-exist").exists()


def test_atomic_release_publication_preserves_the_winner(tmp_path: Path) -> None:
    staging = tmp_path / ".release.worker-two"
    output = tmp_path / "release"
    staging.mkdir()
    output.mkdir()
    (staging / "wheel.whl").write_bytes(b"second")
    (output / "wheel.whl").write_bytes(b"first")

    with pytest.raises(ReleaseError, match="refusing to overwrite"):
        _publish_directory(staging, output)

    assert (output / "wheel.whl").read_bytes() == b"first"
    assert (staging / "wheel.whl").read_bytes() == b"second"


def test_atomic_release_publication_never_replaces_a_racing_empty_winner(
    tmp_path: Path,
) -> None:
    staging = tmp_path / ".release.worker-two"
    output = tmp_path / "release"
    staging.mkdir()
    (staging / "wheel.whl").write_bytes(b"second")
    output.mkdir()
    winner_identity = output.stat().st_ino

    with pytest.raises(ReleaseError, match="another build published it"):
        _publish_directory(staging, output)

    assert output.stat().st_ino == winner_identity
    assert not tuple(output.iterdir())
    assert (staging / "wheel.whl").read_bytes() == b"second"

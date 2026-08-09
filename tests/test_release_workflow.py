"""Security contract for the GitHub-hosted release attestation workflow."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"


def _workflow() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _jobs(workflow: str) -> tuple[str, str, str]:
    build = workflow.split("  build-release:\n", 1)[1].split("\n  smoke-release:\n", 1)[0]
    smoke = workflow.split("\n  smoke-release:\n", 1)[1].split("\n  attest-release:\n", 1)[0]
    attest = workflow.split("\n  attest-release:\n", 1)[1]
    return build, smoke, attest


def _literal_paths(section: str, field: str) -> tuple[str, ...]:
    match = re.search(rf"^          {field}: \|\n((?:            .+\n)+)", section, re.MULTILINE)
    assert match is not None
    return tuple(line.strip() for line in match.group(1).splitlines())


def test_release_workflow_only_promotes_an_official_successful_main_push_gate() -> None:
    workflow = _workflow()
    build, smoke, attest = _jobs(workflow)
    assert "workflow_run:" in workflow
    assert "workflows: [gate]" in workflow
    assert "types: [completed]" in workflow
    assert "pull_request_target" not in workflow

    required_conditions = (
        "github.repository == 'HawzhinBlanca/HawEdit'",
        "github.event.workflow_run.head_repository.full_name == 'HawzhinBlanca/HawEdit'",
        "github.sha == github.event.workflow_run.head_sha",
        "github.ref == 'refs/heads/main'",
        "github.event.workflow_run.event == 'push'",
        "github.event.workflow_run.head_branch == 'main'",
        "github.event.workflow_run.conclusion == 'success'",
    )
    for condition in required_conditions:
        assert condition in build
        assert condition in attest
        assert workflow.count(condition) == 2
    assert "needs: build-release" in smoke


def test_documented_verifier_pins_the_complete_signer_policy() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    evidence = (ROOT / "evidence" / "release-attestation.md").read_text(encoding="utf-8")
    for document in (readme, evidence):
        assert "gh attestation verify" in document
        assert "--repo HawzhinBlanca/HawEdit" in document
        assert "--signer-workflow HawzhinBlanca/HawEdit/.github/workflows/release.yml" in document
        assert "--source-ref refs/heads/main" in document
        assert '--source-digest "$EXPECTED_SHA"' in document
        assert '--signer-digest "$EXPECTED_SHA"' in document
        assert "--deny-self-hosted-runners" in document


def test_release_workflow_has_only_the_permissions_needed_for_oidc_attestation() -> None:
    workflow = _workflow()
    build, smoke, attest = _jobs(workflow)
    assert "permissions: {}" in workflow.split("jobs:\n", 1)[0]
    assert "id-token: write" not in build
    assert "attestations: write" not in build
    assert "id-token: write" not in smoke
    assert "attestations: write" not in smoke
    build_permissions = build.split("    permissions:\n", 1)[1].split("    steps:\n", 1)[0]
    assert build_permissions.strip().splitlines() == [
        "contents: read",
        "      actions: read",
    ]
    assert "    permissions: {}" in smoke
    attest_permissions = attest.split("    permissions:\n", 1)[1].split("    steps:\n", 1)[0]
    assert attest_permissions.strip().splitlines() == [
        "contents: read",
        "      id-token: write",
        "      attestations: write",
    ]
    assert "contents: write" not in workflow
    assert "packages: write" not in workflow


def test_release_workflow_rebuilds_and_attests_the_exact_gated_sha() -> None:
    workflow = _workflow()
    build, smoke, attest_job = _jobs(workflow)
    checkout = "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"
    setup_python = "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97"
    download = "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c"
    attest = "actions/attest@a1948c3f048ba23858d222213b7c278aabede763"
    upload = "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a"
    for action in (checkout, setup_python, download, attest, upload):
        assert f"uses: {action}" in workflow

    assert "ref: ${{ github.event.workflow_run.head_sha }}" in workflow
    assert "persist-credentials: false" in workflow
    assert "GATE_RUN_ID: ${{ github.event.workflow_run.id }}" in workflow
    assert "PYTHONPATH=src python -m hawedit.release" in workflow
    assert '--gate-run-id "$GATE_RUN_ID"' in workflow
    assert "sha256sum --check SHA256SUMS" in workflow
    assert "name: hawedit-release-${{ github.event.workflow_run.head_sha }}" in workflow
    assert "if-no-files-found: error" in workflow
    assert "needs: [build-release, smoke-release]" in attest_job
    assert "actions/checkout" not in smoke
    assert "python -m hawedit.release" not in smoke
    assert "actions/checkout" not in attest_job
    assert "python -m hawedit.release" not in attest_job
    assert "GITHUB_TOKEN:" not in attest_job

    subject_paths = _literal_paths(attest_job, "subject-path")
    upload_paths = _literal_paths(attest_job, "path")
    assert (
        subject_paths
        == upload_paths
        == (
            "${{ runner.temp }}/hawedit-release/*.whl",
            "${{ runner.temp }}/hawedit-release/*.whl.spdx.json",
            "${{ runner.temp }}/hawedit-release/release-provenance.json",
            "${{ runner.temp }}/hawedit-release/SHA256SUMS",
        )
    )

    build_at = workflow.index("PYTHONPATH=src python -m hawedit.release")
    transport_at = build.index(f"uses: {upload}")
    download_at = attest_job.index(f"uses: {download}")
    verify_at = attest_job.index("sha256sum --check --strict SHA256SUMS")
    attest_at = workflow.index(f"uses: {attest}")
    final_upload_at = workflow.rindex(f"uses: {upload}")
    assert build_at < transport_at
    assert download_at < verify_at
    assert verify_at < attest_at < final_upload_at


def test_release_attestation_waits_for_clean_installed_wheel_smoke() -> None:
    _, smoke, attest = _jobs(_workflow())
    assert 'python-version: ["3.11", "3.12"]' in smoke
    assert "actions/checkout" not in smoke
    assert "--only-binary=:all:" in smoke
    assert '"$SMOKE_ROOT/bin/python" -m pip check' in smoke
    assert 'cd "$RUNNER_TEMP"' in smoke
    for installed_data in (
        "NotoNaskhArabic-Regular.ttf",
        "OFL.txt",
        "INSTALLED_SOURCES",
        "INSTALLED_REVISIONS",
        "INSTALLED_INTEGRITY",
    ):
        assert installed_data in smoke
    for command in (
        "hawedit",
        "hawedit-asr-bench",
        "hawedit-editorial-bench",
        "hawedit-asr-setup",
        "hawedit-credentials",
        "hawedit-release",
    ):
        assert command in smoke
    assert "needs: [build-release, smoke-release]" in attest


def test_privileged_job_independently_refuses_any_noncanonical_transport() -> None:
    _, _, attest = _jobs(_workflow())
    assert 'find "$RELEASE_DIR" -mindepth 1 -print0' in attest
    assert 'test "${#entries[@]}" -eq 4' in attest
    assert 'test ! -L "$entry"' in attest
    assert 'test "${#wheels[@]}" -eq 1' in attest
    assert 'test "${#sboms[@]}" -eq 1' in attest
    assert "grep -Ec '^[0-9a-f]{64}  [A-Za-z0-9_.+-]+$'" in attest
    assert 'test "$actual_names" = "$expected_names"' in attest
    assert "sha256sum --check --strict SHA256SUMS" in attest
    for binding in (
        ".schema == 4",
        ".revision == $revision",
        '.gate.repository == "HawzhinBlanca/HawEdit"',
        '.gate.workflow == ".github/workflows/gate.yml"',
        ".gate.run_id == $run_id",
        ".sha256 == $wheel_sha",
        ".sbom_sha256 == $sbom_sha",
    ):
        assert binding in attest


def test_release_workflow_pins_every_remote_action_to_a_full_commit() -> None:
    actions = re.findall(r"^\s*uses:\s*([^\s#]+)", _workflow(), re.MULTILINE)
    assert len(actions) == 8
    assert all(re.fullmatch(r"[^@\s]+@[0-9a-f]{40}", action) for action in actions)

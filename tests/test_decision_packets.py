"""Owner decision packets bind facts and recommendations without making the decisions."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from hawedit.decision_packets import (
    DECISION_IDS,
    DecisionPacketError,
    main,
    prepare_decision_packets,
)

ROOT = Path(__file__).parents[1]
EXPECTED_FILES = {
    "INSTRUCTIONS.txt",
    "decision-09.md",
    "decision-13.md",
    "decision-14.md",
    "decision-15.md",
    "decision-18.md",
    "decision-21.md",
    "decisions.json",
    "owner-decisions.template.json",
}


def _copy_authorities(destination: Path) -> Path:
    destination.mkdir()
    shutil.copy2(ROOT / "BLUEPRINT.md", destination / "BLUEPRINT.md")
    shutil.copy2(ROOT / "BLOCKED.md", destination / "BLOCKED.md")
    evidence = destination / "evidence"
    evidence.mkdir()
    for name in (
        "adversarial-pass-19-2026-08-10.md",
        "adversarial-pass-2026-08-09.md",
        "the-champion-adapter-would-have-shipped-the-base-models-words.md",
        "timelens-relevance-unbounded.md",
        "unlisted-modules.md",
        "vad-pause-segmentation-dead.md",
    ):
        shutil.copy2(ROOT / "evidence" / name, evidence / name)
    return destination


def test_packets_bind_reviewed_authorities_and_leave_every_owner_choice_unset(
    tmp_path: Path,
) -> None:
    prepared = prepare_decision_packets(ROOT, tmp_path / "packets")

    assert {path.name for path in prepared.directory.iterdir()} == EXPECTED_FILES
    manifest_bytes = prepared.manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    template = json.loads(prepared.owner_template_path.read_text(encoding="utf-8"))
    assert manifest["schema"] == 1
    assert manifest["blueprint"] == {
        "path": "BLUEPRINT.md",
        "sha256": hashlib.sha256((ROOT / "BLUEPRINT.md").read_bytes()).hexdigest(),
    }
    assert [packet["blocker_id"] for packet in manifest["packets"]] == list(DECISION_IDS)
    assert template["packet_manifest_sha256"] == hashlib.sha256(manifest_bytes).hexdigest()
    assert template["decided_at_utc"] is None
    assert template["decided_by"] is None
    assert [entry["blocker_id"] for entry in template["decisions"]] == list(DECISION_IDS)
    assert all(entry["selected_option"] is None for entry in template["decisions"])
    assert all(entry["rationale"] is None for entry in template["decisions"])

    template_by_id = {entry["blocker_id"]: entry for entry in template["decisions"]}
    for packet in manifest["packets"]:
        options = {option["id"] for option in packet["options"]}
        template_entry = template_by_id[packet["blocker_id"]]
        assert len(options) >= 2
        assert packet["recommended_option"] in options
        assert set(template_entry["allowed_options"]) == options
        assert template_entry["recommended_option"] == packet["recommended_option"]
        assert packet["recommendation_basis"]
        assert packet["question"]
        assert packet["current_behavior"]
        assert packet["blocker_section_sha256"]
        assert packet["governing_refs"]
        assert packet["evidence"]
        page = (prepared.directory / f"decision-{packet['blocker_id']:02d}.md").read_text(
            encoding="utf-8"
        )
        assert "OWNER DECISION: **UNSET**" in page
        assert f"Recommended: `{packet['recommended_option']}`" in page
        assert all(f"`{option_id}`" in page for option_id in options)


def test_packet_bytes_are_deterministic_and_publication_never_overwrites(tmp_path: Path) -> None:
    first = prepare_decision_packets(ROOT, tmp_path / "first")
    second = prepare_decision_packets(ROOT, tmp_path / "second")

    assert {path.name: path.read_bytes() for path in first.directory.iterdir()} == {
        path.name: path.read_bytes() for path in second.directory.iterdir()
    }

    sentinel = first.directory / "operator-owned.txt"
    sentinel.write_text("do not replace", encoding="utf-8")
    with pytest.raises(DecisionPacketError, match="already exists"):
        prepare_decision_packets(ROOT, first.directory)
    assert sentinel.read_text(encoding="utf-8") == "do not replace"


@pytest.mark.parametrize(
    ("relative", "message"),
    [
        ("BLUEPRINT.md", "reviewed blueprint digest"),
        ("BLOCKED.md", "reviewed blocker section"),
        ("evidence/vad-pause-segmentation-dead.md", "reviewed evidence digest"),
    ],
)
def test_changed_authority_bytes_are_refused(tmp_path: Path, relative: str, message: str) -> None:
    project = _copy_authorities(tmp_path / "project")
    target = project / relative
    if relative == "BLOCKED.md":
        text = target.read_text(encoding="utf-8")
        target.write_text(
            text.replace(
                "The containment test is clearly wrong",
                "The reviewed containment claim changed",
                1,
            ),
            encoding="utf-8",
        )
    else:
        target.write_bytes(target.read_bytes() + b"\nchanged after review\n")

    with pytest.raises(DecisionPacketError, match=message):
        prepare_decision_packets(project, tmp_path / "packets")


def test_linked_authority_is_refused_even_when_its_bytes_match(tmp_path: Path) -> None:
    project = _copy_authorities(tmp_path / "project")
    target = project / "evidence" / "timelens-relevance-unbounded.md"
    original = tmp_path / "external-evidence.md"
    target.replace(original)
    target.hardlink_to(original)

    with pytest.raises(DecisionPacketError, match="hardlink"):
        prepare_decision_packets(project, tmp_path / "packets")


def test_packet_pages_never_serialize_a_hidden_owner_decision(tmp_path: Path) -> None:
    prepared = prepare_decision_packets(ROOT, tmp_path / "packets")
    pages = b"".join(path.read_bytes() for path in prepared.directory.glob("decision-*.md"))

    assert pages.count(b"OWNER DECISION: **UNSET**") == len(DECISION_IDS)
    assert b"OWNER DECISION: **APPROVED**" not in pages
    assert b"decided_by" not in pages


def test_cli_publishes_one_machine_readable_unset_packet(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "owner-packet"

    assert main(["prepare", "--project-root", str(ROOT), "--output-dir", str(output)]) == 0

    captured = capsys.readouterr()
    document = json.loads(captured.out)
    assert captured.err == ""
    assert document == {
        "directory": str(output.resolve()),
        "manifest": str((output / "decisions.json").resolve()),
        "owner_template": str((output / "owner-decisions.template.json").resolve()),
        "status": "prepared-all-owner-decisions-unset",
    }


def test_cli_refuses_authority_drift_without_machine_readable_success(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = _copy_authorities(tmp_path / "project")
    blueprint = project / "BLUEPRINT.md"
    blueprint.write_bytes(blueprint.read_bytes() + b"\nchanged\n")

    assert (
        main(
            [
                "prepare",
                "--project-root",
                str(project),
                "--output-dir",
                str(tmp_path / "owner-packet"),
            ]
        )
        == 2
    )

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("REFUSED: reviewed blueprint digest changed")

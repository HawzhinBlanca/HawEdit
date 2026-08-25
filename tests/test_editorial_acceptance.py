"""The autonomous AC-8 packet is blinded, signed, split, and content-bound."""

from __future__ import annotations

import json
import os
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

import hawedit.editorial_acceptance as acceptance_module
from hawedit.clip import DiscoveryPath
from hawedit.corpus import Dialect
from hawedit.editorial_acceptance import (
    SIGNATURE_NAMESPACE,
    EditorialAcceptanceError,
    PreparedEditorialStudy,
    VerifiedEditorialStudy,
    evaluate_editorial_study,
    main,
    prepare_editorial_study,
)
from hawedit.judge import JUDGE_SHADOW, KURDISH_EDITORIAL_JUDGE, JudgeVerdict

FIXTURE = Path(__file__).parent / "fixtures" / "kurdish-speech-3cuts.mp4"


def _verdict(index: int, judge: str, *, suffix: str) -> JudgeVerdict:
    return JudgeVerdict(
        candidate_id=f"candidate-{index}",
        hook_score=0.8,
        self_contained=True,
        payoff_at_ms=700,
        meaning_fidelity=0.9,
        misleading_edit_risk=0.1,
        cultural_landing=0.8,
        narrative_role="payoff",
        title_ckb=f"ناونیشانی کوردی {suffix}",
        description_ckb=f"وەسفی کوردی بۆ هەڵسەنگاندن {suffix}",
        hashtags_ckb=(f"کوردی{suffix}",),
        judge=judge,
        clip_in_ms=100,
        clip_out_ms=1100,
    )


def _inventory(tmp_path: Path, *, count: int = 210) -> tuple[Path, Path, dict[str, Any]]:
    media_root = tmp_path / "media"
    media_root.mkdir()
    dialects = tuple(Dialect)
    paths = tuple(DiscoveryPath)
    source_bytes = FIXTURE.read_bytes()
    media_paths = tuple(f"candidate-{index}.mp4" for index in range(4))
    for index, relative in enumerate(media_paths):
        (media_root / relative).write_bytes(source_bytes + f"\nfixture-{index}\n".encode())
    items: list[dict[str, object]] = []
    for index in range(count):
        source_index = index // 60
        source_rank = index % 60
        relative = media_paths[source_index]
        items.append(
            {
                "dialect": dialects[index % len(dialects)].value,
                "discovery_path": paths[source_rank % len(paths)].value,
                "incumbent": _verdict(
                    index, KURDISH_EDITORIAL_JUDGE, suffix=f"کۆن{index}"
                ).to_dict(),
                "item_id": f"source-item-{index:03d}",
                "media_duration_ms": 4_162,
                "media_id": f"media-{source_index}",
                "media_path": relative,
                "rank": source_rank // len(paths) + 1,
                "shadow": _verdict(index, JUDGE_SHADOW, suffix=f"نوێ{index}").to_dict(),
            }
        )
    document: dict[str, Any] = {
        "authorized_by": "coordinator@example.test",
        "interim": False,
        "items": items,
        "media_authorization": "client-approved internal editorial evaluation",
        "schema": 1,
        "source_duration_s": 16.648,
        "study_id": "sorani-editorial-2026-08",
        "systems": {
            "incumbent": {
                "total_cost_usd": 16.648 / 3_600,
                "total_wallclock_s": 8.324,
            },
            "shadow": {"total_cost_usd": 3.0, "total_wallclock_s": 4_000.0},
        },
    }
    path = tmp_path / "inventory.json"
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path, media_root, document


def _prepare(tmp_path: Path) -> PreparedEditorialStudy:
    inventory, media_root, _ = _inventory(tmp_path)
    return prepare_editorial_study(
        inventory_path=inventory,
        media_root=media_root,
        output_dir=tmp_path / "study",
        sample_size=200,
    )


def _key(tmp_path: Path, identity: str) -> Path:
    key = tmp_path / identity.replace("@", "-")
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)],
        check=True,
        capture_output=True,
    )
    return key


def _sign(path: Path, key: Path) -> Path:
    subprocess.run(
        [
            "ssh-keygen",
            "-Y",
            "sign",
            "-f",
            str(key),
            "-n",
            SIGNATURE_NAMESPACE,
            str(path),
        ],
        check=True,
        capture_output=True,
    )
    return Path(f"{path}.sig")


def _write_json(path: Path, document: object) -> Path:
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _fill_label(label: dict[str, object], index: int) -> None:
    winner = index % 2 == 0
    label.update(
        {
            "gold_in_ms": 100 if winner else None,
            "gold_out_ms": 1100 if winner else None,
            "is_winner": winner,
            "misleading": index % 11 == 0,
            "preference": ("a", "b", "tie")[index % 3],
            "sentence_complete": index % 17 != 0,
        }
    )


def _signed_human_inputs(
    tmp_path: Path, prepared: PreparedEditorialStudy, *, disagree: bool = True
) -> dict[str, Path]:
    identities = (
        "coordinator@example.test",
        "reviewer-a@example.test",
        "reviewer-b@example.test",
        "adjudicator@example.test",
    )
    keys = {identity: _key(tmp_path, identity) for identity in identities}
    allowed = tmp_path / "allowed_signers"
    allowed.write_text(
        "".join(
            f'{identity} namespaces="{SIGNATURE_NAMESPACE}" '
            f"{Path(f'{key}.pub').read_text(encoding='utf-8').strip()}\n"
            for identity, key in keys.items()
        ),
        encoding="utf-8",
    )

    approval = json.loads(prepared.coordinator_approval_template_path.read_text(encoding="utf-8"))
    approval.update(
        {
            "approved_at_utc": "2026-08-17T02:00:00Z",
            "approved_by": identities[0],
            "media_rights_attested": True,
        }
    )
    approval_path = _write_json(tmp_path / "approval.json", approval)

    template = json.loads(prepared.reviewer_template_path.read_text(encoding="utf-8"))
    review_one = deepcopy(template)
    review_one.update({"completed_at_utc": "2026-08-17T03:00:00Z", "reviewer_id": identities[1]})
    for index, label in enumerate(review_one["labels"]):
        _fill_label(label, index)
    review_two = deepcopy(review_one)
    review_two.update({"completed_at_utc": "2026-08-17T04:00:00Z", "reviewer_id": identities[2]})
    if disagree:
        review_two["labels"][0]["preference"] = "b"
    review_one_path = _write_json(tmp_path / "review-one.json", review_one)
    review_two_path = _write_json(tmp_path / "review-two.json", review_two)

    adjudication = json.loads(prepared.adjudication_template_path.read_text(encoding="utf-8"))
    adjudication.update(
        {
            "adjudicator_id": identities[3],
            "completed_at_utc": "2026-08-17T05:00:00Z",
        }
    )
    if disagree:
        resolution = deepcopy(review_one["labels"][0])
        resolution["reason"] = "reviewers disagreed; adjudicator replayed the complete clip"
        adjudication["resolutions"] = [resolution]
    adjudication_path = _write_json(tmp_path / "adjudication.json", adjudication)
    return {
        "adjudication": adjudication_path,
        "adjudication_signature": _sign(adjudication_path, keys[identities[3]]),
        "allowed_signers": allowed,
        "approval": approval_path,
        "approval_signature": _sign(approval_path, keys[identities[0]]),
        "reviewer_one": review_one_path,
        "reviewer_one_signature": _sign(review_one_path, keys[identities[1]]),
        "reviewer_two": review_two_path,
        "reviewer_two_signature": _sign(review_two_path, keys[identities[2]]),
    }


def _evaluate(
    tmp_path: Path,
    prepared: PreparedEditorialStudy,
    human: dict[str, Path],
    *,
    output_name: str = "result",
) -> VerifiedEditorialStudy:
    return evaluate_editorial_study(
        inventory_path=tmp_path / "inventory.json",
        manifest_path=prepared.manifest_path,
        review_packet_path=prepared.review_packet_path,
        media_root=tmp_path / "media",
        approval_path=human["approval"],
        approval_signature_path=human["approval_signature"],
        reviewer_one_path=human["reviewer_one"],
        reviewer_one_signature_path=human["reviewer_one_signature"],
        reviewer_two_path=human["reviewer_two"],
        reviewer_two_signature_path=human["reviewer_two_signature"],
        adjudication_path=human["adjudication"],
        adjudication_signature_path=human["adjudication_signature"],
        allowed_signers_path=human["allowed_signers"],
        output_dir=tmp_path / output_name,
    )


def test_prepare_is_deterministic_stratified_blinded_and_holdout_frozen(tmp_path: Path) -> None:
    inventory, media_root, _ = _inventory(tmp_path)
    first = prepare_editorial_study(
        inventory_path=inventory,
        media_root=media_root,
        output_dir=tmp_path / "study-one",
        sample_size=200,
    )
    second = prepare_editorial_study(
        inventory_path=inventory,
        media_root=media_root,
        output_dir=tmp_path / "study-two",
        sample_size=200,
    )

    assert first.manifest_path.read_bytes() == second.manifest_path.read_bytes()
    assert first.review_packet_path.read_bytes() == second.review_packet_path.read_bytes()
    manifest = json.loads(first.manifest_path.read_text(encoding="utf-8"))
    counts = {dialect.value: 0 for dialect in Dialect}
    holdout = {dialect.value: 0 for dialect in Dialect}
    for item in manifest["items"]:
        dialect = item["source"]["dialect"]
        counts[dialect] += 1
        holdout[dialect] += item["split"] == "holdout"
    assert sorted(counts.values()) == [66, 67, 67]
    assert holdout == {dialect.value: 13 for dialect in Dialect}
    assert {item["option_a"] for item in manifest["items"]} == {"incumbent", "shadow"}


def test_reviewer_packet_contains_no_answer_key_model_or_split(tmp_path: Path) -> None:
    prepared = _prepare(tmp_path)
    payload = prepared.review_packet_path.read_text(encoding="utf-8")

    assert KURDISH_EDITORIAL_JUDGE not in payload
    assert JUDGE_SHADOW not in payload
    assert '"split"' not in payload
    assert '"discovery_path"' not in payload
    assert '"source-item-' not in payload
    assert '"review-' in payload


def test_prepare_cli_prints_only_machine_readable_status_and_unset_templates(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    inventory, media_root, _ = _inventory(tmp_path)

    result = main(
        [
            "prepare",
            str(inventory),
            "--media-root",
            str(media_root),
            "--output-dir",
            str(tmp_path / "study"),
            "--sample-size",
            "200",
        ]
    )

    captured = capsys.readouterr()
    assert result == 0
    assert captured.err == ""
    assert json.loads(captured.out)["status"] == "prepared-not-reviewed"
    reviewer = json.loads((tmp_path / "study" / "reviewer.template.json").read_text())
    assert reviewer["reviewer_id"] == ""
    assert reviewer["labels"][0]["preference"] is None


@pytest.mark.parametrize("sample_size", [199, 501, True, 200.0])
def test_sample_size_is_exact_and_within_the_human_study_range(
    tmp_path: Path, sample_size: object
) -> None:
    inventory, media_root, _ = _inventory(tmp_path)
    with pytest.raises(EditorialAcceptanceError, match="sample_size"):
        prepare_editorial_study(
            inventory_path=inventory,
            media_root=media_root,
            output_dir=tmp_path / "study",
            sample_size=sample_size,  # type: ignore[arg-type]
        )


def test_interim_inventory_and_schema_coercion_are_refused(tmp_path: Path) -> None:
    inventory, media_root, document = _inventory(tmp_path)
    document["interim"] = True
    _write_json(inventory, document)
    with pytest.raises(EditorialAcceptanceError, match="interim"):
        prepare_editorial_study(
            inventory_path=inventory,
            media_root=media_root,
            output_dir=tmp_path / "study",
            sample_size=200,
        )


def test_real_video_duration_and_source_economics_denominator_are_verified(
    tmp_path: Path,
) -> None:
    inventory, media_root, document = _inventory(tmp_path)
    document["source_duration_s"] = 7_200.0
    _write_json(inventory, document)
    with pytest.raises(EditorialAcceptanceError, match="unique media ids"):
        prepare_editorial_study(
            inventory_path=inventory,
            media_root=media_root,
            output_dir=tmp_path / "study",
            sample_size=200,
        )

    document["source_duration_s"] = 16.644
    for item in document["items"]:
        item["media_duration_ms"] = 4_161
    _write_json(inventory, document)
    with pytest.raises(EditorialAcceptanceError, match="duration is 4162 ms"):
        prepare_editorial_study(
            inventory_path=inventory,
            media_root=media_root,
            output_dir=tmp_path / "study",
            sample_size=200,
        )

    for item in document["items"]:
        item["media_duration_ms"] = 4_162
    document["source_duration_s"] = 16.648
    _write_json(inventory, document)
    (media_root / "candidate-0.mp4").write_bytes(b"not a video")
    with pytest.raises(EditorialAcceptanceError, match="not probeable video"):
        prepare_editorial_study(
            inventory_path=inventory,
            media_root=media_root,
            output_dir=tmp_path / "study",
            sample_size=200,
        )
    document["interim"] = False
    document["items"][0]["rank"] = True
    _write_json(inventory, document)
    with pytest.raises(EditorialAcceptanceError, match="rank"):
        prepare_editorial_study(
            inventory_path=inventory,
            media_root=media_root,
            output_dir=tmp_path / "study",
            sample_size=200,
        )


def test_linked_or_changed_media_is_refused(tmp_path: Path) -> None:
    inventory, media_root, _ = _inventory(tmp_path)
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"outside")
    first = media_root / "candidate-0.mp4"
    first.unlink()
    try:
        os.symlink(outside, first)
    except OSError:
        os.link(outside, first)
    with pytest.raises(EditorialAcceptanceError, match="link|hardlinked"):
        prepare_editorial_study(
            inventory_path=inventory,
            media_root=media_root,
            output_dir=tmp_path / "study",
            sample_size=200,
        )


def test_prepare_never_exposes_a_partial_or_overwrites_a_competing_kit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inventory, media_root, _ = _inventory(tmp_path)
    destination = tmp_path / "study"

    def competing_publish(source: Path, target: Path) -> None:
        assert sorted(path.name for path in source.iterdir()) == sorted(
            acceptance_module._PREPARED_FILES
        )
        target.mkdir()
        (target / "winner").write_text("kept", encoding="utf-8")
        raise FileExistsError(target)

    monkeypatch.setattr(acceptance_module, "rename_directory_noreplace", competing_publish)
    with pytest.raises(EditorialAcceptanceError, match="another publisher won"):
        prepare_editorial_study(
            inventory_path=inventory,
            media_root=media_root,
            output_dir=destination,
            sample_size=200,
        )
    assert (destination / "winner").read_text(encoding="utf-8") == "kept"
    assert tuple(tmp_path.glob(".study.*.staging")) == ()


def test_signed_reviews_adjudication_and_all_metrics_publish_in_separate_slices(
    tmp_path: Path,
) -> None:
    prepared = _prepare(tmp_path)
    human = _signed_human_inputs(tmp_path, prepared)

    verified = _evaluate(tmp_path, prepared, human)

    report = json.loads(verified.report_path.read_text(encoding="utf-8"))
    assert report["training"]["total_items"] == 161
    assert report["holdout"]["total_items"] == 39
    assert report["adjudication"]["disagreement_count"] == 1
    assert len(report["adjudication"]["resolutions"]) == 1
    resolution = report["adjudication"]["resolutions"][0]
    assert resolution["reason"] == "reviewers disagreed; adjudicator replayed the complete clip"
    assert resolution["reviewer_one_label"] != resolution["reviewer_two_label"]
    assert resolution["adjudicated_label"] == resolution["reviewer_one_label"]
    assert report["reviewers"] == [
        "reviewer-a@example.test",
        "reviewer-b@example.test",
    ]
    for split in ("training", "holdout"):
        metrics = report[split]
        assert set(metrics["recall_at_20_by_path"]) == {path.value for path in DiscoveryPath}
        assert "path_unique_wins" in metrics
        assert "mean_temporal_iou" in metrics
        assert "misleading_edit_rate" in metrics
        assert "sentence_completeness_rate" in metrics
        assert "pairwise_preference" in metrics
        assert "decision" in metrics
    assert report["economics"]["incumbent"]["cost_per_source_hour"] == pytest.approx(1.0)
    assert report["economics"]["incumbent"]["wallclock_seconds_per_source_hour"] == pytest.approx(
        1800.0
    )
    assert all(len(value) == 64 for value in report["evidence"].values())
    assert len(set(report["signing_keys"].values())) == 4
    assert all(value.startswith("SHA256:") for value in report["signing_keys"].values())
    training = json.loads(verified.training_labels_path.read_text(encoding="utf-8"))
    holdout = json.loads(verified.holdout_labels_path.read_text(encoding="utf-8"))
    training_ids = {item["label"]["review_id"] for item in training["items"]}
    holdout_ids = {item["label"]["review_id"] for item in holdout["items"]}
    assert len(training_ids) == 161
    assert len(holdout_ids) == 39
    assert training_ids.isdisjoint(holdout_ids)


def test_media_mutation_after_study_freeze_is_refused_before_human_evidence(
    tmp_path: Path,
) -> None:
    prepared = _prepare(tmp_path)
    human = _signed_human_inputs(tmp_path, prepared)
    manifest = json.loads(prepared.manifest_path.read_text(encoding="utf-8"))
    selected_media = tmp_path / "media" / manifest["items"][0]["source"]["media_path"]
    selected_media.write_bytes(b"changed after freeze")

    with pytest.raises(EditorialAcceptanceError, match="not probeable video|media changed"):
        _evaluate(tmp_path, prepared, human)
    assert not (tmp_path / "result").exists()


def test_tampered_signed_review_is_refused(tmp_path: Path) -> None:
    prepared = _prepare(tmp_path)
    human = _signed_human_inputs(tmp_path, prepared)
    review = json.loads(human["reviewer_one"].read_text(encoding="utf-8"))
    review["labels"][0]["preference"] = "tie"
    _write_json(human["reviewer_one"], review)

    with pytest.raises(EditorialAcceptanceError, match="signature verification failed"):
        _evaluate(tmp_path, prepared, human)


def test_evaluation_reopens_the_exact_inventory_used_for_sampling(tmp_path: Path) -> None:
    prepared = _prepare(tmp_path)
    human = _signed_human_inputs(tmp_path, prepared, disagree=False)
    inventory = tmp_path / "inventory.json"
    document = json.loads(inventory.read_text(encoding="utf-8"))
    document["systems"]["incumbent"]["total_cost_usd"] = 2.5
    _write_json(inventory, document)

    with pytest.raises(EditorialAcceptanceError, match="inventory changed"):
        _evaluate(tmp_path, prepared, human)


def test_evaluation_recomputes_sample_order_and_blinding_from_inventory(tmp_path: Path) -> None:
    prepared = _prepare(tmp_path)
    manifest = json.loads(prepared.manifest_path.read_text(encoding="utf-8"))
    manifest["items"].reverse()
    tampered = _write_json(tmp_path / "reordered-manifest.json", manifest)
    human = _signed_human_inputs(tmp_path, prepared, disagree=False)

    with pytest.raises(EditorialAcceptanceError, match="deterministic sampler"):
        evaluate_editorial_study(
            inventory_path=tmp_path / "inventory.json",
            manifest_path=tampered,
            review_packet_path=prepared.review_packet_path,
            media_root=tmp_path / "media",
            approval_path=human["approval"],
            approval_signature_path=human["approval_signature"],
            reviewer_one_path=human["reviewer_one"],
            reviewer_one_signature_path=human["reviewer_one_signature"],
            reviewer_two_path=human["reviewer_two"],
            reviewer_two_signature_path=human["reviewer_two_signature"],
            adjudication_path=human["adjudication"],
            adjudication_signature_path=human["adjudication_signature"],
            allowed_signers_path=human["allowed_signers"],
            output_dir=tmp_path / "result",
        )


def test_adjudicator_must_resolve_exactly_the_disagreements(tmp_path: Path) -> None:
    prepared = _prepare(tmp_path)
    human = _signed_human_inputs(tmp_path, prepared)
    adjudication = json.loads(human["adjudication"].read_text(encoding="utf-8"))
    adjudication["resolutions"] = []
    _write_json(human["adjudication"], adjudication)
    human["adjudication_signature"] = _sign(
        human["adjudication"], tmp_path / "adjudicator-example.test"
    )

    with pytest.raises(EditorialAcceptanceError, match="exactly the reviewer disagreements"):
        _evaluate(tmp_path, prepared, human)


def test_two_files_signed_by_one_reviewer_are_not_independent(tmp_path: Path) -> None:
    prepared = _prepare(tmp_path)
    human = _signed_human_inputs(tmp_path, prepared, disagree=False)
    human["reviewer_two"] = human["reviewer_one"]
    human["reviewer_two_signature"] = human["reviewer_one_signature"]

    with pytest.raises(EditorialAcceptanceError, match="same identity"):
        _evaluate(tmp_path, prepared, human)


def test_distinct_role_names_backed_by_one_key_are_not_independent(tmp_path: Path) -> None:
    prepared = _prepare(tmp_path)
    human = _signed_human_inputs(tmp_path, prepared, disagree=False)
    shared_key = tmp_path / "reviewer-a-example.test"
    lines = human["allowed_signers"].read_text(encoding="utf-8").splitlines()
    shared_public = Path(f"{shared_key}.pub").read_text(encoding="utf-8").strip()
    lines = [
        (
            f'reviewer-b@example.test namespaces="{SIGNATURE_NAMESPACE}" {shared_public}'
            if line.startswith("reviewer-b@example.test ")
            else line
        )
        for line in lines
    ]
    human["allowed_signers"].write_text("\n".join(lines) + "\n", encoding="utf-8")
    human["reviewer_two_signature"].unlink()
    human["reviewer_two_signature"] = _sign(human["reviewer_two"], shared_key)

    with pytest.raises(EditorialAcceptanceError, match="four distinct signing keys"):
        _evaluate(tmp_path, prepared, human)


def test_coordinator_cannot_also_be_an_independent_reviewer(tmp_path: Path) -> None:
    prepared = _prepare(tmp_path)
    human = _signed_human_inputs(tmp_path, prepared, disagree=False)
    review = json.loads(human["reviewer_one"].read_text(encoding="utf-8"))
    review["reviewer_id"] = "coordinator@example.test"
    _write_json(human["reviewer_one"], review)
    human["reviewer_one_signature"].unlink()
    human["reviewer_one_signature"] = _sign(
        human["reviewer_one"], tmp_path / "coordinator-example.test"
    )

    with pytest.raises(EditorialAcceptanceError, match="coordinator must be distinct"):
        _evaluate(tmp_path, prepared, human)


@pytest.mark.parametrize(
    ("document", "field", "timestamp", "message"),
    [
        (
            "approval",
            "approved_at_utc",
            "2026-08-17T04:30:00Z",
            "approval must not postdate",
        ),
        (
            "adjudication",
            "completed_at_utc",
            "2026-08-17T03:30:00Z",
            "adjudication must not predate",
        ),
    ],
)
def test_human_evidence_chronology_is_enforced(
    tmp_path: Path, document: str, field: str, timestamp: str, message: str
) -> None:
    prepared = _prepare(tmp_path)
    human = _signed_human_inputs(tmp_path, prepared, disagree=False)
    path = human[document]
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload[field] = timestamp
    _write_json(path, payload)
    signature_name = f"{document}_signature"
    human[signature_name].unlink()
    key_name = "coordinator-example.test" if document == "approval" else "adjudicator-example.test"
    human[signature_name] = _sign(path, tmp_path / key_name)

    with pytest.raises(EditorialAcceptanceError, match=message):
        _evaluate(tmp_path, prepared, human)


def test_allowed_signers_is_snapshotted_once_for_all_four_verifications(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepared = _prepare(tmp_path)
    human = _signed_human_inputs(tmp_path, prepared, disagree=False)
    original = acceptance_module._read_bound_file
    calls = 0

    def counted(path: Path, label: str, *, maximum: int | None) -> bytes:
        nonlocal calls
        if label == "editorial allowed signers":
            calls += 1
        return original(path, label, maximum=maximum)

    monkeypatch.setattr(acceptance_module, "_read_bound_file", counted)
    _evaluate(tmp_path, prepared, human)

    assert calls == 1


def test_evaluate_cli_is_machine_readable_and_results_are_write_once(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prepared = _prepare(tmp_path)
    human = _signed_human_inputs(tmp_path, prepared, disagree=False)
    output = tmp_path / "result"
    args = [
        "evaluate",
        str(prepared.manifest_path),
        str(prepared.review_packet_path),
        "--inventory",
        str(tmp_path / "inventory.json"),
        "--media-root",
        str(tmp_path / "media"),
        "--approval",
        str(human["approval"]),
        "--approval-signature",
        str(human["approval_signature"]),
        "--reviewer-one",
        str(human["reviewer_one"]),
        "--reviewer-one-signature",
        str(human["reviewer_one_signature"]),
        "--reviewer-two",
        str(human["reviewer_two"]),
        "--reviewer-two-signature",
        str(human["reviewer_two_signature"]),
        "--adjudication",
        str(human["adjudication"]),
        "--adjudication-signature",
        str(human["adjudication_signature"]),
        "--allowed-signers",
        str(human["allowed_signers"]),
        "--output-dir",
        str(output),
    ]

    assert main(args) == 0
    first = capsys.readouterr()
    assert first.err == ""
    assert json.loads(first.out)["status"] == "signed-reviewed-and-split"
    report_before = (output / "study-report.json").read_bytes()

    assert main(args) == 2
    second = capsys.readouterr()
    assert second.out == ""
    assert "refusing to overwrite" in second.err
    assert (output / "study-report.json").read_bytes() == report_before


def test_manifest_split_count_tamper_is_refused_even_before_signatures(tmp_path: Path) -> None:
    prepared = _prepare(tmp_path)
    manifest = json.loads(prepared.manifest_path.read_text(encoding="utf-8"))
    holdout = next(item for item in manifest["items"] if item["split"] == "holdout")
    holdout["split"] = "training"
    tampered = _write_json(tmp_path / "tampered-manifest.json", manifest)
    raw, _ = acceptance_module._load_json(tampered, "tampered manifest")

    with pytest.raises(EditorialAcceptanceError, match="holdout count drifted"):
        acceptance_module._parse_study(raw)


def test_review_must_cover_the_exact_sample_and_never_accept_null_templates(
    tmp_path: Path,
) -> None:
    prepared = _prepare(tmp_path)
    human = _signed_human_inputs(tmp_path, prepared)
    review = json.loads(human["reviewer_one"].read_text(encoding="utf-8"))
    review["labels"].pop()
    _write_json(human["reviewer_one"], review)
    human["reviewer_one_signature"] = _sign(
        human["reviewer_one"], tmp_path / "reviewer-a-example.test"
    )

    with pytest.raises(EditorialAcceptanceError, match="exact sampled item set"):
        _evaluate(tmp_path, prepared, human)

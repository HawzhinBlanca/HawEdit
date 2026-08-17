"""AC-7's content-bound, human-approved Sorani benchmark handoff."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

import hawedit.corpus_acceptance as acceptance_module
from hawedit.corpus import Condition, Corpus, CorpusItem, Dialect, Provenance
from hawedit.corpus_acceptance import (
    SIGNATURE_NAMESPACE,
    CorpusAcceptanceError,
    CorpusRights,
    PreparedCorpusAcceptance,
    main,
    prepare_corpus_acceptance,
    verify_corpus_acceptance,
)


def _corpus(tmp_path: Path) -> tuple[Path, Path, Corpus]:
    audio_root = tmp_path / "audio"
    audio_root.mkdir()
    items: list[CorpusItem] = []
    counter = 0
    for dialect in Dialect:
        for condition in Condition:
            counter += 1
            item_id = f"{dialect.value}-{condition.value}"
            relative = f"{dialect.value}/{condition.value}.wav"
            audio = audio_root / relative
            audio.parent.mkdir(parents=True, exist_ok=True)
            audio.write_bytes(f"RIFF-{counter}-{item_id}".encode())
            items.append(
                CorpusItem(
                    item_id=item_id,
                    audio_path=relative,
                    reference_ckb=f"ئەمە دەقی مرۆڤی ژمارە {counter} ـە",
                    dialect=dialect,
                    conditions=frozenset({condition}),
                    duration_s=600.0,
                    named_entities=("هەولێر",) if condition is Condition.NAMED_ENTITIES else (),
                    code_switch_spans=("HawEdit",)
                    if condition
                    in {
                        Condition.CODE_SWITCH_EN,
                        Condition.CODE_SWITCH_AR,
                    }
                    else (),
                    speaker_count=2 if condition is Condition.OVERLAPPING_SPEAKERS else 1,
                )
            )
    corpus = Corpus(
        tuple(items),
        provenance=Provenance(
            name="Hawa authorised Sorani acceptance set",
            licence="private-evaluation-only",
        ),
    )
    manifest = tmp_path / "corpus.json"
    manifest.write_text(corpus.to_json() + "\n", encoding="utf-8")
    return manifest, audio_root, corpus


def _rights() -> CorpusRights:
    return CorpusRights(
        dataset_owner="Hawa Media",
        authorized_by="hawa@example.test",
        licence="private-evaluation-only",
        consent_basis="recorded speaker consent for ASR quality evaluation",
        permitted_use="HawEdit internal model evaluation and acceptance",
        redistribution_allowed=False,
    )


def _approve_and_sign(
    tmp_path: Path, prepared: PreparedCorpusAcceptance
) -> tuple[Path, Path, Path]:
    approval_template = prepared.approval_template_path
    approval = json.loads(approval_template.read_text(encoding="utf-8"))
    approval.update(
        {
            "approved_by": "hawa@example.test",
            "approved_at_utc": "2026-08-17T04:00:00Z",
            "rights_attested": True,
        }
    )
    approval_path = tmp_path / "approval.json"
    approval_path.write_text(
        json.dumps(approval, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    key = tmp_path / "approval-key"
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "ssh-keygen",
            "-Y",
            "sign",
            "-f",
            str(key),
            "-n",
            SIGNATURE_NAMESPACE,
            str(approval_path),
        ],
        check=True,
        capture_output=True,
    )
    signature = Path(f"{approval_path}.sig")
    public = Path(f"{key}.pub").read_text(encoding="utf-8").strip()
    allowed_signers = tmp_path / "allowed_signers"
    allowed_signers.write_text(
        f'hawa@example.test namespaces="{SIGNATURE_NAMESPACE}" {public}\n',
        encoding="utf-8",
    )
    return approval_path, signature, allowed_signers


def test_prepared_manifest_binds_every_audio_reference_and_corpus_byte(tmp_path: Path) -> None:
    corpus_path, audio_root, corpus = _corpus(tmp_path)
    prepared = prepare_corpus_acceptance(
        corpus_path=corpus_path,
        audio_root=audio_root,
        output_dir=tmp_path / "kit",
        rights=_rights(),
    )

    document = json.loads(prepared.manifest_path.read_text(encoding="utf-8"))
    assert document["schema"] == 1
    assert len(document["items"]) == len(corpus.items) == 21
    assert document["rights"]["authorized_by"] == "hawa@example.test"
    assert document["corpus_sha256"]
    assert all(len(item["audio_sha256"]) == 64 for item in document["items"])
    assert all(len(item["reference_sha256"]) == 64 for item in document["items"])
    assert all(len(item["corpus_item_sha256"]) == 64 for item in document["items"])
    assert prepared.manifest_sha256 in prepared.approval_template_path.read_text(encoding="utf-8")
    coverage = json.loads(prepared.coverage_report_path.read_text(encoding="utf-8"))
    assert coverage["meets_section_8_1"] is True
    assert coverage["item_count"] == 21
    assert "hawedit-asr-bench" in prepared.instructions_path.read_text(encoding="utf-8")


def test_prepare_cli_is_machine_readable_and_leaves_human_approval_unset(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    corpus_path, audio_root, _ = _corpus(tmp_path)

    result = main(
        [
            "prepare",
            str(corpus_path),
            "--audio-root",
            str(audio_root),
            "--output-dir",
            str(tmp_path / "kit"),
            "--dataset-owner",
            "Hawa Media",
            "--authorized-by",
            "hawa@example.test",
            "--licence",
            "private-evaluation-only",
            "--consent-basis",
            "recorded speaker consent for ASR quality evaluation",
            "--permitted-use",
            "HawEdit internal model evaluation and acceptance",
            "--redistribution-forbidden",
        ]
    )

    captured = capsys.readouterr()
    assert result == 0
    assert captured.err == ""
    assert json.loads(captured.out)["status"] == "prepared-not-approved"
    template = json.loads((tmp_path / "kit" / "approval.template.json").read_text())
    assert template["approved_by"] == ""
    assert template["rights_attested"] is False


def test_kit_is_invisible_until_the_exact_set_is_atomically_published(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    corpus_path, audio_root, _ = _corpus(tmp_path)
    destination = tmp_path / "kit"

    def fail_publish(source: Path, target: Path) -> None:
        assert source.parent == destination.parent
        assert target == destination
        assert not destination.exists()
        assert sorted(path.name for path in source.iterdir()) == sorted(
            acceptance_module._KIT_FILENAMES
        )
        raise OSError("simulated atomic-publication failure")

    monkeypatch.setattr(acceptance_module, "rename_directory_noreplace", fail_publish)

    with pytest.raises(CorpusAcceptanceError, match="atomically publish"):
        prepare_corpus_acceptance(
            corpus_path=corpus_path,
            audio_root=audio_root,
            output_dir=destination,
            rights=_rights(),
        )

    assert not destination.exists()
    assert tuple(tmp_path.glob(".kit.*.staging")) == ()


def test_a_competing_kit_publisher_is_never_overwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    corpus_path, audio_root, _ = _corpus(tmp_path)
    destination = tmp_path / "kit"

    def competing_publish(source: Path, target: Path) -> None:
        assert source.is_dir()
        target.mkdir()
        (target / "winner.txt").write_text("other publisher", encoding="utf-8")
        raise FileExistsError(target)

    monkeypatch.setattr(acceptance_module, "rename_directory_noreplace", competing_publish)

    with pytest.raises(CorpusAcceptanceError, match="another publisher won"):
        prepare_corpus_acceptance(
            corpus_path=corpus_path,
            audio_root=audio_root,
            output_dir=destination,
            rights=_rights(),
        )

    assert (destination / "winner.txt").read_text(encoding="utf-8") == "other publisher"
    assert tuple(tmp_path.glob(".kit.*.staging")) == ()


def test_signed_approval_and_unchanged_files_produce_a_guarded_acceptance(tmp_path: Path) -> None:
    corpus_path, audio_root, corpus = _corpus(tmp_path)
    prepared = prepare_corpus_acceptance(
        corpus_path=corpus_path,
        audio_root=audio_root,
        output_dir=tmp_path / "kit",
        rights=_rights(),
    )
    approval, signature, allowed_signers = _approve_and_sign(tmp_path, prepared)

    verified = verify_corpus_acceptance(
        manifest_path=prepared.manifest_path,
        corpus_path=corpus_path,
        audio_root=audio_root,
        approval_path=approval,
        signature_path=signature,
        allowed_signers_path=allowed_signers,
    )

    assert verified.manifest_sha256 == prepared.manifest_sha256
    assert verified.evidence["approval_sha256"]
    assert verified.evidence["signature_sha256"]
    assert verified.evidence["allowed_signers_sha256"]
    assert verified.corpus.provenance == corpus.provenance
    assert [item.item_id for item in verified.corpus.items] == [
        item.item_id for item in corpus.items
    ]
    assert all(Path(item.audio_path).is_absolute() for item in verified.corpus.items)
    with verified.guard(verified.corpus.items[0]):
        pass


def test_audio_mutation_after_human_signature_is_refused(tmp_path: Path) -> None:
    corpus_path, audio_root, corpus = _corpus(tmp_path)
    prepared = prepare_corpus_acceptance(
        corpus_path=corpus_path,
        audio_root=audio_root,
        output_dir=tmp_path / "kit",
        rights=_rights(),
    )
    approval, signature, allowed_signers = _approve_and_sign(tmp_path, prepared)
    (audio_root / corpus.items[0].audio_path).write_bytes(b"changed after approval")

    with pytest.raises(CorpusAcceptanceError, match="audio SHA-256 changed"):
        verify_corpus_acceptance(
            manifest_path=prepared.manifest_path,
            corpus_path=corpus_path,
            audio_root=audio_root,
            approval_path=approval,
            signature_path=signature,
            allowed_signers_path=allowed_signers,
        )


def test_guard_detects_an_audio_change_during_measurement(tmp_path: Path) -> None:
    corpus_path, audio_root, _ = _corpus(tmp_path)
    prepared = prepare_corpus_acceptance(
        corpus_path=corpus_path,
        audio_root=audio_root,
        output_dir=tmp_path / "kit",
        rights=_rights(),
    )
    approval, signature, allowed_signers = _approve_and_sign(tmp_path, prepared)
    verified = verify_corpus_acceptance(
        manifest_path=prepared.manifest_path,
        corpus_path=corpus_path,
        audio_root=audio_root,
        approval_path=approval,
        signature_path=signature,
        allowed_signers_path=allowed_signers,
    )
    item = verified.corpus.items[0]

    with (
        pytest.raises(CorpusAcceptanceError, match="changed while the benchmark was reading"),
        verified.guard(item),
    ):
        Path(item.audio_path).write_bytes(b"changed during inference")


def test_guard_preserves_a_primary_failure_and_attaches_integrity_detail(tmp_path: Path) -> None:
    corpus_path, audio_root, _ = _corpus(tmp_path)
    prepared = prepare_corpus_acceptance(
        corpus_path=corpus_path,
        audio_root=audio_root,
        output_dir=tmp_path / "kit",
        rights=_rights(),
    )
    approval, signature, allowed_signers = _approve_and_sign(tmp_path, prepared)
    verified = verify_corpus_acceptance(
        manifest_path=prepared.manifest_path,
        corpus_path=corpus_path,
        audio_root=audio_root,
        approval_path=approval,
        signature_path=signature,
        allowed_signers_path=allowed_signers,
    )
    item = verified.corpus.items[0]

    with pytest.raises(AssertionError, match="model bug") as caught, verified.guard(item):
        Path(item.audio_path).write_bytes(b"changed during model failure")
        raise AssertionError("model bug")
    assert caught.value.__notes__
    assert "corpus-integrity" in caught.value.__notes__[0]


def test_audio_root_replacement_is_refused_before_measurement(tmp_path: Path) -> None:
    corpus_path, audio_root, _ = _corpus(tmp_path)
    prepared = prepare_corpus_acceptance(
        corpus_path=corpus_path,
        audio_root=audio_root,
        output_dir=tmp_path / "kit",
        rights=_rights(),
    )
    approval, signature, allowed_signers = _approve_and_sign(tmp_path, prepared)
    verified = verify_corpus_acceptance(
        manifest_path=prepared.manifest_path,
        corpus_path=corpus_path,
        audio_root=audio_root,
        approval_path=approval,
        signature_path=signature,
        allowed_signers_path=allowed_signers,
    )
    audio_root.rename(tmp_path / "original-audio")
    audio_root.mkdir()

    with (
        pytest.raises(CorpusAcceptanceError, match="audio root changed"),
        verified.guard(verified.corpus.items[0]),
    ):
        raise AssertionError("measurement must not start")


def test_training_exclusion_collision_is_refused_before_kit_publication(tmp_path: Path) -> None:
    corpus_path, audio_root, corpus = _corpus(tmp_path)
    collision = hashlib.sha256((audio_root / corpus.items[0].audio_path).read_bytes()).hexdigest()

    with pytest.raises(CorpusAcceptanceError, match="training/exclusion set"):
        prepare_corpus_acceptance(
            corpus_path=corpus_path,
            audio_root=audio_root,
            output_dir=tmp_path / "kit",
            rights=_rights(),
            excluded_audio_sha256=(collision,),
        )
    assert not (tmp_path / "kit").exists()


def test_a_hand_authored_manifest_cannot_list_the_same_audio_as_evaluation_and_training(
    tmp_path: Path,
) -> None:
    corpus_path, audio_root, _ = _corpus(tmp_path)
    prepared = prepare_corpus_acceptance(
        corpus_path=corpus_path,
        audio_root=audio_root,
        output_dir=tmp_path / "kit",
        rights=_rights(),
    )
    approval, signature, allowed_signers = _approve_and_sign(tmp_path, prepared)
    manifest = json.loads(prepared.manifest_path.read_text(encoding="utf-8"))
    manifest["excluded_audio_sha256"] = [manifest["items"][0]["audio_sha256"]]
    prepared.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(CorpusAcceptanceError, match="own training/exclusion set"):
        verify_corpus_acceptance(
            manifest_path=prepared.manifest_path,
            corpus_path=corpus_path,
            audio_root=audio_root,
            approval_path=approval,
            signature_path=signature,
            allowed_signers_path=allowed_signers,
        )


def test_duplicate_audio_bytes_are_refused_even_under_different_item_ids(tmp_path: Path) -> None:
    corpus_path, audio_root, corpus = _corpus(tmp_path)
    first = audio_root / corpus.items[0].audio_path
    second = audio_root / corpus.items[1].audio_path
    second.write_bytes(first.read_bytes())

    with pytest.raises(CorpusAcceptanceError, match="duplicate audio bytes"):
        prepare_corpus_acceptance(
            corpus_path=corpus_path,
            audio_root=audio_root,
            output_dir=tmp_path / "kit",
            rights=_rights(),
        )


def test_escaping_and_linked_audio_are_refused(tmp_path: Path) -> None:
    corpus_path, audio_root, corpus = _corpus(tmp_path)
    outside = tmp_path / "outside.wav"
    outside.write_bytes(b"outside")
    linked = audio_root / corpus.items[0].audio_path
    linked.unlink()
    try:
        os.symlink(outside, linked)
    except OSError:
        os.link(outside, linked)

    with pytest.raises(CorpusAcceptanceError, match="link|reparse"):
        prepare_corpus_acceptance(
            corpus_path=corpus_path,
            audio_root=audio_root,
            output_dir=tmp_path / "kit",
            rights=_rights(),
        )


def test_tampered_or_unsigned_human_approval_is_refused(tmp_path: Path) -> None:
    corpus_path, audio_root, _ = _corpus(tmp_path)
    prepared = prepare_corpus_acceptance(
        corpus_path=corpus_path,
        audio_root=audio_root,
        output_dir=tmp_path / "kit",
        rights=_rights(),
    )
    approval, signature, allowed_signers = _approve_and_sign(tmp_path, prepared)
    payload = json.loads(approval.read_text(encoding="utf-8"))
    payload["approved_at_utc"] = "2026-08-18T00:00:00Z"
    approval.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(CorpusAcceptanceError, match="signature verification failed"):
        verify_corpus_acceptance(
            manifest_path=prepared.manifest_path,
            corpus_path=corpus_path,
            audio_root=audio_root,
            approval_path=approval,
            signature_path=signature,
            allowed_signers_path=allowed_signers,
        )


def test_rights_must_match_the_corpus_and_cannot_be_placeholder_text(tmp_path: Path) -> None:
    with pytest.raises(CorpusAcceptanceError, match="placeholder"):
        CorpusRights(
            dataset_owner="unknown",
            authorized_by="hawa@example.test",
            licence="CC0-1.0",
            consent_basis="unknown",
            permitted_use="test",
            redistribution_allowed=False,
        )


def test_schema_invalid_boolean_duration_is_not_coerced_into_one_second(tmp_path: Path) -> None:
    corpus_path, audio_root, _ = _corpus(tmp_path)
    document = json.loads(corpus_path.read_text(encoding="utf-8"))
    document["items"][0]["duration_s"] = True
    corpus_path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(CorpusAcceptanceError, match="duration_s must be a finite JSON number"):
        prepare_corpus_acceptance(
            corpus_path=corpus_path,
            audio_root=audio_root,
            output_dir=tmp_path / "kit",
            rights=_rights(),
        )

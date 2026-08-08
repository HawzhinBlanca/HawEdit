"""Regressions for the independent multi-model review of 2026-08-07.

This project had been written and checked by one model. Six reviewers running a *different*
model read it across separate dimensions, and every finding was then attacked by three
independent skeptics; two refutations killed it. Sixteen were proposed, eleven survived, four
of those are blockers. Each is locked down here.

They are the same class the previous audit found, which is the point worth recording: **a
check that accepts the shape of an answer without checking its content.** The pattern did not
run out. It reappeared in the code written to fix it.

* `_strict_bool` was added so `"false"` could not deserialize as `True` — and then the
  universal boundary gate kept using plain truthiness, and the Gemini adapter used `bool()`.
* The gate was taught that an exit code is not evidence — and then accepted a report in which
  every test skipped.
* `TranscriptStore.write_raw` was given `O_EXCL` so a path could not be attacker-chosen — and
  the credentials module two files away wrote a plaintext key through a symlink.
* `assert_rtl_stack` was given a second evidence source so a build could not certify itself on
  a flag alone — and the render path passes `""` for that second source.

Each fix here is the *content* check its shape check was standing in for.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Mapping
from pathlib import Path

import pytest

from hawedit.boundary import Boundary, BoundaryInvariantViolated, assert_boundary_invariant
from hawedit.credentials import GEMINI_API_KEY, CredentialError, write_credential
from hawedit.gate import NoTestEvidence, check_test_evidence, write_floor
from test_credentials import assert_owner_only

# --- BLOCKER: invariant #2's universal gate used plain truthiness -------------------------


def _boundary(sentence_complete: object) -> Boundary:
    """A boundary built directly, the way a stage other than `from_dict` would build one."""
    return Boundary(
        anchor_in_ms=0,
        anchor_out_ms=1_000,
        final_in_ms=0,
        final_out_ms=1_000,
        in_extended_by=None,
        out_extended_by=None,
        sentence_complete=sentence_complete,  # type: ignore[arg-type]
    )


def test_the_render_gate_refuses_a_non_boolean_sentence_complete() -> None:
    """`Boundary` is *deliberately* not self-validating so `assert_boundary_invariant` can be
    the universal net — its own docstring says a boundary arriving as JSON from another stage
    "has to be checkable on arrival".

    The strict-bool guard was wired into `Boundary.from_dict` only. Anything constructing a
    Boundary by another route — a different serializer, a future stage, `dataclasses.replace` —
    reached the gate with `sentence_complete="false"` and passed it, because a non-empty string
    is truthy. Kurdish invariant #2 is "reject, never render"; this rendered.
    """
    with pytest.raises(BoundaryInvariantViolated, match="boolean"):
        assert_boundary_invariant(_boundary("false"))


def test_the_render_gate_refuses_any_truthy_stand_in_for_true() -> None:
    for impostor in ("true", 1, [1], {"complete": True}):
        with pytest.raises(BoundaryInvariantViolated, match="boolean"):
            assert_boundary_invariant(_boundary(impostor))


def test_a_real_boolean_still_passes_the_gate() -> None:
    assert_boundary_invariant(_boundary(True))  # must not raise
    with pytest.raises(BoundaryInvariantViolated):
        assert_boundary_invariant(_boundary(False))


# --- BLOCKER: an all-skipped run counted as evidence --------------------------------------


def _report(path: Path, *, tests: int, skipped: int = 0, failures: int = 0) -> Path:
    path.write_text(
        f'<testsuites><testsuite tests="{tests}" failures="{failures}" errors="0" '
        f'skipped="{skipped}"></testsuite></testsuites>',
        encoding="utf-8",
    )
    return path


def test_a_run_where_everything_skipped_is_not_evidence(tmp_path: Path) -> None:
    """The gate learned that an exit code is not evidence, then accepted a report proving
    nothing ran.

    700 collected, 0 failures, 0 errors, 700 skipped clears every check it had: non-zero
    collected, no failures, at or above the floor. `bash scripts/verify.sh` printed
    `VERIFY OK` with zero test bodies executed. One over-broad `skipif` — a media guard that
    evaluates true everywhere, say — produces exactly this report.
    """
    floor = tmp_path / "floor"
    write_floor(floor, 686)
    with pytest.raises(NoTestEvidence, match="skipped"):
        check_test_evidence(_report(tmp_path / "r.xml", tests=700, skipped=700), floor_path=floor)


def test_a_run_that_quietly_skips_below_the_floor_is_not_evidence(tmp_path: Path) -> None:
    """The partial case, which is the one that actually happens: collected stays above the
    floor because the tests still exist, while the number that *ran* falls."""
    floor = tmp_path / "floor"
    write_floor(floor, 686)
    with pytest.raises(NoTestEvidence, match="skipped|passed"):
        check_test_evidence(_report(tmp_path / "r.xml", tests=690, skipped=100), floor_path=floor)


def test_a_healthy_run_with_no_skips_still_passes(tmp_path: Path) -> None:
    floor = tmp_path / "floor"
    write_floor(floor, 686)
    evidence = check_test_evidence(_report(tmp_path / "r.xml", tests=686), floor_path=floor)
    assert evidence.passed == 686


# --- BLOCKER: the credential store wrote through a symlink --------------------------------


def _git_repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / ".gitignore").write_text(".env\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("tracked content\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"],
        cwd=tmp_path,
        check=True,
    )
    return tmp_path


def test_a_symlinked_env_file_cannot_be_used_to_write_the_key_into_a_tracked_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`git check-ignore` answers about the *pathname*, never the symlink target.

    So `.env -> README.md` satisfies the ignore check and the write lands in a tracked file,
    putting the plaintext key straight into `git status` and one `git add -A` away from being
    committed forever. `TranscriptStore.write_raw` two files away already used `O_EXCL` for
    exactly this reason; the credential store — the one place actually handling a secret — used
    `Path.write_text`, which follows symlinks.
    """
    repo = _git_repo(tmp_path)
    try:
        (repo / ".env").symlink_to("README.md")
    except OSError:  # Windows without SeCreateSymbolicLinkPrivilege
        # Not a skip. hawapc01 is the machine that will hold the real key, and a test that
        # stops running exactly there protects the least useful host. What is unavailable is
        # the privilege to *build* the attack, not the refusal that stops it: on a platform
        # with no O_NOFOLLOW, `write_credential` decides from `is_symlink()`, so that is the
        # answer supplied here. A POSIX runner takes the branch above and drives the real
        # link through the real syscall — same test, same assertions, both halves covered.
        monkeypatch.setattr(Path, "is_symlink", lambda _self: True)

    with pytest.raises(CredentialError, match="symlink"):
        write_credential(GEMINI_API_KEY, "sk-LEAKED-VIA-SYMLINK", env_file=repo / ".env")

    assert (repo / "README.md").read_text(encoding="utf-8") == "tracked content\n", (
        "the tracked file was overwritten — the key is now in the working tree"
    )


def test_the_key_is_never_world_readable_even_briefly(tmp_path: Path) -> None:
    """`write_text` then `chmod` leaves a window at the process umask — 0644 typically.

    On a shared host any other local user, or a backup/AV/indexer that happens to read during
    that window, gets the key in plaintext. The file must be *created* 0600, not corrected to
    it afterwards.
    """
    env_file = tmp_path / ".env"
    write_credential(GEMINI_API_KEY, "sk-test", env_file=env_file, check_ignored=False)
    assert_owner_only(env_file)

    # The window is invisible after the fact, so assert the mechanism: an O_CREAT with 0600
    # cannot expose a wider mode, whereas write_text+chmod always can.
    source = Path(write_credential.__code__.co_filename).read_text(encoding="utf-8")
    assert "O_NOFOLLOW" in source, "the write must refuse symlinks at the syscall"
    assert "0o600" in source


def test_writing_to_a_tracked_path_is_still_refused(tmp_path: Path) -> None:
    """The original guard must survive the new one."""
    repo = _git_repo(tmp_path)
    with pytest.raises(CredentialError, match="not ignored by git"):
        write_credential(GEMINI_API_KEY, "sk-test", env_file=repo / "README.md")


def test_an_existing_regular_env_file_is_still_updatable(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    write_credential("OTHER", "keep-me", env_file=env_file, check_ignored=False)
    write_credential(GEMINI_API_KEY, "sk-test", env_file=env_file, check_ignored=False)
    body = env_file.read_text(encoding="utf-8")
    assert "OTHER=keep-me" in body and f"{GEMINI_API_KEY}=sk-test" in body


# --- BLOCKER: token counting bypassed the governance gate ---------------------------------


def test_counting_tokens_cannot_send_confidential_text_before_the_zdr_gate() -> None:
    """§3 Stage 3 calls ZDR "mandatory, not advisory" for COMMS and KAAE material.

    `judge()` and `PathADiscovery.discover()` both check governance before any HTTP call.
    `count_request_tokens()` did not — and it builds the full prompt, transcript included, and
    posts it to Google. `smoke.py` calls it directly. A live bypass of the one rule in this
    project with legal consequences.
    """
    from hawedit.gemini import GeminiJudge, GeminiUnavailable, Governance
    from hawedit.judge import InputMode, JudgeRequest

    sent: list[bytes] = []

    def spy(url: str, body: bytes | None, _headers: Mapping[str, str]) -> tuple[int, str]:
        if body:
            sent.append(body)
        return 200, json.dumps({"totalTokens": 10})

    judge = GeminiJudge(
        api_key="k",
        transport=spy,
        governance=Governance(confidential=True, zero_data_retention=False),
    )
    request = JudgeRequest(
        candidate_id="c",
        mode=InputMode.STAGE_4_TRANSCRIPT_FIRST,
        text_ckb="SECRET CLIENT TRANSCRIPT",
        clip_in_ms=0,
        clip_out_ms=1_000,
    )
    with pytest.raises(GeminiUnavailable, match="mandatory, not advisory"):
        judge.count_request_tokens(request)
    assert sent == [], "confidential text reached the network before the governance check"


# --- MAJOR: model output coerced with bool() ----------------------------------------------


def test_a_string_false_from_the_model_is_not_read_as_true() -> None:
    """The one place the least-trusted input in the system becomes a shipped artifact."""
    from hawedit.gemini import GeminiJudge, JudgeUnusable

    fields = {
        "hook_score": 0.8,
        "self_contained": "false",  # a string, not a JSON boolean
        "payoff_at_ms": 500,
        "meaning_fidelity": 0.9,
        "misleading_edit_risk": 0.1,
        "cultural_landing": 0.8,
        "narrative_role": "payoff",
        "title_ckb": "ڕۆژنامەوانی کوردی",
        "description_ckb": "بابەتێکی گرنگ",
        "hashtags_ckb": ["#کوردی"],
    }

    def transport(url: str, body: bytes | None, _headers: Mapping[str, str]) -> tuple[int, str]:
        if "countTokens" in url:
            return 200, json.dumps({"totalTokens": 10})
        return 200, json.dumps(
            {"candidates": [{"content": {"parts": [{"text": json.dumps(fields)}]}}]}
        )

    from hawedit.judge import InputMode, JudgeFrame, JudgeRequest

    judge = GeminiJudge(api_key="k", transport=transport, sleep=lambda _s: None)
    with pytest.raises(JudgeUnusable, match="boolean"):
        judge.judge(
            JudgeRequest(
                candidate_id="c",
                mode=InputMode.STAGE_4_TRANSCRIPT_FIRST,
                text_ckb="ئەمە",
                clip_in_ms=0,
                clip_out_ms=1_000,
                keyframes=(JudgeFrame(500, "image/jpeg", b"jpeg"),),
            )
        )


# --- MAJOR: a dropped network connection was treated as a refusal --------------------------


def test_a_dropped_connection_is_retried_rather_than_reported_as_a_refusal() -> None:
    """`_https` maps every `OSError` to status 0, and 0 was not in the retryable set.

    A reset connection, a DNS blip or a TLS hiccup therefore produced "the judge refused this
    request" on the first attempt — a diagnosis that sends someone looking at their prompt when
    the problem was the network.
    """
    from hawedit.gemini import GeminiJudge
    from hawedit.judge import InputMode, JudgeFrame, JudgeRequest

    attempts = {"n": 0}

    def flaky(url: str, body: bytes | None, _headers: Mapping[str, str]) -> tuple[int, str]:
        if "countTokens" in url:
            return 200, json.dumps({"totalTokens": 10})
        attempts["n"] += 1
        if attempts["n"] == 1:
            return 0, "Connection reset by peer"
        return 200, json.dumps(
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": json.dumps(
                                        {
                                            "hook_score": 0.8,
                                            "self_contained": True,
                                            "payoff_at_ms": 500,
                                            "meaning_fidelity": 0.9,
                                            "misleading_edit_risk": 0.1,
                                            "cultural_landing": 0.8,
                                            "narrative_role": "payoff",
                                            "title_ckb": "ڕۆژنامەوانی کوردی",
                                            "description_ckb": "بابەتێکی گرنگ",
                                            "hashtags_ckb": ["#کوردی"],
                                        }
                                    )
                                }
                            ]
                        }
                    }
                ]
            }
        )

    judge = GeminiJudge(api_key="k", transport=flaky, sleep=lambda _s: None)
    verdict = judge.judge(
        JudgeRequest(
            candidate_id="c",
            mode=InputMode.STAGE_4_TRANSCRIPT_FIRST,
            text_ckb="ئەمە",
            clip_in_ms=0,
            clip_out_ms=1_000,
            keyframes=(JudgeFrame(500, "image/jpeg", b"jpeg"),),
        )
    )
    assert verdict.candidate_id == "c"
    assert attempts["n"] == 2, "the transient failure was not retried"


# --- MAJOR: the RTL check's second evidence source was never supplied ---------------------


def test_the_render_path_supplies_both_rtl_evidence_sources() -> None:
    """§4.3.2's whole point is that a build accepting `shaping=complex` may lack the library.

    `assert_rtl_stack` takes two sources — buildconf flags *and* linked libraries — precisely
    because ffmpeg's own `--enable-libharfbuzz` governs drawtext, not whether the separately
    built, dynamically linked `libass.so` has HarfBuzz. `render_clip` passed `""` for the
    second, so the distro-build case the parameter exists for was dead code and Kurdish
    invariant #4 rested on a flag string.
    """
    import inspect

    from hawedit import render

    source = inspect.getsource(render)
    assert 'assert_rtl_stack(buildconf, "")' not in source, (
        "the render path still discards the linked-library evidence"
    )
    assert "linked_libraries" in source or "ldd" in source


def test_linked_libraries_are_probed_from_the_real_binary(tmp_path: Path) -> None:
    from hawedit.render import linked_libraries

    fake = tmp_path / "ffmpeg"
    fake.write_text("#!/bin/sh\n", encoding="utf-8")
    fake.chmod(0o755)
    # A non-ELF file has no linked libraries; the probe must return a string, never raise —
    # a crash here would take down every render on a static build.
    assert isinstance(linked_libraries(fake), str)


# --- MAJOR: a non-contiguous selection silently dropped spoken content --------------------


def test_a_non_contiguous_sentence_selection_is_refused(tmp_path: Path) -> None:
    """Selecting sentences 0 and 2 spans sentence 1 without captioning or transcribing it.

    The boundary invariant still "passes" — it only compares numbers — so the clip renders with
    real Kurdish speech in the middle that has no caption and is absent from the `raw_ckb` that
    §4.1 says ships to the client. Silence would be better; wrong text is worse than none.
    """
    from hawedit.captions import find_ffmpeg
    from hawedit.pipeline import run_pipeline
    from hawedit.transcripts import AsrProvenance, RawTranscript, Word

    if find_ffmpeg() is None:
        pytest.skip("no ffmpeg — set HAWEDIT_FFMPEG")

    fixture = Path(__file__).resolve().parent / "fixtures" / "kurdish-speech-3cuts.mp4"
    transcript = RawTranscript(
        media_id="gap",
        text_ckb="یەک. دوو. سێ.",
        words=(
            Word(w="یەک.", start_ms=0, end_ms=800, conf=0.9),
            Word(w="دوو.", start_ms=1_500, end_ms=2_300, conf=0.9),
            Word(w="سێ.", start_ms=3_000, end_ms=3_900, conf=0.9),
        ),
        asr=AsrProvenance(canonical="omniASR_LLM_7B_v2", aligner="ctc_viterbi"),
    )
    with pytest.raises(ValueError, match="contiguous"):
        run_pipeline(
            fixture,
            tmp_path / "work",
            media_id="gap",
            transcript=transcript,
            select_sentences=(0, 2),
        )


def test_a_contiguous_selection_is_still_accepted() -> None:
    """Out-of-order indices that still form a run are fine — sorted, they are contiguous."""
    from hawedit.pipeline import assert_contiguous

    assert_contiguous((0, 1, 2), total=3)
    assert_contiguous((2, 1), total=3)
    assert_contiguous((1,), total=3)
    with pytest.raises(ValueError, match="contiguous"):
        assert_contiguous((0, 2), total=3)


def test_a_duplicate_index_is_refused() -> None:
    from hawedit.pipeline import assert_contiguous

    with pytest.raises(ValueError, match="duplicate|contiguous"):
        assert_contiguous((1, 1), total=3)


# --- the review itself, recorded --------------------------------------------------------


def test_the_review_is_recorded_as_evidence() -> None:
    """The first independent review this project has had. Its findings are the reason this
    file exists, so the record of it is part of the deliverable."""
    record = Path(__file__).resolve().parents[1] / "evidence" / "independent-review.md"
    assert record.exists(), f"the review is not recorded at {record}"
    body = record.read_text(encoding="utf-8")
    assert "sonnet" in body.lower(), "the reviewing model must be named — independence is the claim"


def test_no_stray_environment_variable_from_the_old_name_survives() -> None:
    """The rename touched three env vars; a missed one would silently stop configuring."""
    root = Path(__file__).resolve().parents[1]
    for path in list((root / "src").rglob("*.py")) + list((root / "scripts").glob("*.sh")):
        assert "HAWEDIT2_" not in path.read_text(encoding="utf-8"), f"stale env var in {path}"


def test_a_permissive_environment_cannot_widen_the_credential_file(tmp_path: Path) -> None:
    """Belt and braces: make the surroundings as permissive as the OS allows, then check.

    The hostile condition is not the same on both platforms, and asserting the POSIX one on
    Windows would test nothing — `os.umask` is accepted there and changes no ACL. What a
    Windows file actually inherits is its directory's ACL, so that is what gets opened up
    here. It is the direct analogue, and it is the check on `restrict_to_owner`'s
    `/inheritance:r`: without that flag the file below comes out readable by Everyone.
    """
    env_file = tmp_path / ".env"
    if os.name == "nt":
        subprocess.run(
            ["icacls", str(tmp_path), "/grant", "Everyone:(OI)(CI)F"],
            capture_output=True,
            check=True,
        )
        write_credential(GEMINI_API_KEY, "sk-test", env_file=env_file, check_ignored=False)
    else:
        old = os.umask(0o000)
        try:
            write_credential(GEMINI_API_KEY, "sk-test", env_file=env_file, check_ignored=False)
        finally:
            os.umask(old)
    assert_owner_only(env_file)


# =========================================================================================
# ROUND 2 — the same bug class, found inside the code written to fix it
#
# Four of the eleven round-1 fixes introduced a new instance of "a check that accepts the
# shape of an answer without checking its content", one call site over from where the fix
# landed. That is the finding: the pattern is not a bug, it is a habit — fix X at site A,
# never look at site B.
# =========================================================================================


def test_a_hardlinked_env_cannot_rewrite_a_tracked_file(tmp_path: Path) -> None:
    """BLOCKER, introduced by the round-1 symlink fix.

    `O_NOFOLLOW` rejects a `.env` that *is* a symlink. A hardlink is an ordinary regular file
    that happens to share an inode with — say — a tracked file, so O_NOFOLLOW passes it and
    `O_TRUNC` rewrites that file's content with the plaintext key. The round-1 fix validated
    the path's *name*; the symlink bug was really about the file's *identity*.
    """
    repo = _git_repo(tmp_path)
    sink = repo / "README.md"
    os.link(sink, repo / ".env")

    with pytest.raises(CredentialError, match="hard link"):
        write_credential(GEMINI_API_KEY, "sk-LEAKED-VIA-HARDLINK", env_file=repo / ".env")

    assert sink.read_text(encoding="utf-8") == "tracked content\n", (
        "the tracked file was rewritten with the key through a hardlink"
    )


def test_the_raw_transcript_is_complete_the_instant_it_is_visible(tmp_path: Path) -> None:
    """BLOCKER, introduced by the round-1 O_EXCL fix.

    `O_EXCL` protected the writer and, in doing so, made the *name* appear before the content
    did. A concurrent reader hit a half-written file or a missing digest sidecar and crashed
    with `JSONDecodeError`/`FileNotFoundError` instead of the orderly refusal the code
    promises. Whenever raw is readable, it must parse and its sidecar must exist.
    """
    from hawedit.transcripts import AsrProvenance, RawTranscript, TranscriptStore

    store = TranscriptStore(tmp_path)
    raw = RawTranscript(
        media_id="m", text_ckb="ئەمە", words=(), asr=AsrProvenance(canonical="omniASR_LLM_7B_v2")
    )
    store.write_raw(raw)
    # Both artifacts present and consistent immediately after the write returns.
    assert store.raw_path("m").exists()
    store.verify_raw_integrity("m")
    assert store.read_raw("m").text_ckb == "ئەمە"
    # And no staging debris left behind.
    assert not list(tmp_path.glob(".*tmp")), "a temporary file survived the write"


def test_write_once_survives_the_new_write_path(tmp_path: Path) -> None:
    """Invariant #1 must not have been weakened by fixing the race."""
    from hawedit.transcripts import (
        AsrProvenance,
        RawTranscript,
        RawTranscriptImmutable,
        TranscriptStore,
    )

    store = TranscriptStore(tmp_path)
    raw = RawTranscript(
        media_id="m", text_ckb="ئەمە", words=(), asr=AsrProvenance(canonical="omniASR_LLM_7B_v2")
    )
    store.write_raw(raw)
    with pytest.raises(RawTranscriptImmutable):
        store.write_raw(raw)
    assert not list(tmp_path.glob(".*tmp")), "the refused write left debris"


def test_index_contiguity_is_not_time_contiguity() -> None:
    """BLOCKER, introduced by the round-1 contiguity fix.

    The clip is cut in *time*. Index contiguity coincides with time contiguity only when the
    sentence list is already chronological, and nothing guaranteed that. An out-of-time-order
    transcript therefore produced an index-contiguous selection whose window swallowed real,
    un-captioned Kurdish speech — exactly the defect the fix was written to prevent.
    """
    from hawedit.pipeline import assert_time_contiguous
    from hawedit.sentences import Sentence
    from hawedit.transcripts import Word

    def sentence(start: int, end: int) -> Sentence:
        return Sentence(
            words=(Word(w="ئەمە", start_ms=start, end_ms=end, conf=0.9),), complete=True
        )

    # Index order 0,1,2 — but sentence 2 sits in time *between* 0 and 1.
    out_of_order = [sentence(0, 900), sentence(3_000, 3_900), sentence(1_500, 2_400)]
    with pytest.raises(ValueError, match="overlaps sentence"):
        assert_time_contiguous(out_of_order, (0, 1))

    in_order = [sentence(0, 900), sentence(1_500, 2_400), sentence(3_000, 3_900)]
    assert_time_contiguous(in_order, (0, 1))  # must not raise
    assert_time_contiguous(in_order, ())  # empty selection is not a violation


def test_a_persisted_verdict_cannot_smuggle_a_string_boolean() -> None:
    """MAJOR, introduced by the round-1 strict-bool fix.

    `_strict_bool` was added to the live-response parser. `JudgeVerdict.from_dict` — the
    sibling path that rebuilds a verdict from persisted JSON — took the value with no check,
    and it survived all the way into a shipped `Editorial`.
    """
    from hawedit.judge import JudgeVerdict

    payload = {
        "candidate_id": "c",
        "hook_score": 0.8,
        "self_contained": "false",
        "payoff_at_ms": 500,
        "meaning_fidelity": 0.9,
        "misleading_edit_risk": 0.1,
        "cultural_landing": 0.8,
        "narrative_role": "payoff",
        "title_ckb": "ڕۆژنامەوانی کوردی",
        "description_ckb": "بابەتێکی گرنگ",
        "hashtags_ckb": ["#کوردی"],
        "judge": "gemini-2.5-pro",
        "clip_in_ms": 0,
        "clip_out_ms": 1_000,
        "sv6d": None,
    }
    with pytest.raises(ValueError, match="boolean"):
        JudgeVerdict.from_dict(payload)


def test_a_string_of_hashtags_is_not_shredded_into_letters() -> None:
    """A `str` is iterable, so a scalar where the schema says array yields one 'hashtag' per
    character — and each character passes the Kurdish-script check, because a Kurdish letter
    is Kurdish script."""
    from hawedit.gemini import GeminiJudge, JudgeUnusable
    from hawedit.judge import InputMode, JudgeFrame, JudgeRequest

    fields = {
        "hook_score": 0.8,
        "self_contained": True,
        "payoff_at_ms": 500,
        "meaning_fidelity": 0.9,
        "misleading_edit_risk": 0.1,
        "cultural_landing": 0.8,
        "narrative_role": "payoff",
        "title_ckb": "ڕۆژنامەوانی کوردی",
        "description_ckb": "بابەتێکی گرنگ",
        "hashtags_ckb": "کورد",  # a string, not an array
    }

    def transport(url: str, body: bytes | None, _headers: Mapping[str, str]) -> tuple[int, str]:
        if "countTokens" in url:
            return 200, json.dumps({"totalTokens": 10})
        return 200, json.dumps(
            {"candidates": [{"content": {"parts": [{"text": json.dumps(fields)}]}}]}
        )

    with pytest.raises(JudgeUnusable, match="not an array"):
        GeminiJudge(api_key="k", transport=transport, sleep=lambda _s: None).judge(
            JudgeRequest(
                candidate_id="c",
                mode=InputMode.STAGE_4_TRANSCRIPT_FIRST,
                text_ckb="ئەمە",
                clip_in_ms=0,
                clip_out_ms=1_000,
                keyframes=(JudgeFrame(500, "image/jpeg", b"jpeg"),),
            )
        )


def test_narrative_role_is_one_of_the_four_the_prompt_asks_for() -> None:
    """`str()` accepted anything. §5 carries the value to the client, so an unconstrained
    string means the field says whatever the model felt like saying."""
    from hawedit.judge import NARRATIVE_ROLES, JudgeVerdict

    assert {"setup", "escalation", "payoff", "aside"} == NARRATIVE_ROLES
    with pytest.raises(ValueError, match="narrative_role"):
        JudgeVerdict(
            candidate_id="c",
            hook_score=0.8,
            self_contained=True,
            payoff_at_ms=500,
            meaning_fidelity=0.9,
            misleading_edit_risk=0.1,
            cultural_landing=0.8,
            narrative_role="a moment of quiet reflection",
            title_ckb="ڕۆژنامەوانی کوردی",
            description_ckb="بابەتێکی گرنگ",
            hashtags_ckb=("#کوردی",),
            judge="gemini-2.5-pro",
            clip_in_ms=0,
            clip_out_ms=1_000,
        )


def test_costing_a_request_cannot_launder_a_raw_transcript() -> None:
    """`RawTranscript` duck-types `NormalizedTranscript` exactly, and `build_request` is public
    and documented as usable on its own — so invariant #3 needed the check here too."""
    from hawedit.gemini import Governance
    from hawedit.path_a import PathADiscovery
    from hawedit.transcripts import AsrProvenance, RawTranscript

    raw = RawTranscript(
        media_id="m",
        text_ckb="ڕۆژنامەوانی",
        words=(),
        asr=AsrProvenance(canonical="omniASR_LLM_7B_v2"),
    )

    def transport(_url: str, _body: bytes | None, _headers: Mapping[str, str]) -> tuple[int, str]:
        return 200, "{}"

    path_a = PathADiscovery(api_key="k", transport=transport, governance=Governance())
    with pytest.raises(TypeError, match="norm"):
        path_a.build_request(raw)  # type: ignore[arg-type]

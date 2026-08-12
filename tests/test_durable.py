"""The two properties `durable_workflow.py` exists for, checked rather than assumed.

`configure_dbos`'s docstring cites the installed `dbos==2.29.0` source for two claims:
recovery on `launch()` and dedup on a repeated workflow ID. Both are checked here against the
real library — a mock would only prove this module calls DBOS the way it thinks DBOS works, not
that DBOS actually behaves that way. The dedup case runs in-process, fast: it monkeypatches
`_build_and_run` to a stub and counts calls. The crash/restart case does not — a same-process
`DBOS.destroy()` and reconstruct proves DBOS *can* be re-launched, not that a process genuinely
killed mid-step comes back, so that test spawns a real child process and kills it with `os._exit`
(no cleanup, no unwind — the closest a test can come to `kill -9` without an OS call this suite
cannot make portably) before the step returns, then starts a second process against the same
SQLite file and confirms the workflow resumes rather than vanishing.

Everything here needs `dbos`, which is not installed by a bare `pip install -e .` (it lives in
the `agentic` extra; `requirements/gate-linux-py311.txt` carries it for CI). `importorskip` is
defense for that environment, not the normal path — the extra is in CI's lockfile, so these
tests are expected to run there, not skip.
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from collections.abc import Iterator
from pathlib import Path

import pytest

dbos = pytest.importorskip("dbos")

from hawedit.captions import find_ffmpeg  # noqa: E402
from hawedit.durable_workflow import (  # noqa: E402
    configure_dbos,
    read_events,
    run_durable,
)
from hawedit.judge import JudgeVerdict  # noqa: E402
from hawedit.pipeline import PipelineRun  # noqa: E402
from hawedit.transcripts import AsrProvenance, RawTranscript, Word  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "kurdish-speech-3cuts.mp4"

needs_ffmpeg = pytest.mark.skipif(find_ffmpeg() is None, reason="no ffmpeg — set HAWEDIT_FFMPEG")

WORDS = (
    Word(w="ڕۆژنامەوانی", start_ms=100, end_ms=800, conf=0.95),
    Word(w="کوردی.", start_ms=800, end_ms=1_700, conf=0.94),
    Word(w="لە", start_ms=2_000, end_ms=2_400, conf=0.93),
    Word(w="هەولێر.", start_ms=2_400, end_ms=4_100, conf=0.92),
)


def a_transcript(media_id: str = "fixture") -> RawTranscript:
    return RawTranscript(
        media_id=media_id,
        text_ckb="ڕۆژنامەوانی کوردی. لە هەولێر.",
        words=WORDS,
        asr=AsrProvenance(canonical="omniASR_LLM_7B_v2", aligner="ctc_viterbi"),
    )


def a_verdict(clip_in_ms: int, clip_out_ms: int) -> JudgeVerdict:
    return JudgeVerdict(
        candidate_id="fixture-0",
        hook_score=0.8,
        self_contained=True,
        payoff_at_ms=(clip_in_ms + clip_out_ms) // 2,
        meaning_fidelity=0.9,
        misleading_edit_risk=0.05,
        cultural_landing=0.8,
        narrative_role="payoff",
        title_ckb="ڕۆژنامەوانی کوردی لە هەولێر",
        description_ckb="بابەتێکی گرنگ دەربارەی ڕۆژنامەوانی",
        hashtags_ckb=("#کوردی",),
        judge="gemini-2.5-pro",
        clip_in_ms=clip_in_ms,
        clip_out_ms=clip_out_ms,
    )


@pytest.fixture(scope="module", autouse=True)
def _dbos_instance(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """One DBOS instance for this file, launched once against a throwaway SQLite file.

    Module-scoped rather than per-test, and it never destroys the registry: `durable_workflow.
    py`'s `@DBOS.workflow()`/`@DBOS.step()` decorate `_run_pipeline_step`/`run_pipeline_workflow`
    exactly once, at import time, into a process-global registry. `DBOS.destroy(
    destroy_registry=True)` between tests would wipe that registration and every test after the
    first would fail to find the decorated function — measured while writing this fixture.
    Plain `DBOS.destroy()` at session end releases the instance without touching the registry.
    """
    db_path = tmp_path_factory.mktemp("dbos") / "test.sqlite"
    configure_dbos(system_database_url=f"sqlite:///{db_path}")
    yield
    dbos.DBOS.destroy()


# --- durability, proven rather than assumed ------------------------------------------------


def test_calling_the_same_run_id_twice_executes_the_step_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The duplicate-submission guarantee `configure_dbos` cites from the DBOS source.

    `_build_and_run` is monkeypatched to a stub so this proves the *dedup mechanism* — the
    thing `durable_workflow.py` actually adds — without paying for a real pipeline run or needing
    ffmpeg. The stub returns a real (if minimal) `PipelineRun`: `_run_pipeline_step` calls
    `.to_dict()` on whatever it gets back, so the stub has to be the real type, not a mock.
    """
    import hawedit.durable_workflow as durable_module

    calls: list[str] = []

    def stub(args: object, on_event: object = None) -> PipelineRun:
        calls.append("called")
        return PipelineRun(media_id="dedup-check", source="x.mp4", work_dir="work")

    monkeypatch.setattr(durable_module, "_build_and_run", stub)

    first = run_durable(["nonexistent.mp4"], run_id="dedup-check-1")
    second = run_durable(["nonexistent.mp4"], run_id="dedup-check-1")

    assert len(calls) == 1, f"the step body ran {len(calls)} times for one workflow ID"
    assert first["media_id"] == "dedup-check"
    assert first == second, "the second call under the same ID returned a different report"


def test_two_different_run_ids_both_execute(monkeypatch: pytest.MonkeyPatch) -> None:
    """The contrapositive: dedup is keyed on the ID, not on argv or on calling this twice."""
    import hawedit.durable_workflow as durable_module

    calls: list[str] = []

    def stub(args: object, on_event: object = None) -> PipelineRun:
        calls.append("called")
        return PipelineRun(media_id="two-ids", source="x.mp4", work_dir="work")

    monkeypatch.setattr(durable_module, "_build_and_run", stub)

    run_durable(["nonexistent.mp4"], run_id="two-ids-a")
    run_durable(["nonexistent.mp4"], run_id="two-ids-b")

    assert len(calls) == 2


def test_a_bad_argv_combination_is_refused_before_dbos_records_anything() -> None:
    """`run_durable` raises the same refusal `_build_and_run` always has for this combination.

    `--sentences` with no Stage 1 source is one of `tests/test_pipeline.py`'s own
    `_REFUSAL_CASES`. Routed through the durable workflow, it must fail exactly the same way —
    a durability layer that swallows a validation error into a generic workflow-failed status
    would hide the actual problem from whoever is reading the CLI's stderr.
    """
    with pytest.raises(ValueError, match="--sentences requires --transcript or --omni-asr"):
        run_durable(["some.mp4", "--sentences", "0"], run_id="bad-argv-case")


# --- against the real pipeline ---------------------------------------------------------------


@needs_ffmpeg
def test_run_durable_reports_the_same_thing_a_direct_call_would(tmp_path: Path) -> None:
    """The wrapper changes nothing about what the pipeline reports for the same argv."""
    argv = [
        str(FIXTURE),
        "--work-dir",
        str(tmp_path / "work"),
        "--media-id",
        "fixture",
    ]
    durable_payload = run_durable(list(argv), run_id="real-media-case")

    from hawedit.pipeline import _build_and_run, build_parser

    direct = _build_and_run(
        build_parser().parse_args(
            [str(FIXTURE), "--work-dir", str(tmp_path / "direct"), "--media-id", "fixture"]
        )
    )
    direct_payload = json.loads(json.dumps(direct.to_dict(), ensure_ascii=False))

    def strip_work_dir(payload: dict[str, object], marker: Path) -> str:
        # `str(marker)` has single backslashes on Windows; the JSON text has them doubled by
        # `json.dumps`. Round-tripping the marker through `json.dumps` (and stripping the
        # quotes it wraps a string in) produces the escaped form that actually appears in
        # `text` — the same fix `test_events.py`'s equivalent helper needed for the same reason.
        text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        escaped_marker = json.dumps(str(marker))[1:-1]
        return text.replace(escaped_marker, "<work>")

    assert strip_work_dir(durable_payload, tmp_path / "work") == strip_work_dir(
        direct_payload, tmp_path / "direct"
    )


@needs_ffmpeg
def test_the_run_events_ledger_is_written_and_replayable(tmp_path: Path) -> None:
    work = tmp_path / "work"
    run_durable(
        [str(FIXTURE), "--work-dir", str(work), "--media-id", "fixture"],
        run_id="ledger-case",
    )
    events = read_events(work / "events.jsonl")
    assert events, "the durable step wired no event sink"
    assert events[0].stage == "ingest"
    assert [event.sequence for event in events] == list(range(1, len(events) + 1))


@needs_ffmpeg
def test_a_full_run_through_the_durable_workflow_still_renders(tmp_path: Path) -> None:
    work = tmp_path / "work"
    payload = run_durable(
        [
            str(FIXTURE),
            "--work-dir",
            str(work),
            "--media-id",
            "fixture",
            "--transcript",
            _write_transcript(tmp_path),
            "--sentences",
            "0,1",
            "--qc-pass",
            "--verdict",
            _write_verdict(tmp_path),
        ],
        run_id="full-run-case",
    )
    assert payload["clip"] is not None
    assert payload["render"] is not None and not payload["render"].get("skipped")


def _write_transcript(tmp_path: Path) -> str:
    path = tmp_path / "transcript.raw.json"
    path.write_text(a_transcript().to_json(), encoding="utf-8")
    return str(path)


def _write_verdict(tmp_path: Path) -> str:
    path = tmp_path / "verdict.json"
    payload = json.dumps(a_verdict(100, 4_100).to_dict(), ensure_ascii=False)
    path.write_text(payload, encoding="utf-8")
    return str(path)


# --- crash/restart, against a real child process ---------------------------------------------

_CHILD_SCRIPT = textwrap.dedent(
    """
    import os, sys
    sys.path.insert(0, {src_path!r})
    from hawedit.durable_workflow import configure_dbos, run_durable
    import hawedit.durable_workflow as durable_module
    from hawedit.pipeline import PipelineRun

    counter_path = {counter_path!r}

    def stub(args, on_event=None):
        with open(counter_path, "a", encoding="utf-8") as handle:
            handle.write("attempt\\n")
        if {crash}:
            os._exit(137)
        return PipelineRun(media_id="crash-case", source="x.mp4", work_dir="work")

    durable_module._build_and_run = stub
    configure_dbos(system_database_url={db_url!r})
    result = run_durable(["nonexistent.mp4"], run_id={run_id!r})
    with open({result_path!r}, "w", encoding="utf-8") as handle:
        handle.write(result["media_id"])
    """
)


def _run_child(
    tmp_path: Path, *, crash: bool, counter_path: Path, db_url: str, run_id: str
) -> tuple[subprocess.CompletedProcess[str], Path]:
    result_path = tmp_path / f"result-{'crash' if crash else 'recover'}.txt"
    script = _CHILD_SCRIPT.format(
        src_path=str(ROOT / "src"),
        counter_path=str(counter_path),
        crash=crash,
        db_url=db_url,
        run_id=run_id,
        result_path=str(result_path),
    )
    script_path = tmp_path / f"child_{'crash' if crash else 'recover'}.py"
    script_path.write_text(script, encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    return proc, result_path


def test_a_process_killed_mid_step_resumes_in_the_next_process(tmp_path: Path) -> None:
    """The crash/restart acceptance gate, against a real second process — not a mock.

    Process one runs `_build_and_run`'s stand-in, writes an "attempt" marker, and calls
    `os._exit(137)` before returning — no exception, no cleanup, nothing DBOS's step wrapper
    gets a chance to record as failed. That is deliberately closer to `kill -9` than to
    `raise`: an ordinary exception is a completed (failed) step, which a coarse `@DBOS.step()`
    correctly does NOT retry; only a step that never returned at all should be `PENDING` for
    the next `launch()` to pick up. Process two, launched fresh against the same SQLite file
    and the same workflow ID, must find that `PENDING` workflow, retry its one step from
    scratch (the "attempt" counter reaching 2 is the proof — DBOS did not silently treat the
    vanished process as done), and complete it. A third call after that, in-process, must not
    add a third attempt: recovery does not turn off the dedup guarantee.
    """
    db_path = tmp_path / "crash.sqlite"
    counter_path = tmp_path / "attempts.log"
    counter_path.write_text("", encoding="utf-8")
    db_url = f"sqlite:///{db_path}"
    run_id = "crash-recovery-case"

    crashed, _crashed_result = _run_child(
        tmp_path, crash=True, counter_path=counter_path, db_url=db_url, run_id=run_id
    )
    assert crashed.returncode != 0, (
        f"the first child was supposed to die via os._exit(137); it exited "
        f"{crashed.returncode} instead. stdout={crashed.stdout!r} stderr={crashed.stderr!r}"
    )
    assert counter_path.read_text(encoding="utf-8").count("attempt") == 1, (
        "the crashing process should have reached the stub exactly once before dying"
    )

    recovered, recovered_result = _run_child(
        tmp_path, crash=False, counter_path=counter_path, db_url=db_url, run_id=run_id
    )
    assert recovered.returncode == 0, (
        f"the recovery process failed: stdout={recovered.stdout!r} stderr={recovered.stderr!r}"
    )
    attempts_after_recovery = counter_path.read_text(encoding="utf-8").count("attempt")
    assert attempts_after_recovery == 2, (
        f"expected exactly one retry on recovery (2 attempts total), got {attempts_after_recovery} "
        f"— either recovery did not happen (workflow lost) or it ran more than once"
    )
    assert recovered_result.read_text(encoding="utf-8") == "crash-case"

    third, _third_result = _run_child(
        tmp_path, crash=False, counter_path=counter_path, db_url=db_url, run_id=run_id
    )
    assert third.returncode == 0, f"stdout={third.stdout!r} stderr={third.stderr!r}"
    assert counter_path.read_text(encoding="utf-8").count("attempt") == 2, (
        "a third call under the completed run_id must return the recorded result, not re-run "
        "the step — recovery must not have disabled the dedup guarantee"
    )

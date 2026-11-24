"""Original routing vs labelled replay, using external model doubles only."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from hawedit.escalation import DEFAULT_DISAGREEMENT_CER, EscalationDecision
from hawedit.pipeline import PipelineRun, _print_report
from hawedit.transcripts import RawTranscript
from test_asr_origin import traced


def legacy(raw: RawTranscript) -> RawTranscript:
    payload = json.loads(raw.to_json())
    del payload["segment_origins"]
    return RawTranscript.from_json(json.dumps(payload))


def report(raw: RawTranscript | None = None) -> PipelineRun:
    return PipelineRun("episode", "not-media", "not-work", raw_diagnostics=raw)


@pytest.mark.parametrize("failure", ["", "transcription", "alignment"])
def test_recorded_routing_uses_original_trace_not_selected_scores(
    tmp_path: Path, failure: str
) -> None:
    raw, _, _ = traced(tmp_path, failure=failure)
    run = replace(report(raw), escalation=(EscalationDecision("unbound", False, "unbound"),))
    payload = run.to_dict()
    assert payload["asr_routing_status"] == "recorded-original"
    assert payload["escalation"]["scored_segments"] == 3
    assert payload["escalation"]["escalated"] == 3
    assert payload["escalation"]["disagreement_threshold_cer"] == DEFAULT_DISAGREEMENT_CER
    assert len(payload["escalation"]["segments"]) == 3
    assert payload["escalation_diagnostics"] is None


def test_legacy_routing_is_unknown_even_when_selected_replay_is_zero(tmp_path: Path) -> None:
    raw, _, _ = traced(tmp_path)
    old = legacy(raw)
    payload = report(old).to_dict()
    assert payload["asr_diagnostics_status"] == "recorded"
    assert payload["asr_routing_status"] == "legacy-selected-replay"
    assert payload["escalation"] is None
    diagnostics = payload["escalation_diagnostics"]
    assert diagnostics["input_evidence"] == "selected-output-replay"
    assert diagnostics["summary"]["scored_segments"] == 3
    assert diagnostics["summary"]["escalated"] == 0
    assert diagnostics["summary"]["segments"] == []
    assert diagnostics["summary"]["disagreement_threshold_cer"] == DEFAULT_DISAGREEMENT_CER


@pytest.mark.parametrize("failure", ["", "transcription", "alignment"])
def test_scored_legacy_replay_retains_count_threshold_and_trigger_partition(
    tmp_path: Path, failure: str
) -> None:
    raw, _, _ = traced(tmp_path, failure=failure)
    old = legacy(raw)
    assert len(old.segment_confidence) == 3
    assert old.segment_origins is None
    payload = json.loads(json.dumps(report(old).to_dict(), allow_nan=False))
    assert payload["asr_routing_status"] == "legacy-selected-replay"
    assert payload["escalation"] is None
    diagnostic = payload["escalation_diagnostics"]
    assert diagnostic["input_evidence"] == "selected-output-replay"
    escalation = diagnostic["summary"]
    assert escalation["scored_segments"] == 3
    assert escalation["escalated"] == (1 if failure else 0)
    assert escalation["escalated"] == len(escalation["segments"])
    assert escalation["disagreement_threshold_cer"] == DEFAULT_DISAGREEMENT_CER
    by_trigger = escalation["by_trigger"]
    assert set(by_trigger) == {"quartile_only", "disagreement_only", "both"}
    assert sum(by_trigger.values()) == escalation["escalated"]


def test_unbound_routing_is_visible_but_not_observed() -> None:
    run = replace(
        report(),
        escalation=(
            EscalationDecision("0-1", False, "confident and agreeing"),
            EscalationDecision("1-2", True, "the models disagree"),
        ),
    )
    payload = run.to_dict()
    assert payload["asr_routing_status"] == "partial-unbound"
    assert payload["escalation"] is None
    diagnostics = payload["escalation_diagnostics"]
    assert diagnostics["input_evidence"] == "unbound-reported"
    assert diagnostics["summary"]["scored_segments"] == 2
    assert diagnostics["summary"]["escalated"] == 1
    assert diagnostics["summary"]["disagreement_threshold_cer"] is None
    assert diagnostics["summary"]["segments"] == [
        {"segment_id": "1-2", "escalate": True, "reason": "the models disagree"}
    ]


@pytest.mark.parametrize(
    "reason", ["unclassified", "bottom-quartile confidence", "models disagree"]
)
def test_unbound_routing_does_not_infer_policy_triggers(reason: str) -> None:
    run = replace(report(), escalation=(EscalationDecision("1-2", True, reason),))
    payload = run.to_dict()
    assert payload["escalation"] is None
    assert payload["escalation_diagnostics"]["summary"]["by_trigger"] is None


@pytest.mark.parametrize("unbound", [False, True])
def test_raw_words_without_segment_scores_do_not_claim_zero_replay(
    tmp_path: Path, unbound: bool
) -> None:
    traced_raw, _, _ = traced(tmp_path)
    raw = replace(legacy(traced_raw), segment_confidence=())
    run = report(raw)
    if unbound:
        run = replace(run, escalation=(EscalationDecision("1-2", True, "unbound"),))
    payload = run.to_dict()
    assert payload["asr_diagnostics_status"] == "recorded"
    assert payload["escalation"] is None
    assert payload["asr_routing_status"] == ("partial-unbound" if unbound else "unavailable")
    if unbound:
        diagnostic = payload["escalation_diagnostics"]
        assert diagnostic["input_evidence"] == "unbound-reported"
        assert diagnostic["summary"]["scored_segments"] == 1
        assert diagnostic["summary"]["escalated"] == 1
        assert diagnostic["summary"]["by_trigger"] is None
        assert diagnostic["summary"]["disagreement_threshold_cer"] is None
    else:
        assert payload["escalation_diagnostics"] is None


def test_missing_routing_is_unavailable_not_zero() -> None:
    payload = report().to_dict()
    assert payload["asr_routing_status"] == "unavailable"
    assert payload["escalation"] is None
    assert payload["escalation_diagnostics"] is None


def test_recorded_zero_is_not_legacy_unknown(tmp_path: Path) -> None:
    raw, _, _ = traced(tmp_path, no_route=True)
    payload = report(raw).to_dict()
    assert payload["asr_routing_status"] == "recorded-original"
    assert payload["escalation"]["scored_segments"] == 3
    assert payload["escalation"]["escalated"] == 0
    assert payload["escalation"]["segments"] == []
    assert payload["escalation_diagnostics"] is None
    old = report(legacy(raw)).to_dict()
    assert old["asr_routing_status"] == "legacy-selected-replay"
    assert old["escalation"] is None
    assert old["escalation_diagnostics"]["summary"]["escalated"] == 0


@pytest.mark.parametrize("old", [False, True])
def test_routing_report_roundtrips_without_changing_canonical_hash(
    tmp_path: Path, old: bool
) -> None:
    raw, _, _ = traced(tmp_path)
    if old:
        raw = legacy(raw)
    original_bytes, original_hash = raw.to_json(), raw.sha256()
    payload = report(raw).to_dict()
    assert json.loads(json.dumps(payload, allow_nan=False)) == payload
    assert raw.to_json() == original_bytes
    assert raw.sha256() == original_hash


@pytest.mark.parametrize("kind", ["recorded", "zero", "legacy", "unbound", "missing"])
def test_console_routing_matches_json_provenance(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], kind: str
) -> None:
    raw, _, _ = traced(tmp_path, no_route=kind == "zero")
    if kind == "legacy":
        raw = legacy(raw)
    run = report(None if kind in {"unbound", "missing"} else raw)
    if kind == "unbound":
        run = replace(run, escalation=(EscalationDecision("1-2", True, "the models disagree"),))
    _print_report(run)
    output = capsys.readouterr().out
    line = next(line for line in output.splitlines() if line.startswith("stage 1"))
    assert "human validation" not in line
    if kind in {"recorded", "zero"}:
        assert ("3/3" if kind == "recorded" else "0/3") in line
        assert "routed to ASR validator" in line
        assert "original" in line
        assert "unknown" not in line
    elif kind == "legacy":
        assert "0/3" in line
        assert "selected-output replay" in line
        assert "original routing unknown" in line
    elif kind == "unbound":
        assert "1/1" in line and "unbound" in line
        assert "original routing unknown" in line
        assert "the models disagree" in line
    else:
        assert "routing unavailable" in line

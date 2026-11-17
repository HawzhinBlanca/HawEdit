"""History structural guards; actual-browser behavior is separate evidence."""

from __future__ import annotations

from hawedit.studio_ui import DASHBOARD_HTML
from test_studio_ui import markup


def _function(name: str, following: str) -> str:
    _, marker, rest = DASHBOARD_HTML.partition(f"function {name}(")
    assert marker
    body, ending, _ = rest.partition(f"function {following}(")
    assert ending
    return body


def test_history_labels_include_identity_date_and_historical_state() -> None:
    body = _function("renderHistory", "refreshHistory")
    assert "job.job_id" in body and "recordedDate(job.created_at)" in body
    assert "job.source" in body and "statusLabels[job.status]" in body
    assert "job.publication_verified !== true" in body
    assert "statusLabels['unverified-historical']" in body
    assert ".map(isolate)" in body and "item.dir = 'auto'" in body
    assert "'\\u2068' + value + '\\u2069'" in body


def test_history_filter_is_local_and_normalized() -> None:
    body = _function("renderHistory", "refreshHistory")
    assert ".normalize('NFKC')" in body and ".toLocaleLowerCase('ckb')" in body
    assert "$('historySearch').value.trim()" in body
    assert "job.job_id" in body and "job.source" in body and ".includes(query)" in body
    assert "fetch(" not in body and "api(" not in body
    assert "$('historySearch').addEventListener('input', () => renderHistory())" in DASHBOARD_HTML


def test_history_filter_preserves_selection_without_loading_a_job() -> None:
    body = _function("renderHistory", "refreshHistory")
    assert "job.job_id === selected" in body
    assert "select.value = selected" in body
    assert "selectJob(" not in body and "clearJob(" not in body and "save(" not in body
    assert "selectedOutside" in body
    assert "historySelectionWarning" in body


def test_history_search_is_semantic_and_announces_results() -> None:
    document = markup()
    tag, attrs = document.element("historySearch")
    assert tag == "input" and attrs["type"] == "search"
    assert attrs["dir"] == "auto" and attrs["aria-controls"] == "jobSelect"
    assert any(
        tag == "label" and attrs.get("for") == "historySearch" for tag, attrs in document.elements
    )
    assert document.element("historyMessage")[1]["role"] == "status"
    assert document.element("historyMessage")[1]["aria-live"] == "polite"
    assert document.element("historySelectionWarning")[1]["aria-live"] == "polite"
    body = _function("renderHistory", "refreshHistory")
    assert "matched.length" in body and "state.historyTruncated" in body


def test_history_dates_refuse_invalid_values() -> None:
    body = _function("recordedDate", "renderHistory")
    assert "typeof value !== 'number'" in body and "!Number.isFinite(value)" in body
    assert "value < 0" in body and "!Number.isFinite(date.getTime())" in body
    assert "return unknown" in body
    assert "toLocaleString('ckb')" in body
    assert "recordedDate(job.created_at)" in _function("selectJob", "selectClip")


def test_history_and_stage_markers_remain_inside_their_boxes() -> None:
    assert "#historyDiagnostics," in DASHBOARD_HTML
    assert "list-style-position: inside" in DASHBOARD_HTML
    assert "overflow-x: hidden" not in DASHBOARD_HTML
    assert "input[type='search']" in DASHBOARD_HTML
    assert "min-block-size: 44px" in DASHBOARD_HTML


def test_history_counts_are_directionally_isolated() -> None:
    body = _function("renderHistory", "refreshHistory")
    assert "'\\u2066' + matched.length" in body
    assert "state.historyJobs.length + '\\u2069'" in body

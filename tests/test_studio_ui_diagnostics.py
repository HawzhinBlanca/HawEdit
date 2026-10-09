"""Diagnostic display contracts; actual browser and native-editor review are separate."""

from __future__ import annotations

import pytest

from hawedit.studio_ui import DASHBOARD_HTML
from test_studio_ui import markup


def _function(name: str, following: str) -> str:
    _, marker, rest = DASHBOARD_HTML.partition(f"function {name}(")
    assert marker, name
    body, ending, _ = rest.partition(f"function {following}(")
    assert ending, following
    return body


@pytest.mark.parametrize(
    ("code", "explanation"),
    [
        ("history_record_refused", "تۆماری مێژوو ونە، نادروستە یان بەستەرە"),
        ("history_storage_unavailable", "پاشەکەوتی مێژووی کارەکان ئامادە نییە"),
        ("history_scan_limit", "پشکنینی مێژوو بەشێکی نیشان داوە"),
        ("candidate_manifest_missing", "تۆماری بڕگە تایبەتەکان نییە"),
        ("candidate_manifest_refused", "تۆماری بڕگە تایبەتەکان نادروستە"),
        ("legacy_recovery_required", "پێش دووبارە ناردنی ئەم کارە کۆنە"),
    ],
)
def test_studio_known_diagnostics_have_sorani_explanations(code: str, explanation: str) -> None:
    body = _function("diagnosticText", "diagnostics")
    assert code in body and explanation in body
    assert "Object.hasOwn(labels, row.code)" in body
    assert "return labels[row.code]" in body


def test_studio_unknown_diagnostics_keep_original_technical_evidence() -> None:
    body = _function("diagnosticText", "diagnostics")
    assert "بەڵگەی کار پشتڕاست نەکراوەتەوە" in body
    assert "row.message" not in body
    details = _function("diagnostics", "stages")
    assert "row.code" in details and "row.job_id" in details and "row.message" in details
    assert "typeof row.code === 'string'" in details
    assert "typeof row.message === 'string'" in details


def test_studio_diagnostic_details_are_semantic_and_text_only() -> None:
    body = _function("diagnostics", "stages")
    assert "document.createElement('details')" in body
    assert "document.createElement('summary')" in body
    assert "وردەکاریی تەکنیکی" in body
    assert "document.createElement('bdi')" in body
    assert "original.dir = 'auto'" in body
    assert "original.textContent =" in body
    assert "diagnosticText(row)" in body
    assert "innerHTML" not in DASHBOARD_HTML
    assert "'rtl'" in body


def test_studio_job_diagnostics_are_cleared_and_adopted() -> None:
    clearing = _function("clearJob", "diagnosticText")
    assert "diagnostics('jobDiagnostics', [])" in clearing
    selection = _function("selectJob", "selectClip")
    assert "diagnostics('jobDiagnostics'," in selection
    assert "job.diagnostics" in selection
    assert "job.code === 'legacy_recovery_required'" in selection
    assert "message: job.error" in selection
    assert "job.diagnostics.map((row) => row.message).join" not in selection
    assert "if (epoch !== state.selectionEpoch) return" in selection


def test_studio_job_diagnostic_list_preserves_accessibility_contract() -> None:
    document = markup()
    tag, attrs = document.element("jobDiagnostics")
    assert tag == "ul" and "hidden" in attrs
    assert attrs["aria-live"] == "polite"
    assert "#jobDiagnostics," in DASHBOARD_HTML
    assert "list-style-position: inside" in DASHBOARD_HTML
    assert "min-block-size: 44px" in DASHBOARD_HTML
    assert "role" not in attrs or attrs["role"] != "alert"


def test_studio_diagnostic_identity_clears_disclosure_focus_border() -> None:
    assert "#historyDiagnostics details > bdi," in DASHBOARD_HTML
    assert "#jobDiagnostics details > bdi" in DASHBOARD_HTML
    _, marker, rule = DASHBOARD_HTML.partition("#jobDiagnostics details > bdi")
    assert marker
    declarations = rule.split("}", 1)[0]
    assert "display: block" in declarations
    assert "margin-block-start: 12px" in declarations

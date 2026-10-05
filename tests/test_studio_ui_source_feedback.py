"""Source-change structural contracts; native browser execution is separate evidence."""

from __future__ import annotations

import pytest

from hawedit.studio_ui import DASHBOARD_HTML


def _source_change() -> str:
    _, marker, remainder = DASHBOARD_HTML.partition(
        "$('videoFile').addEventListener('change', () => {"
    )
    assert marker
    callback, following, _ = remainder.partition("$('uploadBtn').addEventListener('click', upload)")
    assert following
    return callback


@pytest.mark.parametrize(
    "statement",
    [
        "message('uploadMessage', '')",
        "$('uploadProgress').hidden = true",
        "$('uploadProgress').removeAttribute('value')",
    ],
)
def test_studio_ui_source_selection_clears_previous_transfer_feedback(statement: str) -> None:
    assert statement in _source_change()


def test_studio_ui_source_selection_reports_exact_file_bytes() -> None:
    callback = _source_change()
    assert "state.file.size + ' bytes'" in callback
    assert ".toFixed(" not in callback


def test_studio_ui_source_selection_preserves_invalidation() -> None:
    callback = _source_change()
    for statement in (
        "state.source = null",
        "state.ticket = null",
        "save('source', null)",
        "save('upload', null)",
        "message('sourceIdentity', '')",
        "controls()",
    ):
        assert statement in callback
    assert "state.uploadUncertain = false" not in callback
    assert "state.requestUncertain = false" not in callback
    assert "state.runnerReady = true" not in callback

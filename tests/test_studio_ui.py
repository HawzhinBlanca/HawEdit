"""Structural frontend contracts; browser execution is separate acceptance evidence."""

from __future__ import annotations

import re
from html.parser import HTMLParser

import pytest

from hawedit.web import DASHBOARD_HTML


class StudioMarkup(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.elements: list[tuple[str, dict[str, str | None]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.elements.append((tag, dict(attrs)))

    def element(self, identifier: str) -> tuple[str, dict[str, str | None]]:
        matches = [item for item in self.elements if item[1].get("id") == identifier]
        assert len(matches) == 1, identifier
        return matches[0]


def markup() -> StudioMarkup:
    result = StudioMarkup()
    result.feed(DASHBOARD_HTML)
    return result


def test_studio_semantic_controls_and_no_fabricated_quality() -> None:
    document = markup()
    assert document.elements[0] == ("html", {"lang": "ckb", "dir": "rtl"})
    ids = [attrs["id"] for _, attrs in document.elements if "id" in attrs]
    assert len(ids) == len(set(ids))
    tag, picker = document.element("videoFile")
    assert tag == "input" and picker["type"] == "file"
    assert "hidden" not in picker and "display:none" not in str(picker)
    assert any(
        tag == "label" and attrs.get("for") == "videoFile" for tag, attrs in document.elements
    )
    for name in ("startBtn", "reviseBtn", "approveBtn", "exportBtn"):
        assert "disabled" in document.element(name)[1]
    assert document.element("advancedSettings")[0] == "details"
    assert "open" not in document.element("advancedSettings")[1]
    assert document.element("engineStatus")[1]["role"] == "status"
    assert document.element("sourceError")[1]["role"] == "alert"
    assert document.element("jobMessage")[1]["aria-live"] == "polite"
    assert document.element("uploadProgress")[0] == "progress"
    assert "value" not in document.element("uploadProgress")[1]
    assert "value" not in document.element("stageProgress")[1]
    assert "alert(" not in DASHBOARD_HTML and "virality_score" not in DASHBOARD_HTML
    assert 'class="step completed"' not in DASHBOARD_HTML
    assert "innerHTML" not in DASHBOARD_HTML
    assert "overflow-x: hidden" not in DASHBOARD_HTML
    assert "minmax(0," in DASHBOARD_HTML and "min-inline-size: 0" in DASHBOARD_HTML
    assert "min-block-size: 44px" in DASHBOARD_HTML


def test_studio_ui_upload_and_submission_contract() -> None:
    assert "api('/api/uploads'" in DASHBOARD_HTML
    assert "JSON.stringify({ filename: file.name, size: file.size })" in DASHBOARD_HTML
    assert "xhr.open('PUT', '/api/uploads/'" in DASHBOARD_HTML
    assert "xhr.send(file)" in DASHBOARD_HTML
    assert "event.lengthComputable" in DASHBOARD_HTML
    assert "source_id: state.source.source_id" in DASHBOARD_HTML
    assert "schema: 1" in DASHBOARD_HTML
    assert "api('/api/repurpose'" in DASHBOARD_HTML
    assert "source: file.name" not in DASHBOARD_HTML
    assert "Content-Length'" not in DASHBOARD_HTML
    assert "async function recoverUpload" in DASHBOARD_HTML
    assert "result.state === 'ready'" in DASHBOARD_HTML
    assert "state.uploadUncertain = true" in DASHBOARD_HTML


def test_studio_ui_persists_bound_submission_before_egress() -> None:
    persistence = DASHBOARD_HTML.index("save('request', state.request)")
    submission = DASHBOARD_HTML.index("api('/api/repurpose'")
    assert persistence < submission
    assert "crypto.randomUUID()" in DASHBOARD_HTML
    assert "state.requestUncertain" in DASHBOARD_HTML
    assert "body: JSON.stringify(state.request)" in DASHBOARD_HTML
    assert "localStorage.setItem" in DASHBOARD_HTML
    assert "sessionStorage" not in DASHBOARD_HTML
    assert "studio_runner_unavailable" in DASHBOARD_HTML
    assert "state.request = null" in DASHBOARD_HTML
    assert "applyOptions(request.options)" in DASHBOARD_HTML
    assert "save('options', options())" in DASHBOARD_HTML
    assert "validOptions(request.options)" in DASHBOARD_HTML


def test_studio_ui_history_and_preview_are_explicit() -> None:
    document = markup()
    assert document.element("jobSelect")[0] == "select"
    assert "api('/api/history')" in DASHBOARD_HTML
    assert "jobs.find(" not in DASHBOARD_HTML
    assert "historical" in DASHBOARD_HTML and "unverified-historical" in DASHBOARD_HTML
    assert "function clearPreview" in DASHBOARD_HTML
    assert "player.removeAttribute('src')" in DASHBOARD_HTML
    assert "selectionEpoch" in DASHBOARD_HTML
    assert "previewEpoch" in DASHBOARD_HTML
    assert "$('player').addEventListener('error'" in DASHBOARD_HTML
    assert "method: 'HEAD'" in DASHBOARD_HTML
    assert "X-HawEdit-Artifact-State" in DASHBOARD_HTML
    assert "encodeURIComponent" in DASHBOARD_HTML
    assert "unknown" in DASHBOARD_HTML
    assert "setInterval" not in DASHBOARD_HTML
    assert "downloadBtn.href = clip.video_url" not in DASHBOARD_HTML


def test_studio_ui_assets_remain_local() -> None:
    document = markup()
    for tag, attrs in document.elements:
        for field in ("src", "href"):
            value = attrs.get(field)
            assert not value or not value.startswith(("http:", "https:", "//")), (tag, value)
    assert "url('/assets/fonts/Vazirmatn.ttf')" in DASHBOARD_HTML
    assert "fonts.googleapis" not in DASHBOARD_HTML
    assert "Vazirmatn" in DASHBOARD_HTML


@pytest.mark.parametrize(
    ("foreground", "background", "minimum"),
    [
        ("text", "bg", 4.5),
        ("text", "surface", 4.5),
        ("muted", "bg", 4.5),
        ("muted", "surface", 4.5),
        ("gold", "bg", 4.5),
        ("error", "bg", 4.5),
        ("accent", "bg", 4.5),
        ("border", "surface", 3.0),
    ],
)
def test_studio_ui_declared_color_pairs_meet_contrast(
    foreground: str, background: str, minimum: float
) -> None:
    """Calculated declared CSS pairs, not a rendered-pixel or complete-AA certificate."""
    colors = dict(re.findall(r"--([a-z]+):\s*(#[a-f0-9]{6});", DASHBOARD_HTML))

    def luminance(color: str) -> float:
        rgb = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [
            value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in rgb
        ]
        return sum(
            value * weight for value, weight in zip(linear, (0.2126, 0.7152, 0.0722), strict=True)
        )

    values = sorted((luminance(colors[foreground]), luminance(colors[background])))
    assert (values[1] + 0.05) / (values[0] + 0.05) >= minimum


def test_studio_ui_superseded_requests_cannot_replace_selection() -> None:
    assert "if (epoch !== state.selectionEpoch) return" in DASHBOARD_HTML
    assert "if (epoch !== state.previewEpoch) return" in DASHBOARD_HTML
    assert "if (epoch !== state.historyEpoch) return" in DASHBOARD_HTML
    assert "if (epoch !== state.readinessEpoch) return" in DASHBOARD_HTML
    assert "state.previewController.abort()" in DASHBOARD_HTML
    assert "Boolean(state.source)" in DASHBOARD_HTML
    assert "$('videoFile').disabled = locked || state.uploadUncertain" in DASHBOARD_HTML
    assert 'id="studio" tabindex="-1"' in DASHBOARD_HTML

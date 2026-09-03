"""Unit tests for DaVinci Resolve Studio live editorial integration bridge."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from hawedit.delivery import build_edl
from hawedit.resolve import (
    ResolveImportError,
    ResolveImportResult,
    ResolveUnavailableError,
    build_parser,
    get_resolve,
    import_to_resolve,
)
from test_timeline import a_clip


def test_get_resolve_raises_informative_error_when_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When DaVinciResolveScript is not installed or import fails, raise ResolveUnavailableError."""
    import sys

    # Simulate module not being found
    monkeypatch.setitem(sys.modules, "DaVinciResolveScript", None)

    with pytest.raises(ResolveUnavailableError, match="could not be imported|returned None"):
        get_resolve()


def test_import_to_resolve_refuses_missing_bundle() -> None:
    """Nonexistent bundle paths must raise FileNotFoundError."""
    with pytest.raises(FileNotFoundError, match="does not exist"):
        import_to_resolve(Path("nonexistent_bundle_dir_xyz"))


def test_import_to_resolve_refuses_missing_edl(tmp_path: Path) -> None:
    """A bundle directory without an EDL file cannot be conformed."""
    bundle = tmp_path / "empty_bundle"
    bundle.mkdir()
    (bundle / "clip.json").write_text("{}", encoding="utf-8")

    with pytest.raises(FileNotFoundError, match="No .edl"):
        import_to_resolve(bundle)


def test_import_to_resolve_conforms_916_vertical_timeline_and_markers(
    tmp_path: Path,
) -> None:
    """Verify end-to-end timeline creation, 9:16 vertical geometry configuration,
    editorial marker placement, and subtitle ingestion against mock Resolve instance.
    """
    bundle = tmp_path / "clip-01"
    bundle.mkdir()

    # 1. Write EDL
    edl_content = build_edl(2000, 32000, fps=25.0, title="clip-01")
    (bundle / "clip-01.edl").write_text(edl_content, encoding="utf-8")

    # 2. Write Clip JSON
    clip = a_clip(in_ms=2000, out_ms=32000, payoff_at_ms=20000)
    (bundle / "clip-01.json").write_text(
        json.dumps(clip.to_dict(), ensure_ascii=False), encoding="utf-8"
    )

    # 3. Write SRT
    srt_content = "1\n00:00:02,000 --> 00:00:05,000\nسڵاو لە هەمووان\n"
    (bundle / "clip-01.srt").write_text(srt_content, encoding="utf-8")

    # Mock Resolve Studio API hierarchy
    mock_timeline = MagicMock()
    mock_timeline.GetName.return_value = "clip-01"
    mock_timeline.SetSetting.return_value = True
    mock_timeline.AddMarker.return_value = True

    mock_media_pool = MagicMock()
    mock_media_pool.ImportTimelineFromFile.return_value = mock_timeline
    mock_media_pool.ImportMedia.return_value = [MagicMock()]

    mock_project = MagicMock()
    mock_project.GetName.return_value = "HawEdit_Reels"
    mock_project.GetMediaPool.return_value = mock_media_pool

    mock_pm = MagicMock()
    mock_pm.GetCurrentProject.return_value = mock_project

    mock_resolve = MagicMock()
    mock_resolve.GetProjectManager.return_value = mock_pm

    # Execute import
    result = import_to_resolve(bundle, resolve_app=mock_resolve)

    assert isinstance(result, ResolveImportResult)
    assert result.project_name == "HawEdit_Reels"
    assert result.timeline_name == "clip-01"
    assert result.width == 1080
    assert result.height == 1920
    assert result.subtitle_imported is True
    assert result.markers_count > 0

    # Assert 9:16 vertical settings were applied
    mock_timeline.SetSetting.assert_any_call("useCustomSettings", "1")
    mock_timeline.SetSetting.assert_any_call("timelineResolutionWidth", "1080")
    mock_timeline.SetSetting.assert_any_call("timelineResolutionHeight", "1920")

    # Assert EDL timeline import called
    mock_media_pool.ImportTimelineFromFile.assert_called_once()

    # Assert subtitle imported
    mock_media_pool.ImportMedia.assert_called_once()


def test_import_to_resolve_handles_timeline_creation_failure(tmp_path: Path) -> None:
    """When Resolve returns None for ImportTimelineFromFile, raise ResolveImportError."""
    bundle = tmp_path / "fail_bundle"
    bundle.mkdir()
    (bundle / "test.edl").write_text("TITLE: Fail\n", encoding="utf-8")

    mock_media_pool = MagicMock()
    mock_media_pool.ImportTimelineFromFile.return_value = None

    mock_project = MagicMock()
    mock_project.GetName.return_value = "TestProj"
    mock_project.GetMediaPool.return_value = mock_media_pool

    mock_pm = MagicMock()
    mock_pm.GetCurrentProject.return_value = mock_project

    mock_resolve = MagicMock()
    mock_resolve.GetProjectManager.return_value = mock_pm

    with pytest.raises(ResolveImportError, match="failed to import EDL"):
        import_to_resolve(bundle, resolve_app=mock_resolve)


def test_resolve_cli_parser() -> None:
    """Verify CLI argument parsing for hawedit.resolve."""
    parser = build_parser()
    args = parser.parse_args(
        [
            "import",
            "work/my-clip",
            "--project",
            "Episode_29",
            "--timeline",
            "Hook_01",
            "--fps",
            "30.0",
        ]
    )
    assert args.command == "import"
    assert args.bundle == "work/my-clip"
    assert args.project == "Episode_29"
    assert args.timeline == "Hook_01"
    assert args.fps == 30.0

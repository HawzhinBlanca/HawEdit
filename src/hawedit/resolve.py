"""DaVinci Resolve Studio live editorial integration bridge.

Connects HawEdit's validated delivery bundles directly into running DaVinci Resolve Studio
instances, conforming 9:16 vertical timelines with EDL cuts, Kurdish subtitle tracks,
and colored editorial markers for Hook, Payoff, Punch-Ins, Speaker Turns, and Sentences.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import platform
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hawedit.clip import Clip
from hawedit.timeline import build_clip_markers


class ResolveError(Exception):
    """Base exception for DaVinci Resolve integration failures."""


class ResolveUnavailableError(ResolveError):
    """Raised when DaVinci Resolve is not installed, not running, or scripting is inaccessible."""


class ResolveImportError(ResolveError):
    """Raised when timeline creation or media import fails inside DaVinci Resolve."""


@dataclass(frozen=True, slots=True)
class ResolveImportResult:
    """Outcome of importing a HawEdit delivery bundle into DaVinci Resolve."""

    project_name: str
    timeline_name: str
    width: int
    height: int
    markers_count: int
    subtitle_imported: bool


def _setup_resolve_scripting_paths() -> None:
    """Register standard operating system paths for DaVinci Resolve scripting libraries."""
    system = platform.system()
    if system == "Windows":
        lib_path = Path("C:/Program Files/Blackmagic Design/DaVinci Resolve/fusionscript.dll")
        module_path = Path(
            "C:/ProgramData/Blackmagic Design/DaVinci Resolve/Support/Developer/Scripting/Modules"
        )
        if lib_path.exists() and "RESOLVE_SCRIPT_LIB" not in os.environ:
            os.environ["RESOLVE_SCRIPT_LIB"] = str(lib_path)
        if module_path.exists() and str(module_path) not in sys.path:
            sys.path.append(str(module_path))
    elif system == "Darwin":
        module_path = Path(
            "/Library/Application Support/Blackmagic Design"
            "/DaVinci Resolve/Developer/Scripting/Modules"
        )
        if module_path.exists() and str(module_path) not in sys.path:
            sys.path.append(str(module_path))
    elif system == "Linux":
        lib_path = Path("/opt/resolve/libs/Fusion/fusionscript.so")
        module_path = Path("/opt/resolve/Developer/Scripting/Modules")
        if lib_path.exists() and "RESOLVE_SCRIPT_LIB" not in os.environ:
            os.environ["RESOLVE_SCRIPT_LIB"] = str(lib_path)
        if module_path.exists() and str(module_path) not in sys.path:
            sys.path.append(str(module_path))


def get_resolve() -> Any:
    """Acquire the active DaVinci Resolve Studio application scripting instance.

    Raises:
        ResolveUnavailableError: if Resolve is not running or scripting modules are missing.
    """
    _setup_resolve_scripting_paths()
    try:
        import DaVinciResolveScript as dvr  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ResolveUnavailableError(
            "DaVinci Resolve scripting module (DaVinciResolveScript) could not be imported. "
            "Ensure DaVinci Resolve Studio is installed and scripting libraries are present."
        ) from exc

    try:
        app = dvr.scriptapp("Resolve")
    except Exception as exc:
        raise ResolveUnavailableError(
            f"Failed to connect to DaVinci Resolve scriptapp: {exc}"
        ) from exc

    if app is None:
        raise ResolveUnavailableError(
            "Connected to scripting API but Resolve application instance returned None. "
            "Ensure DaVinci Resolve is open and running."
        )
    return app


def _find_bundle_file(bundle_path: Path, extension: str) -> Path | None:
    """Find the single file matching the given extension in bundle directory or path."""
    resolved = bundle_path.resolve()
    if resolved.is_file():
        stem = resolved.stem
        candidate = resolved.parent / f"{stem}.{extension}"
        if candidate.exists():
            return candidate.resolve()
        return None

    matches = sorted(resolved.glob(f"*.{extension}"))
    return matches[0].resolve() if matches else None


def import_to_resolve(
    bundle_dir: Path | str,
    *,
    project_name: str | None = None,
    timeline_name: str | None = None,
    target_width: int = 1080,
    target_height: int = 1920,
    fps: float = 25.0,
    resolve_app: Any = None,
) -> ResolveImportResult:
    """Import a delivery bundle into DaVinci Resolve as a conformed 9:16 vertical timeline."""
    path = Path(bundle_dir).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Bundle path does not exist: {path}")

    edl_path = _find_bundle_file(path, "edl")
    if not edl_path:
        raise FileNotFoundError(f"No .edl timeline file found in bundle {path}")

    json_path = _find_bundle_file(path, "json")
    srt_path = _find_bundle_file(path, "srt")

    resolve = resolve_app if resolve_app is not None else get_resolve()
    pm = resolve.GetProjectManager()
    project = pm.GetCurrentProject()
    if project is None:
        proj_name = project_name or "HawEdit_Reels"
        project = pm.CreateProject(proj_name)
        if project is None:
            raise ResolveImportError(
                f"Failed to acquire or create project '{proj_name}' in Resolve"
            )
    proj_name = str(project.GetName())

    media_pool = project.GetMediaPool()
    tl_name = timeline_name or (edl_path.stem if edl_path else "HawEdit_Timeline")

    options = {
        "timelineName": tl_name,
        "importSourceClips": False,
    }
    timeline = media_pool.ImportTimelineFromFile(str(edl_path), options)
    if timeline is None:
        raise ResolveImportError(f"DaVinci Resolve failed to import EDL timeline from '{edl_path}'")

    # Configure 9:16 vertical resolution
    timeline.SetSetting("useCustomSettings", "1")
    timeline.SetSetting("timelineResolutionWidth", str(target_width))
    timeline.SetSetting("timelineResolutionHeight", str(target_height))

    # Read editorial metadata and populate markers
    markers_count = 0
    if json_path and json_path.exists():
        try:
            raw_data = json.loads(json_path.read_text(encoding="utf-8"))
            try:
                clip = Clip.from_dict(raw_data)
                markers = build_clip_markers(clip, fps=fps)
            except Exception:
                markers = []
                in_ms = int(raw_data.get("in_ms", 0))
                out_ms = int(raw_data.get("out_ms", 0))
                hook_dur = max(1, int(round(3.0 * fps)))
                markers.append(
                    {
                        "name": "Hook (0-3s)",
                        "color": "Red",
                        "marked_range": {
                            "start_time": {"value": 0.0},
                            "duration": {"value": float(hook_dur)},
                        },
                        "metadata": {"type": "hook"},
                    }
                )
                ed = raw_data.get("editorial") or {}
                payoff_ms = ed.get("payoff_at_ms")
                if payoff_ms is not None and in_ms <= payoff_ms <= out_ms:
                    p_offset_s = (payoff_ms - in_ms) / 1000.0
                    p_frame = int(round(p_offset_s * fps))
                    markers.append(
                        {
                            "name": "Payoff / Core Insight",
                            "color": "Blue",
                            "marked_range": {
                                "start_time": {"value": float(p_frame)},
                                "duration": {"value": float(max(1, int(round(1.5 * fps))))},
                            },
                            "metadata": {"type": "payoff"},
                        }
                    )

            for marker in markers:
                marked_range = marker.get("marked_range", {})
                start_time = marked_range.get("start_time", {})
                duration = marked_range.get("duration", {})
                start_frame = int(round(float(start_time.get("value", 0))))
                dur_frames = max(1, int(round(float(duration.get("value", 1)))))
                name = str(marker.get("name", "Marker"))
                color = str(marker.get("color", "Blue")).title()
                note = f"HawEdit editorial marker ({marker.get('metadata', {}).get('type', '')})"
                if timeline.AddMarker(start_frame, color, name, note, dur_frames):
                    markers_count += 1
        except Exception:
            # Metadata read failures do not abort timeline creation
            pass

    # Import subtitle into media pool if present
    subtitle_imported = False
    if srt_path and srt_path.exists():
        with contextlib.suppress(Exception):
            items = media_pool.ImportMedia([str(srt_path)])
            if items and len(items) > 0:
                subtitle_imported = True

    with contextlib.suppress(Exception):
        resolve.OpenPage("edit")

    return ResolveImportResult(
        project_name=proj_name,
        timeline_name=tl_name,
        width=target_width,
        height=target_height,
        markers_count=markers_count,
        subtitle_imported=subtitle_imported,
    )


def build_parser() -> argparse.ArgumentParser:
    """Build command line argument parser for hawedit.resolve."""
    parser = argparse.ArgumentParser(
        prog="python -m hawedit.resolve",
        description="DaVinci Resolve Studio live editorial integration bridge for HawEdit.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    import_cmd = subparsers.add_parser(
        "import", help="Import a HawEdit delivery bundle into DaVinci Resolve Studio."
    )
    import_cmd.add_argument(
        "bundle",
        type=str,
        help="Path to delivery bundle directory or clip root.",
    )
    import_cmd.add_argument(
        "--project",
        type=str,
        default=None,
        help="Target DaVinci Resolve project name (defaults to active project).",
    )
    import_cmd.add_argument(
        "--timeline",
        type=str,
        default=None,
        help="Target timeline name in DaVinci Resolve.",
    )
    import_cmd.add_argument(
        "--fps",
        type=float,
        default=25.0,
        help="Video frame rate for marker calculation (default: 25.0).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for hawedit.resolve."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "import":
        try:
            result = import_to_resolve(
                args.bundle,
                project_name=args.project,
                timeline_name=args.timeline,
                fps=args.fps,
            )
            print("==> Successfully conformed timeline into DaVinci Resolve Studio:")
            print(f"    Project:   {result.project_name}")
            print(f"    Timeline:  {result.timeline_name}")
            print(f"    Format:    {result.width}x{result.height} (9:16 vertical)")
            print(f"    Markers:   {result.markers_count} editorial markers placed")
            sub_status = "Imported into Media Pool" if result.subtitle_imported else "None"
            print(f"    Subtitles: {sub_status}")
            return 0
        except ResolveError as exc:
            print(f"Resolve Error: {exc}", file=sys.stderr)
            return 1
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

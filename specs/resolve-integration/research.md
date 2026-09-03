# Research — DaVinci Resolve Studio Live Integration (`specs/resolve-integration`)

> Grounding and measured facts for the DaVinci Resolve Studio live editorial integration on `HAWAPC01`.
> Companion to `specs/frontier-rating-2026-09` (editorial handoff architecture) and `specs/pro-grade-program`.

## 1. System & Environment Facts
- **Host**: `HAWAPC01`, Windows 11 Pro, AMD Ryzen Threadripper 3990X, 2× RTX 3090 Ti 24 GB.
- **DaVinci Resolve Studio**: Version 21 installed at `C:\Program Files\Blackmagic Design\DaVinci Resolve\Resolve.exe`.
- **Scripting Library**: `C:\Program Files\Blackmagic Design\DaVinci Resolve\fusionscript.dll`.
- **Python Scripting Module**: `C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting\Modules\DaVinciResolveScript.py`.
- **Required Environment Variables**:
  - `RESOLVE_SCRIPT_LIB = "C:\Program Files\Blackmagic Design\DaVinci Resolve\fusionscript.dll"`
  - `PYTHONPATH` including `C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting\Modules`.

## 2. DaVinci Resolve Scripting API Capabilities & Behaviors
Measured directly against the live running instance (`UUID: bff00616-fcf4-4439-bd91-04c5af14b0a4`):

1. **Connection**:
   ```python
   import DaVinciResolveScript as dvr
   resolve = dvr.scriptapp("Resolve")
   # Returns Resolve (0x00007FF707F10570) [App: 'Resolve' on 127.0.0.1]
   ```
2. **Project & Media Pool Access**:
   ```python
   pm = resolve.GetProjectManager()
   project = pm.GetCurrentProject() # or pm.CreateProject(name)
   media_pool = project.GetMediaPool()
   ```
3. **Timeline Import**:
   - `media_pool.ImportTimelineFromFile(filePath, {importOptions})`:
     - Supported formats: AAF, EDL, XML, FCPXML, DRT, ADL, OTIO.
     - When media file paths are relative or separate from project disks, `importSourceClips: False` safely conforms timeline edits without aborting.
     - Verified: EDL import successfully creates timeline object `Timeline (0x00000276C8CAB6C0)` and switches active page.
4. **Timeline Formatting (9:16 Vertical Reel Mode)**:
   - Setting custom dimensions:
     ```python
     timeline.SetSetting("useCustomSettings", "1")
     timeline.SetSetting("timelineResolutionWidth", "1080")
     timeline.SetSetting("timelineResolutionHeight", "1920")
     ```
   - Verified: Live resolution shifts from 1920×1080 to 1080×1920.
5. **Editorial Markers**:
   - `timeline.AddMarker(frame, color, name, note, duration, customData)`
   - Color values supported: `Red`, `Blue`, `Yellow`, `Cyan`, `Green`, etc.
   - Verified: Markers placed at exact frame indices:
     - Frame 0: `Red` (Hook, 75 frames / 3 sec)
     - Frame 125: `Yellow` (Punch-In cut, 12 frames)
     - Frame 500: `Blue` (Payoff, 38 frames)
   - `timeline.GetMarkers()` returns structured dictionary validating all placed markers.
6. **Subtitle Media Asset Import**:
   - `media_pool.ImportMedia([srt_path])`:
     - Successfully registers the Kurdish `.srt` file as a Subtitle MediaPoolItem.

## 3. Design Requirements
- **Module**: `src/hawedit/resolve.py`
  - Encapsulate connection, project acquisition, timeline creation, format configuration, marker synchronization, and subtitle ingestion.
  - Zero-dependency runtime: when `DaVinciResolveScript` is not on sys.path or Resolve is not running, provide clean error typing (`ResolveConnectionError`, `ResolveImportError`) with informative diagnostic messages.
- **CLI Command**:
  - `python -m hawedit.resolve import <bundle_or_dir>`
- **Testability**:
  - `tests/test_resolve.py`: Mock-based unit tests for all operations (100% executable without requiring Resolve running in CI), plus integration readiness check.

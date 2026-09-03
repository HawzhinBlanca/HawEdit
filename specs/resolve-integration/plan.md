# Plan — DaVinci Resolve Studio Live Integration (`specs/resolve-integration`)

Approved-by: Hawa

> Companion to `specs/frontier-rating-2026-09` and `specs/pro-grade-program`.
> Connects HawEdit's editorial delivery bundles directly into live DaVinci Resolve Studio timelines.

---

## 1. Goal
Provide a native Python bridge (`hawedit.resolve`) connecting HawEdit's validated delivery bundles directly into running DaVinci Resolve Studio instances on `HAWAPC01`, creating 9:16 vertical timelines populated with EDL edits, Kurdish subtitles, and colored editorial markers (Hook, Payoff, Punch-Ins, Speaker Turns, Sentences).

---

## 2. Proposed Architecture

### 2.1 `src/hawedit/resolve.py`
1. **Connection**:
   - `get_resolve() -> Any`: Probes standard Windows/macOS/Linux paths for `fusionscript.dll` / `DaVinciResolveScript.py` and returns the live `Resolve` instance or raises `ResolveUnavailableError`.
2. **Timeline Import**:
   - `import_to_resolve(bundle_dir: Path | str, project_name: str | None = None, timeline_name: str | None = None) -> ResolveImportResult`:
     - Discovers `.edl`, `.srt`, `.json` from the delivery bundle.
     - Acquires or creates the project in Resolve.
     - Imports EDL to construct the conformed edit track.
     - Sets timeline settings to 1080×1920 vertical (`useCustomSettings=1`).
     - Adds colored editorial markers:
       - **Hook** (`Red`, 0..3s)
       - **Payoff** (`Blue`)
       - **Punch-In cuts** (`Yellow`)
       - **Speaker turns** (`Cyan`)
       - **Sentences** (`Green`)
     - Imports `.srt` subtitle into the active Media Pool folder.
3. **CLI Entry Point**:
   - `main(argv=None) -> int`:
     - `python -m hawedit.resolve import <bundle_dir>`
     - Prints human-readable summary of created timeline, geometry, and marker counts.

---

## 3. Tasks

- [ ] T1 Implement `src/hawedit/resolve.py` with Resolve connection, timeline creation, 9:16 configuration, marker mapping, and subtitle import
- [ ] T2 Implement CLI interface for `hawedit.resolve`
- [ ] T3 Implement unit test suite in `tests/test_resolve.py` verifying connection diagnostics, marker translation, resolution setting, and mock Resolve API interactions
- [ ] T4 Execute live import of canonical clip into running DaVinci Resolve Studio instance and record proof

---

## 4. Verification Plan

1. **Unit Tests (`tests/test_resolve.py`)**:
   - Verify connection resolution handles missing DLL/script with informative `ResolveUnavailableError`.
   - Verify marker translation matches frame indices and colors.
   - Verify mock Resolve execution sets 1080×1920 custom resolution and adds all markers.
2. **Gate Verification**:
   - Run `bash scripts/verify.sh` to ensure full test suite passes and typecheck/lint are clean.
3. **Live DaVinci Resolve Verification**:
   - Execute `python -m hawedit.resolve import` against live Resolve Studio on `HAWAPC01`.

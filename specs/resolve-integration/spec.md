# Spec — DaVinci Resolve Studio Live Integration (`specs/resolve-integration`)

## Acceptance Criteria (EARS Format)

- **CRIT-1**: WHEN `get_resolve()` is called on a system where DaVinci Resolve is not running or scripting libraries are absent, THE system SHALL raise `ResolveUnavailableError` with diagnostic installation paths.
- **CRIT-2**: WHEN `import_to_resolve(bundle_dir)` is called with a valid HawEdit delivery bundle and Resolve is active, THE system SHALL import the EDL file to create a timeline in the active project.
- **CRIT-3**: WHEN a timeline is created in Resolve by `import_to_resolve`, THE system SHALL configure the timeline to 9:16 vertical resolution (1080×1920) using `useCustomSettings=1`.
- **CRIT-4**: WHEN editorial metadata is present in the clip bundle (hook, payoff, punch-in cuts, speaker turns, sentences), THE system SHALL populate colored timeline markers matching the exact frame offsets and duration.
- **CRIT-5**: WHEN a `.srt` subtitle file exists in the bundle, THE system SHALL import the subtitle asset into the active Media Pool folder.
- **CRIT-6**: WHEN `python -m hawedit.resolve import <bundle_dir>` is invoked from the CLI, THE system SHALL execute the import and output the timeline name, dimensions, and marker counts.

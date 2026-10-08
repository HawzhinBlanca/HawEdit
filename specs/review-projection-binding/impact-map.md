# Caller Impact

Actual Serena references at c163511, six-pair map cited in research.md.

| Symbol | Actual callers and required verification |
|---|---|
| studio_generation._candidate_view | project_generation_result single-render and episode branches; new binding regressions, entire test_studio_generation/test_web modules |
| studio_generation._sha256 | _candidate_view only; remove ordinary-open duplicate when shared inspection replaces it |
| project_generation_result | test_studio_generation, test_web candidate URL projection; signature unchanged, preserve private states/outcomes |
| studio_artifacts.open_preview | HawEditWebHandler._serve_preview; entire test_studio_artifacts/test_web, range/snapshot/disconnect regressions |
| studio_artifacts._regular | _record_snapshot, open_preview, font_bytes; unchanged implementation, new inspector consumes it |
| studio_artifacts._record_snapshot | _record and read_studio_record; unchanged implementation, new inspector consumes it |

New shared inspection has no pre-existing callers. It grants no decoded-media or
publication authority. Do not alter preview snapshot immutability or add a second
MP4 copy to generation projection.

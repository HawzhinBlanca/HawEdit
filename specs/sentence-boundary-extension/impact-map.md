# Impact Map: Sentence Boundary Extension (Task T4.8)

## 1. Direct Symbols Affected
- `hawedit.pipeline.run_pipeline`: Boundary post-fusion validation logic (lines 2224-2248).
  Instead of immediately failing on `uncaptioned`, checks if touched sentences are completely covered by `[boundary.final_in_ms, boundary.final_out_ms]`. If yes, merges them into `selected`. If no, records `would_ship_uncaptioned` as before.

## 2. Callers & Dependents
- All downstream stages in `pipeline.py`: `clip_words`, `raw_clip_text`, `selected` passed to `build_ass`, `build_srt`, and `ClipTranscript`.
- `tests/test_pipeline.py`:
  - Existing `test_uncaptioned_speech_prevents_render` remains green because the boundary partially cuts the second sentence.
  - New test `test_boundary_extension_completes_enclosed_sentence`: verifies that an enclosed complete sentence is absorbed and rendered without skipping.

# Implementation Plan: Sentence Boundary Extension (Task T4.8)

## Proposed Changes

### Task T1: Sentence Absorption Logic in `src/hawedit/pipeline.py`
- In `run_pipeline`:
  Analyze `uncaptioned` words.
  Find all sentences `s in sentences` that contain any word in `uncaptioned`.
  Check if every such sentence `s` satisfies:
  `all(w.start_ms >= boundary.final_in_ms and w.end_ms <= boundary.final_out_ms for w in s.words)`.
  If True and sentences are adjacent to `selected`:
  Absorb them into `selected = tuple(sorted(set(selected) | set(touched_sentences), key=lambda s: s.words[0].start_ms))`.
  Recalculate `selected_words`.
  If False:
  Proceed to `would_ship_uncaptioned = StageSkipped(...)` as before.

### Task T2: Unit Tests in `tests/test_pipeline.py`
- Add `test_boundary_extension_completes_enclosed_sentence`:
  Constructs a scenario where soft expansion encloses a short complete sentence.
  Verifies the boundary is accepted, `run.clip` is created, and the absorbed sentence words appear in `run.clip.transcript.words`.
- Verify existing `test_uncaptioned_speech_prevents_render` still passes.

### Task T3: Verification & Gate
- Run `verify.sh --fast` and full `verify.sh`.
- Ratchet floor if new test is added.
- Update ledger.

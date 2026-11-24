# Plan — C1 Sentence-number discovery

Read `research.md` first.

## Approach

Replace millisecond guessing and the 4,000-word `_timing_table` in `src/hawedit/path_a.py` with 0-based numbered normalized sentences mapped deterministically in code to CTC word timings (`Sentence.start_ms`, `Sentence.end_ms` from `hawedit.sentences`):

1. **Sentence-indexed prompt & schema (`path_a.py`):**
   - Replace `in_ms` / `out_ms` in `CANDIDATE_SCHEMA` with integer `start_sentence` and `end_sentence` (`0 <= start_sentence <= end_sentence < len(sentences)`).
   - Remove `_timing_table(limit=4000)` (`path_a.py:120-132`). Build `_numbered_sentences(sentences)` using `normalize_sorani(sentence.text)` for every sentence in `0..len(sentences)-1`, enforcing invariant #3 (`assert_model_input(transcript)` plus normalizing sentence surface forms derived from raw aligned words) and failing visibly (`JudgeUnusable`) if `sentences` is empty or contains non-positive timestamps.
   - Include clean guidance in `_PROMPT` explaining 0-based inclusive `[i]` indexing and `[min_s..max_s]` duration target (`D-254`), while guaranteeing zero word-count truncation.
2. **Exact CTC boundary snap & fail-stop (`path_a.py`):**
   - In `PathADiscovery._to_candidates(..., sentences=sentences)`, validate `isinstance(..., int) and not isinstance(..., bool)`, `0 <= start_sentence <= end_sentence < len(sentences)`, and assert complete-sentence validity (`all(s.complete for s in selected_slice)` — or require `anchors_for(selected_slice)` covers the full requested slice `[sentences[start_sentence].start_ms, sentences[end_sentence].end_ms]`, raising `JudgeUnusable` if either boundary sentence has `complete == False` so half-finished fragments fail visibly instead of silently truncating or guessing!).
   - Map directly to `in_ms = sentences[start_sentence].start_ms`, `out_ms = sentences[end_sentence].end_ms`, preserve dense 1-based ranking (`(-score, in_ms)`), and update the K-run SHA-256 cache key in `PathADiscovery.discover` (`path_a.py:237`) to hash `(transcript.text_ckb, [(s.start_ms, s.end_ms, s.complete) for s in sentences])`.
3. **Pipeline & caller integration (`pipeline.py`, `smoke.py`):**
   - Keep `PathADiscovery.discover(transcript, *, k=None, sentences=None)` backward-compatible: if `sentences is None`, derive `segment_sentences(transcript.words)` once; if supplied by `pipeline.py:3289` (`sentences` already segmented at `pipeline.py:3251`), reuse it directly. Update `pipeline.py:3289` to inspect or pass `sentences` cleanly when calling a `PathADiscovery`-compatible discoverer while still supporting custom `discover(normalized)` callables in tests.
4. **Update existing byte/prompt assertions (`tests/test_path_a.py`, `tests/test_review_findings.py`):**
   - Update `test_path_a.py` fixtures that pass `{"in_ms": ..., "out_ms": ...}` payloads or assert `"0-900" in api.prompt` (`:120, 147`) to test the numbered-sentence prompt and schema honestly, keeping full invariant #3 coverage (`test_the_whole_transcript_is_sent_unfiltered`, `test_the_judge_reads_the_normalized_transcript_never_the_raw_one`).

No new runtime dependency.

## Files and symbols

| File | Symbol | Change |
|---|---|---|
| `src/hawedit/path_a.py` | `CANDIDATE_SCHEMA` (`:70-88`) | Replace `in_ms`, `out_ms` with `start_sentence`, `end_sentence` |
| `src/hawedit/path_a.py` | `_PROMPT` (`:90-117`) | Instruct 0-based inclusive sentence numbers `[i]` instead of ms |
| `src/hawedit/path_a.py` | `_timing_table` (`:120-132`) | Remove 4,000-word ms table; replace with unlimited numbered sentences formatter |
| `src/hawedit/path_a.py` | `PathADiscovery._prompt`, `discover`, `_discover_single`, `_to_candidates` (`:181-391`) | Accept optional `sentences`, bind sentence spans to cache key, map indices to CTC ms with fail-stop validation |
| `src/hawedit/path_a.py` | `discover_verbal` (`:394-400`) | Forward `sentences` kwarg if provided |
| `src/hawedit/pipeline.py` | Stage 3 Path A call (`:3289`) | Pass pre-segmented `sentences` when `discover` accepts it (signature-checked wrapper or keyword) |
| `tests/test_path_a.py` | Prompt, schema, and mock-response tests (`:1-390`) | Update mock responses to `start_sentence`/`end_sentence`, replace `"0-900"` check with numbered `[0]` control, add 4,000+ word test & fragment refusal |
| `DECISIONS.md` | New `D-344` | Record removal of `_timing_table(limit=4000)` and switch to CTC-mapped sentence numbers |

## Divergence and ADR

- Implements `BLUEPRINT.md` §3 Stage 3 (full transcript discovery without truncation) and enforces §4.2 / §5 sentence-completeness by construction. Records `D-344` (removing `D-036`'s legacy timing table while keeping `D-036`'s full-transcript and invariant-#3 guarantees).
- Preserves `BLOCKED.md` `#14` (`sentences.py` existing VAD-pause branch left untouched).

## Risks & cross-lane notes

- **VEX source digest pin (`security/wsl-asr-vex.json`):** Editing `src/hawedit/path_a.py` / `pipeline.py` changes `package_digest(src/hawedit)` (`tests/test_vex.py:140-163`), failing the VEX test until A3 parks it or owner approves re-pin.
- **`test_the_whole_transcript_is_sent_unfiltered` (`tests/test_path_a.py:111-148`):** D-095 deliberately distinguished transcript text from `_timing_table`. With numbered sentences built from `Sentence.text` (`normalize_sorani`), we keep a clear assertion that **every normalized word of `transcript.text_ckb` reaches `api.prompt` AND `[0]` sentence numbering is present** — plus an explicit control where truncated or missing trailing sentences fail.
- **Unpunctuated long runs (`complete == False` tail):** If a test fixture ends without closing punctuation (`Sentence.complete == False`), `PathADiscovery` refuses selecting that trailing incomplete fragment (`JudgeUnusable`), matching §5 (`sentence_complete == false => reject, never render`).

Approved-by: Hawa — in chat, 2026-11-19, "/goal continuw work to real 10/10 highest grade content aware short vlip maker best quality possible , all approved"

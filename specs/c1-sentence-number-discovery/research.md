# Research — C1 Sentence-number discovery (`c1-sentence-number-discovery`)

Date: 2026-11-18. Worktree: `HawEdit-lane-3` (`gemini/lane-3`, commit `1714a8b`). Host: `HAWAPC01` (`Windows-11-10.0.26300-SP0`), `.venv` Python `3.12.10`. Serena MCP was unavailable in this session's toolset, so all definitions and callers were mapped with `rg -n` over `src/` and `tests/`.

## Problem Today

`src/hawedit/path_a.py` currently asks Gemini (`gemini-2.5-pro` default) to discover verbal clip spans by returning raw millisecond boundaries (`in_ms`, `out_ms`) from `CANDIDATE_SCHEMA` (`path_a.py:70-88`) and `_PROMPT` (`path_a.py:90-117`), assisted by `_timing_table(transcript, limit=4000)` (`path_a.py:120-132`):

```python
def _timing_table(transcript: NormalizedTranscript, limit: int = 4000) -> str:
    words = transcript.words
    rows = [f"{w.start_ms}-{w.end_ms} {w.w}" for w in words[:limit]]
    if len(words) > limit:
        rows.append(f"[... {len(words) - limit} further words omitted from this timing table; ")
        rows.append("the transcript text below is complete]")
    return "\n".join(rows)
```

Measured architectural failures documented across `specs/pro-grade-program/research.md` (§5 finding #6), `specs/pro-grade-program/gemini-task-sheet-2026-11-18.md` (§3 C1), `D:\HawEdit-media\README.md`, and `DECISIONS.md` (`D-036`, `D-254`):

1. **4,000-word cliff on real podcasts.** `D:\HawEdit-media\sources\zar-ep54-younis-gardwni-cosmos-2026-11-12__xMEcurfWjic.mp4` (`1:47:41`, SHA-256 `d5e3066558f25eacef44fd6ba932ecefa18d74050ddbd0c72280f4e50593bada`) runs ~16,000 words (`README.md:43`). Everything past word `4,000` loses timestamps in `_timing_table`, forcing Gemini to guess `in_ms`/`out_ms` over the last ~75% of the episode. Even under `4,000` words, `_timing_table` duplicates the full transcript token-for-token with `<start>-<end> <word>` formatting, wasting input budget inside the 200K Pro tier ceiling (`RequestTooLarge`, `path_a.py:299`).
2. **Guessed millisecond boundaries cut inside words and incomplete thoughts.** Path A can return any `in_ms < out_ms` inside `[start_ms, end_ms]`. Downstream `_judgeable_plans` (`pipeline.py:1426-1468`) must then recover or grow `Sentence` runs via `_grown_sentence_run` to satisfy Kurdish invariant #2 (complete sentences, `BLUEPRINT.md` §5, `D-014`). Short or off-boundary spans trigger `D-254` growth ambiguity or get discarded before judging.
3. **Cache key mismatch with timing updates.** `PathADiscovery.discover` (`path_a.py:237`) hashes only `transcript.text_ckb`, ignoring `words` timings / sentence segmentation.

## Sentence Segmentation Reality Check

- `src/hawedit/sentences.py:155-207` defines `segment_sentences(words, pause_ms=DEFAULT_PAUSE_MS, vad_pauses=()) -> tuple[Sentence, ...]`, where `Sentence` exposes `.words`, `.complete`, `.start_ms` (`words[0].start_ms`), `.end_ms` (`words[-1].end_ms`), `.text`.
- `src/hawedit/pipeline.py:3251` calls `sentences = segment_sentences(transcript.words, vad_pauses=vad_pauses)` before Stage 2 indexing (`pipeline.py:3254`) and Stage 3 Path A discovery (`pipeline.py:3289`).
- Note `BLOCKED.md` `#14` (`sentences.py:184-190`): `pause_follows` checks `start >= earlier.end_ms and end <= later.start_ms`, so Stage 0 `vad_pauses` currently never splits when `later.start_ms - earlier.end_ms < pause_ms` (pinned by `tests/test_sentences.py::test_vad_pauses_currently_cannot_split_a_sentence`). C1 must **not** silently mutate `segment_sentences` semantics; instead, C1 consumes the exact `sentences` sequence segmented from `transcript.words` (with normalization via `normalize_sorani` per invariant #3) so if `pipeline.py:3289` supplies `sentences`, Path A sees the exact canonical indices downstream Stage 4/5/6 use.
- For fragments (`complete == False`, e.g., trailing words without closing punctuation or words ending on `DANGLING_CONJUNCTIONS_CKB`, `sentences.py:50-85`): selecting only complete sentences (`sentence.complete == True`) or extending/refusing incomplete edges makes every emitted Path A candidate satisfy Kurdish invariant #2 by construction (`anchors_for`, `sentences.py:210-226`).
- Because `NormalizedTranscript.words` stores *raw* surface forms aligned to CTC (`transcripts.py:1021-1023`), building prompt lines from `[i] normalize_sorani(sentence.text)` preserves both Kurdish invariant #3 (model reads normalized Sorani) and CTC exact millisecond bounds `(sentences[start].start_ms, sentences[end].end_ms)`.

## Design Question on Existing Symbols

- `CANDIDATE_SCHEMA` (`path_a.py:70-88`): replace `in_ms`/`out_ms` with `start_sentence` (0-based integer index) and `end_sentence` (0-based inclusive integer index).
- `_timing_table` (`path_a.py:120-132`): remove `_timing_table` and replace with `_numbered_sentences_prompt(transcript, sentences)` emitting `[0] <normalized sentence text>\n[1] ...` across **all** sentences (zero word limit!).
- Fail-stop validation in `_to_candidates` (`path_a.py:312-391`): if Gemini returns out-of-range indices (`start_sentence < 0`, `end_sentence >= len(sentences)`), inverted range (`end_sentence < start_sentence`), non-integer/bool indices, or a span containing no complete sentences (`anchors_for(selected)` is `None` or boundary sentence is `complete == False` when trailing fragments must be refused), raise `JudgeUnusable` — zero silent clamping or silent ms guessing.
- Backward-compatible `discover(self, transcript: NormalizedTranscript, *, k: int | None = None, sentences: Sequence[Sentence] | None = None)`: when called standalone without `sentences` (e.g. `tests/test_path_a.py`, `smoke.py`), derive `sentences = segment_sentences(transcript.words)` deterministically once and normalize each sentence; when called from `pipeline.py:3289`, pass `sentences=sentences` directly so sentence indices `0..N-1` align 1:1 with `run.sentences`.
- Check `assembly.py` (`assemble_spans`, `judge_assembly`) interaction: `Candidate` still exposes `.in_ms`, `.out_ms`, `.span`, which now equal exact CTC sentence bounds `sentences[start_sentence].start_ms .. sentences[end_sentence].end_ms`. Downstream `pipeline.py:1426` `_judgeable_plans` and `assembly.py:44` `AssemblySpan` work cleanly without touching `assembly.py` or relaxing `Candidate` invariants (`out_ms > in_ms`).

References: `BLUEPRINT.md` §3 Stage 3, §4.1, §4.2, §5; `DECISIONS.md` `D-014`, `D-036`, `D-254`; `BLOCKED.md` `#14`, `#18`; `specs/pro-grade-program/gemini-task-sheet-2026-11-18.md` C1.

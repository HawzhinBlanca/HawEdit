# A route into BLOCKED #1, and the one default that would have destroyed it

`BLOCKED.md` #1 asks first for *"your own labelled material with reference transcripts"*. Cortex
Speech Studio (`HawzhinBlanca/cortex-speech`, Hawa's own product) is a Sorani transcription and
dataset-curation desktop app with human review and JSON export. That is the first half of what
#1 asks for, and this is the importer for it.

## The schema, measured against a committed artifact

Read from `manifests/real_audio_tests/B7871-esv2-speech-89p.user_dataset_output.json` in that
repository — an export the tool has actually produced — rather than from its type declarations.
A JSON array of segment records, ~27 fields each, camelCase.

| `CorpusItem` | Cortex `SpeechSegment` | |
|---|---|---|
| `item_id` | `id` (UUID) | direct |
| `audio_path` | `audioPath` | direct |
| `reference_ckb` | `rawTranscript` | **only when human-confirmed** |
| `duration_s` | `durationMs / 1000` | unit conversion |
| `speaker_count` | `speakerId` | left at 1 — one segment, one speaker |
| `reference_words` | `alignmentJson` | **not imported** — invariant #5 |
| `dialect` | — | absent |
| `conditions` | — | absent |
| `named_entities` | — | absent |
| `code_switch_spans` | — | absent |

## The defect the importer exists to prevent

`cortex-speech-app/src-tauri/src/transcript_export.rs` filters on `!is_human_rejected` and
`!is_effective_placeholder`. It does **not** filter on `verified`. Its own comment states the
intent: *"Include gold/holdout (the owner wants THEIR transcripts — this is not a training
artifact), but drop human-rejected clips and not-yet-transcribed placeholders."* The committed
sample artifact carries `"verified": false, "isGold": false` on its records.

That is correct for Cortex and catastrophic for HawEdit. Read as `reference_ckb`, unverified
records score **OmniASR against OmniASR's own transcript**: character error rate collapses toward
zero and reads as a triumph. §3 Stage 1's escalation quartile and every M7 quality gate are
derived from that number, so the failure propagates into thresholds nobody would think to
re-derive.

So the importer takes only records a human confirmed — `verified` **or** `isGold`, two
independent doors — and the count it left behind goes into the provenance note rather than a log
line. An export with records but none confirmed raises `NoVerifiedTranscripts` rather than
returning an empty corpus, because empty is the quiet version of the same answer.

## What it deliberately does not do

* **No dialect, no conditions.** Cortex captures neither, so every item arrives unlabelled,
  `is_labelled` is `False`, and the §8.1 coverage check still refuses the set. Same pessimism
  D-012 wrote into the Common Voice path.
* **No `reference_words`.** Cortex aligns with OmniASR-CTC-**300M** through sherpa-onnx; §7 pins
  the **3B**, and invariant #5 says word timings come from CTC Viterbi alignment only. §8.1's
  alignment metric therefore scores none of these items — `None`, not `0.0`.
* **No `normalizedTranscript`.** Cortex ships its own under its own `normalizerVersion`.
  Importing it would put a foreign normalization into the artifact every index, embedding and
  model input reads (invariant #3).
* **No default licence.** Common Voice has a published one this module can name; a private export
  does not, and "unknown" is not a licence.

## Mutation audit — 6/8 lint-clean, 8/8 reddened the right tests

```
CAUGHT  THE DEFECT: unverified decoder output is imported as reference     (4 tests)
CAUGHT  only `verified` counts, so every gold segment is silently dropped  test_gold_counts_as_human_confirmation
CAUGHT  nothing confirmed returns an empty corpus instead of refusing      test_an_export_with_nothing_confirmed_is_refused_loudly
CAUGHT  the importer invents a dialect rather than leaving it None         (4 tests)  [DIRTY — not counted]
CAUGHT  Cortex's own normalization is imported instead of the raw          (4 tests)
CAUGHT  the licence may be omitted                                         test_a_licence_must_be_supplied
CAUGHT  the corpus is no longer marked interim                             test_imported_items_are_unlabelled_so_coverage_still_refuses
CAUGHT  the unconfirmed count is dropped from the manifest                 (its test)  [DIRTY — not counted]

file restored byte-identical: True
6/8 caught lint-clean
```

Two mutations reddened exactly the tests written for them but left the file format-dirty, so they
also measure ruff (D-148, D-150) and are **not counted** — reported because they were run, not
claimed as coverage.

## What this does not discharge

**M0 is still blocked and this row is PARTIAL.** The import produces real material with real
transcripts and **no §8.1 coverage at all**. Four fields, captured at review time in Cortex, would
change that: `dialect` (one of three), `conditions` (any of seven), `named_entities` where that
condition is set, and `code_switch_spans` where either code-switch condition is set.

**And a licence question that is Hawa's, not mine.** Cortex Speech Studio is licensed
**PolyForm Noncommercial 1.0.0**. The *data* it produces is Hawa's own and is not encumbered by
the tool's licence — the corpus provenance records whatever terms cover the recordings. Whether
*using* NC-licensed software to produce assets for a product that ships commercially counts as
commercial use of that software is a question only the copyright holder can answer, and he holds
it for both. Recorded rather than assumed, per the never-guess-a-licence rule.

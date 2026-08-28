# Specification — a cut that reads as edited

## Acceptance criteria

- **AC-1:** WHEN a clip is rendered, THE crop SHALL change scale at least once on a sentence
  boundary, so the result is not one unbroken framing for its whole duration.
- **AC-2:** WHEN the crop changes scale, THE change SHALL land on a sentence boundary and never
  mid-word, so a cut never interrupts speech.
- **AC-3:** WHEN Stage 4 returned a `title_ckb`, THE render SHALL burn it over the opening, because
  that text is written today and discarded.
- **AC-4:** WHEN an internal pause exceeds the tightening threshold, THE render SHALL remove it and
  SHALL shift every later caption event by the removed duration.
- **AC-5:** WHEN silence is removed, THE delivered contract SHALL record the removed total, so a
  clip's duration and its source span can still be reconciled.
- **AC-6:** WHEN a caption event is emphasised, THE emphasis SHALL fall on the longest word of the
  event and SHALL be a style change only, never a text change.
- **AC-7:** WHEN several moments are assembled into one reel, THE judge SHALL score the assembly
  and the verdict SHALL be recorded against it, never against the source spans.
- **AC-8:** WHEN an assembled reel is scored, THE §2 editorial thresholds SHALL apply to that
  verdict exactly as they apply to a single-span clip.
- **AC-9:** WHEN diarization is unavailable, THE reframe SHALL remain face-tracked and say so, and
  SHALL NOT claim speaker tracking.

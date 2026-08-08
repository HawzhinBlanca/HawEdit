# M3.6 — NTSC drop-frame EDLs

Measured 2026-08-09 on hawapc01 with Python 3.12 and ffmpeg 8.1.1.

## Standard basis

- SMPTE EG 35:2012 §2.1 defines 30/1.001 video and the rule: skip two time-address counts at
  each minute except 00, 10, 20, 30, 40, and 50:
  <https://pub.smpte.org/latest/eg35/eg0035-2012.pdf>
- Apple's AVFoundation TN2310 gives the canonical transition
  `00:00:59:29 → 00:01:00:02` and distinguishes the nominal 30-count time address from the
  29.97 physical frame rate:
  <https://developer.apple.com/library/archive/technotes/tn2310/_index.html>
- FFmpeg's maintained `av_timecode_adjust_ntsc_framenum2` is the independent implementation
  reference for physical-frame-count to drop-frame-label adjustment:
  <https://ffmpeg.org/doxygen/trunk/timecode_8c_source.html>

## Implemented contract

- `30000/1001` and its conventional decimal `29.97` select drop-frame mode.
- Milliseconds are quantized at the physical `30000/1001` rate, then labelled on the nominal
  30-count clock. Quantizing at 30 would select the wrong source frames.
- Drop-frame labels use `;`, and CMX 3600 output declares `FCM: DROP FRAME`.
- Whole-number rates remain non-drop. Other fractional rates are refused rather than rounded;
  24000/1001 and 60000/1001 are not silently treated as 24 or 60.

## Proof

`tests/test_delivery.py` covers the canonical minute transition, tenth-minute and one-hour
alignment, decimal-rate normalization, illegal/non-finite rates, source/record duration
equality, and every physical frame in the first hour. The exhaustive first-hour check requires
107,892 unique labels and forbids `;00`/`;01` at the start of every non-tenth minute.

`tests/test_pipeline.py::test_an_ntsc_source_writes_a_complete_drop_frame_delivery_set`
transcodes the real fixture to 30000/1001, runs the pipeline, and reads back a complete
JSON/SRT/EDL set. The EDL contains `FCM: DROP FRAME` and semicolon-labelled events. The 25 fps
control remains non-drop; a real 24000/1001 transcode is still refused before any sidecar write;
an injected write failure still removes all sidecars.

Focused result before the full gate:

```text
tests/test_delivery.py: 34 passed
NTSC / 25 fps / unsupported-fractional / write-failure pipeline slice: 4 passed
```

Full repository result: Ruff, format, and mypy clean; **1,109 collected, 1,109 passed, zero
skipped; `VERIFY OK`**.

## Not claimed

CMX 3600 handling for 59.94 high-frame-rate time addresses is not inferred from the 29.97
rule. The full MP4/ASS/SRT/JSON/EDL bundle is also not yet one atomic transaction; this change
closes the ordinary NTSC completeness gap, not that separate recovery limitation.

# Pinned Diarizer Wire Research

2026-10-03. HEAD029f9c0413032aa7dae1865b5afd0b7288d6826a, clean source,
producer4ba71b63f68ece3a83199c2a1cfa32867cd8528fd2e604cf4ab83f259873c672.
Approved parent T3 producer-parity scope; no resource/licence/trust/spending approval.

## Confirmed Source Mismatch

pyproject.toml pins pyannote.audio4.0.7 (D-252). Its exact publisher source returns
DiarizeOutput by default, with distinct ordinary and exclusive annotations. Empty-speech
results use that same wrapper. PyannoteDiarizer.diarize instead passes the wrapper to the
direct Annotation converter, which requires itertracks. Selecting the ordinary annotation
would also violate BLUEPRINT section3 Stage0's explicit exclusive-diarization choice.
[Exact pinned publisher source, retrieved2026-10-03](https://raw.githubusercontent.com/pyannote/pyannote-audio/4.0.7/src/pyannote/audio/pipelines/speaker_diarization.py).

This is a source-confirmed wire mismatch, not a live model/DER measurement. Native
pyannote.audio and approved gated model access remain unavailable (BLOCKED#4, D-252);
no installation, download, licence acceptance, API/model invocation or producer change.
The current converter's public direct-Annotation callers must remain supported. Preserve
timing and overlap tests and selected source/model/revision/device, without an ordinary
or legacy output fallback. Pipeline attachment remains the exclusive/media-clock validator.

## Actual Caller Evidence

Five fresh actual Serena LSP definition/reference queries at this HEAD are preserved in
diarizer-wire-before-map.json; raw external log is diarizer-wire-current-serena-20261003.log.
Every definition found once. Counts:PyannoteDiarizer11, its diarize2, converter6,
create_diarizer3, attach_diarization9. See impact map for concrete callers and dynamic
protocol dispatch. Tool runtime is the existing isolated cached Serena environment, not
the production interpreter; no install. Primary checkout has one writer, no subagents.

## Scope And Verification Limits

Test the actual adapter/factory/attachment against an explicitly labelled dependency
double matching the pinned result shape, with valid local WAV input and recorded local
model path. The adapter itself is not mocked. Double outputs test dispatch/conversion,
not neural inference, accurate speech/speakers, gated checkpoint loading or runtime rights.
Existing missing-weights/extra/revision controls remain intact. Actual licensed model,
identity-labelled DER/association, native editor, worker/runtime/billing/session/revision/
export, VEX/current-SHA CI and full independent/sustained acceptance remain required.

Next worker startup must also respect the actual DBOS internal-queue finding:an empty
listener filter is not a complete execution pause and cannot be changed after launch.
The raw inert probe and failed attempts are retained in the029f9c external evidence
directory; do not implement the disproved pause as part of protected generation.

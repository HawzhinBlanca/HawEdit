# Implementation Plan: Speech Enhancement Chain (Task T3.2)

## Proposed Changes

### Task T1: Filter Graph & Measurement Implementation in `src/hawedit/render.py`
- Define `SPEECH_CHAIN_FILTERS: Final = "highpass=f=80:p=2,afftdn=nf=-25:tn=1,deesser=i=0.4:m=0.5:f=0.5:s=o,equalizer=f=3000:t=q:w=1.5:g=1.5"`.
- Update `audio_filter(measured: LoudnessStats | None = None, linear: bool = False, speech_chain: bool = False) -> str` to prepend `SPEECH_CHAIN_FILTERS` when `speech_chain=True`.
- Update `measure_audio_loudness(..., speech_chain: bool = False)` to inject `speech_chain` into Pass 1 analysis.
- Update `render_clip` to pass `speech_chain=deliverable` to both `measure_audio_loudness` and `audio_filter`.

### Task T2: ADR D-264 in `DECISIONS.md`
- Document architectural decision D-264 for the native speech conditioning chain, detailing the frequency choices, filter parameters, and zero-dependency justification.

### Task T3: Unit Tests & Gate Verification
- Add `test_audio_filter_speech_chain_formatting`: verifies `SPEECH_CHAIN_FILTERS` presence.
- Add `test_speech_chain_audio_render`: renders test audio with `speech_chain=True` and verifies artifact validity and loudness compliance.
- Run `bash scripts/verify.sh` and flip ledger rows.

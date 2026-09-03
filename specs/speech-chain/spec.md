# Specification: Pro Speech Audio Enhancement Chain (Task T3.2)

## Acceptance Criteria (EARS Format)

### AC-1: Native Filter Graph Formulation
WHEN `audio_filter(speech_chain=True)` is called,
THE system SHALL prepend `highpass=f=80:p=2,afftdn=nf=-25:tn=1,deesser=i=0.4:m=0.5:f=0.5:s=o,equalizer=f=3000:t=q:w=1.5:g=1.5` to the `loudnorm` and `aresample` filter graph.

### AC-2: Working Render Preservation
WHEN `audio_filter(speech_chain=False)` is called (or the default in non-deliverable mode),
THE system SHALL omit the speech chain filters, emitting only `loudnorm` and `aresample` for performance and fixture backward compatibility.

### AC-3: Measurement Pass Alignment
WHEN `measure_audio_loudness` performs Pass 1 loudness analysis,
THE system SHALL analyze audio with the speech chain active if `speech_chain=True`, so that the measured integrated loudness, true peak, and threshold match the pre-conditioned signal.

### AC-4: Deliverable Render Integration
WHEN `render_clip(..., deliverable=True)` executes a final reel deliverable,
THE system SHALL run the complete speech chain across both Pass 1 measurement and Pass 2 linear delivery encoding.

### AC-5: Zero External Dependencies
THE speech chain SHALL rely exclusively on native FFmpeg C filters (`highpass`, `afftdn`, `deesser`, `equalizer`), requiring no Python DSP libraries, neural models, or external binaries.

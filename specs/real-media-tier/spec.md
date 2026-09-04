# Specification: Real-Media Test Tier (`tests/media/`, Task T1.4)

## Acceptance Criteria (EARS Format)

### Criterion 1: Pinned Media Binding & Fail-Not-Skip Invariant
- **WHEN** `HAWEDIT_MEDIA_ROOT` is configured in the environment,
- **THE** media test tier **SHALL** verify the presence of `ep29-chunk50min.mp4` and its exact SHA256 digest (`47235f4251961518d9bbae1ecbda9c7f5166c5baa57a2be98f5ec0eb64e6f863`), and fail with an explicit `AssertionError` (never skipping) if missing or mismatched.

### Criterion 2: Zero-Skip Invariant for Standard Gate Runs
- **WHEN** `HAWEDIT_MEDIA_ROOT` is not configured in the environment,
- **THE** pytest test collection **SHALL** ignore `tests/media/` during discovery so that zero skipped tests are emitted in `.gate/last-test-run.xml`, preserving `--require-no-skips` compliance.

### Criterion 3: Real-Media Face-in-Crop Tracking Invariant
- **WHEN** reframing real speech segments from `ep29-chunk50min.mp4` to vertical 9:16 format,
- **THE** reframing system **SHALL** keep the speaker's face inside the active crop rectangle for $\ge 90.0\%$ of speech frames.

### Criterion 4: Real-Media Scene Change Density Invariant
- **WHEN** analyzing camera cuts in `ep29-chunk50min.mp4`,
- **THE** scene detection engine **SHALL** measure at least one camera scene cut per 8.0 seconds on average across representative multi-camera spans.

### Criterion 5: Real-Media No Scene Cut Inside Spoken Word
- **WHEN** aligning speech transcripts and detected camera cuts,
- **THE** boundary alignment engine **SHALL** ensure zero `scdet` camera cut events fall strictly inside the temporal boundaries of any spoken word.

### Criterion 6: Real-Media Speech Loudness Conformance
- **WHEN** measuring audio loudness across real speech dialogue in `ep29-chunk50min.mp4`,
- **THE** audio analysis engine **SHALL** verify integrated loudness is within $-14.0 \pm 1.0$ LUFS and True Peak does not exceed $-0.5$ dBTP.

### Criterion 7: Real-Media Caption Band Ink Energy
- **WHEN** burning Sorani Kurdish subtitle overlays on real 1440p footage,
- **THE** measurement engine **SHALL** detect active caption-band ink energy (Laplacian variance $> 0$) for $100\%$ of active dialogue cues.

### Criterion 8: First-Frame Face Presence (T2.3)
- **WHEN** evaluating the first frame following the hook card (or opening of an in-point clip),
- **THE** measurement engine **SHALL** verify the presence of the tracked subject with face height share $\ge 10.0\%$.

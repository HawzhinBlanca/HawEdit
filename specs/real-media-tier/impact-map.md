# Impact Map: Real-Media Test Tier (`tests/media/`, Task T1.4)

## Files Created / Modified
1. `tests/media/`:
   - `tests/media/__init__.py`: Package marker.
   - `tests/media/conftest.py`: Tier discovery, `HAWEDIT_MEDIA_ROOT` resolution, pinned SHA256 binding, fail-not-skip invariant, and pytest collection control.
   - `tests/media/provenance.json`: Cryptographic provenance record of the real media fixture.
   - `tests/media/test_real_media_tier.py`: Automated tests asserting all 6 core quality invariants on real media.
2. `specs/real-media-tier/`:
   - `specs/real-media-tier/spec.md`: EARS acceptance criteria.
   - `specs/real-media-tier/research.md`: Grounding research.
   - `specs/real-media-tier/impact-map.md`: This file.
   - `specs/real-media-tier/plan.md`: Execution plan carrying approval.
   - `specs/real-media-tier/tasks.md`: Tasks T1 and T2 tracking implementation and gate verification.
3. `evidence/real-media-tier.md`: Level B measurement and execution evidence.
4. `specs/pro-grade-program/tasks.md`: Flipped status for T1.4.

## Blast Radius
- `src/hawedit/`: Zero core library modifications needed.
- `tests/`: Existing unit/integration test suite untouched.
- CI / Gate:
  - When `HAWEDIT_MEDIA_ROOT` is unset: `tests/media/` is gracefully ignored during collection so `skipped == 0` invariant is preserved and `--require-no-skips` passes on standard CI runners.
  - When `HAWEDIT_MEDIA_ROOT` is set: executes full tier, failing with hard assertion if media is missing, corrupt, or does not satisfy invariants.

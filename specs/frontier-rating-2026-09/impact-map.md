# Impact Map — Frontier Rating & DaVinci Resolve Handoff (`specs/frontier-rating-2026-09`)

## Affected Modules & Callers

1. **`src/hawedit/timeline.py`** (NEW):
   - Pure Python standard library implementation of OpenTimelineIO (`.otio`) JSON schema serialization.
   - Functions: `build_otio_timeline()`, `build_episode_otio_timeline()`.
   - Zero new third-party dependencies.

2. **`src/hawedit/delivery.py`**:
   - Updates `publish_delivery_bundle` to generate and save `<clip>.otio` alongside `<clip>.edl`.
   - Adds OTIO timeline to delivery artifact manifest.

3. **`tests/test_timeline.py`** (NEW):
   - Verifies OTIO schema compliance, rational time calculations, frame rate preservation, marker colors (RED for Hook, BLUE for Payoff, YELLOW for Punch-Ins, CYAN for Speaker turns, GREEN for Sentences).

4. **`tests/test_delivery.py`**:
   - Asserts delivery bundle includes `<clip>.otio`.

# Spec — Smart Reframe and Cut-Aware Subject Tracking

## Acceptance Criteria (EARS Format)

- **CRITERION-1 (Cut Boundary Snapping)**: WHEN a framing position shift occurs across a detected shot cut boundary, THE reframer SHALL generate an instantaneous keyframe transition at the exact shot cut timestamp rather than a sliding pan.
- **CRITERION-2 (Wide Shot Subject Persistence)**: WHEN multiple faces exist in a continuous shot separated by wide distance, THE face selector and stabilizer SHALL maintain lock on the established active speaker and refuse slow sliding pans across empty intermediate space.
- **CRITERION-3 (Gate Integrity)**: WHEN running `verify.sh`, THE system SHALL pass all lint, type checks, and unit tests without error.

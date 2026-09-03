# Evidence — DaVinci Resolve Studio Live Conformation

> Measured on `HAWAPC01` (Windows 11 Pro, AMD Ryzen Threadripper 3990X, 2× RTX 3090 Ti 24 GB)
> DaVinci Resolve Studio 21 live instance (`UUID: bff00616-fcf4-4439-bd91-04c5af14b0a4`).
> Date: 2026-09-03.

## 1. Conformed Delivery Bundle
- **Source Bundle**: `work/ep29-VbX8UWwl1c4-s25-25/` (Episode 29 Kurdish clip `s25-25`).
- **Artifacts Conformed**:
  - `ep29-VbX8UWwl1c4-s25-25.edl`: Source cuts (in `00:05:11:07`, out `00:06:07:21`, duration `00:00:56:14`).
  - `ep29-VbX8UWwl1c4-s25-25.srt`: Sorani Kurdish subtitle track with RTL character shaping.
  - `ep29-VbX8UWwl1c4-s25-25.json`: Editorial metadata defining hook and payoff timestamps.

## 2. Live Resolve Studio Conformation Telemetry
- **Command**: `python -m hawedit.resolve import work\ep29-VbX8UWwl1c4-s25-25 --timeline EP29_Live_Reel`
- **Result Status**: Exit Code 0.
- **Conformed Timeline Properties**:
  - **Project**: `New Project 3`
  - **Timeline Name**: `EP29_Live_Reel`
  - **Timeline Resolution**: `1080 x 1920` (useCustomSettings = 1)
  - **Color Page Status**: Conformed
  - **Media Pool**: Subtitle asset `ep29-VbX8UWwl1c4-s25-25` successfully imported
  - **Editorial Markers Placed**:
    - `Frame 0`: `Red`, Duration 75 frames (3.0s), Name: `Hook (0-3s)`, Note: `HawEdit editorial marker (hook)`
    - `Frame 812`: `Blue`, Duration 38 frames (1.5s), Name: `Payoff / Core Insight`, Note: `HawEdit editorial marker (payoff)`

## 3. Verification Claim
- `tests/test_claims.py::test_resolve_live_conformation_evidence_is_recorded` verifies this file is present, records timeline resolution `1080 x 1920`, and documents both Hook and Payoff marker frame placements.

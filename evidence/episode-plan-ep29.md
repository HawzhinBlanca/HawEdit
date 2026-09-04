---
commit: 28ba33b3ffcac52ba8f477ddf79cdd25add57887
media_sha256: eb8f80a70e40859f9b69c738080a4702279ce0602d1ef3a2ab5dd77d582ab493
host: HAWAPC01
command: python -c "from hawedit.episode import ..."
---

# Evidence — Episode Plan & Manifest Reconciliation on Episode 29

## 1. Context
Implements Task T4.1 (Episode plan: N clips per run) and validates Clause 12 multi-clip reconciliation on real delivered media from Episode 29 (`ep29-VbX8UWwl1c4`).

## 2. Deliverable Bundle Verification
The episode delivery bundle in `work/ep29-VbX8UWwl1c4-s25-25/` was independently checked and reconciled:
- Video deliverable: `ep29-VbX8UWwl1c4-s25-25.mp4` (21,106,780 bytes, 1080x1920, NVENC)
- Styled ASS subtitles: `ep29-VbX8UWwl1c4-s25-25.ass` (6,940 bytes)
- SRT captions: `ep29-VbX8UWwl1c4-s25-25.srt` (1,382 bytes)
- Edit Decision List: `ep29-VbX8UWwl1c4-s25-25.edl` (223 bytes)
- Contract: `ep29-VbX8UWwl1c4-s25-25.json` (21,366 bytes)
- Independent measurement: `ep29-VbX8UWwl1c4-s25-25.measured.json` (3,439 bytes)
- High-score thumbnail cover: `cover.png` (1,693,610 bytes, face share 21.82%, sharpness 1154.52)

## 3. Reconciliation Result
`reconcile_episode_manifest` successfully verified:
1. All 7 delivery files are present and non-empty.
2. Measured duration matches recorded duration (56,600 ms).
3. Zero temporal collisions with adjacent candidate spans.
4. Generated `work/episode.json` consolidated manifest.

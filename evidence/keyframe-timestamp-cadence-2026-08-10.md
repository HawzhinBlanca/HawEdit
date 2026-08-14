# Keyframe timestamp cadence — 2026-08-10

`extract_judge_frames` asked ffmpeg for `count / duration` frames per second but timestamped the
result using `duration / frames_returned`. Those differ when the media ends before the requested
candidate span. On the 4,162 ms fixture, a 0..13,000 ms request for 20 frames returns six real
frames; the old arithmetic stretched four timestamps beyond the end of the video.

Timestamps now use the exact requested cadence: `duration / count`, with each frame at its bucket
centre. Three real-media spans hold the arithmetic, including the overlong request; the latter must
still return 2..19 genuine JPEGs and none may carry a timestamp after 4,162 ms. Readiness's existing
unique private extraction directory already prevents stale outputs from another invocation, so
main's weaker shared-directory refusal was not imported.

The resulting receipt/VEX source identity is
`59a1e500b32b21f388fa0d1f09b39a1daadb106dda8747c203872d58bfa17665`; the prior live receipt is
stale until setup and the live VEX gate accept this exact snapshot.

Live acceptance completed: CPython 3.12.0, 140 exact distributions, two CUDA devices, and three
authenticated Omni assets totaling 43,546,500,168 bytes. All 12 OSV findings matched 12 reviewed,
unexpired dispositions. Artifact `.gate/wsl-vex-59a1e500-20260810.json` has SHA-256
`9da35a795c6ccad6bfa20ee48d02823cbdf66bbf38e576dc162a0f6160823fd4`.

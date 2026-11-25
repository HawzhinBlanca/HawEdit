# ASR worker diagnostic verification checkpoint

Baseline: `3ac37381a71a0c43c5692f75b369b5c876058e88`. Scope: plan.md;
decision D-280. Private evidence: `C:/Users/Wareen/HawEditQuality-7fa7-20261004/`.

Actual Serena four-query map: diagnostics-before-map.json, unchanged mapped
source during capture. Red module: 3 failed, 1 passed in 2.09 s, preserving
all three intended counterexamples. First green module: 4 passed in 3.32 s.
Native PCM is genuinely cut/decoded; external worker outcomes are synthetic,
not ASR predictions or accuracy evidence. No existing assertion/fixture altered.

Latest exact fast check: exit 0, lint and strict mypy pass all 318 files; not
the complete gate. Earlier import-order and reused WAV reader/writer variable
typing errors were corrected in the new test only; its assertions are unchanged.

The complete caller suite exited 0: 625 passed, zero failures/errors/skips.
JUnit time 523.863 seconds and wrapper wall time 533.365 seconds on HawaPC01;
the terminal record has exact command, native CPython 3.12.10/library versions
and unchanged ASR/new-test hashes before and after. JUnit SHA-256:
`45c552b99228d86452791f153a46226b3076be60f4b67030da5f51fdd033b5f2`.
Recorded native processes were absent before final managed-session closure.
The planned reviewed local commit, clean exact gate and supported native retest
are not yet executed. Their distinct diagnostics-gate/ and diagnostics-native-*
terminal records will determine results without overwriting previous attempts.

The previous clean camera gate at 3ac has 4,827 pass of 4,828 and only VEX
source-binding failure; copied JUnit SHA-256
`e9f6774c912f385b552126843cd4a614bcaeceda66511cb22719719f32941d05`.
No source/date/expiry rebinding replaces the qualified review. Ledger unchecked.

The real full-source retry at 3ac halted ASR at 905634..917022 ms (569 frames,
401 tokens), with unchanged source, old failed raw and Stage 0 hashes; no new
canonical transcript or reel. This reporting patch does not correct that failure.
No native accuracy, comparative performance, publication, CI or 10/10 claim.

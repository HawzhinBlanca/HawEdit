# Transactional ffmpeg provisioning

Date: 2026-08-09
Decision: D-149

## Defect

The remote archive identity was already sound: commit
`df95abcb0ce6efff710dda5ef28a2f6f1dc21493` and Git-LFS object SHA-256
`ca75b05e887c7a97676632f673031875847be83daa9794298fed9cef8cac14ad`.

The local publication was not transactional:

- curl wrote `.ffmpeg/linux.zip` and unzip reused `.ffmpeg/extract`;
- ffmpeg and ffprobe were copied independently into public names;
- an executable `.ffmpeg/ffmpeg` skipped the download branch even if it was corrupt, after which
  final verification failed on every rerun;
- installed bytes had no receipt, so a different executable with the same feature flags was accepted
  as though it were the fetched object;
- a planted hardlink at the predictable output path could be truncated by a downloader/copy step.

## Implemented contract

`scripts/fetch-ffmpeg.sh` now:

1. refuses a linked, non-directory, wrong-owner, or group/other-writable Linux install root;
2. acquires an owner-only, single-link kernel lock without truncating the stable lock path, and
   descriptor-binds it through `/proc` so process death releases it without stale-lock recovery;
3. creates an unpredictable mode-0700 attempt under that root;
4. downloads only to the private attempt and checks the pinned archive SHA-256 before unzip;
5. requires exactly one ffmpeg and one ffprobe, then executes both staged programs;
6. records their SHA-256 values in a unique immutable generation;
7. publishes exact launchers, ffprobe first and discoverable ffmpeg last;
8. revalidates the generation marker, launcher bytes, binary hashes, and RTL capability on reuse;
9. treats any mismatch as repairable rather than permanently skipping the download;
10. cleans only the private attempt it owns and never writes through a pre-existing final hardlink.

An explicitly supplied `HAWEDIT_FFMPEG`, a Windows-local executable, or a PATH executable is
capability-checked but is not described as HawEdit-authenticated content.

## Evidence

Focused verification:

```text
bash -n scripts/fetch-ffmpeg.sh                         PASS
pytest -q tests/test_fetch_scripts.py                   14 passed
scripts/verify.sh                                       1751 passed, 0 skipped, VERIFY OK
```

The executable cases include:

- corrupt installed executable -> private download -> valid receipted generation;
- staged binary missing HarfBuzz/FriBidi -> refusal, old path byte-identical, no generation;
- valid generation with an appended, behavior-preserving byte mutation -> hash refusal and repair;
- final `ffmpeg` hardlinked to an external victim -> link replaced, victim byte-identical;
- linked and non-directory `.ffmpeg` roots -> refusal before curl;
- non-regular or hardlinked lock -> refusal before curl and no external-victim mutation;
- second unchanged run -> hashes verified and zero curl calls.

The real Windows operator path was also exercised:

```text
ffmpeg version 8.1.1-full_build-www.gyan.dev
libass + HarfBuzz + FriBidi: present - nothing to fetch
```

The required Linux CI run is the authoritative real-download acceptance for this change; it must
remain green before this unit is promoted. This evidence does not claim GPL redistribution approval
or protection from a hostile process running as the same account after verification.

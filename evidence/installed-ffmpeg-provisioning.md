# Installed-wheel FFmpeg provisioning

Date: 2026-08-09
Decision: D-150

## Defect

`scripts/fetch-ffmpeg.sh` provided a pinned and transactional Linux installation only from a source
checkout. The wheel did not contain that script or an FFmpeg setup entry point, while runtime errors
instructed installed users to run the checkout-only path. This made remediation unavailable exactly
where release packaging promised a usable application.

## Installed contract

- `hawedit-ffmpeg-setup` is a wheel console entry point.
- `share/hawedit/scripts/fetch-ffmpeg.sh` is a required wheel member.
- Installed lookup authenticates that member through the selected HawEdit distribution's raw RECORD,
  including the recorded size and SHA-256.
- Existing FFmpeg and FFprobe are executed and checked for libass, HarfBuzz, and FriBidi before a
  setup result is reported.
- Linux absence invokes the pinned provisioner in an absolute per-user cache. Windows and macOS
  return package-manager remediation rather than executing a Linux artifact.
- `--check` is non-mutating on every platform.
- Runtime discovery checks the source generation, then the per-user installed generation, then PATH;
  an explicit `HAWEDIT_FFMPEG` remains highest priority.

## Clean-wheel evidence

The actual wheel was built from the current tree, installed without dependency resolution into a
fresh Windows Python 3.12 virtual environment outside the checkout, and then given the packaged base
hash lock with `--require-hashes --only-binary=:all:`.

```text
wheel: hawedit-0.1.0-py3-none-any.whl
wheel SHA-256: 1147b2122455761dc1ef8410186058252e7a7193f337605f6b83361174c07021
pip check: No broken requirements found.
packaged script SHA-256: df165a5d1e53c68b73e9f32650049d4372a69514fd59940614cd2ce41c1c1410
hawedit-ffmpeg-setup --help: PASS
hawedit-ffmpeg-setup --check: hawedit-ffmpeg-ok (FFmpeg 8.1.1 full build)
```

The focused cross-contract suite covered setup, shell transaction, discovery, ingest/render/video
errors, model remedies, wheel validation, release workflow, and Python support:

```text
309 passed in 64.39s
Ruff check/format: PASS
mypy: PASS
bash -n scripts/fetch-ffmpeg.sh: PASS
```

The final canonical source gate, after the module map and VEX source binding were updated, was:

```text
Ruff: PASS
mypy: 123 source files, PASS
format: 123 files, PASS
pytest: 1761 passed in 143.68s, 0 skipped
JUnit evidence: 1761 collected, 1761 passed, 0 skipped
VERIFY OK
```

The release workflow independently installs the exact transported wheel with packaged hash locks,
authenticates the provisioner member, and runs the installed command's help surface before
attestation. The required Linux gate performs the real pinned download. No FFmpeg executable is
bundled in the wheel, so this evidence makes no redistribution or GPL-clearance claim.

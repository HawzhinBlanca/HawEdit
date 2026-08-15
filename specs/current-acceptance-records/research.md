# Research — current acceptance records

## Authority and method

`AGENTS.md` makes `PROGRESS.md` the built-state ledger and `evidence/` the home for measured
claims. `README.md` is the operator path and `AUDIT_REPORT.md` is the honest release call. Serena
is unavailable in this environment, so references were mapped with `rg`, direct file inspection,
GitHub run/job/artifact APIs, downloaded artifact verification, and clean installed-wheel probes.

Source under review is protected main
`ef40ff7c15a58acd3ac3adb3b16808f8194d396a`.

## Measured current state

- Canonical gate run `31874928483`, attempt 2, succeeded for the exact source SHA. Its protected
  `wsl-asr-security`, hosted Python 3.12 compatibility, and canonical gate jobs all succeeded.
- The hosted WSL evidence artifact is
  `hawedit-wsl-asr-vex-ef40ff7c15a58acd3ac3adb3b16808f8194d396a`, with service digest
  `sha256:526d4a181410f1a7a75b3b8c62edd8b24c53aee3091f439097fb00e34ab6d4d0`.
  Its JSON records 140 exact runtime distributions, two CUDA devices, three Omni assets totalling
  43,546,500,168 bytes, and 12 findings matched to 12 reviewed dispositions.
- Release workflow run `31875765513` succeeded for the same exact SHA: unprivileged build, clean
  Linux Python 3.11 and 3.12 wheel smoke, fresh-runner validation and GitHub OIDC attestation, and
  guarded publication logic all passed.
- The retained release artifact is
  `hawedit-release-ef40ff7c15a58acd3ac3adb3b16808f8194d396a`, service digest
  `sha256:3d728ea16e928b914fa66cde3bb88ff88388e46d2efc6a12bff76fb9495567f9`.
  The wheel SHA-256 is
  `a443e77082ed396cf44b9455dc39bdc632e24e5a579bc900ad45d3815d61d075`; every one of the four
  retained payloads passed `gh attestation verify` with exact workflow, main ref, source digest,
  signer digest, and GitHub-hosted-runner policy.
- Independent clean Windows environments installed that exact wheel with its packaged hash lock
  on CPython 3.11.15 and 3.12.10. Both passed `pip check`, exact environment audit, installed font,
  model-manifest and ffmpeg-script lookup, and all nine console-script `--help` probes.
- No `v0.1.0` tag or public GitHub Release exists. The publish job therefore retained the attested
  bundle and made no public release, exactly as the promotion policy requires.

## Documentation drift

1. `README.md` still says protected live VEX enforcement is an acceptance task, although the
   exact-main protected job and hosted artifact succeeded.
2. `README.md` still labels the Windows CUDA graph an unlocked bootstrap, although M0.18 and the
   packaged GPU lock record a real clean dual-GPU smoke.
3. `PROGRESS.md` M3.7 still says the first live attestation has not happened. The durable public
   release remains pending, but the live attestation prerequisite is closed.
4. `AUDIT_REPORT.md` says Meta's downloader owns unverified model-card bytes. Current
   `omni_assets.py`/receipt/VEX acceptance instead binds the exact card, effective cards and three
   asset files. The honest residual is native KenLM/Sox build reproducibility, not Omni checkpoint
   byte identity.
5. `AUDIT_REPORT.md` still requires “a real Sorani ASR run” despite the dated 38-minute acceptance
   already in `PROGRESS.md`; the correct present shortfall is a rerun after the latest source
   changes plus labelled accuracy, not absence of any real run.

## Boundaries that remain open

- No public immutable version exists without the human-authorized exact tag.
- KenLM/Sox source archives are hash-bound, but compiler, headers and produced native bytes are not
  bit-reproducibly attested.
- The current main SHA still needs the planned 38-minute Stage 1 rerun after the external GPU lease
  clears; prior real execution is evidence of the path, not current-SHA acceptance.
- Real labelled Sorani and human editorial benchmarks, confidential Vertex authorization and
  active-speaker reframing remain external/human acceptance items.

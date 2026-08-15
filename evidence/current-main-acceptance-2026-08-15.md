# Current-main WSL, release and clean-wheel acceptance — 2026-08-15

This record binds the accepted deployment and release evidence to protected main
`ef40ff7c15a58acd3ac3adb3b16808f8194d396a`. It is execution, integrity and packaging evidence;
it is not Sorani accuracy, editorial quality, Vertex confidentiality or public-release approval.

## Protected main and WSL security

Canonical gate run `31874928483`, attempt 2, completed successfully for the exact source SHA.
`python-312-compat`, `gate`, and the protected self-hosted `wsl-asr-security` job all succeeded.

The WSL job uploaded
`hawedit-wsl-asr-vex-ef40ff7c15a58acd3ac3adb3b16808f8194d396a` with service digest
`sha256:526d4a181410f1a7a75b3b8c62edd8b24c53aee3091f439097fb00e34ab6d4d0`.
The accepted 10,382-byte report records:

- source package SHA-256
  `d8547bdc2421b3853ba02e050d76cf055ca6f3ebb27f4df45759c9b6bea896bf`;
- CPython 3.12.0 and 140 exact runtime distributions;
- two CUDA devices;
- three canonical OmniASR assets totalling 43,546,500,168 bytes;
- pip-audit 2.10.1 in an exact 29-wheel scanner environment; and
- 12 findings matched to 12 current reviewed dispositions.

The policy expires on 2026-09-08. Acceptance means the reviewed affected/mitigated policy matched;
it does not mean the runtime has no known vulnerabilities.

## Exact-SHA release workflow

Workflow run `31875765513` completed successfully for the same SHA:

- `build-release` succeeded with only contents/actions read permission;
- clean installed-wheel smoke succeeded on Linux CPython 3.11 and 3.12;
- `attest-release` independently revalidated the four-file set and attested every payload; and
- `publish-release` correctly made no public release because no exact `v0.1.0` tag exists.

The retained artifact
`hawedit-release-ef40ff7c15a58acd3ac3adb3b16808f8194d396a` has service digest
`sha256:3d728ea16e928b914fa66cde3bb88ff88388e46d2efc6a12bff76fb9495567f9`.
Downloaded payload identities are:

| payload | SHA-256 |
|---|---|
| `hawedit-0.1.0-py3-none-any.whl` | `a443e77082ed396cf44b9455dc39bdc632e24e5a579bc900ad45d3815d61d075` |
| `hawedit-0.1.0-py3-none-any.whl.spdx.json` | `bbf5b0bc1cac69d8261332224e8cbf1a9a19576b7d80290107ea32e750f54ded` |
| `release-provenance.json` | `029a24c7e3ed92ce3a9726a6465902e03cca1c50035b3ee20d5f5fe2f9f35fb4` |

`SHA256SUMS` verified those three files. All four payloads, including the checksum manifest, passed
`gh attestation verify` with repository `HawzhinBlanca/HawEdit`, signer workflow
`.github/workflows/release.yml`, source ref `refs/heads/main`, source and signer digest
`ef40ff7c15a58acd3ac3adb3b16808f8194d396a`, and `--deny-self-hosted-runners`.

## Independent Windows installed-wheel smoke

The downloaded wheel was installed outside any checkout into fresh Windows environments using its
packaged `host-base-windows-py311.txt` and `host-base-windows-py312.txt` locks with
`--require-hashes --only-binary=:all:`.

| interpreter | result |
|---|---|
| CPython 3.11.15 | exact environment audit, `pip check`, six installed-data probes and nine CLI `--help` probes passed |
| CPython 3.12.10 | exact environment audit, `pip check`, six installed-data probes and nine CLI `--help` probes passed |

The data probes resolved both Noto font files, all three model metadata manifests and the packaged
ffmpeg provisioner. The CLI set was `hawedit`, `hawedit-asr-bench`, `hawedit-editorial-bench`,
`hawedit-asr-setup`, `hawedit-credentials`, `hawedit-fetch-models`, `hawedit-ffmpeg-setup`,
`hawedit-release`, and `hawedit-wsl-vex`.

## Remaining boundary

- There is no tag or public GitHub Release; promotion remains an explicit human authorization.
- KenLM/Sox produced native bytes are not bit-reproducibly attested.
- The latest source still needs the planned 38-minute ASR rerun after the independent GPU lease
  clears.
- Labelled Sorani/editorial benchmarks, authorized confidential Vertex routing and active-speaker
  review remain outside this acceptance.

# WSL OmniASR vulnerability enforcement - 2026-08-09

## Honest result

The code-solvable boundary and a native acceptance run are complete. On 2026-08-09 the canonical
Ubuntu WSL receipt for HawEdit source SHA-256
`aa651eeb520967ee7a8c195508ce863741a7563a336eaf18ec87a997a96ae3db` passed the live gate on
the two-RTX-3090-Ti host: 140 exact distributions, CPython 3.12.0, three canonical OmniASR assets
totalling 43,546,500,168 bytes, and two CUDA devices were revalidated before and after the audit.
The exact result and artifact digest are recorded in
`evidence/wsl-asr-live-acceptance-2026-08-09.md`.

`security/wsl-asr-vex.json` is a 30-day disposition expiring 2026-09-08, not a claim that the
dependency graph is vulnerability-free. It binds CPython 3.12, exact dependency locks, package
versions, all three OmniASR asset identities, and the reviewed HawEdit source SHA-256
`d8547bdc2421b3853ba02e050d76cf055ca6f3ebb27f4df45759c9b6bea896bf`. Any later source change
must trigger disposition review and a new digest; code mitigations cannot be carried onto old or
modified worker bytes by matching only dependencies and assets.

On 2026-08-15 protected `main` commit `bd055e19dc15f9dc4380d149ed3a4184ea77873d`
(package digest `8dc112b148061b69c76d6a2cda5c83913a6fe0e684b23ace7802142227f97519`)
completed GitHub run 31868434251 attempt 2: Python 3.12 compatibility, the canonical gate, and the
self-hosted `wsl-asr-security` job all passed. GitHub artifact
`hawedit-wsl-asr-vex-bd055e19dc15f9dc4380d149ed3a4184ea77873d` has service-reported digest
`sha256:00c8f2d51da9b6831abc5e4cb4a067fcf495974a58c99fa6f43b78cbb66ff194`;
the extracted 10,382-byte JSON hashes to
`c1d682c072d8c64b546711b78ca50144a35fea6ef44d3776e86da0573bba1c82` and records `accepted`,
140 packages, 12 findings, 12 matched dispositions, three assets / 43,546,500,168 bytes, and two
CUDA devices.

The following validator-readiness correction separates exact checkpoint bytes from loader
placement and changes no dependency, advisory disposition, checkpoint, asset, deserialization
path, descriptor binding, or mitigation. Review therefore rebinds the policy to the current
`d8547bdc…` package digest above. It does **not** inherit the accepted `8dc112b…` run: after merge,
the new exact source still requires its own receipt and hosted live audit.

The 2026-08-15 review rebound the policy after setup, Stage 1, and this live gate were composed
through one fail-closed external runtime-root resolver. The change does not alter an advisory
disposition, dependency, checkpoint, or asset. It also does not inherit the 2026-08-09 live result:
the earlier artifact remains historical evidence for its own source digest until this exact source
receives a new receipt and passes the live command below.

The same review was repeated after the editable model-fetch environment began resolving its
code-bound lock from the authoritative PEP 660 checkout instead of requiring a wheel `RECORD`.
That host-only dependency-audit correction changes no WSL package, advisory disposition,
checkpoint, asset, or mitigation. The policy is therefore rebound to the reviewed package digest
above, but it still gains no live acceptance by inheritance; a new receipt and live run remain
required.

The runtime-composition reconciliation then made the already-correct `--exec` behavior a single
public implementation consumed by setup, Stage 1, and this live VEX gate. It removed the VEX
gate's duplicate prefix builder and changed no WSL dependency, advisory disposition, checkpoint,
asset, or mitigation. The policy is rebound to the reviewed package digest above, again without
inheriting live acceptance; the current source still needs its own receipt and live audit.

The live command validates the current receipt and live runtime before and after the audit,
rehashes the canonical assets through the existing probe, captures the VEX bytes once to prevent
pathname-swap evaluation, and publishes success evidence with create-new/no-overwrite semantics.
It parses pip-audit 2.10.1's real top-level object schema, `{dependencies: [...], fixes: []}`, and
refuses non-empty/malformed `fixes`, duplicate keys or advisories, unknown findings, inventory
drift, stale dispositions, expiry, or identity drift.

## Scanner supply-chain boundary

The gate does not use `uvx` or `uv tool run`. It creates an ephemeral CPython 3.12 scanner and
installs a reviewed 29-wheel graph with `--require-hashes --only-binary :all: --no-deps
--no-sources`. The exact installed distribution map is verified before execution.

- pip-audit: `2.10.1`
- scanner lock SHA-256: `53702d6ab105a1630abc25c29e13c52841205d569c02931f82c2faeac22068d5`
- verified scanner inventory SHA-256: `b20c9ba80b886f9f64845197dcd6e88158ad0c126eb4bfd71e6d913e9e30ad6c`
- audit contract SHA-256: `13223c803ec6012b2ad52350f09f591efb4053e7e3fdc2a2660baad3db78cd5e`
- advisory service: OSV, exact endpoint `https://api.osv.dev/v1/query`

The existing absolute `uv` executable remains part of the canonical host/WSL trust base; its
version is recorded. It cannot select unreviewed scanner packages because every installed wheel
is exact-version/hash bound and builds/dependency resolution are disabled.

A bounded diagnostic smoke installed this exact graph with WSL `uv 0.11.15`, verified
`pip-audit 2.10.1`, and received the real 2.10 object report (9,782 bytes, expected finding exit
code 1). It targeted the legacy environment only to exercise scanner mechanics and schema; it is
not current-runtime acceptance evidence.

## Disposition truth

The reviewed report has eight Torch records and four Transformers advisory families after alias
collapse. CVE-2026-24747 remains **affected, mitigated**, not unreachable: Torch 2.8.0 executes
the affected weights-only unpickler, while exact independently measured checkpoint/tokenizer
bytes, no-follow regular-file hashing, descriptor binding, card integrity and path/type controls
limit what reaches it. Other tensor-operation findings also retain residual risk where complete
transitive non-reachability was not proven.

## Acceptance and renewal

The accepted run used these commands; repeat them after any source or dependency change and before
the 2026-09-08 policy expiry:

```powershell
python -m hawedit.wsl_setup --distribution Ubuntu
python -m hawedit.wsl_vex_gate `
  --distro Ubuntu `
  --evidence evidence\live\wsl-asr-vex-20260809T120000Z.json
```

Acceptance requires exit zero and a new evidence file. Exit one, a missing current `.ready`,
scanner/network failure, a pre-existing evidence path, or any drift is refusal. The protected GPU
workflow invokes this boundary; it still needs its first post-merge run from default `main` because
GitHub does not expose the workflow for dispatch before that merge.

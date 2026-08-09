# WSL OmniASR vulnerability enforcement - 2026-08-09

## Honest result

The code-solvable boundary is implemented, but this checkout has **no live acceptance result**.
The current HawEdit source fingerprint is `b1387f64265aa4ea`; its required canonical receipt
`C:\Users\Wareen\AppData\Local\HawEdit\wsl-asr\sources\b1387f64265aa4ea\.ready` does not exist.
Only the legacy unversioned `venv` is present. It is not accepted as the current runtime and was
not used to manufacture a success artifact.

`security/wsl-asr-vex.json` is a 30-day disposition expiring 2026-09-08, not a claim that the
dependency graph is vulnerability-free. It binds CPython 3.12, exact dependency locks, package
versions, all three OmniASR asset identities, and the reviewed HawEdit source SHA-256
`b1387f64265aa4eab3b712aea4d366f66b0bd51e79f2543fee0c62db7f67b722`. Any later source change
must trigger disposition review and a new digest; code mitigations cannot be carried onto old or
modified worker bytes by matching only dependencies and assets.

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

## Acceptance handoff

After all source work is final, first update/review the VEX source digest, provision the matching
canonical runtime, then run the live gate in the same protected job:

```powershell
python -m hawedit.wsl_setup --distribution Ubuntu
python -m hawedit.wsl_vex_gate `
  --distro Ubuntu `
  --evidence evidence\live\wsl-asr-vex-20260809T120000Z.json
```

Acceptance requires exit zero and the new evidence file. Exit one, a missing current `.ready`,
scanner/network failure, a pre-existing evidence path, or any drift is refusal. No workflow or
release command invokes this boundary yet; CI integration and a live success artifact remain the
workflow owner's acceptance task.

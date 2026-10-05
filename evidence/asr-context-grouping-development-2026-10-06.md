# ASR Context Grouping Development Checkpoint

```yaml
commit: 899ab32c0efcdf306245a2dcbe55d8124e436c0e
media_sha256: bd004519e4ed0254f5c4f5197aa501acc56ce957829f62ac0bdc4d7190ec1dd2
host: HawaPC01; Windows 11 build 26200; WSL2 Linux 6.18.40.1; two RTX 3090 Ti
command: .venv/Scripts/python.exe -B C:/Users/Wareen/run_hawedit_isolated_decoder_899.py probe-boundaries
```

The header names the committed source used by the real boundary investigation,
NOT a committed grouping implementation or a release candidate. The component
checks below use explicit uncommitted worktree source. No gate/CI, native accuracy,
independent-job reliability, security closure, publication or 10/10 is claimed.

## Frozen Real Input

ZAR38 source: C:/Users/Wareen/Desktop/Test Videos/ZAR38MinTest.mp4.
Normalized PCM SHA256:
312fe70941e143ef831b763ff9b050cbe2fa5b57023a825f63917e9e12e51b0a.
Champion identity:
lora:dfa6237a3b287b7ca6ef88d848a3540ffbf052f8900bd88e99b5e3495d65809d.
Source package digest:
7021258a988959da0dcaa2be667cc60eab45805fe5eee3454f97d3fa7b57c4e8.
Runtime: CPython 3.12.0, torch 2.8.0/CUDA 12.8, omnilingual-asr 0.2.0,
fairseq2 0.6, PEFT 0.19.1, transformers 4.57.6. Shared host and traced decoder:
timing is not isolated performance acceptance evidence. No paid calls.

## Actual Findings

All 560 loaded adapter tensors match their frozen bundle after runtime dtype cast;
280 adapter layers are active, none disabled; zero modules are in training mode.
Model and tokenizer vocabulary agree. The original 905634..917022-ms excerpt
fails natural-completion admission under greedy and four-beam normalized decoding.
Adding only preceding speech also fails. Four tested windows retaining complete
following speech naturally finish under the unchanged greedy decoder. All
eleven boundary invocations, including controls and failed arms, are retained.
These are completion observations, not accurate speech/number measurements.

The fixed broader experiment compares original/grouped windows for all 25 selected
development/risk rows (50 invocations). Collection closed with five refusals across
the two arms; this is not a passed producer or completed benchmark. All target PCM was
verified unchanged before trials. Repeated groups are correlated within one episode.

## Component Checks

Actual worktree: C:/Users/Wareen/.codex/worktrees/asr-context-grouping/HawEdit.
Read-only installed host interpreter: primary .venv/Scripts/python.exe; child
asserts actual worktree ASR import before pytest. No canonical gate override.
Host: CPython 3.12.10; pytest 9.1.1, ruff 0.9.6, mypy 1.15.0, DBOS 2.29.0.

- Red: all 24 new contract cases fail against old implementation.
- First affected run: one erroneous input fixture at exactly 38000 ms retained;
  correcting its endpoint by one millisecond exercises the intended refusal.
- Separate first type check: one non-exported module access in the new test,
  corrected without changing production behavior or weakening assertions.
- Latest green-v3: 229 passed, zero failures/errors/skips, JUnit 43.177 seconds.
- Full-scope static-v1: lint, mypy (323 files), format (323 files) all exit 0;
  watched Python source stays unchanged. Controller elapsed 93.882349 seconds.

Worktree ASR SHA256:
cbc74c744c6dfc2daf3f6dd89b1f3fbea4fb754ff136dcbf611d0c83c9971c87.
New test SHA256:
9cec76fdc7506011b586d1bf7a904230d6abd6b91e5908f0a2236e54b6067d2d.
Real PCM cutting is exercised; controlled ASR/transport output is not native speech
evidence. Existing first-ASR/validator-failure tests are not bypassed or disabled.

## Records And Next Gates

Private immutable records under C:/Users/Wareen/AppData/Local/HawEditEvidence/:
asr-isolated-decoder-runtime-20261005/{probe-state-v2,probe-boundaries,probe-groups};
asr-context-unit-20261006/{red,green,green-v2,green-v3,static-v1}.
Actual Serena definition/reference maps precede source edits; see the impact map.
D-283 and specs/asr-context-grouping/ describe the conditional input-policy repair.

The wider input aligns 23/25 versus original 22/25, but introduces dev-15/dev-18
refusals while resolving risk-01/02/03. REJECT the 38000-ms prototype, do not
activate it. The full collection and watched inputs/source close unchanged;
controller elapsed 5217.071957 seconds includes traced shared-host work/load.
Sealed stdout SHA256: b6bd75abf3c217ed87c431556410783f7b022df4efba44e3f1881710c023d6c1;
terminal: 25fb5a4787b928785f05278416791261988b48634434ae37604d1b72259f7007.
Counts are not native fidelity, independent job reliability or performance claims.

A predeclared 18000-ms/1000-ms study of all 25 fixed samples is now collecting,
after baseline process closure, with lower-overhead terminal-token observations
and unchanged actual completion admission/CTC. Timings are not comparable.
Retain this rejected prototype locally for reproducibility; no primary integration
or claimed fix from it. Only a supported next candidate can proceed to local
reviewed commit/integration, exact bash scripts/verify.sh at committed source,
supported source-bound runtime and fresh full ZAR38 producer retest. Production
still halts at its first failure. Required CI, current qualified VEX review and all
independent/native/sustained acceptance obligations remain open; no ledger flip.

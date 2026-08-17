# Semantic merge of protected main — 2026-08-10

## Immutable Git proof

- readiness parent: `bc12e13e8180c622889d427e4c67214c013129e3`
- protected-main parent: `ba52888579f4873cfd9a60a84d7934544bfdeeb1`
- merge: `89a1641`
- readiness-parent tree: `6b1963dc27a1e0997c7e7bfa091bcf29c25c72ae`
- merge tree: `6b1963dc27a1e0997c7e7bfa091bcf29c25c72ae`

The merge tree is byte-identical to the first parent that passed the canonical 1,989-test gate.
The second parent is present to join history after semantic integration, not to choose stale files
through 35 textual conflicts.

## Upstream-only semantic matrix

| Upstream commit(s) | Finding | Readiness implementation/evidence |
|---|---|---|
| `bba56a9`, `7fd5a55` | authenticated FFmpeg archive and safe retry | `scripts/fetch-ffmpeg.sh`, `scripts/verify-sha256.sh`, `evidence/an-archive-fetched-from-a-branch-and-never-checked.md` |
| `d391394`, `953af2c` | escalation disagreement and decoded CTC hypothesis | `src/hawedit/escalation.py`, `src/hawedit/asr.py`, `tests/test_escalation.py`, `tests/test_asr.py` |
| `d1676a5`, `b1da684` | deterministic merge/rank and complete §8.1 metrics | `src/hawedit/discovery.py`, `src/hawedit/bench.py`, their focused tests |
| `4f7bafd`, `149624d` | render/delivery proof and strict timecodes | real render tests, strict SRT parsing, and `evidence/m3-6-high-frame-rate-drop-frame.md` |
| `b5662a0` | Stage 4 receives actual pixels | `JudgeFrame`, keyframe extraction, Gemini transport tests and real frame evidence |
| `7269dd0`, `e509c64`, `06adf58` | judge tie refusal, reachable completion, empty benchmark refusal | current judge/pipeline/bench contracts and tests |
| `2ae692c` | stale claims | current `PROGRESS.md`, `AUDIT_REPORT.md`, and claim bindings |
| `5a064ff`, `0e1ad43` | Stage 0 and Stage 1 resumability | D-209 ingest cache, transcript receipts, ASR reuse tests |
| `9f62f10` | normalized Kurdish glyph coverage | D-210 runtime font-bound render guard |
| `36a5f3c` | BM25 needs sentence documents | D-211 `Bm25Index.from_sentences` and runner wiring |
| `bf7daee` | credential panel verify-before-store | hardened credential panel and transport/CLI tests |
| `57c9a76` | TOCTOU test cannot skip | zero-skip gate plus cross-platform simulated reparse coverage |
| `e677f29` | Python dependency supply chain | 12 target hash locks, exact inventory audits, locked release smoke and GPU profile |
| `b0f0391` | Stage 2 embeddings were recomputed | D-215 atomic source/window/model/revision cache; real locked-GPU two-pass evidence |
| `5bb7f18` | console-script audit list drift | audit list bound both ways to all nine current declarations |
| `965a11f`, `6f23d29` | help names an untypeable command / Windows-only test | D-216 shared invocation rule across all nine commands and native Linux/Windows tests |
| `ba52888` | README understated required gate and stale CLI map | required-gate sentence already present; D-217 adds symmetric ledger and `cli.__all__` bindings |

## Gate before merge

Immediately before the history join, `scripts/verify.sh` reported:

```text
1989 passed
test evidence OK — 1989 collected, 1989 passed, 0 skipped
VERIFY OK — hawedit gate green
```

A post-merge gate is required separately because the commit identity changes reproducible-wheel
timestamps even when the tree does not.

## First protected-main advance after the initial join

`main` advanced once more during the first push with `7002331`, which fixed the `ANSWERED`
resolution-vocabulary blind spot. Readiness reproduced that finding, implemented D-219 against
the stronger claims suite, and passed its focused tests before joining history again.

- readiness parent: `baf11b07f82bc87e1c0cafebe2f5a8ccccdc508b`
- protected-main parent: `70023318895e240f2d65b39ef43b5b48113f52a3`
- merge: `81287074d7068692f0e2c3019701f1930d34e079`
- readiness-parent tree: `ecb193121a6778a2ff2b9f65d643e0a4f29b7d2a`
- merge tree: `ecb193121a6778a2ff2b9f65d643e0a4f29b7d2a`

Thus all 26 upstream-only commits at that point were ancestors, and the join again introduced no
unreviewed file content. The canonical 1,994-test gate was run after this merge rather than
inferred from tree equality.

## Confidential-route advance

After that exact-SHA hosted gate completed, protected main advanced to `b24ce15` with the finding
that Vertex's separate constructor had unheld §7 routing. Readiness integrated the finding as
D-221, added the bidirectional constructor-hierarchy matrix, passed 65/65 Gemini tests, and raised
the exact floor to 1,999 before joining history.

- readiness parent: `42aa923b725e03f718a6b1ca0479920fab73a8f5`
- protected-main parent: `b24ce15f451d60d9e5908746c59e5626ddf696f7`
- merge: `ccb11a350d6c1bcb56bc22537babb7ffdd5c7ab0`
- readiness-parent tree: `a332a67e40983efbac9f5cf296b45577f54cca56`
- merge tree: `a332a67e40983efbac9f5cf296b45577f54cca56`

All 27 upstream-only commits are now ancestors. As before, tree equality proves only that the
history join added no content; the full local and hosted gates at the eventual final tip provide
acceptance.

## Auto-selection and interrupted-delivery advance

Protected main next advanced through `e2c768f` with two findings: `9e8f128` addressed a Ctrl-C
leaving flat delivery sidecars that wedged a retry, and `e2c768f` measured `--visual
--auto-select` spending real Stage 0 work despite having no retrieval query.

The delivery finding is semantically superseded, not ignored. Readiness publishes the five files
as one hidden private `ArtifactBundle` directory, validates the exact set, and performs one
no-replace directory rename. Its crash regression proves that an abandoned private directory is
invisible and a clean retry succeeds; its concurrent-publisher regression proves no replacement.
It deliberately does not claim that SIGKILL removes private scratch space.

The precise auto-selection invocation was already rejected by readiness's stricter
`--visual without Path A requires --visual-query` preflight. D-224 made the adjacent producer
predicate structurally query-capable, corrected the structured instruction, and added seven
behavioral tests spanning both positive routes and every refusal. Focused pipeline, claims and
evidence acceptance passed 171/171. The clean first parent then passed the canonical gate: Ruff,
mypy over 129 source files, formatting, 2,008/2,008 tests, zero skipped and accepted JUnit evidence
in 236.2 seconds.

The histories were joined only after those classifications and acceptance:

- readiness parent: `4b63c044f21236445eb6953c15f438faf93070fc`
- protected-main parent: `e2c768f0f63482de5d4dac277643408e5780d23b`
- merge: `ded03cc475b3575cc0429859fc2edca0e3fc9c53`
- readiness-parent tree: `03b07a54ce0d40c98e3f3b0de78b2c1a27640264`
- merge tree: `03b07a54ce0d40c98e3f3b0de78b2c1a27640264`

Thus protected main is an ancestor, while tree equality proves the merge imported no stale file
content. A post-merge canonical gate remains required because the merge changes commit identity
and therefore reproducible-wheel timestamps even though the tree is equal.

## Confidential Vertex ZDR coverage advance

Protected main advanced again to `3765add` with no production-code delta. It proved that disabling
the confidential Vertex ZDR gate reddened nothing and recorded a mutated judge sending both the
client transcript and real source JPEG bytes through `countTokens` and `generateContent`.

D-226 integrated the finding against readiness's newer class-set routing matrix. Every concrete
judge is now exercised under three forbidden confidential states with a recording transport;
configuration and attribution are separated; `count_parts` and `generate_json` gate independently;
and positive controls prove the allowed route still sends. The 13 new cases made the focused
Gemini suite 78/78 and the combined Gemini/claims/evidence slice 124/124.

The exact collector rose from 2,008 to 2,021 and the floor was ratcheted to that measured value.
The clean first parent then passed Ruff, mypy over 129 source files, formatting, 2,021/2,021 tests,
zero skipped and accepted JUnit evidence in 258.6 seconds.

The histories were joined after that acceptance:

- readiness parent: `8bd29740850f0227d4cfe25914f47742e32183e1`
- protected-main parent: `3765addc446ec7ba661091fdc7aaf548fda9573c`
- merge: `8cf878dde4b5cc1ba49e6c2707d85bff3609ad89`
- readiness-parent tree: `32bb011f1195b1f063d51efd5a59f34b327b9c3f`
- merge tree: `32bb011f1195b1f063d51efd5a59f34b327b9c3f`

Protected main is therefore an ancestor and the join imported no older file content. As with each
prior join, an exact post-merge gate is still required for the final commit identity.

## CLI-preflight source-binding advance

Protected main then advanced to `2fd2e55` with the measured CLI-refusal finding integrated in
D-228. Readiness had already replaced the weak exit-only assertions with a broader 21-case matrix,
removed two dominated branches, and covered all 15 live preflight guards. The upstream delta added
one material future-regression net: bind the case table to the source rather than only enumerating
today's behavior.

Readiness adapted that insight by reading every direct `ValueError` before input loading through
the AST and requiring a one-to-one case-fragment match in both directions. A legal-argv control
must pass the whole block. The focused pipeline suite rose to 143/143; the combined
pipeline/claims/evidence slice passed 189/189; and the exact floor rose to 2,039. Package source
bytes remained `3994b043398d95c0f2c01a0d8aac52fd18465b72900f865553738846dfdc05e6`,
so the already accepted receipt-bound WSL VEX artifact remained current.

The clean first parent passed Ruff, mypy over 129 source files, formatting, 2,039/2,039 tests, zero
skipped and accepted JUnit evidence in 257.2 seconds. The histories were then joined:

- readiness parent: `f5087bf72264e4e99456bb95bad538346fe6ab15`
- protected-main parent: `2fd2e55d5679e6aa2a963e14a177449ad99d26fa`
- merge: `f35680459859773cbfc58f3f4b7696aa05bb66e2`
- readiness-parent tree: `a40298ea3654e74eef9f681b32507fde602b35a1`
- merge tree: `a40298ea3654e74eef9f681b32507fde602b35a1`

Protected main is again an ancestor and no older content entered the tree. The final commit identity
still requires its own canonical and hosted gates.

## Stage 2 query-normalization coverage advance

Protected main next advanced to `ba2a445` after measuring that removing query normalization from
either the Qwen visual embedder or reranker left its full suite green. Production code was already
correct; model-input coverage was absent.

D-230 adapted the finding to readiness's newer verified-load and lifecycle tests. The processor
stub now records actual conversations for both adapters; raw Arabic kaf/yeh, ZWNJ and Arabic-Indic
digits must be absent, while normalized Sorani and ASCII digits must be present. An idempotence
control and a bidirectional inventory of query-reading production classes hold both future and
uniform-failure cases. The focused Qwen/visual/Path-B slice passed 95/95 and the combined
Qwen/claims/evidence slice passed 91/91.

The exact collector rose to 2,044. Package source remained
`3994b043398d95c0f2c01a0d8aac52fd18465b72900f865553738846dfdc05e6`, so the accepted WSL
receipt and VEX artifact remained current. The clean first parent passed Ruff, mypy over 129 source
files, formatting, 2,044/2,044 tests, zero skipped and accepted JUnit evidence in 299.9 seconds.

The histories were then joined:

- readiness parent: `8ee40e9bc2a5522b360b94185fcb794807059f5f`
- protected-main parent: `ba2a445bdda76c237f48a2968ac8ac26e66965bd`
- merge: `b663cd3072c5fe424bcaf9281b544c8eb4e4f5eb`
- readiness-parent tree: `64fd3068d0b4b6374b8a7d3ef6b60cc0e5b05634`
- merge tree: `64fd3068d0b4b6374b8a7d3ef6b60cc0e5b05634`

Protected main is an ancestor and the join imported no older file content. Post-merge local and
hosted gates remain required for the final identity.

## Transcript digest-evidence coverage advance

Protected main next advanced to `f189b19` after measuring that its suite did not hold the
missing/unreadable sidecar refusal in `verify_raw_integrity`.  Its commit changed only tests,
evidence and ledgers; readiness production was already correct.

D-233 adapted the finding to the current transcript store, which no longer has main's
`reusable_raw` method.  Five sidecar-destruction states are derived into direct-verification and
normalized-publication cases, then repeated against changed raw bytes.  Three unreadable states
must report missing evidence; two readable-invalid states must report digest mismatch; an intact
control must still publish and read the normalized artifact.  The focused current-tree slice
passed 289/289, the collector and floor rose to 2,062, and package source bytes remained unchanged.

The clean first parent passed Ruff, mypy over 129 source files, formatting, 2,062/2,062 tests,
zero skipped and accepted JUnit evidence in 248.8 seconds.  The histories were then joined:

- readiness parent: `227e1bcd7ed069a355fae908289023d4f787cbf8`
- protected-main parent: `f189b19f17f7bb30f7153b8aa64efab9b2d23f04`
- merge: `003963dc666d2f2c7717835c996f0977fdfcfc26`
- readiness-parent tree: `e41b8c6624664bb95aabcf3f70f529f754b091a2`
- merge tree: `e41b8c6624664bb95aabcf3f70f529f754b091a2`

Protected main is an ancestor and no older file content entered the tree.  A new post-merge local
and hosted gate is still required for the merged commit identity.

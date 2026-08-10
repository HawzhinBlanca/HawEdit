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
| `5a064ff`, `0e1ad43` | Stage 0 and Stage 1 resumability | D-162 ingest cache, transcript receipts, ASR reuse tests |
| `9f62f10` | normalized Kurdish glyph coverage | D-163 runtime font-bound render guard |
| `36a5f3c` | BM25 needs sentence documents | D-164 `Bm25Index.from_sentences` and runner wiring |
| `bf7daee` | credential panel verify-before-store | hardened credential panel and transport/CLI tests |
| `57c9a76` | TOCTOU test cannot skip | zero-skip gate plus cross-platform simulated reparse coverage |
| `e677f29` | Python dependency supply chain | 12 target hash locks, exact inventory audits, locked release smoke and GPU profile |
| `b0f0391` | Stage 2 embeddings were recomputed | D-168 atomic source/window/model/revision cache; real locked-GPU two-pass evidence |
| `5bb7f18` | console-script audit list drift | audit list bound both ways to all nine current declarations |
| `965a11f`, `6f23d29` | help names an untypeable command / Windows-only test | D-169 shared invocation rule across all nine commands and native Linux/Windows tests |
| `ba52888` | README understated required gate and stale CLI map | required-gate sentence already present; D-170 adds symmetric ledger and `cli.__all__` bindings |

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
resolution-vocabulary blind spot. Readiness reproduced that finding, implemented D-172 against
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
D-174, added the bidirectional constructor-hierarchy matrix, passed 65/65 Gemini tests, and raised
the exact floor to 1,999 before joining history.

- readiness parent: `42aa923b725e03f718a6b1ca0479920fab73a8f5`
- protected-main parent: `b24ce15f451d60d9e5908746c59e5626ddf696f7`
- merge: `ccb11a350d6c1bcb56bc22537babb7ffdd5c7ab0`
- readiness-parent tree: `a332a67e40983efbac9f5cf296b45577f54cca56`
- merge tree: `a332a67e40983efbac9f5cf296b45577f54cca56`

All 27 upstream-only commits are now ancestors. As before, tree equality proves only that the
history join added no content; the full local and hosted gates at the eventual final tip provide
acceptance.

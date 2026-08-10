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

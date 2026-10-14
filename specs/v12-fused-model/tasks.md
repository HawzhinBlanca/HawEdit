# Tasks

Approved-by: Wareen - 2026-10-14, "Approve all T0–T8" (see plan.md).

Rows flip only through `scripts/update-ledger.sh` after `scripts/verify.sh` passes.

- [ ] T0 Hardware measurement on GPU 1 with :8000 stopped (operator run, no repo code)
- [ ] T1 Fused loader: `OmniAsrBackend(fused_checkpoint=)`, direct 7b card, no PEFT
- [ ] T2 Identity `fused:<sha256>` across native, WSL request, worker and factory
- [ ] T3 `--omni-asr-checkpoint` / `HAWEDIT_CHAMPION_CHECKPOINT`, refusals, studio host binding
- [ ] T4 GPU 1 only by default (LLM, CTC, validator)
- [ ] T5 :8000 coordination: worker free-VRAM halt and the pause wrapper
- [ ] T6 ADR D-331
- [ ] T7 Make v12 the default champion (owner decision, not automatic)
- [ ] T8 Loop guard: one beam-5 retry per suspect segment, else halt; ADR D-332

## Definition of Done
`bash scripts/verify.sh` green AND the required CI checks green on the pull request.

# Plan — seven audit repairs

Authorized-by: user instruction in Codex chat 01a2037c-1896-79d0-b7e9-e75b5b59ed94 on 2026-11-22: "fix all 7 issues, start with the high priority ones as best as u can ... avoid overlaps and be communacative". This authorizes the concrete audit recommendations and their regressions; it does not attest security review or approve future unrelated design changes.

1. F1: add explicit restart opt-in to silence APIs, default speech preservation. Require a visible truncation marker for prefix deletion. Existing restart tests must exercise explicit opt-in without weakening their assertions.
2. F2: preserve Gemini output-clock fix; exercise real render plus episode reconciliation.
3. F3: record actual decoded temporal frame counts; default unobserved source, validate source existence/decodability and mapped bounds. Wire actual shot/caption evidence. Reject unsupported all-clear at pipeline consumers.
4. F4/F5: retain numbered sentence grounding and test late moments. Bind cache identity to full normalized transcript, exact resolved sentences, model/prompt/schema/audio/voting configuration and validate cached candidate media, type, rank and bounds.
5. F6: separate opening-frame size from presence fraction; all tracked modes enforce their defaults, with no weakening from first-frame option. Keep signed publication independent.
6. F7: add current-media manifest/profile and real probes; retain legacy ep29 identity and tests. Emit configured/not-configured/profile information so zero-skip is not interpreted as real-media execution.
7. Run scoped regressions, canonical fast/format and full verify in isolated environment. Preserve any source-binding policy refusal as separate evidence for lead integration; never move review/expiry dates to hide it. Do not mark ledger complete without required local/CI evidence.

No active lead/lane branch edits, force pushes, automatic merges, model calls or human approvals fabricated. Use one writer in this worktree; communicate handoff before integrating.

# Decoder Completion Research

Baseline: 6df0998072027cf691500c49630a825d4e062daa, 2026-10-05.
BLUEPRINT sections 3, 4.1, 4.2 and 8.1; D-278 and Model Lock / Champion Supremacy.
Ordinary implementation approved by Wareen: "approve all and fix them".

Actual headless Serena SDK/LSP definitions and references are recorded under
C:/Users/Wareen/AppData/Local/HawEditEvidence/zar38-input-integrity-6df0998-20261005/
in serena-completion-map.json and serena-completion-cache-map.json, with logs.
Definitions and dynamic call paths were read before this unit. Source remained
unchanged during both maps and the frozen comparison/probe. Occurrences are not
independent callers; import fallback warnings remain visible in those records.

The installed omnilingual-asr 0.2.0 one-beam decoder treats compression stopping
as completion without sampled EOS. Actual context audio produced guarded text
that nevertheless aligned. Full frozen development comparison: 100 trials,
96 aligned, four refused alignment; two guarded trials aligned. One episode,
20 pre-output development and five enriched risk passages, not independent
acceptance samples. No native references or accuracy claim.

The external completion observer was tested with actual locked champion/CTC:
two risk inputs refused before alignment; two natural controls retained exact
baseline text and aligned. Four of four planned observations, controller exit 0,
watched bytes unchanged and checkout clean. Trial stream SHA256:
e6511d860b15511435bfcabe0c6d93f7d56d8cd9e02b83665d0ec142beb435ab.
Probe command: .venv/Scripts/python.exe -B
C:/Users/Wareen/run_zar38_completion_probe_6df.py completion-probe.
Evidence: approved-completion-probe/{terminal.json,trials.jsonl}; separate from
full-comparison-findings.md. Do not pool duplicates. Two RTX 3090 Ti, WSL Python
3.12.0, torch 2.8.0/CUDA 12.8, fairseq2 0.6, PEFT 0.19.1, transformers 4.57.6.
Elapsed 551.4612659999402 seconds on shared hardware, not isolated performance.

Extra test-first mechanical regressions found two prototype defects: replaced
configuration identity was not rejected, and deleting the temporary method
masked the intended refusal with AttributeError. Both must be repaired in the
integrated observer. These tests are not real-speech accuracy evidence.

run_pipeline checks reusable_raw before inference. Its key lacks a completion
admission policy, so old raw transcripts could bypass the new guard. Raw remains
write-once: preserve old bytes and refuse legacy/mismatched cache use before
expensive inference. A policy record is cache binding, not authenticated native
fidelity evidence. Explicit imported transcripts remain a separate trust route.

No beam, segmentation, model, language, tokenizer, lexical filter or score change.
No repeated-token trimming, fallback or invented alignment. BLOCKED #1, #3, #4,
#21, #24 and #25 and independent acceptance obligations remain separately open.

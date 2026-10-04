# ASR worker diagnostic research

Baseline: `3ac37381a71a0c43c5692f75b369b5c876058e88`, 2026-10-04 UTC.
Scope: existing approved T2 actionable-refusal obligation, not ASR quality repair.

The actual full ZAR38 production-ASR retry used the supported CLI after official
source-current runtime preparation succeeded. The pinned environment was reused;
no decoder, model, licence, spending or trust authority changed. The retry exited
1 after 830.968 seconds at 905634..917022 ms: 569 frames cannot emit 401 tokens.
No new canonical raw or reel. Source, original failed raw and Stage 0 hashes stayed
unchanged. Private terminal record: `C:/Users/Wareen/HawEditQuality-7fa7-20261004/zar38-asr-retry/terminal.json`.
This early refusal is not comparable with the earlier complete diagnostic run.

The real refusal incorrectly says `Run hawedit-asr-setup first` after setup
succeeded. WslOmniAsrProducer.transcribe takes the final 1,200 stderr characters
and adds a prefix; _operational_failure then sanitizes only the first 1,024
message characters. The final alignment cause is crowded out by traceback paths.
Missing-receipt errors originate separately in _runtime and correctly advise
setup; that branch must remain unchanged.

Actual Serena definitions and referencing symbols are in the four-query
`diagnostics-before-map.json` under the private root, captured at clean 3ac with
mapped source hashes unchanged. Source/API signatures, not guessed interfaces,
ground impact-map and tests. The existing exact gate at this SHA has 4,827 passes
and only the VEX source-binding failure. No policy/date/hash rebinding is permitted.

BLUEPRINT section 3 Stage 1 and section 8.1; D-278 all-stop behavior. BLOCKED #24
still requires qualified security review. Native references and model/corpus rights
remain external requirements; better diagnostics do not correct speech or clear them.

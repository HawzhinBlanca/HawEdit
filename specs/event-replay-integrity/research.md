# Event Replay Integrity Research

Baseline fffee676155aef9dd42c86a88ac1283f1e18e7ce; research before source edits.
Read the Obsidian worker/recovery canon and current event-replay counterexample.
BLUEPRINT sections2-5, D-A8 and D-276 require truthful state and retained evidence.
This is the legacy observer repair, not protected producer/attempt adoption.

Actual Serena LSP definition/reference queries for events.read_events and
JsonlEventSink at the baseline are retained in the external native evidence root
worker-continuation-map-20261007/serena-map.json. read_events has ten references;
the actual definition is lines271-290. Embedded documentation is not proof.

The real helper stops at every malformed line, not only a torn final write. An
exclusive synthetic native probe at17:02:35UTC shows a corrupt middle line hides
a later valid billed record, and a complete final object missing fields is also
silently ignored. Valid roundtrip and genuinely torn final prefix controls pass.
All original probe bytes and events.py hash are unchanged. No actual billed call,
model, media, owner artifacts or source edits were used in the probe.

Evidence: C:/Users/Wareen/AppData/Local/HawEditEvidence/event-reader-counterexample-20261007/terminal.json.
HostHawaPC01/Windows26300/CPython3.12.10. Source SHA256
0c102607cf190a0a24db75190a318e483b55a12214018ee9174578bf224661e9.

JsonlEventSink flush makes events visible, but is not an fsync/crash durability
guarantee. Keep its behavior and CLI API; correct that descriptive claim. Future
protected attempts require their own bound private persistence and billing
reopening. Do not loosen project_events mixed-run/duplicate-sequence refusal.
The canonical baseline gate is5176pass/1VEX failure/no errors/skips, not green.

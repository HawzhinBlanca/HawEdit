# Diarizer Checkpoint Consumer Research

Baseline: `6c3bdbe6db8ef185d2116080968c03396d67f1be`, 2026-10-07.
Vault: Honesty Law; HawEdit initial attempt journal and diarization runtime
research correction. BLUEPRINT sections3 Stage0,7,8.1; D-252/D-276/D-294.

Actual Serena LSP found seven definitions and queried their references before
source edits. Raw map: LocalAppData/HawEditEvidence/diarizer-checkpoint-map-20261007/
serena-map.json. Source was unchanged. Dynamic protocol calls remain callers even
when static references cannot resolve them.

`PyannoteDiarizer.diarize` skips ModelStore entirely when an explicit directory
is supplied. Its default assert_available check precedes the actual interpreter
of checkpoint config/weights, with no held reader lock. Existing
verified_checkpoint_access hashes an exact snapshot under the shared publisher
lock; ASR/visual consumers already use it. The adapter's model_id is also freely
selectable despite its fixed Community-1 revision/output contract.

Existing wire tests use empty temporary directories and upstream doubles. They
prove exclusive result selection, not checkpoint bytes, neural inference or DER.
Preserve their assertions while supplying temporary hash-bound opaque test bytes
and a real configured ModelStore. Do not replace the real verifier with a mock.

HF token/access and pinned five LFS identities are available, but tracked
Community-1 manifest remains blocked. Updating models/integrity.json requires a
narrow owner exception not yet received. No real weights are installed by this
unit. The source-string SDK test still does not prove installed package egress.
Current complete gate is RED on stale VEX; all15 actual scanner findings require
qualified review. No policy digest/date/disposition copy is permissible.

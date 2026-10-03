# Authenticated Delivery Research

Observed 2026-10-03 on clean commit 85b01f101a3bd81922fb53b3c8a8999b88c74a2e;
source package 68e131df5008b8d5938e4f7915e2c4475ccd2b855eaa01e49e0cfb3390751bea.
This extends the approved parent plan's phase 4, BLUEPRINT §§2-5, D-263/D-274/D-276.
No source edit, new reviewer trust, paid run or publication approval is claimed.

## Approved SD-A Implementation Observation (2026-10-03)

The opening baseline above remains historical. The owner subsequently explicitly approved
the concrete plan before source changes. D-277 now records that design; no production trust
is configured. New candidate_review.py freezes final JSON with proposed QC before signing,
preserves unresolved flags and original transcript/plan, and verifies real detached proof
against host-selected private policy. Source/configuration/producer/revision and every member
are reopened and bound. Receipt objects are descriptive, not publication authorization.

Test-first record: missing-module collection refusal in SD-A-first-red.log; 30 failed/10
passed in first implementation exposed a real Windows stat/fstat ctime mismatch. The second
run exposed native CRLF signature armor and exact refusal-message case. Both failures remain
in their original logs. Snapshot checks now compare ctime within each path/descriptor view
and retain cross-view identity/size/mtime/link checks. OpenSSH proof supports uniform LF or
CRLF without rewriting raw bytes; mixed armor refuses. Intact proof is verified before
packet/context/trust/schema tampering, so blanket refusal cannot pass those negative tests.

Final focused observation: 58 passed, 0 failed, 0 skipped in 51.40 seconds. Real ephemeral
Ed25519 signing/verification and actual synthetic encoding/decoding, native CPython 3.12.10,
OpenSSH 9.5p2, Gyan FFmpeg 8.1.1 (not project-pinned). No model/provider calls. Runtime,
commands, source/tool hashes and scope are in SD-A-native-mechanics.json. Fast checks passed
297 checked files; neither result is the canonical gate or product-quality acceptance.
SD-A-storage-regressions.log SHA256:
360dfad53193b2bb7f763d0e1b946384b211559ec1028cdca6c2749977e24885.
Actual first-fix Serena map SHA256:
73f3797ebcf6c7a11b6b9740e43e9e7af04153293b2ddf9555756942e397c6ce.
Actual 41-record before-native-proof-fix map SHA256:
a4095493e1f6cab18997333f98ba0339d52c7ab6e500e2255aef660b22b2f929.

Every new engine API is test-only at this checkpoint. Existing unsigned promotion and direct
publication routes are NOT fixed by this unit. Full gate, same-SHA CI, SD-B/SD-C and the rest
of the seven-phase plan remain required. No ledger row is accepted or product verdict granted.

### Token-Budget Correction

Local checkpoint 98dc257cc8fb1b6a49a5ec7c0f4e8ce46a0fbc7b was made without push. The exact
full gate started on that clean frozen source, passed lint/types/format, but was stopped
after read-only review exposed an overbroad credential filter: genuine producer token
limits/tokenizer revisions were refused. Three new regressions failed before correction.
The exact native pytest child identity was verified before PID-only cancellation; no console
control event or app-server cancellation. Preserve its original partial gate.log, actual
exit127, frozen source manifest and gate-interruption.md in external studio-commit-98dc257...
storage. No terminal JUnit or full-gate pass is claimed for that interrupted run.

Guard correction preserves strict credential/depth/nonfinite refusal and accepts numeric
token limits/tokenizer identity. Both APIs remain test-only. Corrected focused run: 68
passed, 0 failed/skipped, 55.96 seconds on the same native toolchain. Details and actual hashes
are in SD-A-final-native-mechanics.json. Earlier failed/native-58 observations are historical,
not rewritten. A fresh clean committed full gate is required for this corrected source.

## Reproduced Refusal Gap

The existing unmocked test_approved_candidate_promotes_identical_bytes_without_render
publishes deliberately fake bytes using QcRecord metadata and constructed measurements.
Actual replay published a 30-byte MP4 with human_reviewed=true, no signature and no configured
trusted reviewer. The recorded ffprobe 8.1.1 executable rejected the published bytes with
exit 1, "moov atom not found" / invalid input. This is a defect diagnostic, never delivery
quality evidence. Counterexample SHA256:
6d6aabb3f506b4a9e3dc46820a2b9b83a31a9ce4b6ceb08480271f8c9b1146cd.

Artifacts are in the external owner-private studio-commit-85b01f101a3bd81922fb53b3c8a8999b88c74a2e
directory under C:/Users/Wareen/AppData/Local/HawEditEvidence: unsigned-promotion-counterexample
.json/.log and the retained unsigned-promotion-diagnostic directory. The JSON records actual
source/test/tool/output hashes, QC fields and decoder refusal. Native CPython 3.12.10 on
HAWAPC01; ffprobe SHA256 a6618e99bb58869ded3c6f37b53aa1a8d701c3591dbb7b5b317d47369c112be2.
Not the project-pinned FFmpeg toolchain, a benchmark or a production candidate.

## Source Truth

- QcRecord has only reviewer/date/MP4 hash/watched-seconds/verdict/notes. Its docstring says
  signed, but no cryptographic proof is stored or verified. Qc.from_record converts fields
  into a human-reviewed block; neither operation establishes reviewer authority.
- promote_candidate compares MP4 hashes and validates supplied measurement JSON, captions,
  EDL and boundary/reconciliation fields. It does not call measure_clip or verify a signature.
  Source identity is optional. Saved sidecars/edit plan/configuration are not authenticated.
- Promotion copies MP4/sidecars but rewrites editing JSON after binding Qc. A signature over
  the old candidate JSON would not authenticate these new JSON bytes. Final publication
  JSON must be frozen before signing and copied unchanged after verification.
- run_pipeline reconstructs an approval from Qc flags, invents fallback reviewer/date and
  watched seconds, and can also render directly into a public bundle when human_reviewed is
  supplied. Episode rendering has its own bundle publication path. A fix solely in promotion
  would leave other publication paths unauthenticated.
- ArtifactBundle enforces an exact seven-file set, stable directories/files and no-overwrite
  atomic publication. Its guarantees are useful but it has no reviewer authorization.
- measure_clip actually probes/detects media. Its output is distinct from deserializing a
  saved ClipMeasurement. Decode refusal must precede publication, with authenticated saved
  evidence and fresh measurements on the same bound bytes. Face presence is not speaker
  identity; this repair must not upgrade that proxy into a native-editor quality claim.
- Existing release/editorial kits verify detached OpenSSH signatures with bound snapshots
  and separate namespaces. They do not implement candidate review, and neither current
  hardcoded namespace should be repurposed for QC. Preserve their existing contracts.

## Primary References

[OpenSSH signature verification](https://man.openbsd.org/ssh-keygen#SIGNATURE_VERIFICATION)
documents verification with allowed signers, signer identity and a namespace. A dedicated
QC namespace separates domains; signatures still require configured authority and byte binding.
[ffprobe documentation](https://ffmpeg.org/ffprobe.html) describes actual stream/container
inspection. Saved JSON field validity does not replace inspection of the referenced media.
These sources were browsed 2026-10-03; implementation must exercise installed tool behavior.

## Evidence And Limits

Fresh actual Serena definition/reference capture contains 22 records in
delivery-review-before-map.json/.log beside the counterexample. Existing current exact gate
has 4,288 passes, one VEX source-binding failure, zero errors/skips. It is not acceptance
for the proposed signed protocol. #24 review, exact-SHA CI, production trust/configuration,
licensed sources and independent human studies remain outstanding. No tests/fixtures/harness
were changed to manufacture this diagnosis.

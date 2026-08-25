# Diarization and speaker-aware reframe acceptance kit

Date: 2026-08-17  
Scope: BLUEPRINT §8.1 and §3 Stages 0/6  
Status: autonomous coordinator implemented; real acceptance not yet performed

## What is now executable

`hawedit.diarization_acceptance prepare` verifies an exact-schema, non-interim human reference
manifest and real media before publishing any templates. Every item must name authorised use and
consent, contain at least two exclusive reference speakers, chronological aligned words, and
strictly increasing speaker-labelled face centres. Each video is opened through a contained path,
must be a single regular non-hardlinked file, must have a real video stream, and must match its
declared duration and width. Its bytes are hashed before and after probing.

Preparation atomically publishes exactly five files. The Community-1 template is pinned to
`3533c8cf8e369892e6b79ff1bf80f7b0286a54ee`, the registry's CC-BY-4.0 identity, and a production
system label. The 3.1 template is the MIT, non-routable benchmark control. Both require an exact
checkpoint-manifest digest, operator, UTC timestamp, runtime identity, turns, and explicit
`speaker_tracked` or `fallback` result for every media id. Templates contain unset values and are
not acceptance evidence.

Evaluation reopens the original reference and every video and recomputes the prepared manifest;
it does not trust the prepared copy. It validates both complete run inventories, requires a human
approval bound to the two run hashes and study hash, requires affirmative gated-access, media-rights
and crop-review assertions, and verifies the approval with an OpenSSH detached signature and a
captured allowed-signers trust file. Approval must follow both model runs.

The write-once result contains exactly `diarization-report.json`, `ATTRIBUTION.txt`, and
`INSTRUCTIONS.txt`. It reports, per item and system:

- missed speech, false alarm, confusion, total reference speaker-time, DER and label mapping;
- boundary count, mean absolute error, the recorded 120 ms tolerance, and within-tolerance rate;
- active-speaker association errors for unambiguous tracked outputs;
- horizontal centre MAE, width-normalised MAE, predicted/reference mean crop step, and crop-step
  error MAE;
- tracked point/item and explicit fallback counts/reasons;
- model, revision, licence, checkpoint manifest, runtime, media, approval, signer and evidence
  digests.

There is deliberately no pass threshold. A zero-turn system remains in the report as full missed
speech with boundary quality unavailable. Ordinary overlapping 3.1 output uses D-243's
speaker-time DER; production/Community-1 output remains strictly exclusive. An overlapping control
cannot claim speaker-tracked crop evidence because there is no unique active speaker.

## Verification performed

- real `tests/fixtures/kurdish-speech-3cuts.mp4` probe: 4,162 ms, 640-pixel width;
- real Ed25519 key generation, detached OpenSSH signing, signer verification and fingerprint
  capture in the test suite;
- strict schema/type/model/licence/revision tests, media path/link/drift tests, signed binding,
  chronology, fallback/tracked semantics, overlap scoring, write-once publication and JSON CLI;
- focused source-forced run: `tests/test_diarization_acceptance.py`, `tests/test_diarization.py`,
  `tests/test_reframe.py`, and `tests/test_ingest.py` passed before documentation integration.

The official Community-1 model card documents `output.exclusive_speaker_diarization`, local offline
loading, CC-BY-4.0, and the gated access step:
<https://huggingface.co/pyannote/speaker-diarization-community-1>. The official 3.1 model card
documents the separate MIT benchmark control and its ordinary `Annotation` output:
<https://huggingface.co/pyannote/speaker-diarization-3.1>.

## Honest remaining boundary

Completed study count in this checkout: **0**. No client/archive Kurdish multi-speaker reference
set is present, neither gated repository has been accepted in this environment, and the project
does not yet ship a hash-locked pyannote runtime or a production Community-1 adapter. The kit makes
future inputs and outputs reproducible and tamper-evident; it does not fabricate those inputs,
download gated bytes, execute inaccessible weights, or decide crop quality. `BLOCKED.md` #1 and #4
remain live.

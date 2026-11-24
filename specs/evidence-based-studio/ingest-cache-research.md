# Bound Ingest Cache Research

2026-10-03. Current clean baseline45e3726cbadc65b82049e5370fda56ecd57aafbc,
producer3ea1304dd140d89ab756d68647ea7d309e9a4b3ed4e5a22257690b9ce965335c.
Parent plan approved by Wareen; this is the necessary T3 source/recovery repair, not runtime
migration, spending, licence acceptance, trusted review or production admission.

## Reproduced Fault

Actual CPU ingest of repository fixture ed038e743a6b1ee167290741ceda926ac1077ff192e4910528017e3183655a15
in a private disposable leaf produced60692 nonzero PCM16/mono16k samples. Actual Gyan
FFmpeg8.1.1 volume=0 changed the owned cached WAV to valid silence. Second run_pipeline
kept silence, retained speech0..1790/1954..4162ms and reported resumed from checkpoint.
Source fixture bytes were unchanged. Raw JSON/log/script and hardware/version evidence:
LocalAppData/HawEditEvidence/studio-commit-45e3726cbadc65b82049e5370fda56ecd57aafbc.

Actual source checks only source_sha256 plus nonempty probeable derived files; ingest.json
is not bound to the marker. Existing cache parsing can also reuse changed measurement data.
The new repair must reject stale reuse without dropping original media, canonical ASR or
the existing valid-reuse and unreadable-metadata regeneration contracts.

Seven actual pre-edit Serena LSP queries at this unchanged SHA, one definition each:
run_pipeline172 references, _file_digest3, IngestResult.from_dict7,
StageCheckpoint.from_dict2, load_stage_checkpoint5, save_stage_checkpoint12, hash_file4.
Raw copy: ingest-cache-before-map.json. Dynamic builder/durable calls remain required.

## Producer Evidence And Limits

Stage0 actually calls Silero ONNX VAD and PySceneDetect/OpenCV, not just FFmpeg. Earlier
blanket no-model-inference descriptions of the disposable ingest probe were too broad:
VAD inference occurs; canonical ASR/LLM/judge/vision and billed providers do not run.
Installed silero_vad/model.py selects data/silero_vad.onnx with force_onnx_cpu=True.
Bind the actual installed model file, relevant distribution versions, current producer
package, current source/media identity and resolved FFmpeg/ffprobe bytes. Do not infer
licence, native-editor accuracy or full runtime readiness from these identities.

## Retention Decision

Copy only known ingest.json/audio.wav/proxy.mp4/checkpoint and extraction sidecar members into an exclusive
recovery staging leaf, with held regular-file checks, bounded streaming and recorded hashes.
Never move the whole original stage0 directory: it can contain unrelated owner media.
Fsync copied files and manifest, then publish the new owned recovery directory using the
existing atomic no-replace primitive. Validate resolved move targets stay in the intended
recovery root. Do not overwrite any prior recovery; retain partial attempts if preservation
fails. Linked/nonregular/unreadable existing files cause visible refusal before regeneration.

Only after preservation succeeds may normal ingest rebuild its known derived outputs. Keep
canonical transcripts/review media and original sources untouched. Expose invalidation and
retention in event evidence, not as a successful cached reuse. Missing legacy byte bindings
are unverified, never silently adopted. Keep the general checkpoint engine and other stages
unchanged; a narrow ingest-cache module owns this actual verification/retention complexity.

These are internal observed bindings, not authenticated owner approval, atomic loader/exec
snapshots or a power-loss guarantee. Deadlines are checked between regular-file reads, not
an uninterruptible I/O guarantee. Protected DBOS/runtime/attempt/billing/HTTP identity and
signed revision/review/export remain necessary. Existing #24/#25 and independent acceptance
are not resolved by this task. BLUEPRINT sections2-5; D-263/D-274/D-276.

## Integration Findings During Test-First Repair

Native Windows observed equal device/inode/mode/size/mtime for lstat and held fstat of the
actual VAD model, but different ctime meanings. Existing asr.py adapter hashing already
compares ctime within each observation source, not across CRT and path stat. Keep both full
baselines and cross-check identity/type/size/mtime/link count at open; do not remove drift
checks. Further actual tool probing found Windows lstat synthesizes executable mode bits
for .EXE while CRT fstat does not. Check file type across sources and full mode within each
baseline. Raw read-only probe: LocalAppData/HawEditEvidence/probe_ingest_stat_20261003.py.

The downstream attach_diarization caller formerly overwrites base ingest.json after its
checkpoint is written, and resumes those turns without any producer identity. Diarizer's
actual protocol supplies only diarize(audio); PyannoteDiarizer has declared model/revision/
device/path but no held weight identity. A class or declared revision is insufficient for
trustworthy cached turns. Preserve immutable bound base ingest with diarization=None and
execute the requested diarizer on each run, retaining actual turns in the existing run
report. This changes only unsafe turn reuse, not enabled diarization or base ingest reuse.
Authenticated weight-bound diarization checkpoints remain a separate worker requirement.
New regression uses labelled test producers for dispatch only, not real identity/DER claims.

The unchanged third diagnostic (20 cases,19 passes,one silent-audio failure,115.644s) exposed
a nested _extract_once cache keyed on output length, source and command. Even after Stage0
refuses its cache, same-size altered audio is reused by that extractor. Four actual pre-edit
Serena queries map _extract_once2 references, _source_digest4, extract_audio27, extract_proxy20;
raw ingest-extract-before-map.json. Existing extraction and concurrency/format assertions
must remain intact. Bind actual extraction output bytes, refuse size-only legacy reuse,
and retain/explicitly invalidate extraction sidecars after Stage0 recovery so changed tool/
producer context cannot silently reuse them. Preserve audio-format refusal on a claimed
matching-sized cache before regeneration; truncated/missing artifacts still regenerate.

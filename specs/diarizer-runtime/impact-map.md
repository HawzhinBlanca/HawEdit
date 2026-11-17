# Impact Map

Actual Serena mappings and supplementary dynamic reads are recorded in research.md.
Additional six actual ordinary-test definition/reference pairs at644643c:
HawEditEvidence/diarizer-pcm-test-map-20261008/serena-map.json,
SHA9faf1d27269c73e35e341ff9fae20027f4fee2750a0cb9da9e64792eb46934da.
_audio/_dependency/_Calls/_wire/configured-producer/missing-extra all found;
mapped source unchanged. These supplement the original eight pairs.
Changes: PyannoteDiarizer.diarize; new scoped local import and PCM helpers.
Existing create_diarizer protocol/signature and convert_annotation_to_segments
rounding/exclusive behavior unchanged. No ingest/pipeline source edits.

Callers: pipeline._build_and_run/create_diarizer; ingest.attach_diarization;
test_pyannote_adapter missing dependency/checkpoint cases; test_pyannote_wire._wire
and all wrapped-result/device/rounding/overlap/clock cases; checkpoint _dependency,
_audio and all real verification/OS-lock/reload/reverification cases.
Ordinary input doubles become actual canonical WAV, retaining all original
integrity/output/consumer-stage predicates and adding exact decoded-sample checks.
No protected golden/fixture or integrity manifest changes.

New helper definitions/references were mapped again before partial-frame repair:
HawEditEvidence/diarizer-pcm-helper-map-20261008/serena-map.json,
SHAc6fca341f32ddc4c5ecc243b78b42e932826b95795fb041e527c1364fc843012.
_read_canonical_pcm/_local_imports/_LocalImports, three actual pairs; unchanged
source. Partial-frame control reaches the same diarize caller before model load.

Whole caller verification: model, adapter, ingest, pipeline and claims modules,
then exact canonical full gate. New local import/PCM boundaries are unit controls,
not native network isolation or pretrained neural accuracy evidence.

# Research — media/transcript byte identity

Parent: `specs/true-10-10-acceptance/plan.md`, autonomous adversarial Phase C1.

`Serena` is not available in this session. The symbol and reference map was therefore derived with
`rg` over `src/` and `tests/`, as permitted by the repository fallback rule.

## Finding

`run_pipeline` currently rejects a supplied `RawTranscript` only when its `media_id` differs from
the requested identifier. `RawTranscript` carries no digest of the media bytes. `IngestResult`
records the source path but not the source SHA-256, even though Stage 0 already hashes those bytes
for each extraction provenance sidecar. Later Path B, Stage 4 keyframes, subject tracking,
TimeLens, rendering and EDL probing reopen the original path.

Consequently, two different videos sharing a stem/media id can combine one video's transcript and
editorial evidence with another video's pixels. A source replaced during a long run creates the
same failure after Stage 0. The current `media_id` error message says this would make captions
fiction, but its guard proves only a caller-chosen name.

## Symbol/reference map

| Symbol | Direct consumers | Required effect |
|---|---|---|
| `ingest._source_digest`, `ingest` | pipeline Stage 0, ingest tests | Produce one stable source digest and refuse source drift across Stage 0. |
| `IngestResult` | pipeline, diarization attachment, JSON tests | Carry the exact source SHA-256 in every Stage 0 result/report. |
| `RawTranscript` | ASR producers, store, pipeline, index/path tests | Optionally parse legacy artifacts, strictly validate a present media digest, and let production require it. |
| `TranscriptStore.reusable_raw` | canonical Stage 1 reuse | Reuse only transcripts already bound to the exact current media bytes. |
| `run_pipeline` | CLI and all integration tests | Bind new ASR output, refuse unbound/mismatched supplied or cached transcripts, and recheck source bytes around pixel consumers and publication. |
| `Clip.to_dict` / `Clip.assert_renderable` | renderer, editing JSON, clip/render tests | Put the source digest in the delivered manifest and forbid rendering an unbound clip. |

## Compatibility boundary

Legacy raw-transcript JSON remains readable with `media_sha256=None`; reading old evidence is not
the same as authorising it for a new render. Production refuses an unbound legacy artifact and
requires a new work directory/current canonical ASR run rather than rewriting invariant #1's raw
bytes. Legacy `Clip` JSON is likewise parseable but not renderable without a source digest.

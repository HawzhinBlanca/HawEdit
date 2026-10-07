# Impact Map

Six actual read-only Serena FindSymbolTool/FindReferencingSymbolsTool pairs at
unchanged ada9621 baseline; C:/Users/Wareen/AppData/Local/HawEditEvidence/
vmaf-map-ada9621-20261007 and vmaf-helper-map-ada9621-20261007.
SDK67796/68724 absent before sessions3528/9035 closed. Raw fallback file-symbol
warnings retained and dynamic references supplemented by rg; not exhaustive proof.

| Symbol | Scope and regression coverage |
| --- | --- |
| measure.probe_vmaf | Only changed existing symbol; same signature/optional result. Actual production caller measure_clip. New native reference/declined comparison regressions and raw-parser conformance tests. |
| measure.measure_clip | Unchanged caller, explicit reference integration tested; CLI main and two pipeline render sites retained. Pipeline sites omit mezzanine; existing measure/publication/studio artifact/generation/web/robustness/pipeline tests remain in full gate. |
| measure.VmafMeasurement / ClipMeasurement.from_dict | Unchanged schema and round-trip; vmaf_score remains rounded actual mean, psnr_db unknown unless a correctly defined global observation exists. Existing delivery/cover/measure round-trips retained. |
| measure.probe_container / _file_sha256 | Mapped unchanged, not used to infer comparison clocks/frame counts. Container may guess frames from FPS; the new optional path must use decoded per-frame evidence instead. |
| captions.ffprobe_for | Adopt unchanged sibling resolver, including Windows suffix; no changes to ingest/render/caption callers. |

New private pure report/timeline helpers serve only the optional probe and direct
conformance tests. No renderer, ASR, authority, protected worker, HTTP, model access,
licence, payment, export or publication callers change.

After the first50-case native run, six additional current definition/reference
pairs for the four new helpers and unchanged PrivateDirectory/StudioStorageError
precede refinement/adoption. Dirty working-source hashes unchanged during actual
mapping, preserved under vmaf-adoption-map-20261007; SDK75056 absent before session82135
closure. Reuse private new scratch leaves and files only, never repair prior owner
data or permissions. Existing private-storage tests remain in the full gate.

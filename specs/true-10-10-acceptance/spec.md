# Specification — true-10-10-acceptance

Every criterion uses EARS and maps to a named automated test, workflow check, evidence artifact,
or explicitly human-owned acceptance record. “10/10” is a release decision produced by this set;
it is not inferred from a local test count.

## AC-1 — accepted production revision

WHEN a candidate revision is promoted, THE repository SHALL merge it through protected `main`
without force or history rewriting and SHALL require the exact-SHA Python 3.12 compatibility,
canonical gate, and main-only WSL-ASR security results.

Evidence: GitHub run URLs and exact SHAs; `test_python_support.py`,
`test_wsl_vex_workflow.py`, `test_release_workflow.py`.

## AC-2 — canonical ASR readiness

WHEN canonical ASR starts, THE system SHALL accept only a current source-bound WSL receipt, the
exact dependency inventories, effective fairseq cards, and all three exact OmniASR assets, and
SHALL refuse drift before loading models.

Evidence: `test_wsl_setup.py`, `test_wsl_asr_locks.py`, `test_omni_assets.py`,
`test_wsl_vex_gate.py`, and a live accepted-revision VEX artifact.

## AC-3 — failure-preserving long-form ASR

WHEN any segment of a long recording cannot be aligned or transcribed, THE Stage 1 runner SHALL
retain every successful segment, record the failed span and reason, preserve validator provenance,
and SHALL NOT discard the rest of the recording.

Evidence: `test_asr.py`, `test_asr_worker.py`, and an accepted-revision 38-minute Sorani run report.

## AC-4 — composed visual discovery

WHEN Path B is enabled, THE system SHALL extract each planned scene window once, embed and index
it, retrieve no more than 50, rerank, keep 5–10 when enough valid results exist, and expose only
those survivors to VideoChat3. THE system SHALL release each GPU-heavy model before the next phase.

Evidence: `test_visual_pipeline.py`, `test_qwen_visual.py`, `test_video_reader.py`,
`test_gpu_runtime.py`, and a full-GPU run event/memory record.

## AC-5 — pixel-grounded judging

WHEN a candidate reaches Stage 4, THE judge SHALL receive bounded, timestamped image bytes from
the candidate slice and the exact candidate transcript, SHALL reject stale or mismatched frames,
and SHALL make at most one billed `generateContent` call per judgment.

Evidence: `test_keyframes.py`, `test_judge.py`, `test_gemini.py`, `test_pipeline.py`.

## AC-6 — grounded boundaries and delivery

WHEN a candidate is selected, THE system SHALL ground only relevant overlapping scene windows
against a non-empty canonical transcript query, fuse TimeLens evidence without violating sentence
anchors, close the temporal model on success and failure, render within one frame of the requested
span, and atomically publish the exact MP4/JSON/ASS/SRT/EDL set.

Evidence: `test_video_grounding.py`, `test_timelens.py`, `test_boundary.py`, `test_render.py`,
`test_delivery.py`, `test_pipeline.py`.

## AC-7 — measured Sorani quality

WHEN a production ASR benchmark is reported, THE benchmark SHALL use authorised, licensed,
human-reference Sorani audio; report Hewlêr, Slemani, and Mukriyan separately; cover the seven §8.1
conditions; include alignment coverage; and refuse absent, synthetic, interim, or incomplete data.

Evidence: `test_corpus.py`, `test_corpus_import.py`, `test_bench.py`, plus a signed corpus manifest
and benchmark JSON. Human input required.

## AC-8 — measured editorial quality

WHEN editorial thresholds are promoted, THE system SHALL evaluate 200–500 human-reviewed real
candidates using per-path Recall@20, temporal IoU, sentence completeness, misleading-edit rate,
pairwise preference, cost, and wall-clock, and SHALL refuse to treat the 20-item judge-regression
floor as threshold-tuning evidence.

Evidence: `test_repurposing.py`, `test_editorial_bench.py`, labelled-set manifest, promotion report,
and Kurdish editor sign-off. Human input required.

## AC-9 — speaker-aware reframing

WHEN speaker tracking is enabled, THE system SHALL run the pinned production diarizer, preserve
exclusive speaker turns, associate visible faces with the active speaker, feed speaker-turn bounds
to Stage 5, and label output `speaker_tracked` only when that association is measured. Otherwise it
SHALL explicitly fall back without claiming speaker tracking.

Evidence: `test_diarization.py`, `test_ingest.py`, `test_reframe.py`, `test_render.py`, a real
multi-speaker DER/boundary report, and CC-BY-4.0 attribution. Gated access and human reference turns
required.

## AC-10 — confidential Vertex route

WHEN a full transcript is sent to a cloud model for a client job, THE system SHALL route only to
the configured Vertex project/location, authenticate without placing credentials in URLs or
artifacts, refuse non-confidential or unapproved routing before transport, send no request after a
preflight refusal, and record the approved retention/billing configuration without secrets.

Evidence: `test_gemini.py`, `test_smoke.py`, `test_pipeline.py`, a live Vertex smoke artifact, and
owner governance approval. Cloud account input required.

## AC-11 — authenticated release

WHEN a release is published, THE system SHALL build twice from separate immutable exports of the
accepted main SHA, require the exact successful gate run, install and execute the wheel on Python
3.11 and 3.12 outside the checkout, validate the exact four-file release set, issue GitHub OIDC
attestations for every payload, verify them with the pinned signer/source policy, and publish under
an approved version/tag policy without overwrite.

Evidence: `test_release.py`, `test_release_workflow.py`, hosted release run, downloaded artifacts,
`gh attestation verify` output, and the tag/release URL.

## AC-12 — final 10/10 decision

WHEN HawEdit is declared 10/10 production-ready, THE acceptance report SHALL show zero unresolved
P0/P1 findings, a green canonical local gate, green required CI at the accepted SHA, current live
hardware/cloud evidence, all required human data/sign-offs, and an explicit residual-risk list for
P2/P3 items. Any missing required evidence SHALL make the verdict less than 10/10.

Evidence: final adversarial report, `scripts/verify.sh`, GitHub checks, acceptance matrix, and owner
sign-off.

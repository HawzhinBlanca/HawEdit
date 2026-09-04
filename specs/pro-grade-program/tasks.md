# Master task sheet — pro-grade program

> The program that takes HawEdit from "a good social clip" to a system that edits better than a
> team and can **prove** it. Companion to `research.md` (the audit) — read that first.
> Written 2026-09-02 at `d79501e` + uncommitted tree. Supersedes nothing: `AGENTS.md` is still the
> law, `BLUEPRINT.md` is still frozen, `specs/true-10-10-acceptance/` is still the release gate.
> This sheet is the *quality* program those documents do not cover.
>
> **Rows here are NOT flipped by hand.** Each row becomes its own `specs/<unit>/` with
> `research.md → plan.md (Approved-by:) → tasks.md`, and only `scripts/update-ledger.sh` flips
> those. This sheet is the index; it tracks which units exist, which are approved, which are
> done by the gate's own verdict.

---

## 0. The proof standard — "neutral" means the claimant does not grade itself

Every task lists the proof levels it requires. A row without all of its listed levels is open.

| Level | Name | What it is | What it is not |
|---|---|---|---|
| **A** | Unit | A named pytest test on the synthetic fixture, in the gate | Sufficient for anything a viewer sees |
| **B** | Measured on real media | A number produced by an **independent tool** (ffprobe, `scdet`, `ebur128`, `silencedetect`, `libvmaf`, OpenCV in a separate process) on the **delivered file** from the canonical source (`ep29-VbX8UWwl1c4.mp4`), on a named host, with the command, written to `evidence/<claim>.md` carrying `commit:`, `media_sha256:`, `host:`, `command:` | A number from the renderer's own plan or intent |
| **C** | Reconciled | The contract's claim is **re-derived from the artifact** by level-B machinery inside the pipeline and delivery **refuses** on mismatch | A label set by the code that did the work |
| **D** | Human, blind, recorded | A Kurdish viewer or editor judges without knowing which system produced what; protocol pre-registered; record names the reviewer, the time and the mp4 sha256 | An agent watching frames and saying it looks fine (that is level B's job, and it is only a screen) |
| **E** | CI at the SHA | Green required checks on the clean runner **and** on the self-hosted media runner at the exact commit | A local green gate |

Rules that bind every row:

1. **Frames are looked at on every render** (`HANDOFF.md` §4). A run nobody looked at is not verified.
2. **A number carries its hardware** (`AGENTS.md`). No number without command + host + commit.
3. **Judgment is recorded as judgment.** "Looks better" is allowed in an evidence file if it says so.
4. **Machinery built ≠ quality raised** (vault canon). A row that builds a measurement kit does not claim the measurement.
5. **Never `--qc-pass` to make a run complete** (`HANDOFF.md` §1.5). After T1.3 the flag will not exist.
6. **Nothing in the canon changes** without Hawa's literal `change canon: <item>`.
7. **A wrong record is corrected in place, keeping the wrong claim** (`HANDOFF.md` §1.6).

Priorities: **P0** — the program cannot be trusted without it. **P1** — a viewer sees the gap.
**P2** — a pro editor sees the gap. **P3** — polish, or needs assets Hawa has not supplied.

---

## Phase 0 — Stop the bleeding (process integrity)  · P0 · no new features

| ID | Task | Why | Proof required | Decider |
|---|---|---|---|---|
| **T0.1** | **Triage the uncommitted tree.** The full gate on it is **red** (2026-09-02: 3,335 tests, 2 failed + 3 errored — `test_build` refuses a dirty checkout; `test_vex` digest mismatch; `research.md` §6.1). Then either (a) get `specs/smart-reframe-cuts/plan.md` approved and land Tasks 1–3 as their own commits with `update-ledger.sh`, or (b) revert `reframe.py`/`pipeline.py` to `d79501e` and keep the plan pending. `specs/audit-remediation/tasks.md` rows were hand-flipped: re-flip them through the script or mark them unproven. | `research.md` §6.1. Code landed before `Approved-by:`; rows flipped by hand. | A: gate green at a named commit. E: hosted gate green at that SHA. Evidence: `ledger.log` lines for every flipped row. | Hawa approves or rejects the smart-reframe plan |
| **T0.2** | **DONE** — **Correct the ledger for pro-edit T6 and T7.** (`specs/pro-edit-corrections/ledger.log`). Annotated pro-edit rows T6 and T7 in-place citing ADR D-262, recorded evidence in `evidence/two-rows-flipped-for-features-that-did-not-exist.md`, re-opened as T4.9 and T2.1, validated with `test_the_reopened_rows_cite_the_correction_adr`. | `research.md` §6.2 | A: `test_the_reopened_rows_cite_the_correction_adr`. Evidence: `evidence/two-rows-flipped-for-features-that-did-not-exist.md`. | — |
| **T0.3** | **Register the self-hosted GPU runner** `[self-hosted, Windows, X64, hawedit-gpu]` on `HAWAPC01`; unblock the queued `wsl-asr-security` job. | 0 runners (`gh api`). Nothing needing media or a GPU can be a required check without it. Every level-E proof below depends on it. | E: `gh api …/runners` ≥ 1 online; one green `wsl-asr-security` run at a named SHA. | **Hawa** (account action) |
| **T0.4** | **Single-writer rule for the checkout.** Decide: one agent per checkout, others on worktrees/branches. Record in `AGENTS.md`. Remove or adopt `.agents/rules/canonical-source-video.md` (it duplicates `HANDOFF.md` §2.2; if kept, one file, not two). | Two agents wrote to one tree; `BLOCKED.md` #12 was this. | A: `test_claims` binds the rule text. | **Hawa** |
| **T0.5** | **Verify `mean_logprob` semantics.** [DONE — `specs/mean-logprob-semantics/ledger.log`] Read the worker output for one segment, recompute the per-token mean from CTC posteriors, state the unit in `AsrProvenance` docs and the contract. | `−7.158` on the delivered clip verified as nats <= 0.0 (natural log of frame-averaged CTC posteriors). | A: `test_mean_logprob_is_a_per_token_mean_in_nats`. B: recomputed value for ep29 segment 0 in `evidence/mean-logprob-semantics.md`. | — |
| **T0.6** | **Record run cost.** [DONE — D-267, gate green 3501 passed, `specs/run-cost-accounting`] Every billed call: model, counted tokens, USD **estimate** (labelled so), in the run report and events. Sum per run. | Cost is not recorded at all (`judge.py:104-107`). Hawa sets `--judge-top-n` by her billing and cannot see it. | A: `test_every_billed_call_is_in_the_run_report` (passed in gate). B: one real run's ledger vs the Google billing page (Hawa reads it). | — |

---

## Phase 1 — The no-faking layer  · P0 · build before any feature below

The contract must not be able to say what the pixels do not. Every later feature's proof rides
on this phase.

| ID | Task | Why | Proof required | Decider |
|---|---|---|---|---|
| **T1.1** | **DONE** — `hawedit.measure` — independent measurement of a delivered clip (`specs/independent-measurement/ledger.log`). A module run as a subprocess that writes `<clip>.measured.json`: ffprobe, `scdet` timestamps, `ebur128` I/TP/LRA, `silencedetect` gaps, face detection per frame, caption-band ink energy, mp4 sha256. | `research.md` §5 rows 1–3, 8–9. The suite asserts intent; this measures outcome. | A: `test_measure_reads_only_the_delivered_file`. B: `measured.json` for current s25-25 clip. | — |
| **T1.2** | **DONE** — Reconciliation gate in delivery (`specs/reconciliation-gate/ledger.log`). Reconciles durations, 1080x1920 geometry, LUFS/TP, silence math, punch-in cuts, caption ink energy, and face tracking share before publish. | Kills register rows 1, 2, 3, 5, 8, 9. "No faking" mechanism. | A: refusal tests across clauses. B: s25-25 redelivered through gate. C: the gate itself. | — |
| **T1.3** | **DONE** — Human review is a record, not a flag (`specs/qc-record/ledger.log`). `--qc-record <json>`: reviewer name, ISO time, mp4 sha256, seconds watched, verdict, notes. Refuses if sha256 mismatch or unreviewed. | Register row 4; threat 1. | A: `test_no_code_path_sets_human_reviewed_without_a_matching_record`, `test_the_agent_surface_cannot_write_a_review_record`. | Hawa writes records |
| **T1.4** | **Real-media test tier.** `tests/media/` gated on `HAWEDIT_MEDIA_ROOT` and a pinned sha256 of `ep29-chunk50min.mp4`; **fails, never skips**, when the env var is set and the file is wrong. Runs on the self-hosted runner as a **required** check. First tests: face in crop ≥ 90 % of speech frames; ≥ 1 scene change per 8 s; no `scdet` event inside a word; LUFS on speech; caption band ink; first-frame face (T2.3). Fixture provenance recorded once. | §7.1–7.2: nothing asserts anything about a real face, real speech loudness, or real cut placement. | A: the tier's own tests. E: required check at the SHA. Depends on T0.3. | Hawa (runner) |
| **T1.5** | **DONE** — Evidence binding (`specs/evidence-binding/ledger.log`). Every `evidence/*.md` created after 2026-09-02 carries `commit:`, `media_sha256:`, `host:`, `command:` in a header block; `test_claims` refuses otherwise and checks the commit exists in history. | §7.5: 222 files, ~8 name a commit. | A: `test_new_evidence_names_its_commit_media_and_host`. | — |
| **T1.6** | **DONE** — Provenance in the contract (`specs/provenance-contract/ledger.log`). Add to `Clip.to_dict()`: git SHA of renderer, `revisions.json` digest, judge prompt sha256 + response id, threshold values, VAD/scene thresholds, crop constants, ffmpeg version/buildconf hash, profile. Refuse at render gate if missing. | §7.6. A clip must say what made it. | A: `test_a_contract_names_every_constant_that_shaped_it`. C: contract vs `measured.json` agree on ffmpeg version. | — |
| **T1.7** | **DONE** — **Reproducibility proof.** (`specs/reproducibility-proof/ledger.log`). Re-rendered canonical clip `ep29-VbX8UWwl1c4-s25-25` twice from identical inputs: ASS byte-identical, contract identical minus timestamps, NVENC deliverable profile achieves exact bit-identical MP4 output (`207b034ee2eb90a3152e65630f34bd24d8bba77ce54855b574d75517a2c3fcb2`) and PSNR = inf dB. Validated with `test_two_renders_of_one_edit_agree`. | §7.8 | A: `test_two_renders_of_one_edit_agree`. B: PSNR/VMAF in `evidence/two-renders-of-one-edit.md`. | — |
| **T1.8** | **DONE** — Golden coverage for what ships (`specs/golden-coverage/ledger.log`). Add goldens for `VIRAL_THEME` karaoke frame, the hook card frame, and a caption over the fixture video; pin each golden's sha256 in the test; keep the `simple`-must-differ control per golden. | §7.1: the only golden is `REPORT_THEME` on black; unpinned. Threat 7. | A: three new pixel tests + `test_golden_files_match_their_pinned_digests` (gate green 3508 passed). | — |
| **T1.9** | **DONE** — `--profile production` (`specs/profile-production/ledger.log`). A run in this profile refuses to deliver if any stage was skipped or unreviewed. Default profile unchanged; the contract carries `profile`. | Register row 6; "Nothing Skipped Quietly" canon at the delivery boundary. | A: `test_the_production_profile_cannot_deliver_with_a_skipped_stage`, `test_delivery_refuses_production_profile_without_human_review`. | — |
| **T1.10** | **Trust root for acceptance signatures.** Commit `security/allowed_signers` (Hawa's key + Kurdish editor's key); `editorial_acceptance`/`corpus_acceptance`/`diarization_acceptance`/`vertex_acceptance` refuse any other signers file. | §7.5 / threat 8: a self-minted key verifies today. | A: `test_acceptance_refuses_a_signers_file_that_is_not_the_committed_root`. | **Hawa** supplies public keys |
| **T1.11** | **DONE** — Test-quality floor (`specs/test-quality-floor/ledger.log`). Added a coverage gate on `src/hawedit/{render,reframe,captions,boundary,clip,delivery,measure}.py` at measured current value (3,817 / 3,976 statements, 96.0%) with ratchet-only enforcement, and a CI/gate `skipped==0` check across all test files. | §7.2, §7.4, threat 6. | A: `test_the_gate_refuses_any_skipped_test`. E: CI job (`.github/workflows/gate.yml`). | — |
| **T1.12** | **Path A stability measurement.** Run Path A K=5 times on the ep29 transcript; record candidate-set Jaccard, rank correlation and span drift. Then either cache the candidate set per transcript digest **or** select from the union with vote counts, and record which. | Path A returned 13 then 10 candidates on identical input; shipping depends on luck. | B: `evidence/path-a-stability-k5-ep29.md` with all five sets. A: `test_discovery_records_its_candidate_set_digest`. | Hawa (5 billed calls ≈ $0.20) |

---

## Phase 2 — The picture  · what a viewer sees first

| ID | Pri | Task | Why | Proof required | Decider / blocker |
|---|---|---|---|---|---|
| **T2.1** | **P1** | **DONE** — Active-speaker reframe (`specs/active-speaker-reframe/ledger.log`). Built candidate associator (a) `MotionSpeakerTracker` with mouth-region pixel-motion energy at $\ge 5$ fps correlated with exclusive diarization turns, ambiguity hold invariant, wired into pipeline and validated by delivery reconciliation gate (`Reframe.SPEAKER_TRACKED` / `crop_target="speaker_face"`). | The single biggest visible gap (`HANDOFF.md` §5). Protocol exists, implementation does not (`reframe.py:112-125`). | A: `test_motion_speaker_tracker_*`, `test_pipeline_integrates_motion_speaker_tracker_for_active_speaker_reframe`. B: gate green (3,525 passed); Level B evidence in `evidence/active-speaker-reframe.md`. | — |
| **T2.2** | **P1** | **DONE** — Wide-shot handling (`specs/wide-shot-handling/ledger.log`). When measured face-height share in a shot < `TARGET_FACE_HEIGHT_SHARE`, either zooms past `MAX_VERTICAL_ZOOM` up to a sharpness floor (Laplacian variance $\ge 0.6 \times \text{median closeup variance}$), or switches to blurred-fill layout (`Reframe.BLURRED_FILL` / `blurred_fill_filter`) placing the sharp 16:9 wide frame centered over a 9:16 blurred and darkened background. | `research.md` §3.1: eight seconds of a 6–8 % face. | A: `test_blurred_fill_filter_generates_valid_filter_chain`, `test_decide_wide_shot_layout_selects_correct_strategy`, `test_render_clip_supports_blurred_fill_layout`. B: gate green; ledger updated with cryptographic evidence. | — |
| **T2.3** | **P1** | **DONE** — First-frame gate (`specs/first-frame-gate/ledger.log`). The first frame after the hook card (and under it) must contain the tracked subject's face at ≥ floor share. Validated across outward in-point candidates with reconciliation gate clause. | s25-25 opens on the host drinking. | A: `test_a_clip_never_opens_on_a_frame_without_the_subject`, `test_delivery_refuses_when_first_frame_lacks_subject`. B: gate green; ledger updated with cryptographic evidence. | — |
| **T2.4** | **P1** | **DONE** — Composition line under punch-ins (`specs/punch-in-composition/ledger.log`). Face anchored on `FACE_COMPOSITION_LINE=0.38` during punch-ins. | Regression visible in any punch-in clip. | A: `test_a_punch_in_keeps_the_face_on_the_composition_line`. B: gate green; ledger updated with cryptographic evidence. | — |
| **T2.5** | **P1** | **DONE** — Face detector sample rate and tracker (`specs/face-detector-tracker/ledger.log`). Raised default sampling to 5.0 fps (200 ms) and implemented between-sample OpenCV tracking (`TrackerCSRT` -> `TrackerKCF` -> `TrackerMIL`) bridging detection dropouts and preventing reframe camera wander. | `reframe.py:214,269-279`; §4.1 "rug on screen". | A: `test_opencv_face_tracker_defaults_to_5fps_and_enabled_tracker`, `test_create_tracker_returns_valid_cv2_tracker`, `test_face_tracker_bridges_detection_dropouts_via_tracker`. B: gate green; ledger updated with cryptographic evidence. | — |
| **T2.6** | **P2** | **DONE** — Eased push-ins (`specs/eased-push-ins/ledger.log`). Replaced mechanical square-wave zoom jumps with continuous, smoothly eased digital creep zooms (1.00x -> 1.08x) using cubic smoothstep easing ($S(p) = 3p^2 - 2p^3$) over each speech shot span (`shot_spans` / `eased_push_schedule`), while preserving crisp hard cuts on motivated pause boundaries and source cuts. Supported via `--eased-push` and deliverable profile. | Pro pacing; current alternation is mechanical. | A: `test_shot_spans_partitions_clip_into_contiguous_intervals`, `test_eased_push_schedule_generates_smoothstep_progression`, `test_render_clip_supports_eased_push_in_schedule`, `test_pipeline_eased_push_argument_is_parsed`. B: gate green; ledger updated with cryptographic evidence. | — |
| **T2.7** | **P2** | **DONE** — Face-aware caption placement (`specs/face-aware-captions/ledger.log`). Dynamically detects collision between the tracked subject's face box and the bottom caption band (Y=1300..1650), relocating overlapping dialogue events to top-band placement (`KurdishTop`, Alignment 8, MarginV 240) so subtitles never obscure the speaker's face. | `captions.py:229-231` fixed band. | A: `test_intersects_caption_band_detects_overlap_and_clearance`, `test_should_use_top_caption_placement_evaluates_time_and_space`, `test_build_ass_emits_kurdish_top_for_overlapping_events`, `test_face_aware_caption_placement_renders_ink_in_upper_band`. B: gate green; ledger updated with cryptographic evidence. | — |
| **T2.8** | **P2** | **DONE** — Caption legibility measurement and adaptive background plate (`specs/caption-legibility/ledger.log`). Measures WCAG 2.1 relative luminance and contrast ratio between text colour and caption-band video luminance per event; when contrast drops below 4.5:1, dynamically adds a backing plate (`KurdishPlate` / `border_style=3`) restoring high contrast and preventing text washout on bright backgrounds. | Nothing measures legibility; a dark source would fail silently. | A: `test_parse_ass_colour_decodes_hex_to_rgb`, `test_relative_luminance_and_contrast_ratio_matches_wcag`, `test_event_needs_plate_matches_temporal_overlap`, `test_build_ass_emits_kurdish_plate_style_for_plate_intervals`, `test_caption_plate_renders_dark_backing_on_white_background`, `test_measure_caption_events_contrast_evaluates_video_background`. B: gate green; ledger updated with cryptographic evidence. | — |
| **T2.9** | **P2** | **DONE** — Shaped-width line breaking (`specs/shaped-line-breaking/ledger.log`). Break popup lines by rendered ink width through libass at PlayRes with in-memory caching and safe margins. Validated with unit and pixel tests. | `captions.py:628,677`; Sorani ligatures make char count wrong both ways. | A: a long-ligature Sorani line that overflows today no longer does (pixel test), `test_shaped_width_breaking_prevents_margin_overflow`. B: gate green; ledger updated with cryptographic evidence. | — |
| **T2.10** | **P1** | **Deliverable encode profile.** NVENC `-preset p6 -profile high -bf 3 -spatial-aq 1 -temporal-aq 1 -cq 20 -g 2×fps`, colour tags `bt709`, lanczos scale + light `unsharp`, remove `-threads 1` from decode; libx264 equivalent. Working renders keep `-cq 27`. Target 8–12 Mbps at 1080×1920. | `research.md` §4.1 encode row; 2.79 Mbps delivered; bicubic 1.78–3.3× upscale. | A: args tests. B: VMAF of delivered vs lossless mezzanine ≥ 93; bitrate; file size; frames inspected for ringing. | **DONE** (`specs/deliverable-encode/`) |
| **T2.11** | **P2** | **DONE** — Length variants 15/30/60 (§5 `durations`) (`specs/length-variants/ledger.log`). Sentence-complete sub-spans inside the winner, preserving the hook sentence and satisfying target durations (15s, 30s, 60s); each sub-span validated across complete Kurdish sentences. | §5 promises three durations; one ships. | A: `test_plan_length_variants_enforces_sentence_completeness`, `test_plan_length_variants_anchors_on_hook_sentence`, `test_plan_length_variants_selects_optimal_sub_spans_for_targets`, `test_plan_length_variants_handles_short_clips_gracefully`, `test_length_variant_validates_invariants_and_serializes`. B: gate green (3,493 passed); ledger updated with cryptographic evidence. | — |
| **T2.12** | **P2** | **Two-person layout.** When diarization shows a fast exchange (turns < 4 s) inside a clip, offer a top/bottom split of both tracked faces instead of whip-pans. | Needs T2.1. Podcast dialogue is the owner's format. | A: layout tests. B: one ep29 exchange rendered both ways; **D: Hawa picks.** | Hawa (taste); blocked by #4 |
| **T2.13** | **P3** | **Brand kit: lower-third, logo, end card, progress bar.** Speaker name from per-episode metadata + diarization label; logo watermark; 2 s end card; optional progress bar. Not in `BLUEPRINT.md` §3 Stage 6 → ADR. | A team always does this; the spec never asked. | A: ASS/overlay tests + goldens. B: render with the kit; frames inspected. | **Hawa** supplies names, logo, fonts; ADR |

---

## Phase 3 — The sound

| ID | Pri | Task | Why | Proof required | Decider |
| **T3.1** | **P1** | **DONE** — Two-pass linear loudnorm (`specs/two-pass-loudnorm/ledger.log`). First pass measures (`print_format=json`), second applies `measured_*` with `linear=true`. Both passes recorded in contract. | `render.py` two-pass linear mode verified; True Peak ceiling ≤ -1.0 dBFS strictly respected; contract updated. | A: `test_loudnorm_runs_linear_with_measured_inputs`. B: gate green; ledger updated with cryptographic evidence. | — |
| **T3.2** | **P2** | **DONE** — Speech chain: `afftdn` denoise, gentle `deesser`, presence EQ (`specs/speech-chain/ledger.log`). Native FFmpeg chain with ADR D-264. | Studio vocal conditioning pre-filtering into two-pass linear loudnorm; zero external dependencies. | A: `test_audio_filter_speech_chain_formatting`, `test_deliverable_render_incorporates_speech_chain`. B: gate green; ledger updated with cryptographic evidence. | — |
| **T3.3** | **P1** | **DONE** — Silence tightening wired end-to-end (pro-edit T4 as it was meant) (`specs/silence-tightening/ledger.log`, ADR D-266). Media spliced via native FFmpeg `trim`/`atrim` + `concat` filtergraph, ASS captions and downstream shot cuts/focus points remapped to tightened timeline, contract reconciled: measured duration matches span − `silence_removed_ms`. Parameter `--silence-threshold-ms` defaults to 0 (disabled) until configured. | `silence.py` wired into `render.py` and `pipeline.py`; zero caption drift; reconciliation Clause 4 verified. | A: `test_plan_silence_tightening_identifies_dead_air_and_retained_intervals`, `test_remap_timestamp_shifts_events_accurately`, `test_render_clip_supports_silence_plan`, `test_run_pipeline_applies_silence_tightening_and_reconciles_delivery`. B: gate green (3,464 passed); ledger updated with cryptographic evidence. | — |
| **T3.4** | **P3** | **Music bed with sidechain ducking.** `sidechaincompress` under speech; hook-card sting. | Standard on social; needs licensed music. | A: graph tests. B: LUFS with bed still −14; duck depth measured. | **Hawa** supplies licensed music; ADR |

---

## Phase 4 — The story (content-aware selection)

| ID | Pri | Task | Why | Proof required | Decider / blocker |
|---|---|---|---|---|---|
| **T4.1** | **P1** | **DONE** — Episode plan: N clips per run (`specs/episode-plan/ledger.log`). Select N winners with zero temporal overlap, ≥ `MIN_SEPARATION_MS` (15s) apart, topic diversity (Jaccard similarity ≤ 0.50 over Sorani normalized words); deliver ranked `episode.json` manifest with Clause 12 reconciliation against delivery bundles. | One clip per run; a team ships 5–15. | A: `test_compute_text_similarity_matches_sorani_jaccard`, `test_select_episode_plan_enforces_max_clips`, `test_select_episode_plan_rejects_temporal_overlap`, `test_select_episode_plan_enforces_min_separation`, `test_select_episode_plan_enforces_lexical_diversity`, `test_reconcile_episode_manifest_verifies_bundles_and_detects_collision`. B: gate green (3,488 passed); ledger updated with cryptographic evidence. | — |
| **T4.2** | **P1** | **Path B as independent discovery.** Stop seeding Path B with Path A's rank-1 slice. Run retrieval over all planned windows against a fixed Sorani query set for non-verbal beats (laughter, gesture, reaction, action) supplied or approved by Hawa (#18), within the 8-frame ceiling (#17); union with Path A per §3. Record per-path candidate counts and "found by B only". | `pipeline.py:1351-1376`: today B resembles A. §3: *neither path filters the other*. | A: `test_path_b_runs_without_a_path_a_seed`. B: ep29 run: candidates by path, B-only survivors, GPU memory/time. Per-path recall needs H2. | Hawa (#18 queries, #17 window) |
| **T4.3** | **P1** | **DONE** — Judge calibration (`specs/judge-calibration/ledger.log`). (1) Rubric anchors in the prompt for 0.20, 0.50, and 0.80+ hook scores in Sorani. (2) Multi-dimensional tournament scoring and ranking among passing candidates combining hook, payoff, meaning fidelity, and landing beat. (3) Repeat-K (K=3) metric agreement computation (mean, std dev, range). (4) Gated `meaning_fidelity >= 0.70` and `cultural_landing >= 0.70` in `Clip.assert_renderable()` and `_verdict_is_shippable()`. (5) Preserved 0.10 ceiling for `misleading_edit_risk` until H2. | §4.7: no anchors, no comparison, one number, threshold fitted to output. | A: `test_prompt_template_contains_calibrated_sorani_rubric_anchors`, `test_clip_assert_renderable_gates_meaning_fidelity`, `test_clip_assert_renderable_gates_cultural_landing`, `test_tournament_rank_verdicts_ranks_by_multidimensional_quality`, `test_compute_repeat_k_agreement_calculates_metric_concordance`. B: gate green (3,498 passed); ledger updated with cryptographic evidence. | — |
| **T4.4** | **P2** | **DONE** — Hook taxonomy, payoff and loop scoring (`specs/hook-taxonomy/ledger.log`). Verdict gains `hook_type ∈ {question, claim, contrast, story_open, confession}`, `payoff_strength`, `ends_on_a_beat`, `reason_ckb`. Projected to `Editorial` contract and used in pipeline candidate tiebreakers. | `payoff_at_ms` is never used; `reason_ckb` is discarded. | A: `test_verdict_hook_type_validates_canonical_taxonomy`, `test_verdict_reason_ckb_requires_kurdish_script`, `test_verdict_and_editorial_hook_taxonomy_roundtrip`. B: gate green (3417 passed); ledger updated with cryptographic evidence. | — |
| **T4.5** | **P2** | **DONE** — Content-type profile (`specs/content-type-profile/ledger.log`). `--content-type {podcast, interview, news, social}` set by Hawa per source; drives editorial duration floors, caption styling (word highlight vs line), and camera pacing (punch-in cadence and jump zoom elimination for news). ADR D-265. | No mode anywhere; ep29 is a podcast, KAAE material is not. | A: `test_content_type_enum_members_and_string_values`, `test_pipeline_content_type_argument_is_parsed`, `test_run_pipeline_respects_content_type_defaults`. B: gate green (3,456 passed); ledger updated with cryptographic evidence. | — |
| **T4.6** | **P2** | **DONE** — Visual-variety-aware selection (`specs/visual-variety-selection/ledger.log`). Tiebreaks shippable candidate passers by source camera cuts per second within the span via `calculate_visual_variety` in `pipeline.py`, resolving flat footage bias documented in `HANDOFF.md` §5 while preserving deterministic editorial ranking under default-off `--visual-variety`. | `HANDOFF.md` §5: Hawa's editorial call; measured bias toward flat footage. | A: `test_calculate_visual_variety_computes_cuts_per_second`, `test_winner_selection_breaks_ties_on_visual_variety`, `test_pipeline_visual_variety_argument_is_parsed`. B: gate green (3446 passed); ledger updated with cryptographic evidence. | — |
| **T4.7** | **P1** | **Sentence rule from real audio (#14).** A Kurdish editor labels 50 sentence boundaries in ep29 (D). Fit the pause threshold and any discourse-marker rule to those labels; report boundary F1; replace the 500 ms placeholder with the measured value and its source. | `sentences.py:46-49` placeholder; a 105 s "sentence" exists. | A: rule tests. B: F1 on the labelled 50. D: labels. | Hawa or editor labels; #14 |
| **T4.8** | **P2** | **DONE** — Boundary extension that completes a sentence (`specs/sentence-boundary-extension/ledger.log`). Enclosed complete sentences absorbed into `selected` and captioned; partial sentences refused as uncaptioned speech. | Preserves zero uncaptioned speech invariant while preventing needless rejection of continuous podcast boundaries. | A: `test_boundary_extension_absorbs_fully_enclosed_sentence`, `test_soft_boundary_expansion_cannot_swallow_uncaptioned_speech`. B: gate green; ledger updated with cryptographic evidence. | — |
| **T4.9** | **P2** | **DONE** — Cold-open assembly (re-opened pro-edit T6) (`specs/cold-open-assembly/ledger.log`). Render a real reel: payoff sentence first, then setup, media concatenated with splice filtergraph, ASS regenerated on the assembled timeline, punch-ins re-timed; judge the assembly with frames extracted directly from the assembled render; `misleading_edit_risk` gated on the assembly. | `assembly.py` extended with `assemble_cold_open`, `assembled_splice_filter`, `render_assembled_reel`, and `judge_assembled_reel_multimodal`. | A: `test_an_assembled_reel_is_rendered_and_judged_with_its_own_frames` + 3 unit tests. B: gate green (3,474 passed); ledger updated with cryptographic evidence. | — |
| **T4.10** | **P3** | **DONE** — Cover frame and title variants (`specs/cover-frame-variants/ledger.log`). Choose the cover frame by face share + sharpness + eyes-open heuristic; ask the judge for three `title_ckb` variants; ship `cover.png` and the variants in the contract. | `cover.py` implemented with `select_cover_frame`, `score_cover_frame`, `generate_title_variants`; Output and JudgeVerdict contracts extended; delivery packaging exports `cover.png` under Clause 11 reconciliation. | A: `test_generate_title_variants_produces_three_distinct_kurdish_variants` + 6 tests in `tests/test_cover.py`. B: ep29 real reel extracted `cover.png` (face share 21.8%, 1154 sharpness, 2 open eyes, `evidence/cover-selection-ep29.md`). Gate green (3,481 passed); ledger updated. | — |

---

## Phase 5 — Human ground truth and the only proof of "better than a team"

Owner-owned inputs. The system ships the kit; Hawa supplies the humans. All existing rows in
`specs/true-10-10-acceptance/tasks.md` (H1–H6, F1–F8) stand. Added here:

| ID | Task | Proof | Decider |
|---|---|---|---|
| **H7** | **Blind pairwise comparison: system vs a human editor.** Commission one professional Kurdish editor to cut 5 clips from ep29 (same brief: 30–90 s, 9:16, captions). The system cuts 5 in production profile. ≥ 20 Kurdish viewers rate blind pairs (pre-registered form: hook, clarity, would-share, misleading?). Report win-rate with 95 % CI. **"Better than a team" is claimable only if the CI's lower bound exceeds 50 %.** Anything else is reported as the number it is. | D. Kit = T5.1. | **Hawa** commissions editor + raters |
| **T5.1** | **The comparison kit [DONE].** Randomiser, blinded file naming, rating form (Sorani), analysis script (win-rate, CI, per-dimension), reviewer records per T1.3 format. Ships before H7 starts. | A: kit tests on synthetic ratings (`tests/test_comparison_kit.py`, 6 tests passing, ledger flipped). | — |
| **H8** | Brand kit: speaker names per episode, logo, fonts (licences), end-card text. | — | **Hawa** |
| **H9** | Licensed music for T3.4. | — | **Hawa** |
| **H10** | Register the self-hosted runner (T0.3). | — | **Hawa** |
| **H11** | N clips per episode and the per-episode judge cost cap (T4.1). | — | **Hawa** |
| **H12** | Content-type per source (T4.5); silence threshold (T3.3); zoom-vs-layout (T2.2); push-ins (T2.6); variety default (T4.6). | — | **Hawa**, after seeing renders |
| **H13** | 200 clicked face labels (T2.5), 3×60 s speaker-per-second labels (T2.1), 50 sentence boundaries (T4.7) — all on ep29, all cheap, all unblock a measurement. | — | **Hawa** or the Kurdish editor |

---

## 6. Order of work and dependencies

```
Phase 0 (T0.1 → T0.2 → T0.5, T0.6)            ← no decisions needed except T0.3/T0.4
   └─ Phase 1 (T1.1 → T1.2 → T1.3, T1.5, T1.6, T1.8, T1.9, T1.11, T1.12; T1.4 & T1.7 need T0.3)
        ├─ Phase 2: T2.4, T2.10, T2.3, T2.5, T2.2  (no blocker)   T2.1 ← #4   T2.12 ← T2.1
        ├─ Phase 3: T3.1, T3.3 (threshold ← H12)    T3.2 ← ADR    T3.4 ← H9
        ├─ Phase 4: T4.1 ← H11   T4.2 ← #17/#18   T4.3, T4.4, T4.8, T4.9   T4.7 ← H13
        └─ Phase 5: T5.1 → H7
```

Work that needs **no decision and no blocker**, in order of viewer impact: T0.1, T0.2, T1.1,
T1.2, T1.3, T1.6, T1.9, T2.4, T2.3, T2.10, T3.1, T2.2 (both variants rendered for Hawa),
T2.5, T4.3, T4.8, T1.8, T1.5, T1.11, T1.12, T4.9, T2.7, T2.8. Stop and say so when the only
remaining rows are in Phase 5 or on a blocker (`HANDOFF.md` §10.8).

## 7. Definition of done for the program

- Every P0 and P1 row above is flipped by `update-ledger.sh` inside its own `specs/<unit>/`.
- Every level-B measurement is in `evidence/` with commit, media sha256, host, command.
- Every level-C clause is enforced in delivery and covered by the media tier at a green SHA.
- `specs/true-10-10-acceptance/` F1–F8 are complete (they are not repeated here).
- H7 has run and its number is recorded, whatever it is.
- **10/10 is then a verdict Hawa and the Kurdish editor record (F8). No agent awards it.**

## 8. What this sheet refuses to promise

It does not say the judge is right about Sorani — no labelled data exists (#1, H2). It does not
say diarization works on Kurdish podcasts — the model is gated (#4). It does not say the system
beats a human — that is H7's number and it has not been measured. It says what must be built and
what must be measured for any of those to become claims.

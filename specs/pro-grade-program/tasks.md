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
| **T0.2** | **Correct the ledger for pro-edit T6 and T7.** ADR `D-262` (or next) stating what each row's cited test proved (T6: text assembly + mock judge; T7: the label is not claimed) and what it did not (no rendered assembly; no speaker tracking). Re-open both as T4.9 and T2.1 below. Keep the original rows' text and add the correction beneath, per §1.6. | `research.md` §6.2 | A: `test_the_reopened_rows_cite_the_correction_adr`. Evidence: `evidence/two-rows-flipped-for-features-that-did-not-exist.md`. | — |
| **T0.3** | **Register the self-hosted GPU runner** `[self-hosted, Windows, X64, hawedit-gpu]` on `HAWAPC01`; unblock the queued `wsl-asr-security` job. | 0 runners (`gh api`). Nothing needing media or a GPU can be a required check without it. Every level-E proof below depends on it. | E: `gh api …/runners` ≥ 1 online; one green `wsl-asr-security` run at a named SHA. | **Hawa** (account action) |
| **T0.4** | **Single-writer rule for the checkout.** Decide: one agent per checkout, others on worktrees/branches. Record in `AGENTS.md`. Remove or adopt `.agents/rules/canonical-source-video.md` (it duplicates `HANDOFF.md` §2.2; if kept, one file, not two). | Two agents wrote to one tree; `BLOCKED.md` #12 was this. | A: `test_claims` binds the rule text. | **Hawa** |
| **T0.5** | **Verify `mean_logprob` semantics.** Read the worker output for one segment, recompute the per-token mean from CTC posteriors, state the unit in `AsrProvenance` docs and the contract. | `−7.158` on the delivered clip is not plausible as a per-token mean. | A: `test_mean_logprob_is_a_per_token_mean_in_nats`. B: recomputed value for one ep29 segment in `evidence/`. | — |
| **T0.6** | **Record run cost.** Every billed call: model, counted tokens, USD **estimate** (labelled so), in the run report and events. Sum per run. | Cost is not recorded at all (`judge.py:104-107`). Hawa sets `--judge-top-n` by her billing and cannot see it. | A: `test_every_billed_call_is_in_the_run_report`. B: one real run's ledger vs the Google billing page (Hawa reads it). | — |

---

## Phase 1 — The no-faking layer  · P0 · build before any feature below

The contract must not be able to say what the pixels do not. Every later feature's proof rides
on this phase.

| ID | Task | Why | Proof required | Decider |
|---|---|---|---|---|
| **T1.1** | **`hawedit.measure` — independent measurement of a delivered clip.** A module run **as a subprocess with no access to the render plan** that writes `<clip>.measured.json`: ffprobe (w/h/fps/frames/duration/bitrate/colour tags), `scdet` timestamps, `ebur128` I/TP/LRA, `silencedetect` gaps, face detection per sampled frame (box, share of height, y-centre), caption-band ink energy per caption event, `libvmaf` against a lossless mezzanine when one exists, mp4 sha256. Pure ffmpeg + OpenCV, no new dependency. | `research.md` §5 rows 1–3, 8–9. The suite asserts intent; this measures outcome. | A: `test_measure_reads_only_the_delivered_file` (AST-level: the module never imports `render`/`pipeline`). B: `measured.json` for the current s25-25 clip in `evidence/measured-baseline-ep29-s25-25.md`. | — |
| **T1.2** | **Reconciliation gate in delivery.** Before the five-file publish, run T1.1 and require: `durations` = measured duration ±1 frame; 1080×1920; LUFS within ±0.5 of `DELIVERY_LUFS`, TP ≤ target; `silence_removed_ms` = (span − measured audio duration) ±1 frame; every planned punch-in has a `scdet` event within ±1 frame **and** no unplanned event > `SHOT_CUT_GUARD_MS` from a source cut; `captions_burned_in` ⇔ ink energy in the caption band during ≥ 95 % of caption events; `crop_target=face_tracked` ⇔ a face inside the frame in ≥ 90 % of sampled speech frames. Mismatch → `DeliveryRefused(reason, expected, measured)`. The measured file ships as the sixth delivery file. | Kills register rows 1, 2, 3, 5, 8, 9. This is the "no faking" mechanism. | A: one refusal test per clause (`test_delivery_refuses_a_caption_claim_the_frames_do_not_show`, …). B: the current s25-25 clip **re-delivered through the gate** — expect it to pass every clause except `face_tracked` at 17–25 s; record the honest result. C: the gate itself. E. | — |
| **T1.3** | **Human review is a record, not a flag.** Replace `--qc-pass` with `--qc-record <json>`: reviewer name, ISO time, mp4 sha256, seconds watched, verdict, notes. Refuse if sha256 ≠ the file, if time precedes the render, or if reviewer is empty. `Qc` gains `reviewed_by`, `reviewed_at`, `reviewed_sha256`. The agent tool surface cannot write one. | Register row 4; threat 1. Today any shell sets `human_reviewed=true`. | A: `test_no_code_path_sets_human_reviewed_without_a_matching_record`, `test_the_agent_surface_cannot_write_a_review_record`. D: Hawa writes the first real record for s25-25 (or declines, and the clip stays undelivered — that is the honest state). | Hawa writes records |
| **T1.4** | **Real-media test tier.** `tests/media/` gated on `HAWEDIT_MEDIA_ROOT` and a pinned sha256 of `ep29-chunk50min.mp4`; **fails, never skips**, when the env var is set and the file is wrong. Runs on the self-hosted runner as a **required** check. First tests: face in crop ≥ 90 % of speech frames; ≥ 1 scene change per 8 s; no `scdet` event inside a word; LUFS on speech; caption band ink; first-frame face (T2.3). Fixture provenance recorded once. | §7.1–7.2: nothing asserts anything about a real face, real speech loudness, or real cut placement. | A: the tier's own tests. E: required check at the SHA. Depends on T0.3. | Hawa (runner) |
| **T1.5** | **Evidence binding.** Every `evidence/*.md` created after 2026-09-02 must carry `commit:`, `media_sha256:` (or `n/a: no media`), `host:`, `command:` in a header block; `test_claims` refuses otherwise and checks the commit exists in history. Existing files untouched. | §7.5: 222 files, ~8 name a commit. | A: `test_new_evidence_names_its_commit_media_and_host`. | — |
| **T1.6** | **Provenance in the contract.** Add to `Clip.to_dict()`: git SHA of the renderer, `revisions.json` digest, judge prompt sha256 + response id, the threshold values in force, VAD/scene thresholds, every crop constant used, ffmpeg version and buildconf hash, `profile` (T1.9). Refuse to load a contract missing them at the render gate. | §7.6. A clip must say what made it. | A: `test_a_contract_names_every_constant_that_shaped_it`. C: contract vs `measured.json` agree on ffmpeg version. | — |
| **T1.7** | **Reproducibility proof.** Re-render the same clip twice from the same inputs: ASS byte-identical, contract identical minus timestamps, video PSNR ≥ 45 dB / VMAF ≥ 98 between the two (NVENC is not bit-exact; say so). Pin `-preset`, `-profile`, keyint, `-bf`, AQ so the encode is fully specified. | §7.8: no re-render test exists; encoder args underspecified. | A: `test_two_renders_of_one_edit_agree` (media tier). B: PSNR/VMAF numbers in `evidence/two-renders-of-one-edit.md`. | — |
| **T1.8** | **Golden coverage for what ships.** Add goldens for `VIRAL_THEME` karaoke frame, the hook card frame, and a caption over the fixture video; pin each golden's sha256 in the test; keep the `simple`-must-differ control per golden. | §7.1: the only golden is `REPORT_THEME` on black; unpinned. Threat 7. | A: three new pixel tests + `test_golden_files_match_their_pinned_digests`. | — |
| **T1.9** | **`--profile production`.** A run in this profile **refuses to deliver** if any of: diarization skipped, Path A skipped, Stage 4 judged without frames, Path B skipped (once T4.2 lands), reconciliation not run, no review record, any stage `StageSkipped`. Default profile unchanged; the contract carries `profile`. | Register row 6; "Nothing Skipped Quietly" canon at the delivery boundary. | A: `test_the_production_profile_cannot_deliver_with_a_skipped_stage`. B: one real production-profile run of ep29 (will refuse until #4 clears — record that). | — |
| **T1.10** | **Trust root for acceptance signatures.** Commit `security/allowed_signers` (Hawa's key + Kurdish editor's key); `editorial_acceptance`/`corpus_acceptance`/`diarization_acceptance`/`vertex_acceptance` refuse any other signers file. | §7.5 / threat 8: a self-minted key verifies today. | A: `test_acceptance_refuses_a_signers_file_that_is_not_the_committed_root`. | **Hawa** supplies public keys |
| **T1.11** | **Test-quality floor.** Add a coverage gate on `src/hawedit/{render,reframe,captions,boundary,clip,delivery,measure}.py` at the measured current value (ratchet-only, like the count floor) and a CI `skipped==0` check across **all** test files, not only `test_ingest.py`. Requires `.codystem-allow-self-edit`. | §7.2, §7.4, threat 6. | A: `test_the_gate_refuses_any_skipped_test`. E: CI job. | — |
| **T1.12** | **Path A stability measurement.** Run Path A K=5 times on the ep29 transcript; record candidate-set Jaccard, rank correlation and span drift. Then either cache the candidate set per transcript digest **or** select from the union with vote counts, and record which. | Path A returned 13 then 10 candidates on identical input; shipping depends on luck. | B: `evidence/path-a-stability-k5-ep29.md` with all five sets. A: `test_discovery_records_its_candidate_set_digest`. | Hawa (5 billed calls ≈ $0.20) |

---

## Phase 2 — The picture  · what a viewer sees first

| ID | Pri | Task | Why | Proof required | Decider / blocker |
|---|---|---|---|---|---|
| **T2.1** | **P1** | **Active-speaker reframe (re-opened pro-edit T7).** Diarization turns (`--diarize`, pyannote Community-1) + a face↔speaker associator. Two candidate associators, decided by measurement: **(a)** no new model — per-face mouth-region pixel-motion energy (lower third of the Haar box, sampled at ≥ 5 fps) correlated with the active turn; **(b)** an audio-visual ASD model (e.g. Light-ASD / TalkNet), which needs a §7 registry row, licence audit and ADR. Build (a) first; measure; add (b) only if (a) fails the bar. Crop follows the associated face; on ambiguity hold, never wander. | The single biggest visible gap (`HANDOFF.md` §5). Protocol exists, implementation does not (`reframe.py:112-125`). | A: unit tests on synthetic turns. B: on three 60 s ep29 spans, a Kurdish editor labels the speaking person per second (D); association accuracy ≥ 90 %, speaker in frame ≥ 95 % of speech frames (media tier). C: T1.2 `speaker_tracked` clause. D: labels. E. | **BLOCKED.md #4** — Hawa accepts the gated licence and supplies `HF_TOKEN` via `hawedit-credentials`. Model (b) needs an ADR. |
| **T2.2** | **P1** | **Wide-shot handling.** When the measured face-height share in a shot < `TARGET_FACE_HEIGHT_SHARE`, either zoom past `MAX_VERTICAL_ZOOM` up to a **sharpness floor** (Laplacian variance of the face region ≥ the median of the close-up shots × 0.6, measured), or switch that shot to a **blurred-fill layout** (scaled wide frame over a blurred, darkened copy — one ffmpeg `split/boxblur/overlay`). Decide per shot by measurement, record which in the contract. | `research.md` §3.1: eight seconds of a 6–8 % face. | A: geometry + layout tests. B: re-render s25-25; face share ≥ 0.12 in ≥ 95 % of frames; sharpness numbers; VMAF vs mezzanine; **frames inspected**. C: T1.2. E. | Hawa picks zoom vs layout after seeing both renders (taste) |
| **T2.3** | **P1** | **First-frame gate.** The first frame after the hook card (and under it) must contain the tracked subject's face at ≥ floor share and not a different person. Among the outward in-point candidates (`vad_onset`, shot cut ≤ 400 ms) choose the one whose first frame passes; if none does, refuse the clip with the measured reason. | s25-25 opens on the host drinking. | A: `test_a_clip_never_opens_on_a_frame_without_the_subject`. B: measured on the re-render. C: T1.2 clause. | — |
| **T2.4** | **P1** | **Composition line under punch-ins.** Keep the face on `FACE_COMPOSITION_LINE=0.38` in every keyframe; today punch-ins drop it to centre (`render.py:565` vs `:431`). | Regression visible in any punch-in clip. | A: `test_a_punch_in_keeps_the_face_on_the_composition_line`. B: measured y-centre across sampled frames within ±5 % of 0.38 on ep29. | — |
| **T2.5** | **P1** | **Face detector: sample rate and tracker.** Raise sampling to ≥ 5 fps and add a between-sample tracker (OpenCV KCF/CSRT, already in the wheel) so a missed detection does not pan to the rug. Evaluate a DNN detector (OpenCV YuNet ships as an ONNX file, Apache-2.0) **only** via ADR + registry row + licence audit. | `reframe.py:214,269-279`; §4.1 "rug on screen". | A: tracker tests. B: detection recall vs 200 hand-labelled ep29 frames (D, cheap: Hawa or editor clicks faces); miss rate before/after. | ADR if a new model file |
| **T2.6** | **P2** | **Eased push-ins.** Replace hard scale steps with a 1.00→1.08 push over the shot (per-frame `sendcmd` or `zoompan`), keeping hard cuts at source cuts and pause-motivated cuts. | Pro pacing; current alternation is mechanical. | A: schedule tests. B: render both versions of one ep29 clip. **D: Hawa picks.** | Hawa (taste) |
| **T2.7** | **P2** | **Face-aware caption placement.** If the tracked face box intersects the caption band in any frame, move the band (top/bottom) for that shot; never overlap. | `captions.py:229-231` fixed band. | A: geometry test. B: zero overlapping frames measured on ep29 renders (media tier). C: T1.2 clause. | — |
| **T2.8** | **P2** | **Caption legibility measurement.** Contrast between text colour and the band's median luminance per caption event; below 4.5:1 add the plate. | Nothing measures legibility; a dark source would fail silently. | A: contrast function tests. B: per-event contrast table for s25-25. C: T1.2 clause (min contrast). | — |
| **T2.9** | **P2** | **Shaped-width line breaking.** Break popup lines by rendered ink width (render the candidate line through libass at PlayRes, measure ink extent) instead of character count. | `captions.py:628,677`; Sorani ligatures make char count wrong both ways. | A: a long-ligature Sorani line that overflows today no longer does (pixel test). | — |
| **T2.10** | **P1** | **Deliverable encode profile.** NVENC `-preset p6 -profile high -bf 3 -spatial-aq 1 -temporal-aq 1 -cq 20 -g 2×fps`, colour tags `bt709`, lanczos scale + light `unsharp`, remove `-threads 1` from decode; libx264 equivalent. Working renders keep `-cq 27`. Target 8–12 Mbps at 1080×1920. | `research.md` §4.1 encode row; 2.79 Mbps delivered; bicubic 1.78–3.3× upscale. | A: args tests. B: VMAF of delivered vs lossless mezzanine ≥ 93; bitrate; file size; frames inspected for ringing. | **DONE** (`specs/deliverable-encode/`) |
| **T2.11** | **P2** | **Length variants 15/30/60 (§5 `durations`).** Sentence-complete sub-spans inside the winner, each re-judged (billed) and re-reconciled; one delivery set per variant. | §5 promises three durations; one ships. | A: sub-span tests. B: three variants of one ep29 clip, each through T1.2. | Hawa (cost ×3) |
| **T2.12** | **P2** | **Two-person layout.** When diarization shows a fast exchange (turns < 4 s) inside a clip, offer a top/bottom split of both tracked faces instead of whip-pans. | Needs T2.1. Podcast dialogue is the owner's format. | A: layout tests. B: one ep29 exchange rendered both ways; **D: Hawa picks.** | Hawa (taste); blocked by #4 |
| **T2.13** | **P3** | **Brand kit: lower-third, logo, end card, progress bar.** Speaker name from per-episode metadata + diarization label; logo watermark; 2 s end card; optional progress bar. Not in `BLUEPRINT.md` §3 Stage 6 → ADR. | A team always does this; the spec never asked. | A: ASS/overlay tests + goldens. B: render with the kit; frames inspected. | **Hawa** supplies names, logo, fonts; ADR |

---

## Phase 3 — The sound

| ID | Pri | Task | Why | Proof required | Decider |
| **T3.1** | **P1** | **DONE** — Two-pass linear loudnorm (`specs/two-pass-loudnorm/ledger.log`). First pass measures (`print_format=json`), second applies `measured_*` with `linear=true`. Both passes recorded in contract. | `render.py` two-pass linear mode verified; True Peak ceiling ≤ -1.0 dBFS strictly respected; contract updated. | A: `test_loudnorm_runs_linear_with_measured_inputs`. B: gate green; ledger updated with cryptographic evidence. | — |
| **T3.2** | **P2** | **DONE** — Speech chain: `afftdn` denoise, gentle `deesser`, presence EQ (`specs/speech-chain/ledger.log`). Native FFmpeg chain with ADR D-264. | Studio vocal conditioning pre-filtering into two-pass linear loudnorm; zero external dependencies. | A: `test_audio_filter_speech_chain_formatting`, `test_deliverable_render_incorporates_speech_chain`. B: gate green; ledger updated with cryptographic evidence. | — |
| **T3.3** | **P1** | **Silence tightening, wired end to end (pro-edit T4 as it was meant).** Actually cut the media (segment `trim`/`atrim` + `concat`, or `select`/`aselect` with `setpts`), regenerate ASS on the new timeline, re-time punch-ins and crop keyframes, then reconcile: measured audio duration = span − `silence_removed_ms` ±1 frame. Threshold is a parameter with **no default until Hawa sets it** from a measured A/B. | `silence.py` has no caller; applied as-is it would desync captions. s25-25 is 11.9 % pauses, none > 545 ms. | A: `test_removed_silence_shifts_every_later_caption`, `test_the_removed_total_matches_the_delivered_audio`. B: two renders (0 ms / 400 ms threshold) measured with `silencedetect`; **frames + audio inspected**. C: T1.2 clause. D: Hawa picks the threshold. | Hawa (threshold) |
| **T3.4** | **P3** | **Music bed with sidechain ducking.** `sidechaincompress` under speech; hook-card sting. | Standard on social; needs licensed music. | A: graph tests. B: LUFS with bed still −14; duck depth measured. | **Hawa** supplies licensed music; ADR |

---

## Phase 4 — The story (content-aware selection)

| ID | Pri | Task | Why | Proof required | Decider / blocker |
|---|---|---|---|---|---|
| **T4.1** | **P1** | **Episode plan: N clips per run.** Shared Stage 0–2; Path A once; judge within a per-episode cost cap; select N winners with zero temporal overlap, ≥ `MIN_SEPARATION_MS` apart, topic diversity (BM25 cosine over norm text below a measured threshold), speaker diversity when diarized; deliver N sets + a ranked `episode.json` manifest reconciled against the sets. | One clip per run; a team ships 5–15. | A: plan tests. B: one ep29 run delivering N clips, each through T1.2, manifest reconciled; wall-clock and cost recorded (§8.2 metrics). E. | **Hawa**: N and the cost cap |
| **T4.2** | **P1** | **Path B as independent discovery.** Stop seeding Path B with Path A's rank-1 slice. Run retrieval over all planned windows against a fixed Sorani query set for non-verbal beats (laughter, gesture, reaction, action) supplied or approved by Hawa (#18), within the 8-frame ceiling (#17); union with Path A per §3. Record per-path candidate counts and "found by B only". | `pipeline.py:1351-1376`: today B resembles A. §3: *neither path filters the other*. | A: `test_path_b_runs_without_a_path_a_seed`. B: ep29 run: candidates by path, B-only survivors, GPU memory/time. Per-path recall needs H2. | Hawa (#18 queries, #17 window) |
| **T4.3** | **P1** | **Judge calibration.** (1) Rubric anchors in the prompt (what 0.2 / 0.5 / 0.8 hook looks like, in Sorani, from the 20-item regression set). (2) Pairwise tournament among passers instead of `max(hook_score)`. (3) Repeat-K (K=3) agreement recorded per verdict. (4) Gate `meaning_fidelity` and `cultural_landing`. (5) Re-derive `MAX_MISLEADING_EDIT_RISK` from labels, not the model's floor — until H2, keep 0.10 and say why. Prompt hash in the contract (T1.6). | §4.7: no anchors, no comparison, one number, threshold fitted to output. | A: schema/gate tests. B: on the 20-item set, Spearman vs human ≥ recorded baseline + agreement stats. D: needs H2 for any threshold change. | Hawa (thresholds are hers) |
| **T4.4** | **P2** | **DONE** — Hook taxonomy, payoff and loop scoring (`specs/hook-taxonomy/ledger.log`). Verdict gains `hook_type ∈ {question, claim, contrast, story_open, confession}`, `payoff_strength`, `ends_on_a_beat`, `reason_ckb`. Projected to `Editorial` contract and used in pipeline candidate tiebreakers. | `payoff_at_ms` is never used; `reason_ckb` is discarded. | A: `test_verdict_hook_type_validates_canonical_taxonomy`, `test_verdict_reason_ckb_requires_kurdish_script`, `test_verdict_and_editorial_hook_taxonomy_roundtrip`. B: gate green (3417 passed); ledger updated with cryptographic evidence. | — |
| **T4.5** | **P2** | **Content-type profile.** `--content-type {podcast, interview, news, social}` set by Hawa per source; drives thresholds, caption style, punch-in cadence, tightening default. ADR. | No mode anywhere; ep29 is a podcast, KAAE material is not. | A: profile tests. B: one render per profile of one span; frames inspected. | Hawa chooses per source |
| **T4.6** | **P2** | **Visual-variety-aware selection, behind a flag.** Tiebreak passers by source cuts per second within the span; default **off**. Measure on ep29 which clip each policy picks. | `HANDOFF.md` §5: Hawa's editorial call; measured bias toward flat footage. | A: flag tests. B: both policies' picks on ep29 with cut counts. **D: Hawa decides the default.** | **Hawa** |
| **T4.7** | **P1** | **Sentence rule from real audio (#14).** A Kurdish editor labels 50 sentence boundaries in ep29 (D). Fit the pause threshold and any discourse-marker rule to those labels; report boundary F1; replace the 500 ms placeholder with the measured value and its source. | `sentences.py:46-49` placeholder; a 105 s "sentence" exists. | A: rule tests. B: F1 on the labelled 50. D: labels. | Hawa or editor labels; #14 |
| **T4.8** | **P2** | **DONE** — Boundary extension that completes a sentence (`specs/sentence-boundary-extension/ledger.log`). Enclosed complete sentences absorbed into `selected` and captioned; partial sentences refused as uncaptioned speech. | Preserves zero uncaptioned speech invariant while preventing needless rejection of continuous podcast boundaries. | A: `test_boundary_extension_absorbs_fully_enclosed_sentence`, `test_soft_boundary_expansion_cannot_swallow_uncaptioned_speech`. B: gate green; ledger updated with cryptographic evidence. | — |
| **T4.9** | **P2** | **Cold-open assembly (re-opened pro-edit T6).** Render a real reel: payoff sentence first, then the setup, media concatenated with `xfade`/`acrossfade`, ASS regenerated on the assembled timeline, punch-ins re-timed; judge the **assembly** with frames from the assembled render; `misleading_edit_risk` gated on the assembly. Reconcile. | `assembly.py` is text-only, unwired, refused by the real judge. Hawa approved building assembly. | A: `test_an_assembled_reel_is_rendered_and_judged_with_its_own_frames`. B: one ep29 cold-open vs its single-span original, both judged; the record states honestly whether the assembly scored worse. C: T1.2. **D: Hawa watches both.** | Hawa (taste) |
| **T4.10** | **P3** | **Cover frame and title variants.** Choose the cover frame by face share + sharpness + eyes-open heuristic; ask the judge for three `title_ckb` variants; ship `cover.png` and the variants in the contract. | One title, no cover. | A: selection tests. B: covers for N ep29 clips inspected. | Hawa (cost) |

---

## Phase 5 — Human ground truth and the only proof of "better than a team"

Owner-owned inputs. The system ships the kit; Hawa supplies the humans. All existing rows in
`specs/true-10-10-acceptance/tasks.md` (H1–H6, F1–F8) stand. Added here:

| ID | Task | Proof | Decider |
|---|---|---|---|
| **H7** | **Blind pairwise comparison: system vs a human editor.** Commission one professional Kurdish editor to cut 5 clips from ep29 (same brief: 30–90 s, 9:16, captions). The system cuts 5 in production profile. ≥ 20 Kurdish viewers rate blind pairs (pre-registered form: hook, clarity, would-share, misleading?). Report win-rate with 95 % CI. **"Better than a team" is claimable only if the CI's lower bound exceeds 50 %.** Anything else is reported as the number it is. | D. Kit = T5.1. | **Hawa** commissions editor + raters |
| **T5.1** | **The comparison kit.** Randomiser, blinded file naming, rating form (Sorani), analysis script (win-rate, CI, per-dimension), reviewer records per T1.3 format. Ships before H7 starts. | A: kit tests on synthetic ratings. | — |
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

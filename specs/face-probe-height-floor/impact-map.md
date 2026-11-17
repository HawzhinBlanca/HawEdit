# Impact map — face probe height floor

Serena did not connect on 2026-11-17, so callers were found with grep over `src/` and `tests/`.
Re-run `find_referencing_symbols` on `probe_face_tracking` before implementing if Serena is back.

| Symbol touched | Callers in `src/` | Tests covering them |
|---|---|---|
| `measure.probe_face_tracking` (`measure.py:509`): which samples count as a face changes; signature and return type do not | `measure.measure_clip` (`measure.py:1157`) only | none directly today; AC1-AC3 add three in `tests/test_measure.py` |
| `measure.measure_clip` (unchanged; its `faces` numbers can drop) | `pipeline.py:2511, 4598`; measurement CLI `measure.py:1212`; subprocess in `candidate_publication.py:107` | the 19 test files in `captures/whatif-log.txt` |
| `delivery.reconcile_delivery` clauses 7, 7a, 7b (unchanged; reads the numbers) | `pipeline.py`, `candidate_publication.py`, `proposals.py` | `tests/test_delivery.py` builds measurements by hand, so it is unaffected |
| new constant `measure.MIN_FACE_HEIGHT_SHARE` | `probe_face_tracking` | AC1-AC3 |
| `security/wsl-asr-vex.json`, `tests/test_vex.py` (`REVIEWED_VEX_SOURCE`) | `package_digest(src/hawedit)` moves with any source edit | `tests/test_vex.py`; re-pin needs owner approval |

## What the floor changes in the existing suite (logged, see `research.md`)

| Today | Calls | After the floor | Outcome change |
|---|---|---|---|
| no box | 64 | no box | none |
| share 0.0476-0.1 from one 2.7 % box | 48 | share 0.0, medians `None` | none: every face threshold is 0.50 or higher, so these were already below it |
| share 1.0 from a faked 80 px box, `test_pipeline_integrates_motion_speaker_tracker_for_active_speaker_reframe[default]` | 1 | share 0.0 | none: that clip is `static_centre`, which Clause 7 does not check, and the test asserts nothing about faces |

- **One test changes its expectation:**
  `test_ambiguous_speaker_tracking_falls_back_without_claiming_speaker_provenance` (T2). It is
  already red; today it measures 0.1 and after the floor 0.0.
- No test pins a measured face number or a digest of `.measured.json`'s face block (grep for
  the logged values and for `["faces"]` found only hand-built measurements).
- Tests that compare two runs byte-for-byte (`test_checkpoint.py`, `test_events.py`) change on
  both sides equally.
- Stored `.measured.json` files from earlier runs are not re-read as input; a clip measured
  again after this change can report a lower face share than its old record.

## Not verified

- At least 8 tests did not reach the probe in the logged run (long temp path, see
  `research.md`). The first full gate after T1 is the real check; any test it shows was passing
  on a sub-5 % box gets T2's treatment and is added to this file before its row flips.
- Real footage: a real face under 5 % of frame height would now count as "no face". D-258's
  smallest measured face is 11.6 %, and the tracker's own floor (`MIN_FACE_AREA`, about 45 px
  on a 1080-high source = 4.2 %) plus the 1.5x zoom toward 15 % make that unlikely, but that is
  reasoning, not a measurement.

# Evidence guide

Read `research.md` for conclusions and `plan.md` for the proposed sequence. `spec.md` names proposed regression tests; it does not claim those tests have been implemented. `impact-map.md` records provisional caller mapping.

* `probes.json`: current commit/runtime, critic controls and bypass, helper assembly seam, real HTTP probes, actual 20-job collision burst.
* `black-media-measurement.json`: independent FFprobe metadata and full OpenCV decode of the black two-second fixture. No audio; 50 all-black frames.
* `assembly-pipeline-probe.json`: actual `run_pipeline` traceback for complete Sorani sentence assembly.
* `pipeline-probes.json`: initial English synthetic transcript is correctly rejected by the language guard; separately, the real rendered review publication probe fails writing its edit plan after publishing the bundle. The later Sorani assembly probe is the assembly failure evidence.
* `recovery-probes.json`: corrupt proxy accepted on resume, face-check controls, absent detector resource returns success, candidate overlap data.
* `conjunction-punctuation-probe.json`: supported punctuation variants bypass the new dangling-conjunction guard.
* `browser-jobs.json` and `browser-final-dom.txt`: selected local fixture job and rank-two UI state with rank-one download URL.
* `captures/01-start.png`, `02-input-validation-viewport.png`, `03-fixture-result.png`, `04-second-candidate.png`: exact saved and inspected browser screenshots. No edited/composited screenshots. A defective full-page capture is excluded from the accepted set.
* `environment.json`, `source-manifest.json`, `verification.md`, `gate.log`: environment, source identity and canonical verification provenance.

All probes ran from `C:/Users/Wareen/Desktop/HawEdit` using `.venv/Scripts/python.exe`. Scripts and generated fault fixtures were isolated at `C:/Users/Wareen/.codex/tmp/hawedit-audit-532e6ef`, preserving a clean checkout during the gate. No protected fixture or application source was changed. The HTTP probe used a temporary localhost server launched with `python -m hawedit.web 8080`, which was stopped afterward. The browser tab was closed.

To rerun, copy the scripts into a fresh external temporary directory and run from the repository root with its venv. The pipeline scripts create their own working directories and intentionally trigger errors; do not reuse a previous publication directory and interpret a no-overwrite refusal as the original failure. Run the assembly-only script separately for the corrected Sorani case. `recovery-probe.py` intentionally corrupts only the generated audit proxy after that assembly run. `probe.py` requires the local web server; it creates temporary in-memory jobs. These scripts are retained reproductions, not additions to the canonical test suite.

Large generated review/intermediate artifacts remain in the external temporary directory. The report directory contains the small black test MP4 and 32-second synthetic assembly MP4 plus relevant JSON evidence. The publication result includes all observed review paths; those files remain available in the external audit directory.

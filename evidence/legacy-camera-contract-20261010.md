# Approved Legacy Camera Contract Correction

```yaml
commit: 7f3ee2f9ff93555eea7a45d26c23503bef8fb586
media_sha256: ed038e743a6b1ee167290741ceda926ac1077ff192e4910528017e3183655a15
host: HawaPC01 Windows26300 Python3.12.10 pytest9.1.1 ruff0.9.6 mypy1.15.0 OpenCV4.12.0 ffmpeg8.1.1
command: .venv/Scripts/python.exe -m pytest tests/test_pipeline.py tests/test_reframe.py tests/test_candidate_framing_parity.py tests/test_review_candidate_cache.py --junitxml=C:/Users/Wareen/HawEdit-video-rating-20261010/legacy-camera-contract-final-affected.xml
```

2026-10-10. BLUEPRINT §3 Stage6 and §§8.1-8.3; D-241/D-263/D-274.
Approved specs/legacy-camera-contract/plan.md. Parent local-only source commit
7f3ee2f9ff93555eea7a45d26c23503bef8fb586; production package unchanged
f9c3871bb6cd3d32cff0203f8d222b78bce61ed0fc965cfe64a5efe8aefabc6e.
The cohorts below tested development test changes, not a clean committed gate
or same-SHA CI. No production source, model, dependency, threshold or trust change.

The original collected integration function remains, now preview/production
parameterized. Actual MotionSpeakerTracker decodes the unchanged digit fixture:
nonempty observations, no speaking observations and no confirmed identity.
Preview is explicitly STATIC_CENTRE and private/awaiting-human-review/incomplete;
the retained legacy QC digest differs from actual measured MP4 bytes and has no
signature. Production refuses camera admission and has exactly its legitimate
Stage0 source proxy, no candidate MP4. All private sidecars and hash binding checked.
No source-proven actual-person identity or native meaning claim follows.

Read-only AST comparison against parent confirms _test_qc, the original
MOTION_SPEAKER_TRACKED_RENDER_SHA256 and injected _MockClassifier unchanged.
Fixture SHA256ed038e743a6b1ee167290741ceda926ac1077ff192e4910528017e3183655a15;
final development tests/test_pipeline.py raw SHA256
ec18a360fac5c1b7591c1e684d4cae9dc7372588b87d5dc39aa5bea135168de0,
unchanged across final affected run. Fixtures, goldens, existing positive controls,
QC helper/digest and security policy unchanged. Actual five-pair Serena map:
C:/Users/Wareen/HawEditLegacyCameraContractMap-20261010/serena-map.json,
SHA25647da35e0bdfb3472d233809495f69ea766f9d6c9f895e6e54a933a9a84e87597.

Reports under C:/Users/Wareen/HawEdit-video-rating-20261010:

| Report | Result | JUnit seconds | SHA256 |
| --- | --- | ---: | --- |
| legacy-camera-contract-affected.xml | 469cases/467pass/2fail/0errors/skips | 928.588 | 0793138e5384d69ce4911bcf9efdffb2bd6f5bc51f5264ba0ae38a0564ffb318 |
| legacy-camera-contract-focused.xml | 2pass/0fail/errors/skips | 18.207 | bd42a53995629d2b71b5b175a223445335b5dd355fef001bcb0ad108f54a210b |
| legacy-camera-contract-final-affected.xml | 469pass/0fail/errors/skips | 934.480 | 846f67d04fb2c8dc1714bf3a8b5028358b1e0548eb571362eca0a0346481add4 |

First trial speaking assertions passed; incorrect test assumptions were absent
legacy QC data and absence of even the ingest proxy. Corrected to the actual
stronger publication contract above, not permissive speaker evidence. Trial
and actual failed artifacts preserved in legacy-contract-first-trial-artifacts;
final actual artifacts in legacy-contract-final-artifacts. Original 7f gate
remains6139pass/2fail, never retroconverted; see camera-admission-20261010.md.

Whole affected command: .venv/Scripts/python.exe -m pytest tests/test_pipeline.py
tests/test_reframe.py tests/test_candidate_framing_parity.py
tests/test_review_candidate_cache.py --junitxml=<named report above>.
No deselection, skip, assertion-forged fixture, tool override or gate substitution.
Exact Git bash scripts/verify.sh --fast passes lint/strict mypy389files;
separate ruff format --check src tests scripts passes389files. Fast is not the gate.

HawaPC01, Windows26300/Python3.12.10, pytest9.1.1/Ruff0.9.6/mypy1.15.0/
OpenCV4.12.0/DBOS2.29.0/ffmpeg8.1.1-full_build-www.gyan.dev, existing installed
Winget media tools. Timings are contract-cohort timings, not creator performance.
Next exact clean committed gate remains required, as do independent current-source
VEX (#24), same-SHA CI (#25), actual protected model resources/lifetime and ZAR,
native editorial/identity/benchmark/sustained acceptance. No row promoted,
publication/provider spending or true10 claim.

## Original Frozen Gate At 4b2b7ca

Exact clean committed bash scripts/verify.sh at
4b2b7ca4cbadc45aa24088c94cfd2af3992c2243, source packagef9 unchanged:
6142cases/6140pass/2fail/0errors/skips, JUnit2795.535s,
observer2879.490263100015s. Lint/strict typing/format pass389files.
Frozen checkout/watched bytes unchanged; original processes ended.
The corrected camera test passes; remaining failures are the old VEX binding
and this new note's missing required YAML header. The header is corrected in
a later documentation-only change, not by weakening claims tests. Original
gate remains RED and this4b source history retains the original deficient note.

Raw C:/Users/Wareen/AppData/Local/HawEditEvidence/legacy-camera-contract-clean-gate-20261010:
gate.xml SHA2564edd8bc59dc0e72296aa03359b7e07389984312a0f857090bce651a7aa134274;
terminal.json SHA256d2ae39f59ccdd068ca11069186d11873c8fc0d10c47b5f8b0d8f7a699d8f7f8f.
Header identifies the committed parent of development cohorts, not acceptance
of different test bytes at that parent. Full later committed gate/CI and #24
qualified review still required; no task promotion, provider calls or publication.

## Evidence Header Repair Check

Documentation-only header repair followed the original red gate. All 67 cases in
tests/test_claims.py pass, JUnit21.644s, on the recorded Windows/Python/toolchain
above. Command: .venv/Scripts/python.exe -m pytest tests/test_claims.py
--junitxml=C:/Users/Wareen/HawEdit-video-rating-20261010/legacy-camera-header-claims.xml.
Report SHA256d8950126e1c036235e91e3e719df5f9afb7a454e533c908072ae9aa1c96dc2f2.
This is a focused metadata check, not a replacement for the full committed gate.
The original red gate and its two failures remain preserved.

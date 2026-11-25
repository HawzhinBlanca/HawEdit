# Local Evidence, Not Release Acceptance

HawaPC01 / Windows26300 / Threadripper3990X / two RTX3090Ti24GiB, driver610.88.
Contract tests use CPython3.12.10 / pytest9.1.1 / Torch2.13.0+cpu / NumPy2.2.2;
ruff0.9.6 / mypy1.15 strict. Source corpus contains explicitly doubled vendor
model inference; actual WAV/checkpoint hashes and OS locks are real. No protected
fixtures/manifest, test skips, selectors, weakened assertions or ledger promotion.

External native HawEditEvidence roots under C:/Users/Wareen/AppData/Local:

| Run | Actual Result | JUnit SHA-256 |
|---|---|---|
| diarizer-runtime-source-red-20261008 | 21 cases:18 failed/3 passed, no errors/skips;5.377s | 587e432912af29e4e71ab81fc7cbd4b3c34497555c6348a3837eaf47e0180b36 |
| diarizer-runtime-whole-callers-20261008 | 608 passed, no errors/skips;538.637s | b04fa84ca61fe8588adfb7ef93d2bf51bc832d09f76a438d2f37fbea7b458461 |
| diarizer-partial-pcm-source-red-20261008 | 22 cases:21 passed/one partial-frame failure, no errors/skips;4.748s | 692b4b7b0eb6bfbdd88c3167630866ee21ce9af00732985179bb15afc8e62be3 |
| diarizer-runtime-final-model-adapters-20261008 | 161 passed, no errors/skips;12.548s | 092139c509ebbdf2296971d152bb95f5e015c642d55b75be870e132cab0b244d |

Whole callers ran before the partial-frame tightening; final model/adapter run
includes that correction. Counts overlap, not independent evidence to sum.
Lint/format/strict types pass344 source files. Exact full committed-source gate
and required same-SHA CI are still pending at this document's creation.

Actual source helper/vendor Audio observation: isolated supported studio
CPython3.11.15 / Torch2.13.0+cu130 / torchaudio2.11.0+cu130 / torchvision0.28.0+cu130 /
TorchCodec0.15.0+cu130 / NumPy2.2.2 / Pyannote4.0.7 / inert SDK0.4.0 / DBOS2.29.0.
Native diarizer-runtime-actual-pcm-final-20261008/terminal.json records exact
commands, controller/source identities, versions, timing, warnings and bytes.
Actual final helper run8.62527409999166s, recordSHA
831f0ed855b8a868cf224fd08c6655db0a95db7ad68f5c953fa15608e20470fe;
working package digestf1f862021a750b973b33f11fab485dd8576dc51702d873949d0b521b2eda848b.
It ran against the recorded dirty implementation before its local commit, not
committed-source gate/CI evidence.
ZAR sourceSHA bd004519e4ed0254f5c4f5197aa501acc56ce957829f62ac0bdc4d7190ec1dd2;
8 seconds, mono16kHz/128000 samples/256000 PCM bytes,
PCM SHA7861a9cd2e072f3c04901b9c5ca7d3be6245e81501a01999e91680c25e535f99.
Source WAV unchanged, exact sample/clock roundtrip, metrics false, SDK inventory
empty, no Python socket audit attempts, owned guard removed and original finders
retained. Native networking is not covered by Python audit. Actual PATH Gyan
FFmpeg8.1.1 is recorded, not qualified as the pinned delivery toolchain.

First actual probe failed a whole-import-list equality because vendor initialization
legitimately adds an import finder. Preserve diarizer-runtime-actual-pcm-20261008
and v1 controller, not a successful run. Correctly scoped cleanup observation in
v2 and final records succeeds; no production guard/assertion was weakened for it.
TorchCodec's missing shared-FFmpeg warning is retained: in-memory input does not
claim that the file decoder now works. No licensed checkpoint/neural inference,
DER/speaker identity/editorial/reel/publication/full-source or no-egress acceptance.

No current qualified VEX or genuine reviewer/owner authority is fabricated. No
paid cloud call or protected model-manifest change. Full system acceptance remains
subject to the approved plan and all existing AC obligations.

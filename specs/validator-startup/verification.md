# Verification

Exact map/probe provenance is in research.md. Frozen primary c163511 ZAR run
is ongoing and does not execute this change.

HawaPC01, Windows26300, Threadripper3990X; native CPython3.12.10,
NumPy2.2.2, pytest9.1.1, Ruff0.9.6, mypy1.15.0, DBOS2.29.0. Secondary
R: alias points to this checkout's unchanged installed environment.

Test-first whole new module: 15 cases, six failures, nine passes, no errors/skips.
Four genuine permanent-error retries and two canonical PCM path requests fail.
Immutable root validator-startup-red-529dd23-20261008 under local HawEditEvidence;
JUnit SHA256 121b336dfd44e347776610c2aa700f35fd7c945cfb824374f360f5b2ff01de43.

After repair, complete test_validator_startup, test_asr, test_asr_stop,
test_asr_resume and test_wsl_setup:177 passes,0 failures/errors/skips,
JUnit50.182s/controller52.229274999990594s, source unchanged. Report SHA256
09f559368a997ff2ca5b7d751b060f3003ab8f7ffcc0fb26b0818abe38591666;
stdout faec0587de96eed43e40c0a1f58b8fd7affe22f9e5d9d7a3051e0357945f17e1;
root validator-startup-callers-20261008. Initial fast lint then refused SIM117 in
the new test; combined contexts, unchanged assertions. Subsequent exact --fast
passes lint/strict types349 files; format349 passes. Not the full gate.

Actual installed WSL Qwen0.0.6 normalizer and soundfile0.14.0, NumPy1.26.4,
CPython3.12.0: all158 real ZAR segment waveforms equal independent soundfile
float32 decoding and official tuple normalization. First segment also equals
the actual official string-input normalization. No mocked decoder/model loaded.
Every source WAV hash unchanged; script/adapter/upstream utils hashes unchanged.
Controller21.28998230000434s; tuple loop5.5938751450012205s; first actual
string normalization13.289341579002212s. These are decoder-check observations,
not matched neural speed or performance acceptance. Root
validator-startup-real-pcm-parity-20261008; stdout SHA256
c4f593396141e8cc38e67450efa8d04502f71e371ab6d98db4611fcbc518998b;
script C:/Users/Wareen/check_hawedit_qwen_pcm_parity_20261008.py SHA256
133e0e0b41b5edcc68de84fcd011258d40061109535e66776b9383fa7a724a03;
installed utils b37fb4140e6d9be85f2ecb1552ed16136eb98a57f44b402f8b0b213cb6df2a82.

Real repaired CLI on the same unsupported UNC runtime root exits1 with errno22
and local-lock-support guidance in0.4906003000069177s; no six-hour sleep, neural
child or runtime receipt. Existing .setup.lock and observation file retained.
Root validator-startup-unc-refusal-20261008; stderr SHA256
d2df373874e982b4a362b9163a678694003ccc6a5dafc7719a64a755f2a97b08;
source unchanged, package079c8d173e373fa2c687e44c57c804429abb095de7a649d2fe7dc8ce0971f731.

Exact clean committed full gate and same-SHA CI remain. Qualified VEX is already
known stale; no agent rebinding, expiry extension, ledger promotion or10/10.

Cross-platform correction before acceptance: actual Linux model-free call using
Windows CRT errno36 exposed the native-POSIX enum mismatch in36b68149.
Root validator-startup-linux-crt-red-36b6814-20261008, unchanged source,exit1;
stderr bacf8afd02bc8ebd29c6f4c58a8722da62850b9a79912bc674d6bdac6a8afaf5.
Native Windows EDEADLK36 differs from Linux35. Explicit Windows CRT36 preserves
the existing simulated-Windows caller contract on every gate host.
New test parameter also uses actual CRT36, not the host's POSIX enum.

The initial exact36b68149 full gate was deliberately cancelled to repair this
known portability bug: only verified owned pytest/build descendants stopped by
exact PID, no console-wide event and no primary ASR interruption. Actual exit127,
controller189.58411029999843s, unchanged source; no fresh JUnit, no full gate
result. Root validator-startup-full-gate-36b6814-20261008;
stdout969b4551a084beacb1f60469d8e1a23bda8ba88988e9ba7c08eca6d356080de6.
Rerun whole affected modules, Linux CRT observation and exact frozen full gate.

Corrected whole177 callers pass again,0failures/errors/skips; JUnit43.894s,
controller52.96822580001026s, source unchanged. Final report SHA256
8a5f3c57411aa7457d01912ed34fc5f45a9b1c6721fc02ad997ee4f6200d4a45;
root validator-startup-callers-final-20261008. Actual Linux CRT36 observation
also passes retry and unlock, unchanged source,2.465672300008009s;
root validator-startup-linux-crt-final-20261008, stdout SHA256
86bb63c200d0ad0219afae7b872ba2d8ca660366b7ede96fdc118bb2da72e6af.
No full Linux suite/current CI claim follows the bounded observation.

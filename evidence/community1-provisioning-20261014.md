---
commit: 5a5b284b04d369fcf8ca45cb434e038fa68150e5
media_sha256: n/a (actual pinned model provisioning, no inference)
host: HawaPC01 Threadripper3990X Windows26300; downloader CPython3.11.15; tests CPython3.12.10
libraries: huggingface_hub0.36.2 pytest9.1.1 ruff0.9.6 mypy1.15.0
command: .venv-gpu/Scripts/python.exe -m hawedit.model_fetch pyannote/speaker-diarization-community-1
status: WIP; real download verified; no ASR, gate/CI pass, model-release or publication claim
---

# Community-1 Actual Provisioning

The header identifies the baseline; the approved metadata and regression changes
were in the working tree for this actual provisioning attempt. Initial evidence
validation refused a missing command field (1failed/66passed); this record was
corrected, not the validator or its assertions. Canonical --fast subsequently
passes lint and strict typecheck409files; it is explicitly not the full gate.

Wareen explicitly approved the scoped reconciliation and integrity-row exception
on2026-10-14. Only the Community-1 row in models/integrity.json changed. Structured
comparison against baseline confirms every other row and top-level field unchanged.
The historical top-level comment still describes its2026-08-09 observation;
this record supplies provenance for the newly reconciled row without expanding
the approved edit. No repository/revision/model substitution or new terms accepted.

Repeated authenticated metadata at the exact existing revision:
3533c8cf8e369892e6b79ff1bf80f7b0286a54ee. All ten paths, sizes, regular Git
identities and five LFS hashes match the retained read-only response. Raw
C:/Users/Wareen/HawEditCommunity1-approved-metadata-20261014.json,
SHA2566ac8aa93d5fa0a9435612d466b72f3b4e8a9cb3be6aa5528453f3474f7e9d956.
No credential is present in that output. A first metadata comparison used the
wrong UTF16 decoder and refused; rerun with actual UTF8 passed, not suppressed.

Actual Serena seven definition/reference pairs before test/metadata edits,
unchanged source custody: C:/Users/Wareen/HawEditCommunity1Map-5a5b284-20261014/serena-map.json,
SHA2560be42b43dffe0fd8c25786e1200b1b61d5ecf52bdd580fc800dcbb50f9a71412.

Strict historical refusal uses a real temporary manifest containing the old
blocked row and the same refused-checkpoint assertion, not a mocked validator.
Separate pinned-identity regression failed before reconciliation:1failed/1passed,
2.27s. Raw red XML977cd2e71ea964524a68478f0adafe97f5e59c4343a0db90da4f14e772a4e187.
After reconciliation all three row tests pass. Full ten caller modules:
382passed/0failures,104.53s, C:/Users/Wareen/HawEditCommunity1-callers-20261014.xml,
SHA2565f21ee504be3e47af12e353cccde51680c29d4e46ee1fb03d9627bbb92cba13e.
These are scoped regressions, not a full gate or demonstrated diarization accuracy.
Single-file mypy refused imports because its scope omitted the source package;
the canonical configured whole-project typecheck is the authoritative result.

Exact actual fetch command, existing audited models profile, no installation:
`.venv-gpu/Scripts/python.exe -m hawedit.model_fetch pyannote/speaker-diarization-community-1`.
Exit0; private staged fetch verified and atomically published10files/33695573bytes.
Raw C:/Users/Wareen/HawEditCommunity1-approved-fetch-20261014.log,
SHA256c52d7bf5c119072ae6062fd0819847322daf83af4451a83863e6e6dd15475f36.

Independent second ModelStore.verify_checkpoint on the actual final path:
C:/Users/Wareen/Desktop/HawEdit/models/pyannote__speaker-diarization-community-1.
Ten exact files/33695573bytes verified again, exit0. Raw JSON
C:/Users/Wareen/HawEditCommunity1-independent-verification-20261014.json,
SHA25696e87b834e551c25b1964d3902c87dac0c4838aa25f53ef7dfa7e44e867cacf7.
Reconciled metadata SHA256a48b2116a34b739ca24467cdaf648023d211be78cd572327fe959921f8f2d902.

Fetcher readiness still refuses canonical OmniASR because current-source WSL
receipt is missing. No fake receipt, fallback model, invented transcript,
guessed captions, actual Community-1 inference, complete GPU producer, ZAR reel,
ledger promotion, current-SHA CI or10/10 claim. BLOCKED #24/current qualified
security assessment and approved protected-producer requirements remain required.

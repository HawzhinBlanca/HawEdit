# Current-main long-form OmniASR acceptance — 2026-08-17

This is execution and integrity evidence for protected main
`4dbffa2585e50e60d4dcebf6c508699aac0a35ad`; it is not a transcription-accuracy claim. The
source package digest was
`2860455ff8887bea311438405e006544592a784de77c65c73620ddbe612612b1`, exactly matching the
receipt-selected WSL snapshot used by the worker.

## Inputs and runtime

The representative source was
`C:\Users\Wareen\Desktop\Test Videos\ZAR38MinTest.mp4`: 82,446,418 bytes, 2,313,800 ms,
SHA-256 `bd004519e4ed0254f5c4f5197aa501acc56ce957829f62ac0bdc4d7190ec1dd2`.

The accepted WSL receipt selected generation `Ubuntu-a3a875601325fe6bd6497791`: CPython 3.12.0,
140 exact installed distributions, build/runtime dependency lock SHA-256 values
`b153285953b96583bf60945783364662f6ab58f8fc1cb6f58fbdd2caa454a9a9` and
`190844f326d409b8d6b7b9536a880e2a77a9eebfe056369688337ce6386f5aea`, two CUDA devices, and
43,546,500,168 authenticated OmniASR asset bytes. Stage 1 used canonical
`omniASR_LLM_7B_v2`, CTC/Viterbi alignment, and the byte-verified
`rzgar/qwen3-asr-sorani-kurdish-ckb-v1` validator.

The exact command was:

```text
python -m hawedit.pipeline ZAR38MinTest.mp4 \
  --work-dir C:\Users\Wareen\AppData\Local\HawEdit\acceptance\zar38-2860455f-20260817-015331 \
  --media-id zar38-2860455f \
  --omni-asr --omni-asr-runtime wsl --wsl-distro Ubuntu --json
```

The host run took 2,804.384 seconds. The atomic WSL request-to-worker-output interval was
2,567.184 seconds. Stderr was exactly zero bytes. The CLI's structured report is incomplete by
design because diarization, visual discovery, editorial judging, boundary, render and delivery
were not enabled for this Stage 1 acceptance.

## Artifact validation

The worker result was published only after all inference and validation completed. Parsing both
artifacts with the current `RawTranscript` schema proved that the worker result exactly equals the
host's immutable stored raw transcript. `TranscriptStore.verify_raw_integrity` passed; the stored
raw bytes and write-once sidecar both have SHA-256
`27341fcfdcbc8b13af7c5f331b4fd2e88de055b4dfb7c23288ca86be239c682d`. The worker file differs
only by its protocol trailing newline and has SHA-256
`a41eceb93cad73e0c80d020df30f9f6d7151ea68d98b45f6544cbf8fd1cd6394`.

The normalized transcript in the emitted report exactly equals the store's normalized artifact
and names that raw digest as `source_sha256`. Report gaps and rejected corrections exactly equal
the raw artifact fields. The 1,040,535-byte report has SHA-256
`c1f66f7a703f73c1b4db68a2184b032b25a1c823ddc88f0aa1e0ab7864a18823`.

Measured transcript facts:

* Stage 0 produced 547 bounded speech regions and 138 shot cuts.
* 545 regions produced aligned transcript lines and 545 per-region confidence values.
* The raw transcript contains 34,703 characters and 5,897 timed words.
* Mean segment log-probability is `-6.581392978628334`.
* The first word starts at 322 ms; the last ends at 2,313,729 ms, 71 ms before source end.
* Two genuinely unaligned regions remain explicit: `226754..227070` and
  `1985346..1985694`, totalling 664 ms.
* Two validator corrections were refused while their canonical timed speech was retained:
  `1043426..1043742` (`AlignmentInfeasible`) and `1488354..1488734` (validator returned no
  transcription).
* The routing rule scored all 545 aligned regions and escalated 294: 121 by both triggers,
  158 by disagreement only, and 15 by confidence quartile only. `validated_by` records the
  pinned Sorani validator, proving at least one correction was accepted.
* Sentence segmentation produced 195 sentences and BM25 indexed exactly 195 documents.
* The non-GPU Stage 2 planner produced 142 default visual windows.

## Reuse and CLI contract

A second invocation against the same work directory completed in 57.151 seconds without a model
reload. It exited 1 because the intentionally omitted downstream stages remain named
`StageSkipped` values, wrote zero stderr bytes, and emitted a report byte-identical to the first
one, with the same `c1f66f7a…` digest. The immutable raw transcript's last-write time remained
`2026-08-17T02:40:13.6662624+03:00`; only the replaceable normalized derivative was regenerated.

This proves the expensive Stage 1 reuse key, deterministic structured report, write-once raw
boundary and incomplete-run exit contract on current main.

## Claim boundary

This closes current-main executable acceptance for canonical long-form Stage 1 on the measured
dual-RTX-3090-Ti host. It does not establish CER/WER, dialect or named-entity accuracy, speaker
diarization, visual retrieval quality, editorial quality, or confidential Vertex routing. Those
claims require their own labelled or authorized acceptance evidence and are not inferred here.

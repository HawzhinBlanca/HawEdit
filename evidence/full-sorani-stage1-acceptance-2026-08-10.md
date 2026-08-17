# Full Sorani Stage 1 acceptance — 2026-08-10

This is production-host execution evidence, not a unit-test inference and not an accuracy claim.
The source was the 2,313.8-second, 82,446,418-byte Sorani episode
`C:\Users\Wareen\Desktop\Test Videos\ZAR38MinTest.mp4` on hawapc01. Stage 1 used the
receipt-selected Ubuntu WSL generation, canonical OmniASR LLM-7B + CTC-3B/Viterbi, and the exact
21-file rzgar validator checkpoint at revision
`d71490a623113b4b069ac07cfc85b409389dde4c`.

## Defect exposed by the first full run

Source digest `b2f4e6976e20e3d04753f2daad61487930d074e8df3d2f7ad8d3d40887029cdd`
first closed a Windows composition defect: the host no longer required the Linux-only
`qwen_asr` loader before handing an exact checkpoint to WSL. Host verification measured the
expected contrast: `ModelStore.assert_available` refused the missing Windows loader, while
`verified_checkpoint_access` authenticated the same checkpoint and held its publication lease.

The resulting full CLI run cut all 547 speech regions and ran for 2,095.9 seconds, then correctly
returned a structured Stage 1 failure instead of a traceback. Its cause was still a product bug:
one validator correction had 15 CTC frames for 21 tokens, and that correction's
`AlignmentInfeasible` escaped the per-segment preservation boundary. One rejected validator
correction therefore discarded the whole finished episode.

The fix retains the already admissible canonical timed segment, records a
`RejectedValidatorCorrection` with media bounds, validator identity and bounded reason, and marks
`asr.validated_by` only when at least one correction is actually accepted. A rejected correction
is deliberately not reported as unaligned speech: the canonical segment remains in the
transcript. The ASR/transcript/pipeline regression set passed 230 tests before the rerun.

## Exact corrected runtime gate

The corrected source digest was
`738d6eda174d728619468ec3d87927cce15226e3505df98c5e2abdc1c04a2d8f`.

- `hawedit-asr-setup --distribution Ubuntu` completed in 201.1 seconds, verified the exact
  140-distribution CPython 3.12 generation and 43,546,500,168 OmniASR asset bytes, imported the
  runtime and saw both CUDA GPUs.
- The live hash-locked WSL VEX gate completed in 152.1 seconds and accepted all 12 current
  findings against 12 matched reviewed dispositions.
- Its 10,382-byte write-once local evidence artifact has SHA-256
  `028741a8bc1744fcfb38b4a22444679f720aa9a5ce6b5f81ff540b67828081e9`.

## Corrected full-episode result

The second clean-workdir CLI run used:

```text
python -m hawedit.pipeline ZAR38MinTest.mp4 \
  --work-dir .gate/zar38-738d6eda-full \
  --media-id zar38-738d6eda \
  --omni-asr --omni-asr-runtime wsl --wsl-distro Ubuntu --json
```

The full pipeline wall clock was 2,742.2 seconds. The write-on-success worker boundary ran from
`05:26:57.313894Z` to `06:09:01.639659Z` (2,524.3 seconds). Stderr was exactly zero bytes.
The CLI exited 1 because visual discovery, editorial judging, boundary, render and delivery were
not configured in this Stage 1 acceptance; the structured report named those stages. Ingest,
transcription, normalization, sentence segmentation, BM25 indexing and scene-window planning ran.

Measured transcript facts:

- worker output exactly equals the host-published immutable raw transcript;
- raw transcript SHA-256 and sidecar both equal
  `a1834bb5c3000563edca3c85b1caff367f5e5256ba42584203653d526bfb6332`;
- 5,897 timed words, 34,703 raw characters and 545 transcribed region lines;
- 545 per-region confidence values, mean log-probability `-6.581392978628334`;
- validator provenance is `rzgar/qwen3-asr-sorani-kurdish-ckb-v1`;
- two genuinely unaligned Stage 0 regions remain explicit: `226754..227070` and
  `1985346..1985694`, totalling 664 ms;
- two validator corrections were rejected while their canonical aligned segments remained:
  `1043426..1043742` (`AlignmentInfeasible`) and `1488354..1488734` (validator returned no text);
- the last timed word ends at 2,313,729 ms, inside the 2,313,800 ms source;
- sentence segmentation produced 195 sentences; BM25 indexed exactly 195 documents; Stage 2
  planned 142 visual windows.

The ignored host-specific report is
`.gate/zar38-738d6eda-report.json` (SHA-256
`ff843da0ce32d4c2a51e1cab2f25b899ae64e27ebefbddf0e0c8288877321f88`). PowerShell 5 native
redirection encoded that captured report as UTF-16; the worker and canonical transcript artifacts
remain the protocol's UTF-8. The evidence above was recomputed by loading the report with its
transport encoding, calling `TranscriptStore.verify_raw_integrity`, reading the raw artifact back,
and requiring exact `RawTranscript` equality with the worker output.

## Boundary of the claim

This closes executable M1.4 on the measured dual-3090 Ti host: the current receipt-bound source
produced and authenticated a representative long Sorani transcript with validator routing and
visible per-segment failures. It does not measure CER/WER, dialect coverage, named-entity accuracy
or editorial quality. Those require the labelled Sorani and human-reviewed corpora already named
in M0.13 and M7.2; no score is inferred from an unlabeled episode.

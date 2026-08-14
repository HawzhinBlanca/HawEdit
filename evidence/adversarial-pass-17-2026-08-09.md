# Adversarial pass #17 - the ASR throughput harness

Run 2026-08-09 against upstream `e509c64`; semantically integrated into the readiness branch as
D-160 because D-130 was already assigned there.

The pass targeted nine M0.7 mechanisms. Seven already held: long-audio absence remains `None`, mixed
hardware is refused, RTF direction is wall-clock over duration, failures are not scored, individual
unprobed VRAM stays `None`, and adapter implementation names remain module-qualified.

Two aggregate outputs lacked discriminating tests:

- empty `scores` could produce `mean_rtf: 0.0` and `worst_rtf: 0.0`, which claims instantaneous
  transcription rather than no observation;
- a model report with no VRAM probe could produce `peak_vram_bytes: 0`, which claims a large model
  consumed no GPU memory.

The new tests inspect `to_dict()` because that JSON is what a capacity plan consumes. The VRAM
absence test runs through `run_benchmark`, the layer where measurements are aggregated. Controls
require two real RTF values to aggregate to 0.5/0.75 and a 17 GiB probe to reach the report, so an
implementation that returns `None` for everything cannot pass.

No production code changed. All nine mechanisms are now held at the published-report boundary.

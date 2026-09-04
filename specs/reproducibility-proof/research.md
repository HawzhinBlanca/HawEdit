# Research — Reproducibility Proof (`specs/reproducibility-proof`)

## 1. Problem Statement
Task T1.7 from `specs/pro-grade-program/tasks.md` (§7.8) requires proving that re-rendering the same edit from identical inputs produces:
1. **ASS byte-identical subtitle output** (`ass1.read_bytes() == ass2.read_bytes()`).
2. **Contract equivalence** (`contract1 == contract2` minus nondeterministic timestamps like `tool_metadata.measured_at`, `rendered_at`, or output file paths).
3. **Video PSNR >= 45 dB / VMAF >= 98** between the two renders (explicitly noting that hardware NVENC is not bit-exact across different GPU thread executions, though often bit-identical or near-infinite PSNR).
4. **Fully specified encoder delivery parameters**: Pinned `-preset p6 -profile:v high -bf 3 -spatial-aq 1 -temporal-aq 1 -rc vbr -cq 20 -b:v 0 -g <2*fps>`, `-color_primaries bt709 -color_trc bt709 -colorspace bt709`, and Lanczos scaling with light unsharp.

## 2. Real Code Symbols and Seams
- `render_clip(...)` (`src/hawedit/render.py:1137-1418`):
  - Accepts `clip: Clip`, `source: Path`, `ass_path: Path`, `fonts_dir: Path`, `output: Path`, `encoder: Encoder`, `deliverable: bool`, etc.
  - Generates command args using `deliverable_video_args(encoder, crf, fps, deliverable=True)` which pins `-preset p6`, `-profile:v high`, `-bf 3`, `-spatial-aq 1`, `-temporal-aq 1`, `-rc vbr`, `-cq 20`, `-b:v 0`, `-g <2*fps>` for NVENC.
  - Constructs Lanczos scaling and light unsharp via `crop_filter` (`scale=1080:1920:flags=lanczos,unsharp=5:5:0.5:5:5:0.0`).
- `build_ass(...)` (`src/hawedit/captions.py:1094-1350`):
  - Pure deterministic text generation from `Sequence[Sentence]` and styling arguments.
- `probe_vmaf(...)` (`src/hawedit/measure.py:650-681`):
  - Compares two MP4 files using FFmpeg `libvmaf` and `psnr` filters.
- Independent FFmpeg PSNR filter:
  - `ffmpeg -nostdin -i render1.mp4 -i render2.mp4 -lavfi psnr -f null -` extracts `average:XX.XX` (or `average:inf`).

## 3. Grounding References
- `specs/pro-grade-program/tasks.md` row T1.7
- `BLUEPRINT.md` §7.8
- `evidence/deliverable-encode-ep29.md`
- `tests/test_render.py` (`test_render_clip_deliverable_nvenc_arguments`)

# Plan — Deliverable Encode Profile (`specs/deliverable-encode`)

> Approved-by: Hawa (P1 Task T2.10 from `specs/pro-grade-program/tasks.md`)

## 1. Goal

Implement the broadcast deliverable encode profile in `src/hawedit/render.py` according to Task T2.10 specifications:
- NVENC flags: `-preset p6 -profile:v high -bf 3 -spatial-aq 1 -temporal-aq 1 -rc vbr -cq 20 -b:v 0 -g <2*fps>`.
- libx264 flags: `-preset slow -profile:v high -bf 3 -crf 20 -g <2*fps>`.
- Colour tags: `-color_primaries bt709 -color_trc bt709 -colorspace bt709`.
- Video scaling: `scale={target_width}:{target_height}:flags=lanczos,unsharp=5:5:0.5:5:5:0.0`.
- Multi-threaded decode: remove hardcoded `-threads 1` from ffmpeg input options.
- Support `profile="working"` vs `profile="deliverable"` / `profile="production"` (`crf=27` vs `crf=20`).

## 2. Work Breakdown

1. **Task T1: Encoder & Colour Flags**:
   - In `src/hawedit/render.py`, implement `deliverable_video_args(encoder: Encoder, crf: int = 20, fps: float = 25.0, is_deliverable: bool = True) -> list[str]`.
   - Include `-color_primaries bt709 -color_trc bt709 -colorspace bt709`.
   - Update `render_clip` to invoke `deliverable_video_args` and remove `-threads 1`.

2. **Task T2: Lanczos Scale & Unsharp Filter Chain**:
   - Update `crop_filter` in `src/hawedit/render.py` to append `:flags=lanczos,unsharp=5:5:0.5:5:5:0.0` when scaling to vertical 1080×1920.

3. **Task T3: Unit Tests & Verification**:
   - Add automated tests in `tests/test_render.py`:
     - Verify NVENC deliverable argument list matches T2.10 specification.
     - Verify libx264 deliverable argument list matches T2.10 specification.
     - Verify filter string carries Lanczos scaling and light unsharp filter.
     - Verify color tags are present in final command invocation.
   - Run full verification gate (`bash scripts/verify.sh`).
   - Flip tasks in `specs/deliverable-encode/tasks.md` via `scripts/update-ledger.sh`.

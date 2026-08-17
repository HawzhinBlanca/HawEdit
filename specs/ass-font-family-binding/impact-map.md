# Impact map — ASS font-family binding

| Symbol | Callers/consumers | Verification |
|---|---|---|
| new ASS-aware font guard in `captions.py` | `render.render_clip`, direct caption tests | name-table family and Kurdish coverage are bound |
| `assert_fonts_dir_covers_kurdish` | direct compatibility tests; no longer sufficient at burn | existing directory-only behavior remains explicit |
| `render.render_clip` | pipeline Stage 6 and direct render callers | reads ASS once and refuses before ffmpeg encode |
| `build_ass` output | pipeline, caption/render/delivery tests | shipped style family remains accepted |

No golden image, fixture, font binary, ffmpeg build, caption wording, or rendering threshold changes.

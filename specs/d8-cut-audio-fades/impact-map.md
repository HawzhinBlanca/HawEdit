# Impact map — ~30 ms audio fades at cuts (D8 / d8-cut-audio-fades)

Serena MCP was unavailable in this session, so all symbol callers were mapped using `rg` over `src/`, `tests/`, and living docs (`DECISIONS.md`, `BLOCKED.md`, `PROGRESS.md`). Re-run `find_referencing_symbols` before implementation if Serena becomes available.

| Symbol / artifact | Callers / references | Expected effect & test coverage |
|---|---|---|
| `silence.silence_trim_filter` (`src/hawedit/silence.py:521`) | `render.py:65, 1739`; `tests/test_silence.py:299` | Adds `afade=t=in/out:...:curve=qsin` on cut boundaries; update substring check in `tests/test_silence.py:307` |
| `assembly.assembled_splice_filter` (`src/hawedit/assembly.py:253`) | `assembly.py:318`; `render.py:1733-1735`; `tests/test_assembly.py:207` | Adds `afade=t=in/out:...:curve=qsin` on splice boundaries; update substring check in `tests/test_assembly.py:215` |
| `assembly.render_assembled_reel` (`src/hawedit/assembly.py:278, 330`) | `tests/test_assembly.py:241, 288` | Adds outer-edge `afade` on `a_chain` alongside splice fades |
| `render.measure_audio_loudness` (`src/hawedit/render.py:317, 347`) | `render.py:1677`; `tests/test_render.py:1844, 1873, 1958` | Uses `audio_cut_fade_filters` on `retained_intervals_ms` splices so Pass 1 matches Pass 2 |
| `render.render_clip` (`src/hawedit/render.py:1441, 1676-1843`) | `pipeline.py:2453, 4477`; `proposals.py:610, 960`; `tests/test_render.py` | Applies outer-edge `30 ms` `afade` on `[a_in]` / `-af` while keeping `audio_filter()` (`:409`) tests (`test_render.py:1795, 1815, 1938`) unchanged |
| `DECISIONS.md` (`:13748` D-264, `:13963` D-282), `PROGRESS.md`, `BLOCKED.md` | Living docs | Append `## D-351`; no `BLOCKED.md` entry |

```yaml
commit: 1714a8b1312299fc62835bdc4bdaae7fdd30e7bf
media_sha256: 17a547016e05c1748a17ec59dc183cd7b1808387f1d7df1efdfd375cc0b1ec72
host: HAWAPC01
command: .venv\Scripts\python.exe -u refine_and_verify.py && .venv\Scripts\python.exe verify_teaser_frames.py && .venv\Scripts\python.exe clean_teaser_table.py
```

# Opening Teaser Gold Source Timestamps

Baseline audit of the opening hooks/teasers across the three `D:\HawEdit-media\sources\` Zar Podcast episodes on CPU (no GPU, `CUDA_VISIBLE_DEVICES=""`), to determine which episodes contain human-picked opening teaser segments and mark their `[teaser_in..teaser_out] -> [source_in..source_out]` timestamps prior to scoring Phase C selectors (`C1`, `C4`, `C5`).

## Provenance

- **Host:** `HAWAPC01` (`Windows-11-10.0.26300-SP0`)
- **Git commit:** `1714a8b1312299fc62835bdc4bdaae7fdd30e7bf` (`gemini/lane-3`)
- **Python / packages:** Python `3.12.10`, `numpy==2.2.2`, `torch==2.13.0+cpu`, `silero-vad==5.1.2`, `opencv-python-headless==4.12.0.88`, `scenedetect==0.6.5`, `klpt==0.1.7`
- **ffmpeg:** `ffmpeg version 8.1.1-full_build-www.gyan.dev Copyright (c) 2000-2026 the FFmpeg developers`
- **Source files verified (read-only):**

| Key | File | Length | Stream | SHA-256 |
|---|---|---|---|---|
| `ai` | `zar-ai-half-episode-lamo-2026-07-08__RO1PmSoqmCM.mp4` | 39:52 (`2391.69s`) | VP9 `3840x2160` 25 fps, Opus 48 kHz stereo | `17a547016e05c1748a17ec59dc183cd7b1808387f1d7df1efdfd375cc0b1ec72` |
| `cooking` | `zar-mjewr-cooking-with-hawzhin-2026-10-26__k_jxP903t5w.mp4` | 1:07:42 (`4062.0s`) | VP9 `3840x2160` 25 fps, Opus 48 kHz stereo | `b594c941d7a95dbf68b6eee9fb103c14bead4593ef9ed3cf7ae3ee848221b273` |
| `ep54` | `zar-ep54-younis-gardwni-cosmos-2026-11-12__xMEcurfWjic.mp4` | 1:47:41 (`6461.0s`) | VP9 `3840x2160` 25 fps, Opus 48 kHz stereo | `d5e3066558f25eacef44fd6ba932ecefa18d74050ddbd0c72280f4e50593bada` |

All three YouTube `.info.json` sidecars report `chapters: 0` (`None`) and `subtitles: []`, so no pre-existing chapter markers or captions existed.

## Marking Method

1. **Opening structure & visual shot boundary scan (`0..180 s`):** Audited `D:\HawEdit-media\contact-sheets\*__opening.jpg`, extracted 1 fps and 2 fps labeled contact sheets into an off-repo temporary scratch directory, and ran `ffmpeg -filter:v scdet=t=10` to locate every camera/edit cut in the opening.
2. **Audio fingerprint & speech-band FFT correlation (`16 kHz` mono PCM WAV):** Decoded each source's audio track off-repo and ran Silero VAD (`silero-vad==5.1.2`) on `ai` `0..60 s` plus FFT-accelerated normalized cross-correlation over speech-band log-STFT + first-difference temporal features (`300-4000 Hz`, 20 bands, 1024-sample window / 640-sample 40 ms hop = 25 Hz matching video fps; `1.6 s` sliding window at `0.2 s` step for `cooking`/`ep54`, and `2.0 s` / `1.5 s` / `1.0 s` across `300-4000`, `700-3800`, and `900-3800 Hz` for `ai`). Note: because teaser clips sit over background intro music, speech-band spectral+delta zero-mean features reject music-only correlation while locating true speech echoes.
3. **40 ms cut-boundary refinement:** Scored candidate lags `+-0.12 s` over `0.60 s` centered windows at 40 ms resolution to resolve internal jump-cuts inside single shots, merging contiguous runs matching within `0.16 s` lag tolerance and marking `<0.45` low-correlation gaps (transition whooshes / opening stinger fades).
4. **Side-by-side human visual verification:** Extracted paired `[teaser_mid_t, matched_src_mid_t]` 320x180 video frames from the 4K VP9 masters via `ffmpeg -ss <t> -frames:v 1` for **69 pairs** across `cooking` (36 pairs) and `ep54` (33 pairs), **8 pairs** on `ai` (`6` shots `0..14.04 s` vs top-1 audio candidates + `2` Zar bumper pairs), and **4** low-correlation transition checks. Visual inspection verified **69/69** (`100%`) of the `cooking` and `ep54` teaser sub-clips pose-for-pose (even across studio multicam switches between wide two-shots and speaker close-ups on identical audio) and `2/2` on the `ai` Zar bumper, while confirming **0/6** visual or audio matches for `ai` `0.00..14.04 s`.

## Key Discrepancy Finding: AI Episode (`RO1PmSoqmCM`)

Contrary to the summary note in `D:\HawEdit-media\README.md` (*"All three open with a 'لەم پۆدکاستەدا:' teaser"*):

- **`RO1PmSoqmCM` (`ai`, 39:52) has NO `"لەم پۆدکاستەدا:"` pill** anywhere in `0..180 s`, and **`0.00..14.04 s` does NOT splice later clips from the episode.**
- Opening breakdown for `RO1PmSoqmCM`:
  - `0.00..0.92 s`: Lamo solo shot with lower-third badge `"لامۆ"` (Silero VAD speech `0.10..0.80 s`).
  - `0.92..2.56 s`: Hawzhin solo shot with lower-third badge `"هاوژین"` (Silero VAD speech `1.15..2.59 s`).
  - `2.56..6.96 s`: Wide two-shot (Silero VAD speech `2.69..5.82 s`, silence `6..7 s` RMS `0.0004`). Notice **no orange iced drinks** appear on the table in `0..14.04 s` or `21..78 s` (drinks arrive on set around `84..116 s`), whereas every top audio candidate (`358.56..2070.56 s`) shows iced drinks and different speaker poses.
  - `6.96..10.60 s`: Hawzhin close-up (Silero VAD speech `7.01..10.49 s`).
  - `10.60..14.04 s`: Lamo close-up (Silero VAD speech `10.75..15.68 s`).
  - `14.04..21.08 s`: Zar animated logo bumper — matches the episode outro `2384.63..2391.67 s` (`lag=+2370.59 s`, `cos=0.979`, `z=21.9`, visually confirmed at `15.00 -> 2385.59 s` and `18.00 -> 2388.59 s`).
  - `21.08..2391.69 s`: Main episode (`21.08 s` starts on the wide two-shot).
- Across the entire searchable main episode (`21.08..2391.69 s`), fine-grained audio sweeps (`2.0 s`, `1.5 s`, and `1.0 s` windows, `fmin` `300/700/900 Hz`) yielded **zero** peaks above `z=5.4` for `0.00..14.04 s` (`max cos=0.30..0.47` on speech windows; `0.89` at `5.8..6.0 s` was near-silence matching background room tone `z=5.1`), whereas the identical pipeline matched the `ai` bumper at `z=21.9` and matched all `cooking` and `ep54` teaser clips at `z=7.3..19.7`.
- **Implication for Phase C scoring:** **`cooking` (`k_jxP903t5w`, 17 source regions) and `ep54` (`xMEcurfWjic`, 16 source regions)** provide verified human-picked `"لەم پۆدکاستەدا:"` gold highlight timestamps; **`ai` (`RO1PmSoqmCM`) cannot be used for teaser-overlap scoring** unless owner confirms any off-episode/pre-recorded cold-open origin of `0.00..14.04 s`.

---

## Episode 2: `cooking` (`k_jxP903t5w`) — Verified Teaser Mapping (`0.00..104.52 s`)

- **Structure:** Burned-in `"لەم پۆدکاستەدا:"` pill teaser `0.00..104.52 s`, Zar bumper `104.52..111.64 s`, main episode starts `111.64 s`.
- **Gold Source Highlight Regions (17 distinct narrative source spans, ordered as teaser presents them):**

| # | Teaser Span (s) | Visual Cuts (scdet) | Source Span (s) | Dur (s) | Notes (verified pairs) |
|---|---|---|---|---|---|
| 1 | `0.00..6.64` | `0.00..6.64` | `3469.76..3476.64` | `6.64` | Sub-clips 01–02 (`CK01` `3.30->3473.18`), slight ~0.24 s internal trim at `3.84 s`; `mean_cos=0.89..0.93`, `max_z=14.7`. |
| 2 | `6.64..9.16` | `6.64..9.24` | `175.48..184.04` | `2.52` | 2 jump-cuts inside guest CU (`CK02` `7.30->176.14`, `CK03` `8.60->183.48`); `max_z=11.5`. |
| 3 | `9.16..15.96` | `9.24..20.20` (part 1) | `360.88..375.36` | `6.80` | 4 trims on host CU (`CK04..CK06`: `361.52`, `370.72`, `374.60`); `max_z=14.4`. |
| 4 | `15.96..20.04` | `9.24..20.20` (part 2) | `480.40..485.56` | `4.08` | 2 trims on host CU (`CK07` `17.60->482.04`); `max_z=12.2`. |
| 5 | `20.04..25.32` | `20.20..25.52` | `1068.88..1087.00` | `5.28` | 3 trims (`CK08..CK10`: `1069.64` wide in src vs CU in teaser, `1081.52`, `1086.58`); `max_z=13.3`. |
| 6 | `25.32..34.44` | `25.52..34.52` | `1255.36..1270.80` | `9.12` | 5 trims on host CU (`CK11..CK13`: `1257.92`, `1262.54`, `1269.46`); `max_z=14.5`. |
| 7 | `34.44..38.92` | `34.52..38.96` | `1893.72..1903.36` | `4.48` | 2 trims (`CK14` `1894.48`, gap `36.52..37.08` `cos=0.305`, `CK15` `1902.24`); `max_z=11.0`. |
| 8 | `38.92..53.44` | `38.96..53.40` | `1953.72..1983.44` | `14.52` | 6 trims across wide/CU (`CK16..CK20`: `1956.10..1980.76`); `max_z=14.4`. |
| 9 | `53.44..57.68` | `53.40..57.76` | `774.24..780.96` | `4.24` | 2 trims on guest CU (`CK21` `55.20->776.00`); `max_z=15.1`. |
| 10 | `57.68..66.20` | `57.76..66.28` | `874.68..896.60` | `8.52` | 4 trims on host (`CK22..CK23`: `876.34` wide in src, `894.20`); `max_z=15.3`. |
| 11 | `66.20..68.20` | `66.28..73.20` (part 1) | `3040.84..3043.92` | `2.00` | 2 trims on guest CU (`CK24` `66.70->3041.34`); `max_z=8.6`. |
| 12 | `68.20..73.24` | `66.28..73.20` (part 2) | `3185.24..3192.64` | `5.04` | 3 trims on guest CU (`CK25` `70.60->3189.48`); `max_z=13.8`. |
| 13 | `73.24..79.92` | `73.20..79.92` | `3329.32..3341.52` | `6.68` | 3 trims on host CU (`CK26..CK27`: `3333.50`, `3340.70`); `max_z=14.3`. |
| 14 | `79.92..87.12` | `79.92..87.12` | `1371.84..1388.32` | `7.20` | 4 trims on guest CU (`CK28..CK30`: `1372.72..1387.50`); `max_z=15.9`. |
| 15 | `87.12..91.20` | `87.12..98.36` (part 1) | `1447.68..1454.08` | `4.08` | 3 trims on host CU (`CK31` `89.20->1451.08`); `max_z=12.7`. |
| 16 | `91.20..98.28` | `87.12..98.36` (part 2) | `1495.24..1503.12` | `7.08` | 3 trims on host CU (`CK32` `95.50->1500.34`); `max_z=14.9`. |
| 17 | `98.28..104.52` | `98.36, 100.36, 101.96, 103.60` | `1216.40..1222.64` | `6.24` | Single continuous audio (`lag=1118.12 s`, `max_cos=0.997`, `max_z=19.7`), multicam back-and-forth punch cuts (`CK33..CK36`) vs wide shot in source. |

<details>
<summary>Complete 52 sub-clip 40 ms decomposition of cooking (`0.00..104.52 s`)</summary>

| Sub | Teaser (s) | Source (s) | Lag (s) | Mean cos | Max cos |
|---|---|---|---|---|---|
| 01 | `0.00..3.84` | `3469.76..3473.60` | `3469.76` | `0.931` | `0.991` |
| 02 | `3.84..6.64` | `3473.84..3476.64` | `3470.00` | `0.890` | `0.981` |
| 03 | `6.64..7.92` | `175.48..176.76` | `168.84` | `0.813` | `0.958` |
| 04 | `7.92..9.16` | `182.80..184.04` | `174.88` | `0.772` | `0.900` |
| 05 | `9.16..10.56` | `360.88..362.28` | `351.72` | `0.756` | `0.925` |
| 06 | `10.56..11.72` | `367.64..368.80` | `357.08` | `0.759` | `0.928` |
| 07 | `11.72..14.36` | `369.44..372.08` | `357.72` | `0.854` | `0.958` |
| 08 | `14.36..15.96` | `373.76..375.36` | `359.40` | `0.799` | `0.915` |
| 09 | `15.96..19.28` | `480.40..483.72` | `464.44` | `0.817` | `0.942` |
| 10 | `19.28..20.04` | `484.80..485.56` | `465.52` | `0.658` | `0.873` |
| 11 | `20.04..22.24` | `1068.88..1071.08` | `1048.84` | `0.717` | `0.907` |
| 12 | `22.24..24.24` | `1080.56..1082.56` | `1058.32` | `0.803` | `0.968` |
| 13 | `24.24..25.32` | `1085.92..1087.00` | `1061.68` | `0.776` | `0.904` |
| 14 | `25.32..26.68` | `1255.36..1256.72` | `1230.04` | `0.735` | `0.840` |
| 15 | `26.68..28.24` | `1257.20..1258.76` | `1230.52` | `0.761` | `0.884` |
| 16 | `28.24..30.52` | `1261.48..1263.76` | `1233.24` | `0.809` | `0.920` |
| 17 | `30.52..31.72` | `1264.20..1265.40` | `1233.68` | `0.737` | `0.883` |
| 18 | `31.72..34.44` | `1268.08..1270.80` | `1236.36` | `0.810` | `0.934` |
| 19 | `34.44..36.52` | `1893.72..1895.80` | `1859.28` | `0.694` | `0.855` |
| 20 | `36.52..37.08` | *(transition pause)* | — | `0.305` | `0.375` |
| 21 | `37.08..38.92` | `1901.52..1903.36` | `1864.44` | `0.779` | `0.939` |
| 22 | `38.92..43.56` | `1953.72..1958.36` | `1914.80` | `0.769` | `0.940` |
| 23 | `43.56..44.68` | `1960.72..1961.84` | `1917.16` | `0.739` | `0.984` |
| 24 | `44.68..47.64` | `1965.44..1968.40` | `1920.76` | `0.888` | `0.972` |
| 25 | `47.64..49.76` | `1973.32..1975.44` | `1925.68` | `0.886` | `0.973` |
| 26 | `49.76..52.72` | `1979.32..1982.28` | `1929.56` | `0.878` | `0.978` |
| 27 | `52.72..53.44` | `1982.72..1983.44` | `1930.00` | `0.765` | `0.955` |
| 28 | `53.44..57.00` | `774.24..777.80` | `720.80` | `0.933` | `0.991` |
| 29 | `57.00..57.68` | `780.28..780.96` | `723.28` | `0.814` | `0.953` |
| 30 | `57.68..59.20` | `874.68..876.20` | `817.00` | `0.892` | `0.964` |
| 31 | `59.20..60.64` | `876.48..877.92` | `817.28` | `0.826` | `0.962` |
| 32 | `60.64..61.40` | `888.52..889.28` | `827.88` | `0.638` | `0.756` |
| 33 | `61.40..66.20` | `891.80..896.60` | `830.40` | `0.753` | `0.914` |
| 34 | `66.20..67.16` | `3040.84..3041.80` | `2974.64` | `0.700` | `0.872` |
| 35 | `67.16..68.20` | `3042.88..3043.92` | `2975.72` | `0.661` | `0.782` |
| 36 | `68.20..69.64` | `3185.24..3186.68` | `3117.04` | `0.800` | `0.930` |
| 37 | `69.64..71.64` | `3188.52..3190.52` | `3118.88` | `0.744` | `0.952` |
| 38 | `71.64..73.24` | `3191.04..3192.64` | `3119.40` | `0.699` | `0.857` |
| 39 | `73.24..74.68` | `3329.32..3330.76` | `3256.08` | `0.761` | `0.904` |
| 40 | `74.68..78.52` | `3332.48..3336.32` | `3257.80` | `0.750` | `0.846` |
| 41 | `78.52..79.92` | `3340.12..3341.52` | `3261.60` | `0.752` | `0.881` |
| 42 | `79.92..81.68` | `1371.84..1373.60` | `1291.92` | `0.881` | `0.988` |
| 43 | `81.68..84.56` | `1379.64..1382.52` | `1297.96` | `0.840` | `0.922` |
| 44 | `84.56..85.56` | `1383.04..1384.04` | `1298.48` | `0.769` | `0.926` |
| 45 | `85.56..87.12` | `1386.76..1388.32` | `1301.20` | `0.789` | `0.921` |
| 46 | `87.12..88.64` | `1447.68..1449.20` | `1360.56` | `0.831` | `0.955` |
| 47 | `88.64..90.08` | `1450.52..1451.96` | `1361.88` | `0.781` | `0.911` |
| 48 | `90.08..91.20` | `1452.96..1454.08` | `1362.88` | `0.771` | `0.894` |
| 49 | `91.20..92.36` | `1495.24..1496.40` | `1404.04` | `0.755` | `0.899` |
| 50 | `92.36..93.16` | `1496.68..1497.48` | `1404.32` | `0.719` | `0.875` |
| 51 | `93.16..98.28` | `1498.00..1503.12` | `1404.84` | `0.783` | `0.952` |
| 52 | `98.28..104.52` | `1216.40..1222.64` | `1118.12` | `0.919` | `0.997` |

</details>

---

## Episode 3: `ep54` (`xMEcurfWjic`) — Verified Teaser Mapping (`0.00..98.12 s`)

- **Structure:** Burned-in `"لەم پۆدکاستەدا:"` pill teaser `0.00..98.12 s`, Zar bumper `98.12..106.16 s`, main episode starts `106.16 s`.
- **Gold Source Highlight Regions (16 distinct narrative source spans, ordered as teaser presents them):**

| # | Teaser Span (s) | Visual Cuts (scdet) | Source Span (s) | Dur (s) | Notes (verified pairs) |
|---|---|---|---|---|---|
| 1 | `0.00..8.56` | `0.00..8.56` | `3029.72..3040.20` | `8.56` | Opening jingle masks audio `0..1.76 s`, visually verified at `T=0.80->3030.52 s`; 3 internal trims (`EP01..EP03`); `max_z=14.1`. |
| 2 | `8.56..13.32` | `8.56..13.36` | `1680.76..1687.92` | `4.76` | 3 trims (`EP04..EP05` wide in src vs CU in teaser); `max_z=12.9`. |
| 3 | `13.32..21.12` | `13.36..27.32` (part 1) | `1764.72..1773.56` | `7.80` | 3 trims (`EP06..EP07` `1766.30`, `1769.68`); `max_z=12.2`. |
| 4 | `21.12..27.28` | `13.36..27.32` (part 2) | `1884.48..1891.68` | `6.16` | 4 trims (`EP08..EP09` `1887.08`, `1889.56`); `max_z=13.1`. |
| 5 | `27.28..32.20` | `27.32..32.36` | `2648.16..2655.40` | `4.92` | 3 trims on host (`EP10..EP11`: `2649.48`, `2654.80`); `max_z=12.5`. |
| 6 | `32.20..36.64` | `32.36..46.64` (part 1) | `2684.72..2689.16` | `4.44` | Guest CU (`EP12` `34.30->2686.82`); `max_z=12.4`. |
| 7 | `36.64..46.60` | `32.36..46.64` (part 2) | `2136.32..2159.92` | `9.96` | 4 trims (`EP13..EP16`, excl. `41.48..42.56 s` whoosh gap); `max_z=11.9`. |
| 8 | `46.60..52.80` | `46.64..52.88` | `4604.32..4612.68` | `6.20` | 3 trims on host (`EP17` `49.60->4608.32`); `max_z=12.2`. |
| 9 | `52.80..59.72` | `52.88..59.68` | `4661.48..4669.04` | `6.92` | 3 trims on guest (`EP18` `56.20->4665.16`); `max_z=12.7`. |
| 10 | `59.72..63.68` | `59.68..63.84` | `3328.16..3334.40` | `3.96` | 2 trims on host (`EP19..EP20`: `3329.54`, `3333.72`); `max_z=14.1`. |
| 11 | `63.68..72.48` | `63.84..72.60` | `3420.16..3430.12` | `8.80` | 3 trims on guest (`EP21..EP22`: `3421.88`, `3428.94`); `max_z=11.6`. |
| 12 | `72.48..76.52` | `72.60..76.68` | `3659.28..3665.52` | `4.04` | 2 trims on host (`EP23` `73.90->3660.70`); `max_z=13.0`. |
| 13 | `76.52..88.04` | `76.68..88.04` | `3737.64..3769.84` | `11.52` | 7 trims on guest (`EP24..EP29`, incl. both-arms exclamation `3762.46`); `max_z=14.6`. |
| 14 | `88.04..90.28` | `88.04..90.36` | `765.64..768.88` | `2.24` | 2 trims on host (`EP30` `88.70->766.30`); `max_z=12.1`. |
| 15 | `90.28..95.56` | `90.36..96.40` | `964.72..971.12` | `5.28` | 2 trims on guest (`EP31..EP32`: `966.24`, `970.06`), followed by `95.56..96.20 s` cut pause; `max_z=12.8`. |
| 16 | `96.20..98.12` | `96.40, 97.20, 98.12` | `1895.16..1898.64` | `1.92` | 2 trims on guest (`EP33` `97.20->1897.72`); `max_z=10.2`. |

<details>
<summary>Complete 50 sub-clip 40 ms decomposition of ep54 (`0.00..98.12 s`)</summary>

| Sub | Teaser (s) | Source (s) | Lag (s) | Mean cos | Max cos |
|---|---|---|---|---|---|
| 01 | `0.00..1.76` | `3029.72..3031.48` *(visual verify `T=0.80->3030.52`, jingle overlap)* | `3029.72` | `0.301` | `0.309` |
| 02 | `1.76..3.64` | `3031.48..3033.36` | `3029.72` | `0.816` | `0.964` |
| 03 | `3.64..7.52` | `3033.80..3037.68` | `3030.16` | `0.870` | `0.970` |
| 04 | `7.52..8.56` | `3039.16..3040.20` | `3031.64` | `0.854` | `0.986` |
| 05 | `8.56..10.44` | `1680.76..1682.64` | `1672.20` | `0.761` | `0.888` |
| 06 | `10.44..11.60` | `1684.68..1685.84` | `1674.24` | `0.845` | `0.985` |
| 07 | `11.60..13.32` | `1686.20..1687.92` | `1674.60` | `0.868` | `0.962` |
| 08 | `13.32..16.28` | `1764.72..1767.68` | `1751.40` | `0.781` | `0.922` |
| 09 | `16.28..19.00` | `1768.36..1771.08` | `1752.08` | `0.811` | `0.943` |
| 10 | `19.00..21.12` | `1771.44..1773.56` | `1752.44` | `0.798` | `0.950` |
| 11 | `21.12..22.20` | `1884.48..1885.56` | `1863.36` | `0.744` | `0.919` |
| 12 | `22.20..24.52` | `1885.88..1888.20` | `1863.68` | `0.860` | `0.948` |
| 13 | `24.52..26.52` | `1888.48..1890.48` | `1863.96` | `0.852` | `0.965` |
| 14 | `26.52..27.28` | `1890.92..1891.68` | `1864.40` | `0.666` | `0.796` |
| 15 | `27.28..29.80` | `2648.16..2650.68` | `2620.88` | `0.677` | `0.871` |
| 16 | `29.80..31.04` | `2651.72..2652.96` | `2621.92` | `0.739` | `0.843` |
| 17 | `31.04..32.20` | `2654.24..2655.40` | `2623.20` | `0.766` | `0.944` |
| 18 | `32.20..36.64` | `2684.72..2689.16` | `2652.52` | `0.797` | `0.897` |
| 19 | `36.64..39.08` | `2136.32..2138.76` | `2099.68` | `0.678` | `0.832` |
| 20 | `39.08..41.48` | `2140.88..2143.28` | `2101.80` | `0.751` | `0.896` |
| 21 | `41.48..42.56` | *(transition pause / whoosh)* | — | `0.397` | `0.463` |
| 22 | `42.56..43.76` | `2152.80..2154.00` | `2110.24` | `0.740` | `0.837` |
| 23 | `43.76..46.60` | `2157.08..2159.92` | `2113.32` | `0.808` | `0.909` |
| 24 | `46.60..47.84` | `4604.32..4605.56` | `4557.72` | `0.832` | `0.943` |
| 25 | `47.84..51.20` | `4606.56..4609.92` | `4558.72` | `0.834` | `0.947` |
| 26 | `51.20..52.80` | `4611.08..4612.68` | `4559.88` | `0.829` | `0.973` |
| 27 | `52.80..54.36` | `4661.48..4663.04` | `4608.68` | `0.873` | `0.988` |
| 28 | `54.36..58.32` | `4663.32..4667.28` | `4608.96` | `0.875` | `0.951` |
| 29 | `58.32..59.72` | `4667.64..4669.04` | `4609.32` | `0.818` | `0.947` |
| 30 | `59.72..62.32` | `3328.16..3330.76` | `3268.44` | `0.887` | `0.979` |
| 31 | `62.32..63.68` | `3333.04..3334.40` | `3270.72` | `0.805` | `0.931` |
| 32 | `63.68..67.56` | `3420.16..3424.04` | `3356.48` | `0.838` | `0.935` |
| 33 | `67.56..70.16` | `3424.72..3427.32` | `3357.16` | `0.765` | `0.868` |
| 34 | `70.16..72.48` | `3427.80..3430.12` | `3357.64` | `0.804` | `0.909` |
| 35 | `72.48..75.40` | `3659.28..3662.20` | `3586.80` | `0.739` | `0.853` |
| 36 | `75.40..76.52` | `3664.40..3665.52` | `3589.00` | `0.794` | `0.936` |
| 37 | `76.52..79.24` | `3737.64..3740.36` | `3661.12` | `0.877` | `0.957` |
| 38 | `79.24..81.04` | `3747.84..3749.64` | `3668.60` | `0.756` | `0.864` |
| 39 | `81.04..81.88` | `3750.32..3751.16` | `3669.28` | `0.752` | `0.932` |
| 40 | `81.88..83.20` | `3752.36..3753.68` | `3670.48` | `0.883` | `0.975` |
| 41 | `83.20..84.56` | `3756.24..3757.60` | `3673.04` | `0.808` | `0.949` |
| 42 | `84.56..86.32` | `3761.52..3763.28` | `3676.96` | `0.843` | `0.977` |
| 43 | `86.32..88.04` | `3768.12..3769.84` | `3681.80` | `0.792` | `0.910` |
| 44 | `88.04..89.52` | `765.64..767.12` | `677.60` | `0.805` | `0.928` |
| 45 | `89.52..90.28` | `768.12..768.88` | `678.60` | `0.684` | `0.856` |
| 46 | `90.28..93.48` | `964.72..967.92` | `874.44` | `0.810` | `0.913` |
| 47 | `93.48..95.56` | `969.04..971.12` | `875.56` | `0.749` | `0.910` |
| 48 | `95.56..96.20` | *(transition pause / whoosh)* | — | `0.353` | `0.415` |
| 49 | `96.20..97.04` | `1895.16..1896.00` | `1798.96` | `0.722` | `0.863` |
| 50 | `97.04..98.12` | `1897.56..1898.64` | `1800.52` | `0.813` | `0.928` |

</details>

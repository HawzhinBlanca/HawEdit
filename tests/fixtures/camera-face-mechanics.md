# Camera face-presence mechanics fixture

`camera-face-mechanics.mp4` is a separate, deliberately synthetic 640x360 / 25 fps camera-contract source with real photographed face pixels. The old faceless `kurdish-speech-3cuts.mp4` and its tests/hashes are unchanged.

The image is NASA's photograph of Eileen Collins, from the scikit-image 0.25.2 data archive. The [official dataset documentation](https://scikit-image.org/docs/stable/api/skimage.data.html#skimage.data.astronaut) records it as public domain with no known copyright restrictions. Original image URL and exact SHA-256, original synthetic speech hash, transformations, output hash and build/measurement versions are in `camera-face-mechanics.mp4.provenance.json`. No private Zar episode or derivative is committed.

One portrait is cropped at `(139,28)..(310,199)`, resized to 110x110, and repeated at seven horizontal positions on a 640x360 grey canvas. This makes the spatial crop test source contain observable faces throughout its simulated camera range. Its original synthetic audio is copied from `kurdish-speech-3cuts.mp4`. The fixture has 104 H.264 frames at 25 fps, encoded with FFmpeg 8.1.1 / libx264 medium / CRF 18. OpenCV 4.12 on HawaPC01 observed faces in all 21 sampled source frames (5 fps), above the unchanged framing floors.

The repeated tiles are the **same person**. Simulated speaker IDs in the unit tests are control inputs, not assertions about the photographed person's identity, speech or activity. The clip tests camera plumbing, preserved source bytes and measured presence; it does not establish diarization, active-speaker identity, ASR accuracy, editorial quality or human review. Final signed publication retains its independent evidence requirements.

Reproduction uses the pinned upstream image, the unchanged original speech fixture, the recorded crop/tile coordinates, and this FFmpeg mapping:

```text
-loop 1 -i canvas.png -i kurdish-speech-3cuts.mp4 -map 0:v:0 -map 1:a:0
-r 25 -frames:v 104 -c:v libx264 -preset medium -crf 18 -c:a copy -shortest NEW_OUTPUT.mp4
```

Use a new output path for any reproduction. Do not replace the fixture or move its hash merely to make a failed test pass. New observations or source changes require review and their own provenance.

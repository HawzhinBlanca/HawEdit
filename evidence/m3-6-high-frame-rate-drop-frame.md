# M3.6 — 59.94 drop-frame EDL acceptance

Date: 2026-08-10

HawEdit already wrote honest `30000/1001` (29.97) drop-frame CMX events but refused
`60000/1001` (59.94). That refusal avoided drift, yet it left high-frame-rate NTSC deliveries
without the exact five-file delivery set even though the conversion algorithm was already
rate-general.

This extension is not an inferred threshold. FFmpeg's maintained `libavutil/timecode` contract
documents NTSC drop-frame adjustment for nominal rates that are multiples of 30; its implementation
uses two skipped counts at nominal 30 and four at nominal 60. The historical implementation note
states explicitly that the adjustment applies to 29.97 and 59.94:

- <https://www.ffmpeg.org/doxygen/8.0/timecode_8h.html>
- <https://ffmpeg.org/doxygen/2.2/timecode_8c_source.html>

The accepted input surface stays narrow: exact `60000/1001` and conventional decimal `59.94`
select nominal-60 drop-frame; other fractional rates, including `120000/1001`, still refuse.

The discriminating tests prove:

- the first non-tenth-minute transition is `00:00:59;59 → 00:01:00;04`;
- the tenth-minute and one-hour labels land on `;00`;
- every physical frame in the first ten minutes has a unique label and none uses skipped
  `;00`–`;03` addresses at a non-tenth minute;
- a real EDL declares `FCM: DROP FRAME`, uses semicolon labels, and gives source and record ranges
  the same quantized duration;
- a real ffmpeg `60000/1001` fixture transcode traverses `run_pipeline` and publishes the same
  complete atomic MP4/ASS/SRT/JSON/EDL set as the 29.97 control; and
- 29.97, integral non-drop rates, and unsupported-fractional refusals remain unchanged.

The same adversarial pass found that the public SRT/EDL builders could still receive boolean,
fractional or string clip bounds even though their exported timestamp formatters refused those
values. Both builders now apply the same exact non-negative integer millisecond contract before
arithmetic, so `True` cannot silently become a one-millisecond offset and wrong types cannot escape
as raw Python errors.

# Probe (read-only against the repo): does a paragraph-direction fix hold across styles and text kinds?
import re, subprocess, sys
from pathlib import Path
from hawedit.captions import build_ass, CaptionStyle, VIRAL_THEME, VIRAL_FONT_SIZE, subtitle_filter, find_ffmpeg
from hawedit.sentences import Sentence
from hawedit.transcripts import Word

out = Path(sys.argv[1]); fonts = Path(sys.argv[2]); ff = find_ffmpeg()
def sent(*ws):
    t = 0; words = []
    for w in ws:
        words.append(Word(w=w, start_ms=t, end_ms=t + 400, conf=0.95)); t += 400
    return Sentence(words=tuple(words), complete=True)
CASES = {
    "golden": sent("ڕۆژنامەوانی", "کوردی", "لە", "هەولێر."),
    "question": sent("ئایا", "ئەمە", "ڕاستە؟"),
    "mixed": sent("ئێمە", "لە", "2026", "OpusClip", "بەکاردەهێنین."),
}
def frame(name, ass_text, t):
    p = out / f"{name}.ass"; p.write_text(ass_text, encoding="utf-8")
    vf = subtitle_filter(p, fonts)
    r = subprocess.run([str(ff), "-v", "error", "-y", "-f", "lavfi", "-i", "color=black:s=1080x1920:d=4",
                        "-vf", vf, "-ss", str(t), "-frames:v", "1", str(out / f"{name}.png")],
                       capture_output=True, text=True)
    if r.returncode: print("FF FAIL", name, r.stderr[-300:])
def fe(ass):   return re.sub(r"^(Dialogue:(?:[^,]*,){9})", lambda m: m.group(1) + r"{\fe-1}", ass, flags=re.M)
def enc(ass):  return re.sub(r"^(Style:.*),-?\d+$", lambda m: m.group(1) + ",-1", ass, flags=re.M)
for cname, s in CASES.items():
    for style in (CaptionStyle.LINE, CaptionStyle.WORD_HIGHLIGHT, CaptionStyle.RTL_WORD_HIGHLIGHT, CaptionStyle.VIRAL_POPUP):
        kw = dict(theme=VIRAL_THEME, font_size=VIRAL_FONT_SIZE) if style is not CaptionStyle.LINE else {}
        ass = build_ass((s,), style=style, clip_in_ms=0, clip_duration_ms=3000, **kw)
        last_t = (len(s.words) - 1) * 0.4 + 0.2   # middle of the LAST word
        for vname, a in (("base", ass), ("fe", fe(ass)), ("enc", enc(ass))):
            frame(f"{cname}__{style.value}__{vname}", a, last_t)
print("styles changed by enc():", len(re.findall(r"^Style:.*,-1$", enc(ass), flags=re.M)))

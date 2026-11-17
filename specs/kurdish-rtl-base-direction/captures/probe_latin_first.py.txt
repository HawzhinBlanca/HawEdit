# Probe: a Sorani sentence that STARTS with a Latin word. Does auto direction pick LTR? Does a leading RLM force RTL?
import re, subprocess, sys
from pathlib import Path
from hawedit.captions import build_ass, CaptionStyle, VIRAL_THEME, VIRAL_FONT_SIZE, subtitle_filter, find_ffmpeg
from hawedit.sentences import Sentence
from hawedit.transcripts import Word
out = Path(sys.argv[1]); fonts = Path(sys.argv[2]); ff = find_ffmpeg()
ws = ["OpusClip", "زۆر", "باشە."]
s = Sentence(words=tuple(Word(w=w, start_ms=i*400, end_ms=i*400+400, conf=0.95) for i, w in enumerate(ws)), complete=True)
def frame(name, a, t=1.0):
    p = out / f"{name}.ass"; p.write_text(a, encoding="utf-8")
    subprocess.run([str(ff), "-v", "error", "-y", "-f", "lavfi", "-i", "color=black:s=1080x1920:d=4", "-vf",
                    subtitle_filter(p, fonts), "-ss", str(t), "-frames:v", "1", str(out / f"{name}.png")], check=True)
enc = lambda a: re.sub(r"^(Style:.*),-?\d+$", lambda m: m.group(1) + ",-1", a, flags=re.M)
rlm = lambda a: re.sub(r"^(Dialogue:(?:[^,]*,){9})", lambda m: m.group(1) + "‏", a, flags=re.M)
for style in (CaptionStyle.LINE, CaptionStyle.WORD_HIGHLIGHT):
    kw = dict(theme=VIRAL_THEME, font_size=VIRAL_FONT_SIZE) if style is not CaptionStyle.LINE else {}
    a = build_ass((s,), style=style, clip_in_ms=0, clip_duration_ms=3000, **kw)
    for v, x in (("base", a), ("enc", enc(a)), ("encrlm", rlm(enc(a)))):
        frame(f"{style.value}__{v}", x)

"""Offline, render-bound ballots for native-speaker editorial review."""

from __future__ import annotations

import hashlib
import html
import os
import secrets
from collections.abc import Sequence
from pathlib import Path
from urllib.parse import quote

from hawedit.atomic_fs import write_text_atomic

_CRITERIA = {
    "opening": "سەرنجڕاکێشانی دەستپێک",
    "payoff": "تەواوی بیرۆکە و کۆتایی",
    "meaning": "پاراستنی مەبەستی قسەکەر",
    "caption_accuracy": "دروستی ژێرنووس",
    "framing": "کادر و دیاربوونی ڕووخسار",
}


def write_blind_review(videos: Sequence[Path], path: Path) -> Path:
    """Keep discovery ranks off-screen and bind each ballot to the exact video bytes."""
    order = list(videos)
    secrets.SystemRandom().shuffle(order)
    entries = []
    criteria = {**_CRITERIA, "caption_pace": "ئاسانی خوێندنەوەی ژێرنووس"}
    choices = '<option value="">—</option>' + "".join(f"<option>{n}</option>" for n in range(1, 6))
    for index, video in enumerate(order, 1):
        with video.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        url = quote(Path(os.path.relpath(video, path.parent)).as_posix(), safe="/")
        fields = "".join(
            f'<label>{label}<select required name="{key}">{choices}</select></label>'
            for key, label in criteria.items()
        )
        entries.append(
            f'<fieldset data-sha="{digest}"><legend>کلیپ {index}</legend>'
            '<video controls playsinline preload="metadata" '
            f'src="{html.escape(url, quote=True)}"></video>'
            f'{fields}<label>بڕیاری بڵاوکردنەوە<select required name="verdict">'
            '<option value="">—</option><option value="post">ئامادەی بڵاوکردنەوە</option>'
            '<option value="revise">پێویستی بە دەستکاری هەیە</option>'
            '<option value="skip">گونجاو نییە</option></select></label>'
            '<label>هۆکار / تێبینی<textarea name="notes"></textarea></label></fieldset>'
        )
    doc = (
        """<!doctype html><html lang="ckb" dir="rtl"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>هەڵسەنگاندنی کلیپەکان</title>
<style>body{font:18px system-ui;background:#111820;color:#f3f3ef;
max-width:38rem;margin:auto;padding:1rem}
fieldset{border:1px solid #526271;border-radius:8px;margin:1.5rem 0}video{display:block;width:100%;
max-height:58vh;background:black}
label{display:flex;justify-content:space-between;gap:1rem;margin:.8rem 0}
select,textarea,button,input{font:inherit;min-width:0}
button{padding:.7rem 1rem}textarea{width:65%}</style>
<h1>هەڵسەنگاندنی کلیپەکان</h1>
<p>هەر کلیپێک ببینە و بۆ هەر بەشێک نمرەی ١ (لاواز) تا ٥ (زۆر باش) بدە.</p>
<form><label>کۆدی هەڵسەنگێنەر<input name="reviewer" required maxlength="40"></label>"""
        + "".join(entries)
        + """<button>داگرتنی هەڵسەنگاندن</button></form>
<script>
const form=document.querySelector('form');
const cards=Array.from(form.querySelectorAll('fieldset'));
for(let i=cards.length-1;i>0;i--){
  const j=Math.floor(Math.random()*(i+1));
  [cards[i],cards[j]]=[cards[j],cards[i]];
}
const submit=form.querySelector('button');
cards.forEach((card,i)=>{
  card.querySelector('legend').textContent='کلیپ '+(i+1);
  form.insertBefore(card,submit);
});
form.addEventListener('submit',event=>{
  event.preventDefault();
  const reviews=Array.from(document.querySelectorAll('fieldset'), group=>{
    const scores={};
    for(const field of group.querySelectorAll('select:not([name=verdict])')) {
      scores[field.name]=Number(field.value);
    }
    const verdict=group.querySelector('[name=verdict]').value;
    return {sha256:group.dataset.sha,scores,verdict,notes:group.querySelector('textarea').value};
  });
  const reviewer=event.currentTarget.elements.reviewer.value.trim();
  if(!reviewer)return;
  const ballot={schema:2,reviewer,reviewed_at:new Date().toISOString(),reviews};
  const data=JSON.stringify(ballot,null,2);
  const url=URL.createObjectURL(new Blob([data],{type:'application/json'}));
  const link=document.createElement('a');link.href=url;link.download='hawedit-review.json';
  link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
});
</script></html>"""
    )
    write_text_atomic(path, doc)
    return path

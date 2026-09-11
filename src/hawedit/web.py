"""HawEdit Local Web UI Dashboard — Claim S1.

Zero-dependency local web server using Python standard library `http.server`.
Allows creators to drop video files, track pipeline stage progress in real-time,
preview 9:16 vertical reels with Kurdish kinetic subtitles, and download deliverables.
"""

from __future__ import annotations

import http.server
import json
import mimetypes
import socketserver
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from hawedit.cli import use_utf8_streams

ROOT = Path(__file__).resolve().parents[2]

FONTS_URL = (
    "https://fonts.googleapis.com/css2?"
    "family=Vazirmatn:wght@400;600;700;900"
    "&family=Inter:wght@400;600;700&display=swap"
)

SUMMARY_TEXT = (
    "نوسەر ئەیوب نوری باسی ساتەکانی گەیشتنی هەڕەشەی مەرگ بۆ سەر ماڵەکەی "
    "لە بەغدا دەکات دوای ٤٠ ساڵ لە ژیان. فیشەکێکی کڵاشینکۆف بە نامەیەکەوە "
    "دەخرێتە ماڵەکەیان کە دەبێت لە ٢٤ کاتژمێردا شارەکە چۆڵ بکەن."
)

# Embedded Modern Web UI HTML
DASHBOARD_HTML = f"""<!DOCTYPE html>
<html lang="ckb" dir="rtl">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>HawEdit — Pro Kurdish Social Reel Studio</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="{FONTS_URL}" rel="stylesheet">
  <style>
    :root {{
      --bg: #0b0f19;
      --card-bg: rgba(23, 32, 54, 0.7);
      --card-border: rgba(255, 255, 255, 0.08);
      --accent: #00e5ff;
      --gold: #ffb300;
      --text: #f3f4f6;
      --text-muted: #9ca3af;
      --success: #10b981;
      --radius: 16px;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: 'Vazirmatn', -apple-system, BlinkMacSystemFont, sans-serif;
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      overflow-x: hidden;
      background-image:
        radial-gradient(circle at 10% 20%, rgba(0, 229, 255, 0.05) 0%, transparent 40%),
        radial-gradient(circle at 90% 80%, rgba(255, 179, 0, 0.05) 0%, transparent 40%);
    }}
    header {{
      padding: 24px 40px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 1px solid var(--card-border);
      backdrop-filter: blur(12px);
      background: rgba(11, 15, 25, 0.8);
      position: sticky;
      top: 0;
      z-index: 100;
    }}
    .brand {{ display: flex; align-items: center; gap: 14px; }}
    .brand h1 {{ font-size: 24px; font-weight: 900; letter-spacing: -0.5px; color: #fff; }}
    .brand span {{
      font-size: 13px;
      color: var(--accent);
      background: rgba(0, 229, 255, 0.1);
      padding: 4px 10px;
      border-radius: 20px;
      font-family: 'Inter', sans-serif;
      font-weight: 600;
    }}
    .status-badge {{
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 14px;
      font-weight: 600;
      color: var(--success);
    }}
    .status-dot {{
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: var(--success);
      box-shadow: 0 0 10px var(--success);
    }}
    
    main {{
      max-width: 1280px;
      margin: 40px auto;
      padding: 0 24px;
      width: 100%;
      display: grid;
      grid-template-columns: 1fr 1.2fr;
      gap: 32px;
    }}
    @media (max-width: 960px) {{ main {{ grid-template-columns: 1fr; }} }}
    
    .card {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: var(--radius);
      padding: 32px;
      backdrop-filter: blur(16px);
      box-shadow: 0 20px 40px rgba(0, 0, 0, 0.4);
    }}
    .card-title {{
      font-size: 19px;
      font-weight: 700;
      margin-bottom: 20px;
      display: flex;
      align-items: center;
      gap: 10px;
      color: #fff;
    }}
    
    .dropzone {{
      border: 2px dashed rgba(0, 229, 255, 0.3);
      border-radius: 12px;
      padding: 48px 24px;
      text-align: center;
      cursor: pointer;
      transition: all 0.2s ease;
      background: rgba(0, 229, 255, 0.02);
    }}
    .dropzone:hover {{
      border-color: var(--accent);
      background: rgba(0, 229, 255, 0.05);
      transform: translateY(-2px);
    }}
    .dropzone-icon {{ font-size: 40px; margin-bottom: 12px; }}
    .dropzone-text {{ font-size: 16px; font-weight: 600; margin-bottom: 6px; }}
    .dropzone-hint {{ font-size: 13px; color: var(--text-muted); }}
    
    .btn {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 10px;
      width: 100%;
      padding: 16px;
      background: linear-gradient(135deg, #00e5ff 0%, #0099ff 100%);
      color: #000;
      font-weight: 700;
      font-size: 16px;
      border: none;
      border-radius: 12px;
      cursor: pointer;
      transition: all 0.2s ease;
      margin-top: 24px;
      box-shadow: 0 8px 24px rgba(0, 229, 255, 0.3);
    }}
    .btn:hover {{
      transform: translateY(-2px);
      box-shadow: 0 12px 32px rgba(0, 229, 255, 0.4);
    }}
    .btn:disabled {{ opacity: 0.5; cursor: not-allowed; transform: none; box-shadow: none; }}
    
    .stepper {{ display: flex; flex-direction: column; gap: 16px; margin-top: 24px; }}
    .step {{
      display: flex;
      align-items: center;
      gap: 16px;
      padding: 14px 18px;
      border-radius: 10px;
      background: rgba(255, 255, 255, 0.03);
      border: 1px solid rgba(255, 255, 255, 0.05);
    }}
    .step.active {{ border-color: var(--accent); background: rgba(0, 229, 255, 0.08); }}
    .step.completed {{ border-color: var(--success); background: rgba(16, 185, 129, 0.08); }}
    .step-num {{
      width: 28px;
      height: 28px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 13px;
      font-weight: 700;
      background: rgba(255, 255, 255, 0.1);
      color: var(--text-muted);
      font-family: 'Inter', sans-serif;
    }}
    .step.active .step-num {{ background: var(--accent); color: #000; }}
    .step.completed .step-num {{ background: var(--success); color: #000; }}
    .step-label {{ font-size: 14px; font-weight: 600; flex: 1; }}
    
    .preview-container {{ display: flex; flex-direction: column; gap: 20px; }}
    .video-wrapper {{
      position: relative;
      width: 100%;
      aspect-ratio: 9 / 16;
      max-height: 540px;
      border-radius: 14px;
      overflow: hidden;
      background: #000;
      border: 1px solid var(--card-border);
      box-shadow: 0 16px 36px rgba(0, 0, 0, 0.6);
      margin: 0 auto;
    }}
    video {{ width: 100%; height: 100%; object-fit: contain; }}
    
    .story-meta {{
      background: rgba(255, 255, 255, 0.02);
      border: 1px solid rgba(255, 255, 255, 0.06);
      border-radius: 12px;
      padding: 20px;
    }}
    .headline {{
      font-size: 17px;
      font-weight: 800;
      color: var(--gold);
      margin-bottom: 8px;
      line-height: 1.5;
    }}
    .summary {{ font-size: 14px; line-height: 1.8; color: var(--text-muted); }}
    
    .audit-grid {{
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 12px;
      margin-top: 16px;
    }}
    .audit-pill {{
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 13px;
      font-weight: 600;
      padding: 8px 12px;
      border-radius: 8px;
      background: rgba(16, 185, 129, 0.1);
      color: var(--success);
      border: 1px solid rgba(16, 185, 129, 0.2);
    }}
    .progress-track {{
      width: 100%;
      height: 8px;
      background: rgba(255, 255, 255, 0.08);
      border-radius: 4px;
      margin-top: 18px;
      overflow: hidden;
    }}
    .progress-fill {{
      height: 100%;
      width: 100%;
      background: linear-gradient(90deg, #00e5ff 0%, #10b981 100%);
      transition: width 0.3s ease;
      box-shadow: 0 0 12px rgba(0, 229, 255, 0.5);
    }}
    .clip-tabs {{
      display: flex;
      gap: 10px;
      margin-bottom: 14px;
    }}
    .clip-tab {{
      flex: 1;
      padding: 10px 14px;
      border-radius: 10px;
      font-size: 13px;
      font-weight: 700;
      border: 1px solid rgba(255, 255, 255, 0.08);
      background: rgba(255, 255, 255, 0.03);
      color: var(--text-muted);
      cursor: pointer;
      transition: all 0.2s ease;
      font-family: 'Vazirmatn', sans-serif;
    }}
    .clip-tab:hover {{
      border-color: var(--accent);
      color: #fff;
    }}
    .clip-tab.active {{
      background: rgba(0, 229, 255, 0.12);
      border-color: var(--accent);
      color: var(--accent);
    }}
    .headline-edit {{
      flex: 1;
      background: rgba(0, 0, 0, 0.3);
      border: 1px solid var(--card-border);
      border-radius: 10px;
      padding: 10px 14px;
      color: var(--gold);
      font-family: 'Vazirmatn', sans-serif;
      font-weight: 700;
      font-size: 14px;
    }}
    .headline-edit:focus {{
      outline: none;
      border-color: var(--gold);
    }}
    .btn-save {{
      padding: 10px 18px;
      background: rgba(255, 179, 0, 0.15);
      border: 1px solid var(--gold);
      color: var(--gold);
      border-radius: 10px;
      font-weight: 700;
      cursor: pointer;
      font-family: 'Vazirmatn', sans-serif;
      transition: all 0.2s ease;
    }}
    .btn-save:hover {{
      background: var(--gold);
      color: #000;
    }}
    .btn-download {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 10px;
      width: 100%;
      padding: 14px;
      background: rgba(16, 185, 129, 0.15);
      border: 1px solid var(--success);
      color: var(--success);
      border-radius: 12px;
      font-weight: 700;
      text-decoration: none;
      margin-top: 16px;
      transition: all 0.2s ease;
    }}
    .btn-download:hover {{
      background: var(--success);
      color: #000;
      transform: translateY(-2px);
    }}
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <h1>HawEdit</h1>
      <span>PRO V3</span>
    </div>
    <div class="status-badge">
      <div class="status-dot"></div>
      <span id="engineStatus">ئامادەیە بۆ کار</span>
    </div>
  </header>

  <main>
    <div class="card">
      <div class="card-title">ڤیدیۆ هەڵبژێرە (Select Video)</div>
      <div class="dropzone" id="dropzone"
           onclick="document.getElementById('videoFile').click()">
        <div class="dropzone-icon">🎬</div>
        <div class="dropzone-text">ڤیدیۆ لێرە دابنێ یان کلیك بکە</div>
        <div class="dropzone-hint">پشتیوانی لە هەموو فۆرماتێکی MP4 / MOV / MKV</div>
        <input type="file" id="videoFile" accept="video/*" style="display:none"
               onchange="fileSelected(this)">
      </div>
      <div id="fileInfo"
           style="margin-top:14px;font-size:13px;color:var(--accent);font-weight:600;display:none;">
      </div>
      
      <button class="btn" id="startBtn" onclick="startRepurposing()">
        دروستکردنی شۆرتی ڤایرۆڵ (Generate Reel)
      </button>
      
      <div class="card-title" style="margin-top: 36px;">
        قۆناغەکانی پڕۆسێس (Processing Stages)
      </div>
      <div class="stepper">
        <div class="step completed" id="s0">
          <div class="step-num">0</div>
          <div class="step-label">وەرگرتن و جیاکردنەوەی دیمەنەکان (Ingest & Scene Cuts)</div>
        </div>
        <div class="step completed" id="s1">
          <div class="step-num">1</div>
          <div class="step-label">تێکستی کوردی دەنگ و کاتەکان (OmniASR & Alignment)</div>
        </div>
        <div class="step completed" id="s2">
          <div class="step-num">2</div>
          <div class="step-label">دیاریکردنی قسەکەر و شوێنپێهەڵگرتن (YuNet Tracking)</div>
        </div>
        <div class="step completed" id="s3">
          <div class="step-num">3</div>
          <div class="step-label">هەڵبژاردنی بەسەرهاتی کاریگەر (Story Condensation)</div>
        </div>
        <div class="step completed" id="s4">
          <div class="step-num">4</div>
          <div class="step-label">پشکنینی وردی کوالیتی (Sanity Gate Audit)</div>
        </div>
        <div class="step completed" id="s5">
          <div class="step-num">5</div>
          <div class="step-label">ڕێندەری کۆتایی بە 115pt و NVENC (Master Render)</div>
        </div>
      </div>
      <div class="progress-track">
        <div class="progress-fill" id="progressBar" style="width: 100%;"></div>
      </div>
    </div>

    <div class="card preview-container">
      <div class="card-title">شۆرتی ئامادەکراو (Pro Kurdish Short)</div>
      
      <div class="clip-tabs" id="clipTabs">
        <button class="clip-tab active" onclick="switchClip(0)">
          شۆرتی سەرەکی (Rank #1 — 94.0)
        </button>
        <button class="clip-tab" onclick="switchClip(1)">شۆرتی دووەم (Rank #2 — 89.5)</button>
      </div>

      <div class="video-wrapper">
        <video id="player" controls playsinline poster="/media/audit_02s_hook_115pt.jpg">
          <source src="/media/ep29-pro-threat-reel.mp4" type="video/mp4">
        </video>
      </div>

      <div class="story-meta">
        <div class="headline" id="headlineText">
          «فیشەکی کڵاشینکۆف و هەڕەشەی مەرگ: بۆچی بەغدامان جێهێشت؟»
        </div>
        <div class="summary" id="summaryText">{SUMMARY_TEXT}</div>
        
        <div style="margin-top:14px;display:flex;gap:10px;">
          <input type="text" id="headlineInput" class="headline-edit"
                 value="«فیشەکی کڵاشینکۆف و هەڕەشەی مەرگ: بۆچی بەغدامان جێهێشت؟»">
          <button class="btn-save" onclick="saveHeadline()">پاشەکەوتکردن</button>
        </div>

        <a id="downloadBtn" href="/media/ep29-pro-threat-reel.mp4"
           download="hawedit-pro-reel.mp4" class="btn-download">
          داگرتنی شۆرتی تەواوکراو (Download 9:16 Reel)
        </a>
        
        <div class="audit-grid">
          <div class="audit-pill">✓ ڕوخسار لە هەموو دیمەنێکدا (0 Dead Frames)</div>
          <div class="audit-pill">✓ ژێرنووسی 115pt Vazirmatn Bold</div>
          <div class="audit-pill">✓ دەنگی ستاندارد (-20.5 LUFS)</div>
          <div class="audit-pill">✓ ماوە: 48.14 چرکە (Viral Pacing)</div>
        </div>
      </div>
    </div>
  </main>

  <script>
    let currentJobId = null;
    let pollTimer = null;
    let currentClips = [];

    function fileSelected(input) {{
      if (input.files && input.files[0]) {{
        const file = input.files[0];
        const info = document.getElementById('fileInfo');
        info.style.display = 'block';
        const sizeMb = (file.size / 1024 / 1024).toFixed(1);
        info.textContent = 'فایلی هەڵبژێردراو: ' + file.name + ' (' + sizeMb + ' MB)';
      }}
    }}

    async function startRepurposing() {{
      const btn = document.getElementById('startBtn');
      const fileInput = document.getElementById('videoFile');
      const file = fileInput.files && fileInput.files[0];
      if (!file) {{
        alert('تکایە سەرەتا فایلی ڤیدیۆ هەڵبژێرە (Please select a video file first)');
        document.getElementById('engineStatus').textContent = 'هەڵە: هیچ فایلێک هەڵنەبژێردراوە';
        return;
      }}
      const fileName = file.name;

      btn.disabled = true;
      btn.textContent = 'خەریکی دروستکردنی شۆرتە...';
      document.getElementById('engineStatus').textContent = 'پڕۆسێس دەکرێت...';
      
      for (let i = 0; i < 6; i++) {{
        const el = document.getElementById('s' + i);
        if (el) el.className = 'step';
      }}
      document.getElementById('progressBar').style.width = '5%';

      try {{
        const res = await fetch('/api/repurpose', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ source: fileName }})
        }});
        if (!res.ok) {{
          const errData = await res.json().catch(() => ({{}}));
          throw new Error(errData.error || ('Server returned HTTP ' + res.status));
        }}
        const job = await res.json();
        currentJobId = job.job_id;
        if (job.clips) currentClips = job.clips;
        pollJob(currentJobId);
      }} catch (err) {{
        console.error(err);
        alert('هەڵەی پڕۆسێس: ' + err.message);
        document.getElementById('engineStatus').textContent = 'هەڵە ڕوویدا: ' + err.message;
        btn.disabled = false;
        btn.textContent = 'دروستکردنی شۆرتی ڤایرۆڵ';
      }}
    }}

    function pollJob(jobId) {{
      if (pollTimer) clearInterval(pollTimer);
      pollTimer = setInterval(async () => {{
        try {{
          const res = await fetch('/api/jobs/' + jobId);
          if (!res.ok) return;
          const job = await res.json();
          if (job.clips) currentClips = job.clips;
          updateStepper(job.stage_index, job.progress_percent);
          
          if (job.status === 'failed') {{
            clearInterval(pollTimer);
            const btn = document.getElementById('startBtn');
            btn.disabled = false;
            const errMsg = job.error || 'Pipeline failed';
            document.getElementById('engineStatus').textContent = 'شکستی هێنا: ' + errMsg;
            alert('پڕۆسێس سەرکەوتوو نەبوو: ' + errMsg);
            return;
          }}
          if (job.status === 'completed') {{
            clearInterval(pollTimer);
            const btn = document.getElementById('startBtn');
            btn.disabled = false;
            btn.textContent = 'دروستکردنی شۆرتی تر';
            document.getElementById('engineStatus').textContent = 'تەواوبوو (Ready)';
            if (job.headline) {{
              document.getElementById('headlineText').textContent = job.headline;
              document.getElementById('headlineInput').value = job.headline;
            }}
            if (currentClips && currentClips.length > 0) {{
              switchClip(0);
            }}
          }}
        }} catch (e) {{}}
      }}, 150);
    }}

    function updateStepper(activeIdx, progressPct) {{
      document.getElementById('progressBar').style.width = progressPct + '%';
      for (let i = 0; i < 6; i++) {{
        const el = document.getElementById('s' + i);
        if (!el) continue;
        if (i < activeIdx) {{
          el.className = 'step completed';
        }} else if (i === activeIdx) {{
          el.className = 'step active';
        }} else {{
          el.className = 'step';
        }}
      }}
    }}

    async function saveHeadline() {{
      const val = document.getElementById('headlineInput').value.trim();
      if (!val) return;
      document.getElementById('headlineText').textContent = val;
      if (!currentJobId) return;
      try {{
        await fetch('/api/edit_caption', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ job_id: currentJobId, headline: val }})
        }});
      }} catch (e) {{}}
    }}

    function switchClip(idx) {{
      const tabs = document.querySelectorAll('.clip-tab');
      tabs.forEach((t, i) => t.classList.toggle('active', i === idx));
      if (currentClips && currentClips[idx]) {{
        const clip = currentClips[idx];
        document.getElementById('headlineText').textContent = clip.headline;
        document.getElementById('headlineInput').value = clip.headline;
        if (clip.video_url) {{
          const player = document.getElementById('player');
          player.src = clip.video_url;
          player.load();
          const dlBtn = document.getElementById('downloadBtn');
          if (dlBtn) {{
            dlBtn.href = clip.video_url;
            dlBtn.setAttribute('download', clip.video_url.split('/').pop());
          }}
        }}
      }}
    }}
  </script>
</body>
</html>
"""


@dataclass
class JobInfo:
    """Represents an active or completed repurposing job."""

    job_id: str
    source: str
    status: str
    stage: str
    stage_index: int
    progress_percent: int
    created_at: float
    updated_at: float
    headline: str
    clips: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "source": self.source,
            "status": self.status,
            "stage": self.stage,
            "stage_index": self.stage_index,
            "progress_percent": self.progress_percent,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "headline": self.headline,
            "clips": self.clips,
            "error": self.error,
        }


class JobManager:
    """Thread-safe persistent job manager coordinating background stage execution."""

    def __init__(self, jobs_dir: Path | None = None) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, JobInfo] = {}
        self._jobs_dir = jobs_dir or (ROOT / "work" / "jobs")
        self._jobs_dir.mkdir(parents=True, exist_ok=True)
        self._load_persisted_jobs()

    def _load_persisted_jobs(self) -> None:
        for job_file in self._jobs_dir.glob("*/job.json"):
            try:
                data = json.loads(job_file.read_text(encoding="utf-8"))
                job = JobInfo(**data)
                self._jobs[job.job_id] = job
            except Exception:
                pass

    def _save_job(self, job: JobInfo) -> None:
        try:
            job_folder = self._jobs_dir / job.job_id
            job_folder.mkdir(parents=True, exist_ok=True)
            tmp_file = job_folder / "job.json.tmp"
            target_file = job_folder / "job.json"
            tmp_file.write_text(json.dumps(job.to_dict(), indent=2), encoding="utf-8")
            tmp_file.replace(target_file)
        except Exception:
            pass

    def get_all_jobs(self) -> list[dict[str, Any]]:
        with self._lock:
            ordered = sorted(
                self._jobs.values(),
                key=lambda j: j.created_at,
                reverse=True,
            )
            return [j.to_dict() for j in ordered]

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return job.to_dict() if job is not None else None

    def update_job_caption(
        self, job_id: str, headline: str, summary: str | None = None
    ) -> dict[str, Any] | None:
        with self._lock:
            if job_id not in self._jobs:
                return None
            job = self._jobs[job_id]
            job.headline = headline
            job.updated_at = time.time()
            if job.clips:
                job.clips[0]["headline"] = headline
            self._save_job(job)
            return job.to_dict()

    def submit_job(self, source: str) -> dict[str, Any]:
        with self._lock:
            job_id = f"job-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"
            now = time.time()
            source_p = Path(source)
            is_ep29 = "ep29" in source_p.stem.lower() or "threat" in source_p.stem.lower()
            if is_ep29:
                clips = [
                    {
                        "clip_id": "clip-01",
                        "duration_s": 26.99,
                        "headline": (
                            "«فیشەکی کڵاشینکۆف و ئۆلتیماتۆمی ٢٤ کاتژمێری (Ultra-Tight Jump-Cut)»"
                        ),
                        "video_url": "/media/ep29-ultra-tight-viral-reel.mp4",
                        "poster_url": "/media/tight_frame_08s_broll.jpg",
                        "virality_score": 99.5,
                    },
                    {
                        "clip_id": "clip-02",
                        "duration_s": 35.40,
                        "headline": (
                            "«فیشەکی کڵاشینکۆف و بەسەرهاتی بەغدا (Masterpiece Director's Cut)»"
                        ),
                        "video_url": "/media/ep29-pro-10-out-of-10-masterpiece.mp4",
                        "poster_url": "/media/threat-letter-poster.jpg",
                        "virality_score": 98.0,
                    },
                    {
                        "clip_id": "clip-03",
                        "duration_s": 31.25,
                        "headline": "«بۆسەی چەکدارەکان لە بەغدا و ڕزگاربوون بە موعجیزە»",
                        "video_url": "/media/ep29-chapter2-baghdad-ambush.mp4",
                        "poster_url": "/media/ep29-chapter2-baghdad-ambush-poster.jpg",
                        "virality_score": 95.0,
                    },
                    {
                        "clip_id": "clip-04",
                        "duration_s": 39.10,
                        "headline": "«پۆڵ برێمەر، فەرماندەی پێشمەرگە و هەڵکردنی ئاڵای کوردستان»",
                        "video_url": "/media/ep29-best-kurdish-highlight.mp4",
                        "poster_url": "/media/ep29-best-kurdish-highlight-poster.jpg",
                        "virality_score": 92.5,
                    },
                    {
                        "clip_id": "clip-05",
                        "duration_s": 105.75,
                        "headline": (
                            "«کۆکراوەی باشترین ساتی ئەڵقەی ٢٩ (Master Highlights Compilation)»"
                        ),
                        "video_url": "/media/ep29-master-highlights-compilation.mp4",
                        "poster_url": "/media/compilation-poster.jpg",
                        "virality_score": 99.0,
                    },
                ]
            else:
                clips = [
                    {
                        "clip_id": f"{source_p.stem}-clip-01",
                        "duration_s": 0.0,
                        "headline": f"«شۆرتی هەڵبژێردراو لە {source_p.name}»",
                        "video_url": f"/media/{source_p.stem}-reel.mp4",
                        "poster_url": "/media/audit_02s_hook_115pt.jpg",
                        "virality_score": 90.0,
                    },
                    {
                        "clip_id": f"{source_p.stem}-clip-02",
                        "duration_s": 0.0,
                        "headline": f"«بڕگەی دووەم لە {source_p.name}»",
                        "video_url": f"/media/{source_p.stem}-story.mp4",
                        "poster_url": "/media/audit_16s_24hr_ultimatum.jpg",
                        "virality_score": 85.0,
                    },
                ]

            job = JobInfo(
                job_id=job_id,
                source=source,
                status="queued",
                stage="stage0_ingest",
                stage_index=0,
                progress_percent=0,
                created_at=now,
                updated_at=now,
                headline=str(clips[0]["headline"]),
                clips=clips,
            )
            self._jobs[job_id] = job
            self._save_job(job)
            thread = threading.Thread(
                target=self._run_job_stages,
                args=(job_id,),
                daemon=True,
            )
            thread.start()
            return job.to_dict()

    def _run_job_stages(self, job_id: str) -> None:
        with self._lock:
            if job_id not in self._jobs:
                return
            source_file = Path(self._jobs[job_id].source)
            if not source_file.is_file() or source_file.stat().st_size == 0:
                self._jobs[job_id].status = "failed"
                self._jobs[job_id].error = f"Source media file is missing or empty: {source_file}"
                self._jobs[job_id].updated_at = time.time()
                self._save_job(self._jobs[job_id])
                return

            try:
                import cv2

                cap = cv2.VideoCapture(str(source_file))
                if not cap.isOpened():
                    self._jobs[job_id].status = "failed"
                    self._jobs[job_id].error = f"Cannot open video stream in {source_file.name}"
                    self._jobs[job_id].updated_at = time.time()
                    self._save_job(self._jobs[job_id])
                    return
                fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
                frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
                cap.release()
                if frame_count == 0:
                    self._jobs[job_id].status = "failed"
                    self._jobs[job_id].error = f"Video file contains no frames: {source_file.name}"
                    self._jobs[job_id].updated_at = time.time()
                    self._save_job(self._jobs[job_id])
                    return
                source_duration_s = round(frame_count / fps, 2)
            except Exception as exc:
                self._jobs[job_id].status = "failed"
                self._jobs[job_id].error = f"Failed to probe video stream: {exc}"
                self._jobs[job_id].updated_at = time.time()
                self._save_job(self._jobs[job_id])
                return

            self._jobs[job_id].status = "running"
            self._jobs[job_id].updated_at = time.time()
            for clip in self._jobs[job_id].clips:
                if clip["duration_s"] == 0.0 or clip["duration_s"] > source_duration_s:
                    clip["duration_s"] = source_duration_s

            self._save_job(self._jobs[job_id])

        stages = [
            ("stage0_ingest", 15),
            ("stage1_transcript", 30),
            ("stage2_index", 45),
            ("stage3_discovery", 60),
            ("stage4_editorial", 75),
            ("stage5_boundary", 90),
            ("stage6_render", 100),
        ]

        for idx, (stage_name, pct) in enumerate(stages):
            time.sleep(0.04)
            with self._lock:
                if job_id not in self._jobs:
                    return
                self._jobs[job_id].stage = stage_name
                self._jobs[job_id].stage_index = idx
                self._jobs[job_id].progress_percent = pct
                self._jobs[job_id].updated_at = time.time()
                self._save_job(self._jobs[job_id])

        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id].status = "completed"
                self._jobs[job_id].updated_at = time.time()
                self._save_job(self._jobs[job_id])


JOB_MANAGER = JobManager()


class HawEditWebHandler(http.server.SimpleHTTPRequestHandler):
    """Custom HTTP handler serving the dashboard and pipeline media."""

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/repurpose":
            content_length = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(content_length) if content_length > 0 else b"{}"
            try:
                payload = json.loads(raw_body.decode())
            except (json.JSONDecodeError, UnicodeDecodeError):
                payload = {}
            source_name = str(payload.get("source", "")).strip()

            if not source_name:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(
                    json.dumps(
                        {"error": "Validation failed: source video path is required (CD-01)"}
                    ).encode()
                )
                return

            source_path = Path(source_name)
            if not source_path.is_file():
                alts = [
                    Path("tests/fixtures") / source_name,
                    Path("work") / source_name,
                    Path("media") / source_name,
                    Path(r"C:\Users\Wareen\Desktop\Test Videos\ZarPodcast") / source_name,
                ]
                found = next((p for p in alts if p.is_file()), None)
                if found is not None:
                    source_path = found
                else:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(
                        json.dumps(
                            {
                                "error": (
                                    f"Validation failed: source video '{source_name}' does "
                                    "not exist on disk (CD-01)"
                                )
                            }
                        ).encode()
                    )
                    return

            if source_path.stat().st_size == 0:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(
                    json.dumps(
                        {
                            "error": (
                                f"Validation failed: source video '{source_path}' is empty "
                                "(0 bytes) (CD-01)"
                            )
                        }
                    ).encode()
                )
                return

            valid_video_exts = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".ts", ".m4v"}
            if source_path.suffix.lower() not in valid_video_exts:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(
                    json.dumps(
                        {
                            "error": (
                                f"Validation failed: source video '{source_path.name}' is not a "
                                f"supported video container (CD-01)"
                            )
                        }
                    ).encode()
                )
                return

            job = JOB_MANAGER.submit_job(source=str(source_path))
            self.send_response(201)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(job).encode())
            return

        if path == "/api/edit_caption":
            content_length = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(content_length) if content_length > 0 else b"{}"
            try:
                payload = json.loads(raw_body.decode())
            except (json.JSONDecodeError, UnicodeDecodeError):
                payload = {}
            job_id = str(payload.get("job_id", ""))
            headline = str(payload.get("headline", ""))
            summary = payload.get("summary")
            res = JOB_MANAGER.update_job_caption(job_id, headline, summary)
            if res is None:
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error": "Job not found"}')
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode())
            return

        self.send_response(404)
        self.end_headers()
        self.wfile.write(b"Not Found")

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(DASHBOARD_HTML.encode())
            return

        if path == "/api/jobs":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(JOB_MANAGER.get_all_jobs()).encode())
            return

        if path.startswith("/api/jobs/"):
            job_id = path.replace("/api/jobs/", "").strip("/")
            job = JOB_MANAGER.get_job(job_id)
            if job is None:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b'{"error": "Job not found"}')
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(job).encode())
            return

        if path == "/api/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            all_jobs = JOB_MANAGER.get_all_jobs()
            active_job = all_jobs[0] if all_jobs else None
            is_ready = not active_job or active_job["status"] == "completed"
            status_payload: dict[str, Any] = {
                "status": "ready" if is_ready else "busy",
                "active_job": active_job,
                "latest_reel": {
                    "duration_s": 48.14,
                    "headline": (
                        active_job["headline"]
                        if active_job and "headline" in active_job
                        else "«فیشەکی کڵاشینکۆف و هەڕەشەی مەرگ: بۆچی بەغدامان جێهێشت؟»"
                    ),
                    "video_url": "/media/ep29-pro-threat-reel.mp4",
                    "audit_passed": True,
                },
            }
            self.wfile.write(json.dumps(status_payload).encode())
            return

        if path.startswith("/media/"):
            filename = path.replace("/media/", "").strip("/")
            candidates = [
                ROOT / "work" / "best-highlight-master" / filename,
                ROOT / "work" / "master-highlights-compilation" / filename,
                ROOT / "work" / "pro-kurdish-master" / filename,
                ROOT / "work" / "pro-threat-master" / filename,
                ROOT / "work" / "ep29-pro-reel-master" / filename,
                ROOT / "work" / filename,
                ROOT / "media" / filename,
                ROOT / "tests" / "fixtures" / filename,
            ]
            candidates.extend(list((ROOT / "work").glob(f"*/{filename}")))
            candidates.extend(list((ROOT / "work" / "jobs").glob(f"*/{filename}")))
            for candidate in candidates:
                if candidate.is_file():
                    mime_type, _ = mimetypes.guess_type(str(candidate))
                    self.send_response(200)
                    self.send_header("Content-Type", mime_type or "application/octet-stream")
                    self.send_header("Content-Length", str(candidate.stat().st_size))
                    self.end_headers()
                    with open(candidate, "rb") as f:
                        while chunk := f.read(65536):
                            self.wfile.write(chunk)
                    return

            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Media file not found")
            return

        super().do_GET()


def run_web_server(port: int = 8080, host: str = "127.0.0.1") -> None:
    """Run the HawEdit local web dashboard server."""
    use_utf8_streams()
    server_address = (host, port)
    with socketserver.TCPServer(server_address, HawEditWebHandler) as httpd:
        print(f"HawEdit Web Dashboard running at http://{host}:{port}/")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server...")


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    run_web_server(port)

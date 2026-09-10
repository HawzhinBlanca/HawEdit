import sys,json,hashlib,subprocess,traceback,runpy
from pathlib import Path
from dataclasses import replace
sys.stdout.reconfigure(encoding='utf-8')
from hawedit.captions import find_ffmpeg
from hawedit.pipeline import run_pipeline
from hawedit.transcripts import RawTranscript,AsrProvenance,Word
root=Path(__file__).parent
out={}
ffmpeg=find_ffmpeg()
video=root/'assembly-source-32s.mp4'
subprocess.run([str(ffmpeg),'-hide_banner','-loglevel','error','-y','-f','lavfi','-i','color=black:s=160x90:r=25:d=32','-f','lavfi','-i','anullsrc=r=16000:cl=mono','-t','32','-c:v','libx264','-c:a','aac',str(video)],check=True,timeout=30)
words=tuple(Word(w=f'sentence{i}.',start_ms=start,end_ms=start+1000,conf=1.0) for i,start in enumerate([10000,20000,30000]))
raw=RawTranscript(media_id='assemblyprobe',text_ckb=' '.join(w.w for w in words),words=words,asr=AsrProvenance(canonical='omniASR_LLM_7B_v2',aligner='ctc_viterbi'),media_sha256=hashlib.sha256(video.read_bytes()).hexdigest())
try:
 run=run_pipeline(video,root/'assembly-run',media_id='assemblyprobe',transcript=raw,select_sentences=(0,2),assemble=True,min_clip_ms=1000)
 out['assembly_run']=run.to_dict()
except Exception as e:out['assembly_run']={'exception':type(e).__name__,'traceback':traceback.format_exc()}
(root/'pipeline-probes.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(out,ensure_ascii=False,indent=2),flush=True)

# Actual pipeline/render with existing test fixture and supplied test transcript/verdict.
# No model-quality claim. A directory at the plan pathname is a real write failure;
# no publication, rendering, filesystem, or gate functions are mocked.
t=runpy.run_path('tests/test_pipeline.py')
work=root/'publication-run'
work.mkdir(exist_ok=True)
(work/'pubprobe-s0-0.edit_plan.json').mkdir(exist_ok=True)
try:
 run=run_pipeline(t['FIXTURE'],work,media_id='pubprobe',transcript=t['a_transcript']('pubprobe'),select_sentences=(0,),verdict=t['a_verdict'](100,1700),min_clip_ms=1000)
 out['publication_run']=run.to_dict()
 out['publication_files']=[str(p.relative_to(work)) for p in work.rglob('*') if p.is_file() and ('review' in p.parts or p.name.endswith('edit_plan.json'))]
except Exception as e:out['publication_run']={'exception':type(e).__name__,'traceback':traceback.format_exc()}
(root/'pipeline-probes.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(out,ensure_ascii=False,indent=2),flush=True)

import sys, json, subprocess, platform, time, urllib.request, urllib.error
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')
import cv2
from hawedit.captions import find_ffmpeg
from hawedit.render_critic import RenderedSequenceContext, inspect_rendered_sequence
from hawedit.pipeline import _prepare_selection, _raw_text_for_words
from hawedit.sentences import Sentence
from hawedit.transcripts import Word, RawTranscript, AsrProvenance
from hawedit.web import JobManager

root = Path(__file__).parent
ffmpeg = find_ffmpeg()
video = root / 'black-2s-no-audio.mp4'
subprocess.run([str(ffmpeg), '-hide_banner','-loglevel','error','-y','-f','lavfi','-i','color=black:s=160x90:r=25:d=2','-an','-c:v','libx264',str(video)],check=True,timeout=30)
text_source = root / 'not-video.txt'
text_source.write_text('This is an audit canary, not video.',encoding='utf-8')
out = {'sha':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'environment':{'python':sys.version,'platform':platform.platform(),'opencv':cv2.__version__,'ffmpeg':subprocess.check_output([str(ffmpeg),'-version'],text=True).splitlines()[0]}}
out['critic'] = []
for label,path,duration,sha in [('missing',root/'absent.mp4',60000,None),('real_black_2s',video,2000,None),('real_2s_declared_60s',video,60000,None),('wrong_digest',video,2000,'0'*64)]:
 result=inspect_rendered_sequence(RenderedSequenceContext(render_path=path,duration_ms=duration,expected_sha256=sha),claim_all_clear=True)
 try:
  result.assert_verdict_grounded()
  grounded=True
 except Exception as e: grounded=str(e)
 out['critic'].append({'case':label,'all_clear':result.is_all_clear,'observed_media':result.observed_media,'coverage':result.coverage_ratio,'windows':len(result.windows),'last_window_end':max(w.end_ms for w in result.windows),'claimed_frame_counts_sum':sum(w.frame_count for w in result.windows),'grounding_assertion':grounded,'defects':[d.to_dict() for d in result.defects]})

sentences=tuple(Sentence(words=(Word(w=f'sentence{i}.',start_ms=start,end_ms=start+1000,conf=1.0),),complete=True) for i,start in enumerate([10000,20000,30000]))
raw=RawTranscript(media_id='audit',text_ckb=' '.join(s.text for s in sentences),words=tuple(w for s in sentences for w in s.words),asr=AsrProvenance(canonical='omniASR_LLM_7B_v2',aligner='ctc_viterbi'))
ordered,selected,anchors=_prepare_selection(raw,sentences,(0,2),allow_assembly=True)
out['assembly_selection']={'source_intervals':[(sentences[i].start_ms,sentences[i].end_ms) for i in ordered],'returned_anchors':anchors,'returned_sentence_times':[(s.start_ms,s.end_ms) for s in selected],'original_span_map_returned':False}
try:out['assembly_raw_text']=_raw_text_for_words(raw,tuple(w for s in selected for w in s.words))
except Exception as e:out['assembly_raw_text']={'exception':type(e).__name__,'detail':str(e)}

def request(path,payload=None):
 req=urllib.request.Request('http://127.0.0.1:8080'+path,data=None if payload is None else json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
 try:
  with urllib.request.urlopen(req,timeout=5) as r:
   body=r.read(30000)
   return {'status':r.status,'body':json.loads(body) if r.headers.get_content_type()=='application/json' else body.decode(errors='replace')[:300]}
 except urllib.error.HTTPError as e:return {'status':e.code,'body':e.read(300).decode(errors='replace')}
 except Exception as e:return {'exception':type(e).__name__,'detail':str(e)}
out['web']=[]
for source in ['',str(root/'absent.mp4'),str(text_source),str(video)]:
 submitted=request('/api/repurpose',{'source':source})
 job=submitted.get('body',{}).get('job_id') if isinstance(submitted.get('body'),dict) else None
 time.sleep(.4)
 out['web'].append({'source':source,'submitted':submitted,'after':request('/api/jobs/'+job) if job else None})
out['web_malformed_array']=request('/api/repurpose',[])
out['web_rank2_media']=request('/media/ep29-pro-threat-story.mp4')
out['web_status']=request('/api/status')
manager=JobManager()
ids=[manager.submit_job(str(video))['job_id'] for _ in range(20)]
time.sleep(.4)
out['job_burst']={'submitted':len(ids),'unique_ids':len(set(ids)),'retained_jobs':len(manager.get_all_jobs()),'ids':ids,'fresh_manager_jobs':JobManager().get_all_jobs()}
(root/'probes.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(out,ensure_ascii=False,indent=2))

import json,sys,hashlib
from pathlib import Path
from unittest.mock import patch
sys.stdout.reconfigure(encoding='utf-8')
from hawedit.pipeline import run_pipeline
from hawedit.sanity_gate import check_face_presence
from hawedit.condenser import condense_multiple_arcs
from hawedit.sentences import Sentence
from hawedit.transcripts import Word
root=Path(__file__).parent
work=root/'assembly-run-ckb'
proxy=work/'stage0/proxy.mp4'
before=hashlib.sha256(proxy.read_bytes()).hexdigest()
proxy.write_bytes(b'corrupted audit proxy')
events=[]
run=run_pipeline(root/'assembly-source-32s.mp4',work,media_id='assemblyprobe',on_event=lambda event:events.append(str(event)))
out={'checkpoint_corruption':{'original_proxy_sha256':before,'current_size':proxy.stat().st_size,'events':events,'ingest':run.to_dict()['ingest']}}
video=root/'black-2s-no-audio.mp4'
out['face_empty_shot_schedule']=check_face_presence(video,())
out['face_black_video_control']=check_face_presence(video,((0,2),))
# Model-resource boundary failure only; perception function is not stubbed.
import cv2
with patch.object(cv2.data,'haarcascades',str(root/'absent-cascades')):
 out['face_missing_cascade']=check_face_presence(video,((0,2),))
sentences=tuple(Sentence(words=(Word(w='وتەیەکی گرنگ.',start_ms=i*10000,end_ms=(i+1)*10000,conf=1),),complete=True) for i in range(30))
plans=condense_multiple_arcs(sentences,max_clips=3)
out['candidate_redundancy']={'selected_indices':[p.retained_sentence_indices for p in plans],'shared_indices':sorted(set(plans[0].retained_sentence_indices)&set(plans[1].retained_sentence_indices)) if len(plans)>1 else []}
(root/'recovery-probes.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(out,ensure_ascii=False,indent=2))

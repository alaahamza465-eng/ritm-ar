#!/usr/bin/env python3
"""الخطوة 2: تفريغ عربي بتوقيت الكلمة (faster-whisper، على الجهاز، مجاني).
الاستخدام: python3 transcribe.py <مجلد_الشغل> [--model large-v3-turbo|medium|small] [--prompt "نص يساعد اللهجة"]
يكتب tr.json = {segments:[{start,end,text,words:[{w,s,e,p}]}]}
ملاحظة: الصوت بيتقرأ بـ numpy مباشرة (بعض نسخ PyAV بتفشل مع faster-whisper)."""
import sys, os, json, wave, argparse
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument('work'); ap.add_argument('--model', default='large-v3-turbo')
ap.add_argument('--prompt', default='فيديو بالعامية العربية.')
ap.add_argument('--threads', type=int, default=max(1, (os.cpu_count() or 2)))
a = ap.parse_args()
from faster_whisper import WhisperModel

wf = wave.open(os.path.join(a.work, 'a.wav'))
audio = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
m = WhisperModel(a.model, device='cpu', compute_type='int8', cpu_threads=a.threads)
segs, info = m.transcribe(audio, language='ar', word_timestamps=True, beam_size=5, vad_filter=False, initial_prompt=a.prompt)
out = []
for s in segs:
    out.append({'start': s.start, 'end': s.end, 'text': s.text.strip(),
                'words': [{'w': w.word.strip(), 's': w.start, 'e': w.end, 'p': w.probability} for w in s.words]})
    print(f"[{s.start:6.2f}] {s.text.strip()}", flush=True)
json.dump({'model': a.model, 'segments': out}, open(os.path.join(a.work, 'tr.json'), 'w'), ensure_ascii=False, indent=1)
print(f"✓ {len(out)} جملة · {sum(len(s['words']) for s in out)} كلمة")

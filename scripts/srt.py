#!/usr/bin/env python3
"""ملف ترجمة .srt (يوتيوب ولينكدإن) + نص الكلام كامل .txt لكابشن البوست — من timeline.json.
الاستخدام: python3 srt.py <work> [اسم]   ← <work>/<اسم>.srt و <work>/<اسم>.txt (الافتراضي final)"""
import os, sys, json
W = sys.argv[1]; name = sys.argv[2] if len(sys.argv) > 2 else 'final'
T = json.load(open(os.path.join(W, 'timeline.json'), encoding='utf8'))
ts = lambda t: f"{int(t // 3600):02d}:{int(t % 3600 // 60):02d}:{int(t % 60):02d},{int(round((t % 1) * 1000)) % 1000:03d}"
caps = [c for c in T['captions'] if c.get('on') is not False and c['w']]
with open(os.path.join(W, name + '.srt'), 'w', encoding='utf8') as f:
    for i, c in enumerate(caps, 1): f.write(f"{i}\n{ts(c['s'])} --> {ts(c['e'])}\n{' '.join(w['t'] for w in c['w'])}\n\n")
lines = (json.load(open(os.path.join(W, 'words.json'), encoding='utf8')).get('lines') or []) if os.path.exists(os.path.join(W, 'words.json')) else []
txt = '\n'.join(l for l in lines if l.strip()) or ' '.join(w['t'] for c in caps for w in c['w'])
open(os.path.join(W, name + '.txt'), 'w', encoding='utf8').write(txt + '\n')
print(f'✓ {name}.srt ({len(caps)} سطر) · {name}.txt')

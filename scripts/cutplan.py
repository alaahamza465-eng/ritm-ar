#!/usr/bin/env python3
"""الخطوة 3: خطة القص — يشيل السكتات الطويلة ويخلّي نَفَس طبيعي.
الاستخدام: python3 cutplan.py <مجلد_الشغل> [--noise -38] [--min-sil 0.25] [--pre 0.08] [--post 0.14] [--merge 0.15]
- السكتة اللي أقصر من (pre+post+merge) بتضل زي ما هي (نَفَس طبيعي).
- overrides.json اختياري بمجلد الشغل: {"keep":[[s,e]], "drop":[[s,e]]} بثواني الفيديو الأصلي
  keep = مقاطع بدها تضل حتى لو صامتة (لقطة قهوة، حركة يد)، drop = مقاطع تنشال (جملة معادة، غلط).
- بيتجنّب يخلّي «شقفة» أقل من ربع ثانية من لقطة بعد قطع موجود بالفيديو.
يكتب keeps.json = [[s,e],...] بثواني الأصل، مقرّبة لفريمات 30."""
import sys, os, re, json, argparse, subprocess

ap = argparse.ArgumentParser()
ap.add_argument('work'); ap.add_argument('--noise', type=float, default=-38); ap.add_argument('--min-sil', type=float, default=0.25)
ap.add_argument('--pre', type=float, default=0.08); ap.add_argument('--post', type=float, default=0.14); ap.add_argument('--merge', type=float, default=0.15)
a = ap.parse_args()
W = a.work
info = json.load(open(os.path.join(W, 'info.json')))
DUR = info['duration']; FPS = 30

out = subprocess.run(['ffmpeg', '-nostats', '-i', os.path.join(W, 'a.wav'), '-af', f'silencedetect=noise={a.noise}dB:d={a.min_sil}', '-f', 'null', '-'],
                     capture_output=True, text=True).stderr
st = [float(x) for x in re.findall(r'silence_start: ([\d.]+)', out)]
en = [float(x) for x in re.findall(r'silence_end: ([\d.]+)', out)]
sp, cur = [], 0.0
for s, e in zip(st, en):
    if s > cur: sp.append([cur, s])
    cur = e
if cur < DUR: sp.append([cur, DUR])

keeps = [[max(0, s - a.pre), min(DUR, e + a.post)] for s, e in sp]
ov = {}
p = os.path.join(W, 'overrides.json')
if os.path.exists(p): ov = json.load(open(p))
keeps += [list(k) for k in ov.get('keep', [])]
keeps.sort()
m = []
for k in keeps:
    if m and k[0] - m[-1][1] < a.merge: m[-1][1] = max(m[-1][1], k[1])
    else: m.append(list(k))
for d0, d1 in ov.get('drop', []):          # اطرح المقاطع المحذوفة
    nm = []
    for s, e in m:
        if e <= d0 or s >= d1: nm.append([s, e]); continue
        if s < d0: nm.append([s, d0])
        if e > d1: nm.append([d1, e])
    m = nm

# قطعات المشاهد الموجودة أصلاً (من النسخة الصغيرة)
sc_out = subprocess.run(['ffmpeg', '-hide_banner', '-i', os.path.join(W, 'proxy.mp4'), '-vf', "select='gt(scene,0.3)',showinfo", '-f', 'null', '-'],
                        capture_output=True, text=True).stderr
scenes = [float(x) for x in re.findall(r'pts_time:([\d.]+)', sc_out)]
for k in m:
    for s in scenes:
        if k[0] < s < k[1]:
            if s - k[0] < 0.25: k[0] = s
            elif k[1] - s < 0.25: k[1] = s
q = lambda t: round(t * FPS) / FPS
m = [[q(s), q(e)] for s, e in m if q(e) - q(s) >= 0.2]
json.dump(m, open(os.path.join(W, 'keeps.json'), 'w'))
json.dump(scenes, open(os.path.join(W, 'scenes.json'), 'w'))
tot = sum(e - s for s, e in m)
print(f"✓ {len(m)} مقطع · الفيديو صار {tot:.1f} ث بدل {DUR:.1f} (انشال {DUR - tot:.1f} ث سكوت)")

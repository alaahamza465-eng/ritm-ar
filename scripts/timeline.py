#!/usr/bin/env python3
"""يبني timeline.json — ملف واحد فيه كل الريل (كابشن، مربعات، رسومات، بي-رول، أصوات، ختام).
الاستخدام: python3 timeline.py <work>
بيقرا: words.json + chunks.json (من script.py align) · keeps.json · plan.json (انت بتكتبه — references/plan.md) · broll/index.json · clip.mp4
وبيضبط التوقيت لحاله بالدروس اللي تعلمناها:
- حدود المربع على بداية قطعة كابشن، ولو فيه قطع كاميرا قريب بتصير عليه (الحركة تبدأ مع القطع مش بنصها).
- ولا قطع بنص ذوبان بي-رول: يا البي-رول مغطّي الشاشة كاملة وقت القطع، يا بيبلش بعده.
- البي-رول بيخلص ذوبانه قبل ما يتحرك المربع.
- الأصوات الخفيفة بتنحط لحالها على اللحظات اللي إلها معنى (بحد أقصى ~15 بالدقيقة)."""
import os, re, sys, json, subprocess
W = os.path.abspath(sys.argv[1])
J = lambda n, d=None: json.load(open(os.path.join(W, n), encoding='utf8')) if os.path.exists(os.path.join(W, n)) else d
words = J('words.json')['words']; chunks = J('chunks.json'); keeps = J('keeps.json'); plan = J('plan.json', {}) or {}
bidx = J('broll/index.json', {}) or {}
clip = os.path.join(W, 'clip.mp4')
dur = float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', clip], capture_output=True, text=True).stdout)
knobs = {'zoom': 1, 'dissolve': 0.4, 'box': 0.7, **(plan.get('knobs') or {})}
D = knobs['dissolve'] / 2; BOX = knobs['box']
warn = []

# ---- القصّات: حدود المقاطع + تغيّر زاوية الكاميرا جوّا الفيديو المقصوص ----
cuts, acc = [], 0.0
for s, e in keeps[:-1]: acc += e - s; cuts.append(round(acc, 3))
r = subprocess.run(['ffmpeg', '-hide_banner', '-i', clip, '-vf', "scale=96:-2,select='gt(scene,0.32)',showinfo", '-an', '-f', 'null', '-'], capture_output=True, text=True).stderr
cuts += [round(float(x), 3) for x in re.findall(r'pts_time:([\d.]+)', r)]
cuts = sorted({c for c in cuts if 0.2 < c < dur - 0.2})
cuts = [c for i, c in enumerate(cuts) if i == 0 or c - cuts[i - 1] > 0.12]

# ---- الكابشن ----
clean = lambda s: re.sub(r'[^\u0621-\u064A\u0660-\u0669\u0671-\u06D3\u06FA-\u06FF0-9A-Za-z]', '', s)
hot_spec = plan.get('hot', [])
allw = [(ci, wi, w) for ci, c in enumerate(chunks) for wi, w in enumerate(c['w'])]
HOT = {}   # (قطعة، كلمة) ← True أو قوة الزوم
for h in hot_spec:
    t0, want = (h, None) if isinstance(h, (int, float)) else (h.get('t', -9), h.get('w'))
    cand = [x for x in allw if abs(x[2]['s'] - t0) < 0.4 and (not want or clean(want) == clean(x[2]['t']))]
    if not cand: warn.append(f'كلمة مهمة على {t0} ما لقيتها بالكلام — شيك words.json'); continue
    ci, wi, _ = min(cand, key=lambda x: abs(x[2]['s'] - t0))
    HOT[(ci, wi)] = h.get('z', True) if isinstance(h, dict) else True
caps = []
for ci, c in enumerate(chunks):
    ws = c['w']; out = []
    for i, w in enumerate(ws):
        e = ws[i + 1]['s'] if i + 1 < len(ws) else c['e']
        h = HOT.get((ci, i), False)
        o = {'t': w['t'], 's': round(w['s'], 3), 'e': round(min(e, w['s'] + 0.9), 3), 'hot': bool(h)}
        if isinstance(h, (int, float)) and not isinstance(h, bool): o['z'] = h
        out.append(o)
    caps.append({'s': round(c['s'], 3), 'e': round(c['e'], 3), 'w': out})
starts = [c['s'] for c in caps]

def snap_box_edge(t):
    near = [s for s in starts if abs(s - t) <= 0.3]
    if near: t = min(near, key=lambda s: abs(s - t))
    cc = [c for c in cuts if abs(c - t) <= 0.2]
    return round(min(cc, key=lambda c: abs(c - t)), 3) if cc else round(t, 3)

# ---- المربعات (رسمة فوق، الوجه بكرت تحت) والرسومات ----
layout, panels = [], []
for bx in plan.get('boxes', []):
    s, e = snap_box_edge(bx['s']), snap_box_edge(bx['e'])
    if e - s < 1.2: warn.append(f'مربع قصير ({s}-{e}) — أقل من 1.2 ث');
    layout.append({'s': s, 'e': e, 'mode': 'box'})
    p = dict(bx.get('panel') or {}); p.update({'s': s, 'e': e, 'box': True}); panels.append(p)
for ov in plan.get('over', []):
    p = dict(ov); p['box'] = False; panels.append(p)
edges = []
for l in layout: edges += [l['s'], l['e']]

# ---- البي-رول ----
broll = []
for b in plan.get('broll', []):
    if b['id'] not in bidx: warn.append(f"بي-رول «{b['id']}» مش موجود — شغّل broll.py add"); continue
    s, e = float(b['s']), float(b['e'])
    busy = lambda x: any(x - D < a0 + BOX and x + D > a0 for a0 in edges)   # الذوبان فوق حركة مربع؟
    for _ in range(3):
        for a0 in edges:   # يبلش ذوبانه بعد ما يوقف المربع
            if s - D < a0 + BOX and s + D > a0: s = max(s, a0 + BOX + D + 0.02)
        for c in cuts:   # ولا قطع بنص الذوبان
            if s - D < c < s + D:
                pre = c - D - 0.03
                s = pre if pre >= s - 0.35 and not busy(pre) else c + D + 0.05
            if e - D < c < e + D: e = c + D + 0.03 if (c + D + 0.03) - e <= 0.35 else c - D - 0.03
    for a0 in edges:   # يخلص ذوبانه قبل ما يتحرك المربع
        if e - D < a0 + BOX and e + D > a0 and not (s + D <= a0 and a0 + BOX <= e - D): e = min(e, a0 - D - 0.02)
    if round(s, 3) != round(float(b['s']), 3) and abs(s - float(b['s'])) > 0.25: warn.append(f"«{b['id']}» انزاح من {b['s']} لـ{s:.2f} (قطع كاميرا أو حركة مربع)")
    off = float(b.get('off', 0.2)); maxlen = bidx[b['id']]['dur'] - off - D - 0.05
    if e - s > maxlen: e = s + maxlen; warn.append(f"«{b['id']}» أقصر من الفترة — قصّرتها لـ{maxlen:.1f} ث")
    if e - s < 0.6: warn.append(f"«{b['id']}» صار أقصر من 0.6 ث بعد الضبط — شيله أو حرّكه"); continue
    broll.append({'id': b['id'], 's': round(s, 3), 'e': round(e, 3), 'off': off, 'on': b.get('on', True)})
broll.sort(key=lambda x: x['s'])
for x, y in zip(broll, broll[1:]):   # لقطتين قريبين (فجوة أقل من 0.5) بيصيروا موصولين
    if 0 < y['s'] - x['e'] < 0.5: x['e'] = y['s']

# ---- زوم القصّات: يتبدّل 1.00 / 1.05 بين المقاطع عشان القطع ما يبين نطّة ----
cz, acc = [], 0.0
for i, (s, e) in enumerate(keeps):
    cz.append({'s': round(acc, 3), 'e': round(acc + (e - s), 3), 'z': 1.0 if i % 2 == 0 else 1.05}); acc += e - s

# ---- الأصوات ----
sfx = []
add = lambda t, k, g: sfx.append({'t': round(max(0, t), 3), 'k': k, 'g': g})
for i, b in enumerate(broll):
    if i == 0 or abs(broll[i - 1]['e'] - b['s']) > 0.03: add(b['s'] - D - 0.1, 'whoosh', 0.32)
for p in panels:
    if p.get('type') == 'list':
        for i, it in enumerate(p.get('items', [])): add(it.get('at', p['s'] + 0.4 + i * 0.45), 'tick', 0.5)
    if p.get('type') == 'chat':
        for i, it in enumerate(p.get('bubbles', [])): add(it.get('at', p['s'] + 0.4 + i * 0.5), 'pop', 0.45)
    if p.get('type') == 'stat': add(p.get('at', p['s'] + 0.5) + p.get('dur', 1.2), 'snap', 0.5)
    if p.get('type') == 'title' and p.get('lines'):
        add(p['lines'][0].get('at', p['s'] + 0.2), 'tick', 0.35)
    if p.get('type') == 'cta': add(p.get('at', p['s']), 'pop', 0.45)
outro = plan.get('outro')
if outro: add(dur + 0.3, 'chime', 0.35)
for l in layout:   # صوت ناعم للمربع إلا لو في صوت ثاني جاي وراه على طول
    if not any(0 <= x['t'] - l['s'] < 0.6 for x in sfx): add(l['s'], 'soft', 0.35)
sfx += plan.get('sfx', [])
sfx.sort(key=lambda x: x['t'])
per_min = len(sfx) / (dur / 60)
if per_min > 30: warn.append(f'الأصوات كثيرة ({per_min:.0f} بالدقيقة) — خففها')

theme = {'bg': '#272B71', 'ink': '#FFFFFF', 'acc': '#F79210', 'mut': '#C9CCEA', 'dark': '#14163D', 'font': 'IBM Plex Sans Arabic',
         'capStyle': 'shadow', 'handle': '', **(plan.get('theme') or {})}
T = {'v': 1, 'fps': int(plan.get('fps', 30)), 'dur': round(dur, 3), 'theme': theme, 'knobs': knobs, 'captions': caps,
     'layout': layout, 'panels': panels, 'broll': broll, 'cutzoom': cz, 'cuts': cuts, 'sfx': sfx,
     'outro': outro, 'outroDur': 3.0 if outro else 0}
json.dump(T, open(os.path.join(W, 'timeline.json'), 'w'), ensure_ascii=False, indent=1)
if not os.path.exists(os.path.join(W, 'timeline.orig.json')) or '--reset' in sys.argv:
    json.dump(T, open(os.path.join(W, 'timeline.orig.json'), 'w'), ensure_ascii=False, indent=1)
print(f"✓ timeline.json · {dur:.1f} ث · {len(caps)} قطعة كابشن · {sum(1 for c in caps for w in c['w'] if w['hot'])} كلمة عليها زوم · "
      f"{len(layout)} مربع · {len(panels)} رسمة · {len(broll)} بي-رول · {len(sfx)} صوت · قصّات {cuts}")
for w_ in warn: print('⚠', w_)

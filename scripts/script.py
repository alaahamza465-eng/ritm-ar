#!/usr/bin/env python3
"""الخطوة 4: السكربت — عرض، حذف جمل، ومحاذاة الكلام المصحّح بالتوقيت.
الاستخدام:
  python3 script.py <work> show          # يطبع الجمل مرقّمة بتوقيت الفيديو بعد القص، ويكتب fixed.txt لو مش موجود
  python3 script.py <work> drop 6 8      # يشيل الجمل 6 و8 (يضيفها لـ overrides.json) — بعدها أعد cutplan.py ثم show
  python3 script.py <work> align         # بعد تصحيح fixed.txt: يكتب words.json و chunks.json ويطبع كل كلمة بتوقيتها
fixed.txt: سطر لكل جملة بنفس الترتيب. صحّح الكلمات بس (لهجة، أسماء) — لا تعيد صياغة ولا تختصر.
عدد الكلمات ممكن يختلف شوي؛ التوقيت بيتوزّع حسب طول الحروف."""
import sys, os, re, json

W, cmd = sys.argv[1], sys.argv[2]
tr = json.load(open(os.path.join(W, 'tr.json')))['segments']
keeps = json.load(open(os.path.join(W, 'keeps.json')))

def remap(t):
    acc = 0.0
    for a, b in keeps:
        if t < a: return acc
        if t <= b: return acc + (t - a)
        acc += b - a
    return acc

def kept(t):
    return any(a <= t <= b for a, b in keeps)

if cmd == 'show':
    fp = os.path.join(W, 'fixed.txt')
    if not os.path.exists(fp):
        open(fp, 'w', encoding='utf8').write('\n'.join(s['text'] for s in tr) + '\n')
    lines = [l.rstrip('\n') for l in open(fp, encoding='utf8')]
    for i, s in enumerate(tr):
        mid = (s['start'] + s['end']) / 2
        tag = '' if kept(mid) else '  ← (منشالة)'
        print(f"{i + 1:2d}) [{remap(s['start']):6.1f}] {lines[i] if i < len(lines) else s['text']}{tag}")
    print(f"المدة بعد القص: {sum(b - a for a, b in keeps):.1f} ث")

elif cmd == 'drop':
    p = os.path.join(W, 'overrides.json')
    ov = json.load(open(p)) if os.path.exists(p) else {}
    for n in sys.argv[3:]:
        s = tr[int(n) - 1]
        ov.setdefault('drop', []).append([round(s['start'] - 0.05, 3), round(s['end'] + 0.05, 3)])
    json.dump(ov, open(p, 'w'), ensure_ascii=False)
    print('✓ انضافت للحذف. هلقيت: cutplan.py ثم script.py show')

elif cmd == 'align':
    lines = [l.strip() for l in open(os.path.join(W, 'fixed.txt'), encoding='utf8')]
    lines += [''] * (len(tr) - len(lines))
    ar = lambda w: re.sub(r'[^؀-ۿ0-9]', '', w)
    words = []
    for si, (seg, line) in enumerate(zip(tr, lines)):
        mw, cw = seg['words'], line.split()
        if not mw or not cw: continue
        if len(mw) == len(cw):
            tt = [(w['s'], w['e']) for w in mw]
        else:                       # ساعة بالحروف فوق كلمات وِسبر
            L = [max(1, len(ar(w['w']))) for w in mw]; tot = sum(L)
            pts = [(0, mw[0]['s'])]; c = 0
            for w, l in zip(mw, L):
                pts.append((c / tot, w['s'])); c += l; pts.append((c / tot, w['e']))
            def clk(f):
                for (f0, t0), (f1, t1) in zip(pts, pts[1:]):
                    if f0 <= f <= f1: return t0 + (t1 - t0) * ((f - f0) / (f1 - f0) if f1 > f0 else 0)
                return pts[-1][1]
            CL = [max(1, len(ar(w))) for w in cw]; T = sum(CL); c = 0; tt = []
            for l in CL: tt.append((clk(c / T), clk((c + l) / T))); c += l
        # الجملة كلها منشالة (drop)؟ شيلها. غير هيك ولا كلمة بتضيع: الكلمة اللي وقعت بسكتة منشالة بتلصق على حد القص
        if not kept((seg['start'] + seg['end']) / 2) and not any(kept((s + e) / 2) for s, e in tt): continue
        for w, (s, e) in zip(cw, tt):
            ns, ne = remap(s), remap(e)
            if words and words[-1]['seg'] == si: ns = max(ns, words[-1]['ns'] + 0.04)
            ne = max(ne, ns + 0.08)
            words.append({'w': w, 'seg': si, 's': round(s, 3), 'e': round(e, 3), 'ns': round(ns, 3), 'ne': round(ne, 3)})
    json.dump({'words': words, 'lines': lines}, open(os.path.join(W, 'words.json'), 'w'), ensure_ascii=False, indent=0)

    # كروت الكابشن: 2-3 كلمات، ما بتنكسر بعد حرف جر أو أداة، وبتحترم الوقفات
    WEAK = {'إن', 'من', 'في', 'على', 'إنه', 'اللي', 'علشان', 'عشان', 'يا', 'لما', 'إذا', 'كل', 'هذا', 'هاي', 'هاد', 'مش', 'بس', 'انت', 'أنا', 'عن',
            'ما', 'الذي', 'لا', 'إله', 'إلا', 'وقت', 'رح', 'بدي', 'كنت', 'و', 'هو', 'ربنا', 'لـ', 'مع', 'عند'}
    clean = lambda w: re.sub(r'[.،:,!؟?]$', '', w)
    chunks, cur = [], []
    for w in words:
        if cur:
            gap = w['ns'] - cur[-1]['ne']; chars = sum(len(x['w']) for x in cur) + len(w['w'])
            if gap > 0.35 or (w['seg'] != cur[-1]['seg'] and re.search(r'[.،:؟,!]$', cur[-1]['w'])):
                chunks.append(cur); cur = []
            elif len(cur) >= 3 or chars > 18:
                if len(cur) > 1 and clean(cur[-1]['w']) in WEAK:
                    last = cur.pop(); chunks.append(cur); cur = [last]
                else: chunks.append(cur); cur = []
        cur.append(w)
        if re.search(r'[.؟!:]$', w['w']): chunks.append(cur); cur = []
    if cur: chunks.append(cur)
    C = [{'s': c[0]['ns'], 'e': c[-1]['ne'], 'w': [{'t': clean(x['w']), 's': x['ns']} for x in c]} for c in chunks]
    txt = lambda c: ' '.join(x['t'] for x in c['w'])
    i = 1
    while i < len(C):                       # ضم الكلمة اليتيمة واللصيقات القصيرة
        p, c = C[i - 1], C[i]
        if (len(c['w']) == 1 and len(p['w']) <= 3 and len(txt(p)) + len(txt(c)) <= 21 and c['s'] - p['e'] < 0.6) or \
           (len(p['w']) <= 2 and len(c['w']) <= 2 and len(txt(p)) + len(txt(c)) <= 14 and c['s'] - p['e'] < 0.3):
            p['w'] += c['w']; p['e'] = c['e']; C.pop(i); continue
        i += 1
    for x, y in zip(C, C[1:]):
        x['e'] = round(min(y['s'], max(x['e'], x['s'] + 0.6) + 0.6) if y['s'] - x['e'] < 1.2 else x['e'] + 0.4, 3)
    if C: C[-1]['e'] += 0.3
    json.dump(C, open(os.path.join(W, 'chunks.json'), 'w'), ensure_ascii=False)
    cur = -1; line = ''
    for w in words:
        if w['seg'] != cur:
            if line: print(line)
            cur = w['seg']; line = f"{cur + 1}:"
        line += f" {w['w']}|{w['ns']:.2f}"
    print(line)
    print(f"✓ words.json ({len(words)} كلمة) · chunks.json ({len(C)} كرت كابشن)")
else:
    print(__doc__)

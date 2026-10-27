#!/usr/bin/env python3
"""يولّد أصوات نقر خفيفة (wav) رياضياً — بدون مكتبات صوت وبدون حقوق.
الاستخدام: python3 make_sfx.py <مجلد>"""
import sys, os, wave, struct, math

SR = 44100
out = sys.argv[1] if len(sys.argv) > 1 else 'sfx'
os.makedirs(out, exist_ok=True)

def write(name, samples):
    peak = max(1e-9, max(abs(s) for s in samples))
    k = 0.6 / peak
    with wave.open(os.path.join(out, name + '.wav'), 'w') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(b''.join(struct.pack('<h', int(max(-1, min(1, s * k)) * 32767)) for s in samples))

def env(t, a, d):
    return (t / a if t < a else math.exp(-(t - a) / d))

def noise(i):          # ضجيج حتمي
    x = (i * 1103515245 + 12345) & 0x7fffffff
    return (x / 0x7fffffff) * 2 - 1

def tone(dur, f, a=0.002, d=0.03, harm=(1,), fdrop=0.0):
    n = int(SR * dur); s = []
    for i in range(n):
        t = i / SR; ff = f * (1 - fdrop * t / dur)
        s.append(env(t, a, d) * sum(math.sin(2 * math.pi * ff * h * t) / (k + 1) for k, h in enumerate(harm)))
    return s

write('tick', [v + 0.15 * noise(i) * env(i / SR, .001, .006) for i, v in enumerate(tone(.09, 2200, .001, .012, (1, 2.7)))])
write('pop', tone(.17, 520, .003, .045, (1, 1.5), fdrop=.45))
write('snap', [0.9 * noise(i) * env(i / SR, .0008, .018) + v for i, v in enumerate(tone(.16, 180, .001, .03))])
write('switch', [a + b for a, b in zip(tone(.14, 1400, .001, .01, (1, 3)), [0] * int(SR * .05) + tone(.09, 900, .001, .012, (1, 3)))])
write('star', tone(.07, 3200, .001, .02, (1, 1.5, 2.01)))
write('chime', [a + b for a, b in zip(tone(.95, 880, .004, .35, (1, 2, 3)), tone(.95, 1320, .004, .28, (1, 2)))])
write('fill', tone(1.4, 300, .3, .5, (1, 2), fdrop=-.8))
# عملات بتنعد: نقرات معدن متسارعة
cnt = [0.0] * int(SR * 1.05)
for j in range(9):
    st = int(SR * (0.02 + 0.11 * j * (1 - j * .045)))
    for q, v in enumerate(tone(.08, 2600 + (j % 3) * 260, .001, .015, (1, 2.4, 3.9))):
        if st + q < len(cnt): cnt[st + q] += v * (1 - j * .05)
write('counter', cnt)
# نجاح: نغمتين طالعات
write('success', [a + b for a, b in zip(tone(.75, 660, .004, .18, (1, 2)), [0] * int(SR * .14) + tone(.61, 990, .004, .22, (1, 2)))])
# ووش ناعم للانتقالات: ضجيج بفلتر بيتحرك، بيطلع وبينزل بهدوء
def whoosh(dur, up=True):
    n = int(SR * dur); s = []; lp = 0.0
    for i in range(n):
        t = i / SR; k = t / dur; e = math.sin(math.pi * k) ** 2
        a = 0.04 + 0.5 * (k if up else 1 - k)          # فلتر بسيط بيفتح أو بيسكّر
        lp += a * (noise(i) - lp); s.append(lp * e)
    return s
write('whoosh', whoosh(0.55, True))
write('soft', [v * 0.6 for v in whoosh(0.4, False)])
print('sfx ok')

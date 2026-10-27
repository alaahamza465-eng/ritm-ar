#!/usr/bin/env python3
"""الرندر: بيرسم فريمات الريل بمحرّك رِتم (نفس كود المحرر) وبيجمّعها مع الصوت.
الاستخدام:
  python3 render.py <work> preview 1.2 6.8 13.9 22.5 30.4 40.5   # ورقة 6 لقطات ← <work>/sheet.jpg
  python3 render.py <work> all [--fps 30|60] [--workers 3] [--force]  # الفيديو كامل ← <work>/final.mp4
  python3 render.py <work> range 12.0 15.5                          # يعيد رسم فترة بس (بعد تعديل صغير) ثم: all
بيكمّل من وين وقف: الفريمات المرسومة ما بتنعاد إلا مع --force.
الصوت: صوت clip.mp4 (معاير -14) + الأصوات الخفيفة من timeline.sfx، وبعدين معايرة نهائية -14 LUFS."""
import os, sys, json, math, base64, asyncio, argparse, subprocess, shutil, wave
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)

ap = argparse.ArgumentParser()
ap.add_argument('work'); ap.add_argument('mode', choices=['preview', 'all', 'range'])
ap.add_argument('times', nargs='*', type=float)
ap.add_argument('--fps', type=int, default=0); ap.add_argument('--workers', type=int, default=0)
ap.add_argument('--force', action='store_true'); ap.add_argument('--out', default='')
a = ap.parse_args()
W = os.path.abspath(a.work)
T = json.load(open(os.path.join(W, 'timeline.json'), encoding='utf8'))
FPS = a.fps or T.get('fps', 30)
DUR = T['dur'] + (T.get('outroDur', 3.0) if T.get('outro') else 0)
SRC_FPS = 30

def sh(cmd): subprocess.run(cmd, check=True)

def ensure_frames():
    fd = os.path.join(W, 'frames'); clip = os.path.join(W, 'clip.mp4')
    stamp = os.path.join(fd, '.from')
    if os.path.isdir(fd) and os.path.exists(stamp) and open(stamp).read() == str(os.path.getmtime(clip)): return fd
    shutil.rmtree(fd, ignore_errors=True); os.makedirs(fd)
    print('⏳ بفك فريمات الفيديو المقصوص…', flush=True)
    sh(['ffmpeg', '-v', 'error', '-i', clip, '-vf', f'fps={SRC_FPS}', '-q:v', '2', '-y', os.path.join(fd, '%05d.jpg')])
    open(stamp, 'w').write(str(os.path.getmtime(clip)))
    return fd

def font_css():
    f = (T.get('theme') or {}).get('font')
    if not f or f == 'IBM Plex Sans Arabic': return None
    return 'https://fonts.googleapis.com/css2?family=' + f.replace(' ', '+') + ':wght@400;700;800;900&display=swap'

FD = ensure_frames()
NMAIN = len([x for x in os.listdir(FD) if x.endswith('.jpg')])
BRN = {}
for b in T.get('broll', []):
    d = os.path.join(W, 'broll', b['id'])
    if os.path.isdir(d): BRN[b['id']] = len([x for x in os.listdir(d) if x.endswith('.jpg')])
url = lambda p: 'file://' + p

def frame_args(t):
    i = min(NMAIN, max(1, int(math.floor(t * SRC_FPS + 1e-6)) + 1))
    main = url(os.path.join(FD, f'{i:05d}.jpg')) if t < T['dur'] + 0.6 else None   # آخر لقطة بتضل تحت الختام وهو طالع
    brs = {}
    D = (T.get('knobs') or {}).get('dissolve', 0.4) / 2
    for b in T.get('broll', []):
        if b.get('on') is False or b['id'] not in BRN: continue
        if t < b['s'] - D - 0.05 or t > b['e'] + D + 0.05: continue
        lt = t - (b['s'] - b.get('off', 0)); j = min(BRN[b['id']], max(1, int(lt * SRC_FPS) + 1))
        brs[b['id']] = url(os.path.join(W, 'broll', b['id'], f'{j:05d}.jpg'))
    return main, brs

async def run(jobs, workers):
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        br = await p.chromium.launch(args=['--allow-file-access-from-files', '--disable-web-security', '--font-render-hinting=none', '--force-color-profile=srgb'])
        q = asyncio.Queue(); [q.put_nowait(j) for j in jobs]
        done = [0]; total = len(jobs); errs = []
        async def worker():
            pg = await br.new_page(viewport={'width': 1080, 'height': 1920})
            pg.on('pageerror', lambda e: errs.append(str(e)))
            await pg.goto(url(os.path.join(ROOT, 'engine', 'render.html')))
            ok = await pg.evaluate('([tl,css])=>window.setup(tl,css)', [T, font_css()])
            if not ok and not errs: errs.append('الخط ما اكتمل تحميله — رح يطلع بالخط البديل')
            while not q.empty():
                t, path = q.get_nowait()
                main, brs = frame_args(t)
                data = await pg.evaluate('([t,m,b])=>window.frame(t,m,b)', [t, main, brs])
                open(path, 'wb').write(base64.b64decode(data.split(',', 1)[1]))
                done[0] += 1
                if done[0] % 150 == 0: print(f'  فريم {done[0]}/{total}', flush=True)
        await asyncio.gather(*[worker() for _ in range(workers)])
        await br.close()
        for e in sorted(set(errs))[:5]: print('⚠', e)

def sheet(paths, times, out):
    from PIL import Image, ImageDraw
    cols = 3; rows = math.ceil(len(paths) / cols); cw, ch = 360, 640
    im = Image.new('RGB', (cols * cw, rows * ch), (0, 0, 0)); d = ImageDraw.Draw(im)
    for k, (p, t) in enumerate(zip(paths, times)):
        x, y = (k % cols) * cw, (k // cols) * ch
        im.paste(Image.open(p).convert('RGB').resize((cw, ch)), (x, y))
        d.rectangle([x, y, x + 74, y + 26], fill=(0, 0, 0)); d.text((x + 6, y + 6), f'{t:.2f}s', fill=(255, 255, 255))
    im.save(out, quality=88)

def sfx_track(path):
    import numpy as np
    SR = 48000; n = int(DUR * SR) + SR
    mix = np.zeros(n, dtype=np.float32)
    for e in T.get('sfx', []):
        f = os.path.join(ROOT, 'assets', 'sfx', e['k'] + '.wav')
        if not os.path.exists(f): continue
        wf = wave.open(f); sr = wf.getframerate()
        x = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768
        if sr != SR: x = np.interp(np.arange(0, len(x) * SR / sr) * sr / SR, np.arange(len(x)), x).astype(np.float32)
        i = int(max(0, e['t']) * SR); j = min(n, i + len(x)); mix[i:j] += x[:j - i] * float(e.get('g', 0.4))
    pk = float(abs(mix).max() or 1); mix *= min(1.0, 0.7 / pk)   # الذروة ما بتطلع فوق ‎-3 dBFS
    st = (np.stack([mix, mix], 1) * 32767).astype('<i2')
    wo = wave.open(path, 'w'); wo.setnchannels(2); wo.setsampwidth(2); wo.setframerate(SR); wo.writeframes(st.tobytes()); wo.close()

def encode():
    OUT = os.path.join(W, 'out'); sx = os.path.join(W, 'sfx.wav'); sfx_track(sx)
    mixed = os.path.join(W, 'mix.wav')
    sh(['ffmpeg', '-v', 'error', '-i', os.path.join(W, 'clip.mp4'), '-i', sx, '-filter_complex',
        f'[0:a]apad=whole_dur={DUR:.3f}[v];[v][1:a]amix=inputs=2:normalize=0:duration=first[m]', '-map', '[m]', '-ar', '48000', '-ac', '2', '-t', f'{DUR:.3f}', '-y', mixed])
    r = subprocess.run(['ffmpeg', '-nostats', '-i', mixed, '-af', 'loudnorm=I=-14:TP=-1.5:LRA=9:print_format=json', '-f', 'null', '-'], capture_output=True, text=True).stderr
    m = json.loads(r[r.rindex('{'):])
    final = os.path.join(W, 'final.mp4')
    print('⏳ بجمّع الفيديو…', flush=True)
    sh(['ffmpeg', '-v', 'error', '-framerate', str(FPS), '-i', os.path.join(OUT, '%05d.jpg'), '-i', mixed,
        '-af', f"loudnorm=I=-14:TP=-1.5:LRA=9:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true,aresample=48000",
        '-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-pix_fmt', 'yuv420p', '-r', str(FPS), '-g', str(FPS * 2),
        '-color_primaries', 'bt709', '-color_trc', 'bt709', '-colorspace', 'bt709', '-c:a', 'aac', '-b:a', '192k',
        '-movflags', '+faststart', '-shortest', '-y', final])
    r = subprocess.run(['ffmpeg', '-nostats', '-i', final, '-af', 'ebur128=peak=true', '-f', 'null', '-'], capture_output=True, text=True).stderr
    I = [l for l in r.splitlines() if l.strip().startswith('I:')][-1].split()[1]
    P = [l for l in r.splitlines() if l.strip().startswith('Peak:')][-1].split()[1]
    mb = os.path.getsize(final) / 1e6
    print(f'✓ final.mp4 · {DUR:.1f} ث · {FPS} إطار · {mb:.1f} ميقا · الصوت {I} LUFS · الذروة {P} dBFS')

workers = a.workers or max(1, min(4, (os.cpu_count() or 2) // 2))
if a.mode == 'preview':
    pv = os.path.join(W, 'prev'); os.makedirs(pv, exist_ok=True)
    times = a.times or [1, DUR * 0.2, DUR * 0.4, DUR * 0.6, DUR * 0.8, DUR - 1]
    jobs = [(t, os.path.join(pv, f't{t:07.2f}.jpg')) for t in times]
    asyncio.run(run(jobs, min(workers, len(jobs))))
    out = a.out or os.path.join(W, 'sheet.jpg'); sheet([j[1] for j in jobs], times, out); print('✓', out)
else:
    OUT = os.path.join(W, 'out')
    import hashlib   # بصمة للخطة والمحرّك: لو تغيّر إشي (تعديل من المحرر مثلاً) الفريمات القديمة بتنمسح
    h = hashlib.sha1(open(os.path.join(W, 'timeline.json'), 'rb').read())
    for f in ('ritm.js', 'render.html'): h.update(open(os.path.join(ROOT, 'engine', f), 'rb').read())
    STAMP = os.path.join(OUT, '.stamp'); stamp = h.hexdigest()
    old = open(STAMP).read() if os.path.exists(STAMP) else ''
    if a.mode == 'all' and (a.force or (old and old != stamp)):
        if not a.force: print('↻ الخطة تغيّرت من آخر رندر — برسم من جديد', flush=True)
        shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(OUT, exist_ok=True)
    open(STAMP, 'w').write(stamp)   # الرندر الجزئي (range) بيعتمد الباقي زي ما هو
    N = int(math.ceil(DUR * FPS))
    lo, hi = (0, N) if a.mode == 'all' else (int(a.times[0] * FPS), min(N, int(math.ceil(a.times[1] * FPS)) + 1))
    jobs = []
    for i in range(lo, hi):
        pth = os.path.join(OUT, f'{i + 1:05d}.jpg')
        if a.mode == 'all' and os.path.exists(pth) and not a.force: continue
        jobs.append((i / FPS, pth))
    print(f'الرسم: {len(jobs)} فريم · {FPS} إطار · {workers} رسّام', flush=True)
    if jobs: asyncio.run(run(jobs, workers))
    for k in range(N + 1, N + 400):    # فريمات زايدة من رندر أطول قبل
        x = os.path.join(OUT, f'{k:05d}.jpg')
        if os.path.exists(x): os.remove(x)
        else: break
    if a.mode == 'all': encode()
    else: print('✓ انرسمت الفترة. هلقيت: render.py <work> all (بيجمّع بدون ما يعيد الباقي)')

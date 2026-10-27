#!/usr/bin/env python3
"""البي-رول: لقطات حقيقية من مكتبة Pexels (مجانية للاستخدام التجاري) أو من ملفات المستخدم.
الاستخدام:
  python3 broll.py <work> search "man alarm clock" [--n 8]     # مرشّحين + ورقة صور broll/cand_sheet.jpg (شوفها بعينك قبل ما تختار)
  python3 broll.py <work> add <رقم_Pexels | مسار_ملف> <اسم> [--from 0] [--len 4]
  python3 broll.py <work> list
البحث بيحتاج مفتاح Pexels مجاني بمتغيّر PEXELS_API_KEY (pexels.com/api — دقيقة تسجيل).
كل لقطة بتصير: broll/<اسم>.mp4 (1080×1920 · 30 إطار) + فريمات للرندر + لوحة لقطات صغيرة للمحرر."""
import os, sys, json, argparse, subprocess, urllib.request, urllib.parse, shutil
ap = argparse.ArgumentParser()
ap.add_argument('work'); ap.add_argument('cmd', choices=['search', 'add', 'list'])
ap.add_argument('args', nargs='*'); ap.add_argument('--n', type=int, default=8)
ap.add_argument('--from', dest='start', type=float, default=0); ap.add_argument('--len', type=float, default=4)
a = ap.parse_args()
W = os.path.abspath(a.work); B = os.path.join(W, 'broll'); os.makedirs(B, exist_ok=True)
IDX = os.path.join(B, 'index.json')
idx = json.load(open(IDX)) if os.path.exists(IDX) else {}
KEY = os.environ.get('PEXELS_API_KEY', '')

def api(path):
    if not KEY: sys.exit('✗ ناقص مفتاح Pexels: سجّل مجاناً على pexels.com/api وحطه بـ PEXELS_API_KEY — أو استعمل ملفات عندك: broll.py add <مسار> <اسم>')
    req = urllib.request.Request('https://api.pexels.com' + path, headers={'Authorization': KEY, 'User-Agent': 'ritm-ar'})
    return json.load(urllib.request.urlopen(req, timeout=40))

def fetch(u, dst):
    req = urllib.request.Request(u, headers={'User-Agent': 'ritm-ar'})
    with urllib.request.urlopen(req, timeout=120) as r, open(dst, 'wb') as f: shutil.copyfileobj(r, f)

if a.cmd == 'search':
    q = ' '.join(a.args); r = api('/videos/search?' + urllib.parse.urlencode({'query': q, 'orientation': 'portrait', 'per_page': a.n, 'size': 'medium'}))
    C = os.path.join(B, 'cand'); os.makedirs(C, exist_ok=True); cands = []
    for v in r.get('videos', []):
        pic = (v.get('video_pictures') or [{}])[min(3, len(v.get('video_pictures') or [1]) - 1)].get('picture') or v.get('image')
        p = os.path.join(C, f"{v['id']}.jpg")
        try: fetch(pic, p)
        except Exception: continue
        cands.append({'id': v['id'], 'dur': v.get('duration'), 'w': v.get('width'), 'h': v.get('height'), 'by': (v.get('user') or {}).get('name'), 'url': v.get('url'), 'thumb': p})
    json.dump(cands, open(os.path.join(B, 'cand.json'), 'w'), ensure_ascii=False, indent=1)
    from PIL import Image, ImageDraw
    cw, ch, cols = 240, 426, 4; rows = max(1, (len(cands) + cols - 1) // cols)
    sheet = Image.new('RGB', (cw * cols, ch * rows), (0, 0, 0)); d = ImageDraw.Draw(sheet)
    for k, c in enumerate(cands):
        im = Image.open(c['thumb']).convert('RGB'); s = max(cw / im.width, ch / im.height)
        im = im.resize((int(im.width * s) + 1, int(im.height * s) + 1)); x0 = (im.width - cw) // 2; y0 = (im.height - ch) // 2
        sheet.paste(im.crop((x0, y0, x0 + cw, y0 + ch)), ((k % cols) * cw, (k // cols) * ch))
        d.rectangle([(k % cols) * cw, (k // cols) * ch, (k % cols) * cw + 120, (k // cols) * ch + 24], fill=(0, 0, 0))
        d.text(((k % cols) * cw + 6, (k // cols) * ch + 6), f"{c['id']} · {c['dur']}s", fill=(255, 255, 255))
    sheet.save(os.path.join(B, 'cand_sheet.jpg'), quality=85)
    for c in cands: print(f"{c['id']}\t{c['dur']}ث\t{c['w']}x{c['h']}\t{c['by']}")
    print(f"✓ {len(cands)} مرشّح · الورقة: {os.path.join(B, 'cand_sheet.jpg')}")

elif a.cmd == 'add':
    src, name = a.args[0], a.args[1]
    raw = os.path.join(B, f'{name}.src.mp4'); credit = None
    if os.path.exists(src): shutil.copyfile(src, raw); credit = 'ملف المستخدم'
    else:
        v = api(f'/videos/videos/{int(src)}')
        files = [f for f in v.get('video_files', []) if f.get('height') and f.get('width') and f['height'] >= f['width']] or v.get('video_files', [])
        best = min(files, key=lambda f: abs((f.get('height') or 0) - 1920) + (0 if (f.get('height') or 0) >= 1280 else 4000))
        print(f"⏳ بنزّل {best.get('width')}x{best.get('height')} من Pexels…", flush=True); fetch(best['link'], raw)
        credit = f"Pexels · {(v.get('user') or {}).get('name', '')} · {v.get('url', '')}"
    out = os.path.join(B, f'{name}.mp4')
    subprocess.run(['ffmpeg', '-v', 'error', '-ss', str(a.start), '-i', raw, '-t', str(a.len), '-an',
                    '-vf', 'scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:1920,fps=30,format=yuv420p',
                    '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18', '-y', out], check=True)
    fd = os.path.join(B, name); shutil.rmtree(fd, ignore_errors=True); os.makedirs(fd)
    subprocess.run(['ffmpeg', '-v', 'error', '-i', out, '-q:v', '3', '-y', os.path.join(fd, '%05d.jpg')], check=True)
    n = len([x for x in os.listdir(fd) if x.endswith('.jpg')]); m15 = (n + 1) // 2; rows = (m15 + 7) // 8
    subprocess.run(['ffmpeg', '-v', 'error', '-framerate', '30', '-i', os.path.join(fd, '%05d.jpg'), '-vf', f'fps=15,scale=216:384,tile=8x{rows}',
                    '-frames:v', '1', '-q:v', '5', '-y', os.path.join(B, f'{name}_sprite.jpg')], check=True)
    os.remove(raw)
    idx[name] = {'file': f'broll/{name}.mp4', 'frames': n, 'dur': round(n / 30, 2), 'sprite': {'src': f'broll/{name}_sprite.jpg', 'n': m15, 'cols': 8, 'w': 216, 'h': 384}, 'credit': credit}
    json.dump(idx, open(IDX, 'w'), ensure_ascii=False, indent=1)
    print(f"✓ {name}: {n / 30:.1f} ث جاهزة")

else:
    for k, v in idx.items(): print(f"{k}\t{v['dur']}ث\t{v.get('credit') or ''}")

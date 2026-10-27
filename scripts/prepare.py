#!/usr/bin/env python3
"""الخطوة 1: يجهّز مجلد الشغل من فيديو المستخدم.
الاستخدام: python3 prepare.py <الفيديو> <مجلد_الشغل>
- ينسخ الفيديو باسم src.<ext>
- يكشف HDR (آيفون) والفريمات والمقاس والدوران
- يستخرج الصوت a.wav (16k mono) للتفريغ
- يعمل نسخة صغيرة proxy.mp4 للمعاينة وكشف القطعات
- يكتب info.json"""
import sys, os, json, shutil, subprocess

src, work = sys.argv[1], sys.argv[2]
os.makedirs(work, exist_ok=True)
ext = os.path.splitext(src)[1].lower() or '.mp4'
dst = os.path.join(work, 'src' + ext)
if os.path.abspath(src) != os.path.abspath(dst):
    shutil.copyfile(src, dst)

def probe(args):
    return subprocess.run(['ffprobe', '-v', 'error'] + args + [dst], capture_output=True, text=True).stdout

j = json.loads(probe(['-show_streams', '-show_format', '-of', 'json']))
v = next(s for s in j['streams'] if s['codec_type'] == 'video')
num, den = (v.get('avg_frame_rate') or v.get('r_frame_rate') or '30/1').split('/')
fps = float(num) / float(den or 1)
rot = 0
for sd in v.get('side_data_list', []) or []:
    if 'rotation' in sd: rot = int(sd['rotation'])
trc = v.get('color_transfer', '')
info = {
    'src': os.path.basename(dst), 'width': v['width'], 'height': v['height'], 'rotation': rot,
    'fps_src': round(fps, 3), 'duration': float(j['format']['duration']),
    'hdr': trc in ('arib-std-b67', 'smpte2084'), 'transfer': trc, 'primaries': v.get('color_primaries', ''),
    'pix_fmt': v.get('pix_fmt', ''),
}
subprocess.run(['ffmpeg', '-v', 'error', '-i', dst, '-vn', '-ac', '1', '-ar', '16000', '-y', os.path.join(work, 'a.wav')], check=True)
subprocess.run(['ffmpeg', '-v', 'error', '-i', dst, '-vf', 'fps=30,scale=270:-2:flags=fast_bilinear,format=yuv420p',
                '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '26', '-an', '-y', os.path.join(work, 'proxy.mp4')], check=True)
json.dump(info, open(os.path.join(work, 'info.json'), 'w'), indent=1)
print(f"✓ {info['width']}x{info['height']} · {info['duration']:.1f} ث · {info['fps_src']} فريم · HDR={'آه' if info['hdr'] else 'لا'}")

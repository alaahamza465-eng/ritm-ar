#!/usr/bin/env python3
"""القص + الألوان + الصوت بأمر واحد ← clip.mp4 (1080x1920، 30 فريم، ‎-14 LUFS).
الاستخدام: python3 grade_cut.py <work> [--grade none|natural|warm]   (الافتراضي none: ألوان الفيديو زي ما هي) [--crf 16]
- آيفون HDR (HLG/PQ): تحويل صحيح لـ SDR (بدونه الصورة بتطلع باهتة أو محروقة) ثم التدريج.
- warm: تباين أوضح، دفا خفيف على البشرة، أبيض نظيف، فينيت خفيف، حدّة خفيفة.
- الصوت: فلتر همهمة، تخفيف ضجيج خفيف، كمبرسر لطيف، ومعايرة -14 LUFS (نفس علو انستقرام/تيك توك).
القص دقيق على مستوى الفريم، والصوت بنفس الحدود بالضبط فما في انزياح."""
import os, json, argparse, subprocess

ap = argparse.ArgumentParser()
ap.add_argument('work'); ap.add_argument('--grade', default='none', choices=['warm', 'natural', 'none']); ap.add_argument('--crf', type=int, default=16)
a = ap.parse_args()
W = a.work
info = json.load(open(os.path.join(W, 'info.json')))
keeps = json.load(open(os.path.join(W, 'keeps.json')))
src = os.path.join(W, info['src'])

# مقاس عمودي 1080x1920 (قص وسطي لو النسبة مختلفة)
fit = 'scale=1080:1920:force_original_aspect_ratio=increase:flags=spline,crop=1080:1920'
if info['hdr']:
    tin = 'arib-std-b67' if info['transfer'] == 'arib-std-b67' else 'smpte2084'
    base = (f"{fit},zscale=tin={tin}:pin=bt2020:min=bt2020nc:t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,"
            f"tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,format=yuv420p")
else:
    base = f"{fit},format=yuv420p"
GR = {
    'warm': ("eq=contrast=1.08:saturation=1.08:brightness=0.015,"
             "colorbalance=rs=-0.03:bs=0.05:rm=0.025:gm=0.005:bm=-0.02:rh=0.02:gh=0.01:bh=-0.01,"
             "curves=master='0/0.015 0.2/0.17 0.5/0.52 0.8/0.84 1/0.99',vignette=angle=PI/6:mode=forward,unsharp=5:5:0.35:5:5:0"),
    'natural': "eq=contrast=1.04:saturation=1.03,unsharp=5:5:0.3:5:5:0",
    'none': "null",
}[a.grade]
sel = '+'.join(f'between(n,{round(s * 30)},{round(e * 30) - 1})' for s, e in keeps)
vf = f"[0:v]fps=30,select='{sel}',setpts=N/30/TB,{base},{GR},setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709[v]"
parts, labels = [], []
for i, (s, e) in enumerate(keeps):
    S, E = round(s * 30) / 30, round(e * 30) / 30
    parts.append(f"[0:a]atrim=start={S:.5f}:end={E:.5f},asetpts=PTS-STARTPTS,afade=t=in:d=0.008,afade=t=out:st={E - S - 0.008:.5f}:d=0.008[a{i}]")
    labels.append(f'[a{i}]')
af = ';'.join(parts) + ';' + ''.join(labels) + f"concat=n={len(keeps)}:v=0:a=1,highpass=f=75,afftdn=nf=-28:nr=8,acompressor=threshold=-20dB:ratio=2.5:attack=8:release=120:makeup=2[ac]"

print('⏳ الصوت…')
acut = os.path.join(W, 'acut.wav')
subprocess.run(['ffmpeg', '-v', 'error', '-i', src, '-filter_complex', af, '-map', '[ac]', '-ar', '48000', '-ac', '2', '-y', acut], check=True)
r = subprocess.run(['ffmpeg', '-nostats', '-i', acut, '-af', 'loudnorm=I=-14:TP=-1.5:LRA=9:print_format=json', '-f', 'null', '-'], capture_output=True, text=True).stderr
m = json.loads(r[r.rindex('{'):])
amaster = os.path.join(W, 'amaster.wav')
subprocess.run(['ffmpeg', '-v', 'error', '-i', acut, '-af',
                f"loudnorm=I=-14:TP=-1.5:LRA=9:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true,aresample=48000",
                '-y', amaster], check=True)
print('⏳ الصورة (قص + ألوان) — بتاخذ وقت حسب الجهاز…')
subprocess.run(['ffmpeg', '-v', 'error', '-stats', '-i', src, '-i', amaster, '-filter_complex', vf, '-map', '[v]', '-map', '1:a',
                '-c:v', 'libx264', '-preset', 'medium', '-crf', str(a.crf), '-pix_fmt', 'yuv420p', '-r', '30', '-g', '30', '-keyint_min', '30',
                '-color_primaries', 'bt709', '-color_trc', 'bt709', '-colorspace', 'bt709', '-c:a', 'aac', '-b:a', '256k',
                '-movflags', '+faststart', '-shortest', '-y', os.path.join(W, 'clip.mp4')], check=True)
d = float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', os.path.join(W, 'clip.mp4')], capture_output=True, text=True).stdout)
print(f"✓ clip.mp4 · {d:.2f} ث · ألوان: {a.grade}{' (HDR→SDR)' if info['hdr'] else ''}")

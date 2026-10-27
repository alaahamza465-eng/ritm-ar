#!/usr/bin/env python3
"""محرر رِتم: صفحة تعديل بتفتحها من الجوال أو المتصفح، وبتشوف التعديل فوراً بنفس محرّك الرندر.
الاستخدام: python3 editor.py <work> [port]     (الافتراضي 8790)
- الجوال لازم يكون على نفس الواي فاي. الرابط بيطلع بالطرفية.
- التعديلات بتنحفظ بـ timeline.json (ونسخة الأصل timeline.orig.json للرجوع).
- زر «صدّر» بيشغّل render.py all وبيعطيك final.mp4.
⚠ ما فيه كلمة سر: لا تشغّله على شبكة عامة."""
import os, sys, json, re, socket, shutil, subprocess, threading, time
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
W = os.path.abspath(sys.argv[1]); PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8790
JOB = {'running': False, 'log': '', 'done': False, 'ok': None, 'started': 0}

def proxy():
    p = os.path.join(W, 'edit_proxy.mp4'); clip = os.path.join(W, 'clip.mp4')
    if os.path.exists(p) and os.path.getmtime(p) > os.path.getmtime(clip): return
    print('⏳ بجهّز نسخة خفيفة للمعاينة…', flush=True)
    T = json.load(open(os.path.join(W, 'timeline.json'), encoding='utf8'))
    pad = (T.get('outroDur') or 0) + 0.5
    subprocess.run(['ffmpeg', '-v', 'error', '-i', clip, '-vf', f'scale=540:960,fps=30,tpad=stop_mode=clone:stop_duration={pad},format=yuv420p',
                    '-af', f'apad=pad_dur={pad}', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '27', '-g', '15', '-c:a', 'aac', '-b:a', '96k',
                    '-movflags', '+faststart', '-y', p], check=True)

def render_job():
    JOB.update(running=True, done=False, ok=None, log='', started=time.time())
    pr = subprocess.Popen([sys.executable, os.path.join(HERE, 'render.py'), W, 'all'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in pr.stdout: JOB['log'] += line
    pr.wait()
    if pr.returncode == 0: subprocess.run([sys.executable, os.path.join(HERE, 'srt.py'), W])
    JOB.update(running=False, done=True, ok=pr.returncode == 0)

class H(SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
    def end_headers(self): self.send_header('Cache-Control', 'no-store'); self.send_header('Accept-Ranges', 'bytes'); super().end_headers()
    def translate_path(self, path):
        path = path.split('?', 1)[0]
        if path.startswith('/w/'): base, rel = W, path[3:]
        elif path.startswith('/engine/') or path.startswith('/assets/'): base, rel = ROOT, path[1:]
        else: base, rel = os.path.join(ROOT, 'engine'), (path.lstrip('/') or 'editor.html')
        full = os.path.normpath(os.path.join(base, rel))
        return full if full.startswith(base) else os.path.join(base, '__nope__')
    def _json(self, code, obj):
        b = json.dumps(obj, ensure_ascii=False).encode(); self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8'); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        p = self.path.split('?', 1)[0]
        if p == '/api/project':
            T = json.load(open(os.path.join(W, 'timeline.json'), encoding='utf8'))
            O = os.path.join(W, 'timeline.orig.json')
            bi = os.path.join(W, 'broll', 'index.json')
            return self._json(200, {'timeline': T, 'orig': json.load(open(O, encoding='utf8')) if os.path.exists(O) else T,
                                    'broll': json.load(open(bi, encoding='utf8')) if os.path.exists(bi) else {},
                                    'proxy': '/w/edit_proxy.mp4', 'final': os.path.exists(os.path.join(W, 'final.mp4'))})
        if p == '/api/status':
            m = re.findall(r'فريم (\d+)/(\d+)', JOB['log']); pct = (int(m[-1][0]) / int(m[-1][1])) if m else 0
            return self._json(200, {**JOB, 'pct': pct, 'tail': JOB['log'][-600:]})
        rng = self.headers.get('Range')
        if rng:
            f = self.translate_path(self.path)
            if os.path.isfile(f):
                size = os.path.getsize(f); mm = re.match(r'bytes=(\d*)-(\d*)', rng); a = int(mm.group(1) or 0); b = min(int(mm.group(2) or size - 1), size - 1)
                self.send_response(206); self.send_header('Content-Type', self.guess_type(f)); self.send_header('Content-Range', f'bytes {a}-{b}/{size}')
                self.send_header('Content-Length', str(b - a + 1)); self.end_headers()
                with open(f, 'rb') as fh:
                    fh.seek(a); left = b - a + 1
                    while left > 0:
                        d = fh.read(min(65536, left))
                        if not d: break
                        try: self.wfile.write(d)
                        except (BrokenPipeError, ConnectionResetError): return
                        left -= len(d)
                return
        return super().do_GET()
    def do_POST(self):
        p = self.path.split('?', 1)[0]; n = int(self.headers.get('Content-Length') or 0); body = self.rfile.read(n) if n else b'{}'
        if p == '/api/timeline':
            T = json.loads(body.decode('utf8')); f = os.path.join(W, 'timeline.json')
            if os.path.exists(f): shutil.copyfile(f, os.path.join(W, 'timeline.prev.json'))
            json.dump(T, open(f, 'w', encoding='utf8'), ensure_ascii=False, indent=1); return self._json(200, {'ok': True})
        if p == '/api/render':
            if JOB['running']: return self._json(409, {'ok': False, 'msg': 'في رندر شغّال'})
            threading.Thread(target=render_job, daemon=True).start(); return self._json(200, {'ok': True})
        return self._json(404, {'ok': False})

def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try: s.connect(('10.255.255.255', 1)); return s.getsockname()[0]
    except Exception: return '127.0.0.1'
    finally: s.close()

proxy()
srv = ThreadingHTTPServer(('0.0.0.0', PORT), H)
print(f'✓ المحرر شغّال\n  على هالجهاز:  http://localhost:{PORT}\n  من الجوال (نفس الواي فاي):  http://{lan_ip()}:{PORT}', flush=True)
try: srv.serve_forever()
except KeyboardInterrupt: pass

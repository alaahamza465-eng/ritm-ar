/* رِتم — محرّك الرسم
   نفس الملف بيرسم المعاينة بالمحرر والفريمات النهائية بالرندر، فاللي بتشوفه بالمحرر هو اللي بيطلع.
   الإحداثيات دائماً 1080×1920؛ اللوحة الحقيقية ممكن تكون أصغر (المحرر) أو أكبر (4K) عن طريق scale.

   الاستعمال:
     const r = Ritm.create(canvas, timeline, host, {scale:1});
     r.draw(t);
   host: { video(t) → صورة الفيديو المقصوص بهاللحظة (img/canvas/video) أو null
           broll(id, localT) → صورة فريم البي-رول بهاللحظة أو null } */
(function (G) {
  'use strict';
  const W = 1080, H = 1920;
  const clamp = (v, a, b) => v < a ? a : v > b ? b : v;
  const lerp = (a, b, k) => a + (b - a) * k;
  const prog = (t, a, b) => b <= a ? (t >= b ? 1 : 0) : clamp((t - a) / (b - a), 0, 1);
  const smooth = k => k * k * (3 - 2 * k);

  /* Easy Ease زي After Effects (influence 50%): بداية هادية ونهاية هادية لكل حركة */
  const EZ = (() => {
    const N = 1024, L = new Float32Array(N + 1), a = 0.5;
    const bx = u => 3 * a * u * (1 - u) * (1 - u) + 3 * (1 - a) * u * u * (1 - u) + u * u * u;
    for (let i = 0; i <= N; i++) {
      const x = i / N; let lo = 0, hi = 1;
      for (let j = 0; j < 32; j++) { const m = (lo + hi) / 2; if (bx(m) < x) lo = m; else hi = m; }
      const u = (lo + hi) / 2; L[i] = u * u * (3 - 2 * u);
    }
    return k => { k = clamp(k, 0, 1); const f = k * N, i = f | 0; return i >= N ? 1 : L[i] + (L[i + 1] - L[i]) * (f - i); };
  })();

  function hexRgb(h) { h = String(h || '#000').replace('#', ''); if (h.length === 3) h = h.split('').map(c => c + c).join('');
    const n = parseInt(h, 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; }
  const rgba = (h, a) => { const [r, g, b] = hexRgb(h); return `rgba(${r},${g},${b},${a})`; };

  const DEF_THEME = { bg: '#272B71', ink: '#FFFFFF', acc: '#F79210', mut: '#C9CCEA', dark: '#14163D',
    font: 'IBM Plex Sans Arabic', capStyle: 'shadow', handle: '', boxTop: 840, headTop: 0.12, faceY: 0.36 };
  const DEF_KNOBS = { zoom: 1, dissolve: 0.4, box: 0.7 };

  function create(canvas, T, host, opt) {
    opt = opt || {};
    const S = opt.scale || 1;
    canvas.width = Math.round(W * S); canvas.height = Math.round(H * S);
    const X = canvas.getContext('2d');
    let th, kn, CAPS, LAY, BR, PAN, zc = null, dur;

    function load(tl) {
      T = tl;
      th = Object.assign({}, DEF_THEME, T.theme || {});
      kn = Object.assign({}, DEF_KNOBS, T.knobs || {});
      dur = T.dur;
      CAPS = (T.captions || []).filter(c => c.w && c.w.length && c.on !== false);
      LAY = (T.layout || []).filter(l => l.on !== false).slice().sort((a, b) => a.s - b.s);
      BR = (T.broll || []).filter(b => b.on !== false).slice().sort((a, b) => a.s - b.s);
      PAN = (T.panels || []).filter(p => p.on !== false);
      zc = null;
    }
    load(T);
    const F = (w, px) => `${w} ${px}px "${th.font}", "IBM Plex Sans Arabic", "Segoe UI", Tahoma, sans-serif`;

    /* ---------- التخطيط: ملء الشاشة أو «المربع» (رسمة فوق، الوجه بكرت تحت) ---------- */
    const modeAt = t => { let m = 'full'; for (const l of LAY) if (t >= l.s && t < l.e) m = l.mode || 'full'; return m; };
    const topOf = m => m === 'box' ? th.boxTop : 0;
    const oyOf = m => m === 'box' ? th.boxTop - th.headTop * H : 0;
    /* نقاط تغيّر التخطيط (تنحسب مرة وحدة) */
    let EDG = [];
    function buildEdges() {
      const pts = new Set([0]); for (const l of LAY) { pts.add(l.s); pts.add(l.e); }
      let prev = modeAt(0); EDG = [];
      for (const tt of [...pts].sort((a, b) => a - b)) { const m = modeAt(tt + 1e-4); if (m !== prev) { EDG.push([tt, prev, m]); prev = m; } }
    }
    buildEdges();
    /* حالة الكرت بهاللحظة: آخر تغيير + تقدّمه على Easy Ease. الصورة جوّا الكرت بتنزلق معه كقطعة وحدة */
    function layoutState(t) {
      let from = modeAt(0), to = from, at = null;
      for (const e of EDG) if (e[0] <= t) { at = e[0]; from = e[1]; to = e[2]; }
      const k = at == null ? 1 : EZ(prog(t, at, at + kn.box));
      return { from, to, k, top: lerp(topOf(from), topOf(to), k), oy: lerp(oyOf(from), oyOf(to), k) };
    }
    const edgesList = () => EDG;

    /* ---------- الزوم على الكلمات المهمة: منحنى واحد متصل بزنبرك ناعم ---------- */
    function zoomCurve() {
      if (zc) return zc;
      const ev = [{ s: 0, e: 0.45, a: 0.05 }]; let n = 0;
      for (const c of CAPS) for (const w of c.w) {
        if (!w.hot) continue;
        const a = (typeof w.z === 'number' ? w.z : (n % 2 ? 0.10 : 0.085)); n++;
        ev.push({ s: w.s - 0.10, e: Math.max(w.e + 0.26, w.s + 0.5), a });
      }
      const dt = 1 / 240, N = Math.ceil((dur + 4) / dt), out = new Float32Array(N);
      const om = 12; let x = 0, v = 0;
      for (let i = 0; i < N; i++) {
        const t = i * dt; let g = 0;
        for (const h of ev) if (t >= h.s && t < h.e && h.a > g) g = h.a;
        g *= kn.zoom; v += (om * om * (g - x) - 2 * om * v) * dt; x += v * dt; out[i] = x > 0 ? x : 0;
      }
      return (zc = { out, dt });
    }
    function zoomAt(t) { const z = zoomCurve(), f = t / z.dt, i = Math.floor(f);
      if (i <= 0) return z.out[0]; if (i >= z.out.length - 1) return z.out[z.out.length - 1];
      return z.out[i] + (z.out[i + 1] - z.out[i]) * (f - i); }

    /* ---------- البي-رول: ذوبان بـEasy Ease + حركة لقدّام ---------- */
    const joinedNext = i => BR[i + 1] && Math.abs(BR[i + 1].s - BR[i].e) < 0.03;
    const joinedPrev = i => BR[i - 1] && Math.abs(BR[i - 1].e - BR[i].s) < 0.03;
    function brAlpha(i, t) { const b = BR[i], d = kn.dissolve / 2;
      const a = joinedPrev(i) ? smooth(prog(t, b.s - d, b.s + d)) : smooth(prog(t, b.s - d, b.s + d));
      const o = joinedNext(i) ? (t < b.e + d ? 1 : 0) : 1 - smooth(prog(t, b.e - d, b.e + d));
      return a * o; }
    function pushZoom(t) { let z = 0; const d = kn.dissolve / 2;   /* الوجه بيتقدّم شوي وهو يذوب */
      BR.forEach((b, i) => {
        if (!joinedPrev(i) && t < b.e) z = Math.max(z, 0.06 * EZ(prog(t, b.s - d, b.s + d)));
        if (!joinedNext(i) && t >= b.e - d) z = Math.max(z, 0.06 * (1 - EZ(prog(t, b.e - d, b.e + d + 0.35))));
      }); return z; }

    /* ---------- رسم ---------- */
    function cover(img, x, y, w, h) {
      const iw = img.videoWidth || img.naturalWidth || img.width, ih = img.videoHeight || img.naturalHeight || img.height;
      if (!iw || !ih) return; const s = Math.max(w / iw, h / ih), dw = iw * s, dh = ih * s;
      X.drawImage(img, x + (w - dw) / 2, y + (h - dh) / 2, dw, dh); }
    function rr(x, y, w, h, r) { r = Math.min(r, w / 2, h / 2); X.beginPath(); X.moveTo(x + r, y);
      X.arcTo(x + w, y, x + w, y + h, r); X.arcTo(x + w, y + h, x, y + h, r); X.arcTo(x, y + h, x, y, r); X.arcTo(x, y, x + w, y, r); X.closePath(); }
    const dirOf = s => /[\u0600-\u06FF]/.test(String(s)) ? 'rtl' : 'ltr';   /* @حساب أو رابط بيضل من الشمال لليمين */
    function text(s, x, y, px, color, weight, align) { X.save(); X.font = F(weight || 800, px); X.fillStyle = color;
      X.textAlign = align || 'center'; X.textBaseline = 'middle'; X.direction = dirOf(s); X.fillText(s, x, y); X.restore(); }
    function tw(s, px, weight) { X.save(); X.font = F(weight || 800, px); X.direction = dirOf(s); const m = X.measureText(s).width; X.restore(); return m; }
    function check(cx, cy, s, col, k) { X.save(); X.strokeStyle = col; X.lineWidth = s * 0.16; X.lineCap = 'round'; X.lineJoin = 'round';
      const p = [[-0.36, 0.02], [-0.1, 0.28], [0.4, -0.3]], L1 = Math.hypot(0.26, 0.26), L2 = Math.hypot(0.5, 0.58), tot = L1 + L2, d = tot * clamp(k, 0, 1);
      X.beginPath(); X.moveTo(cx + p[0][0] * s, cy + p[0][1] * s);
      if (d <= L1) { const f = d / L1; X.lineTo(cx + lerp(p[0][0], p[1][0], f) * s, cy + lerp(p[0][1], p[1][1], f) * s); }
      else { X.lineTo(cx + p[1][0] * s, cy + p[1][1] * s); const f = (d - L1) / L2; X.lineTo(cx + lerp(p[1][0], p[2][0], f) * s, cy + lerp(p[1][1], p[2][1], f) * s); }
      X.stroke(); X.restore(); }
    function person(cx, cy, r, col) { X.save(); X.fillStyle = col; X.beginPath(); X.arc(cx, cy, r, 0, 7); X.fill();
      X.beginPath(); X.arc(cx, cy, r, 0, 7); X.clip(); X.fillStyle = th.bg;
      X.beginPath(); X.arc(cx, cy - r * 0.2, r * 0.34, 0, 7); X.fill(); X.beginPath(); X.ellipse(cx, cy + r * 0.74, r * 0.62, r * 0.5, 0, 0, 7); X.fill(); X.restore(); }

    function drawVideo(t, ls) {
      const img = host.video && host.video(t); if (!img) return;
      let cz = 0; for (const c of (T.cutzoom || [])) if (t >= c.s && t < c.e) cz = (c.z || 1) - 1;   /* زوم ثابت يتبدّل على القصّات (يخبّي القطع) */
      const z = zoomAt(t) + pushZoom(t) + cz;
      const px = W / 2, py = ls.oy + th.faceY * H;
      X.save(); X.beginPath(); X.rect(0, ls.top, W, H - ls.top); X.clip();
      if (z > 0.0005) { X.translate(px, py); X.scale(1 + z, 1 + z); X.translate(-px, -py); }
      X.drawImage(img, 0, ls.oy, W, H);
      X.restore();
    }
    function drawBroll(t) {
      const d = kn.dissolve / 2;
      BR.forEach((b, i) => {
        if (t < b.s - d || t > b.e + d) return; const al = brAlpha(i, t); if (al <= 0.002) return;
        const img = host.broll && host.broll(b.id, t - (b.s - (b.off || 0))); if (!img) return;
        const p = prog(t, b.s, b.e);
        const z = 1 + 0.08 * (1 - EZ(prog(t, b.s - d, b.s + d + 0.5))) + 0.03 * p + 0.04 * EZ(prog(t, b.e - d, b.e + d)) + zoomAt(t) * 0.7;
        X.save(); X.globalAlpha = al; X.translate(W / 2, H * 0.47); X.scale(z, z); X.translate(-W / 2, -H * 0.47);
        cover(img, 0, 0, W, H); X.restore();
      });
    }

    /* ---------- الكابشن: قطع قصيرة بتطلع رول-أب من ورا خط مخفي ---------- */
    function capAnchor(c) {   /* الوضع اللي بتنكتب فيه القطعة + تأخير دخولها لو المربع بيتحرك */
      const m = modeAt(c.s + 0.01); let delay = 0;
      for (const [at, from, to] of edgesList()) if (from !== to && c.s >= at - 0.06 && c.s < at + kn.box) {
        delay = Math.max(0, (at + (to === 'box' ? kn.box * 0.45 : 0.06)) - c.s); }
      return { m, delay };
    }
    function drawCaption(t, ls) {
      const c = CAPS.find(c => t >= c.s && t < c.e); if (!c) return;
      if (PAN.some(p => p.nocap && t >= p.s && t < p.e)) return;
      const an = capAnchor(c);
      let px = th.capStyle === 'plate' ? 66 : 84;
      const base = an.m === 'box' ? th.boxTop - px * 0.9 - 10 : 1430;
      let maskY = base + px * 0.82;   /* الخط اللي بيطلع من وراه — تحت أذيال الحروف */
      if (an.m === 'box') { if (ls.top < 200) return; maskY = Math.min(maskY, ls.top - 6); }
      const kin = EZ(prog(t, c.s + an.delay, c.s + an.delay + 0.4));
      if (kin <= 0) return;
      const out = 1 - smooth(prog(t, c.e - 0.12, c.e));
      const gap = px * 0.34;
      const widths = c.w.map(w => tw(w.t, px, 900)); let total = widths.reduce((a, b) => a + b, 0) + gap * (c.w.length - 1);
      const maxW = 860; if (total > maxW) { const k = maxW / total; px *= k; widths.forEach((v, i) => widths[i] = v * k); total = maxW; }
      const dy = (1 - kin) * (px * 1.9);
      X.save(); X.globalAlpha = out; X.beginPath(); X.rect(0, 0, W, maskY); X.clip(); X.translate(0, dy);
      if (th.capStyle === 'plate') { X.fillStyle = rgba(th.dark, 0.82); rr(W / 2 - total / 2 - 34, base - px * 0.78, total + 68, px * 1.56, 22); X.fill(); }
      let x = W / 2 + total / 2;   /* من اليمين لليسار */
      c.w.forEach((w, i) => {
        const ww = widths[i], cx = x - ww / 2, spoken = t >= w.s;
        const pulse = w.hot && spoken ? 1 + 0.08 * Math.sin(Math.PI * prog(t, w.s, w.s + 0.36)) : 1;
        X.save(); X.translate(cx, base); X.scale(pulse, pulse);
        X.font = F(900, px); X.textAlign = 'center'; X.textBaseline = 'middle'; X.direction = 'rtl';
        if (th.capStyle !== 'plate') { X.shadowColor = 'rgba(0,0,0,0.55)'; X.shadowBlur = 18 * S; X.shadowOffsetY = 6 * S; }
        X.fillStyle = w.hot && spoken ? th.acc : th.ink; X.fillText(w.t, 0, 0); X.restore();
        x -= ww + gap;
      });
      X.restore();
    }

    /* ---------- رسومات المربع (فوق الكرت) والطبقات ---------- */
    const panelAlpha = (p, t) => { const inA = smooth(prog(t, p.s, p.s + 0.3)); const outA = 1 - smooth(prog(t, p.e - 0.35, p.e)); return inA * outA; };
    const boxReady = (p, t) => p.box === false ? 1 : smooth(prog(t, p.s + kn.box * 0.5, p.s + kn.box));
    const areaB = () => th.boxTop - 200;   /* أسفل منطقة الرسم بالمربع */

    function pList(p, t) {
      const items = p.items || []; const n = items.length; if (!n) return;
      const rowH = Math.min(118, (areaB() - 180) / n - 14), top = 180 + Math.max(0, ((areaB() - 180) - n * (rowH + 14)) / 2);
      items.forEach((it, i) => {
        const at = it.at != null ? it.at : p.s + 0.4 + i * 0.45; if (t < at) return;
        const k = EZ(prog(t, at, at + 0.55)), y = top + i * (rowH + 14) + (1 - k) * 60;
        X.save(); X.globalAlpha *= smooth(prog(t, at, at + 0.3));
        X.fillStyle = th.ink; rr(140, y, 800, rowH, 26); X.fill();
        const cx = 140 + 800 - 62, cy = y + rowH / 2;
        X.fillStyle = it.x ? '#E5484D' : th.acc; X.beginPath(); X.arc(cx, cy, 34, 0, 7); X.fill();
        if (it.x) { const q = EZ(prog(t, at + 0.2, at + 0.5)) * 16; X.strokeStyle = th.ink; X.lineWidth = 7; X.lineCap = 'round'; X.beginPath(); X.moveTo(cx - q, cy - q); X.lineTo(cx + q, cy + q); X.moveTo(cx + q, cy - q); X.lineTo(cx - q, cy + q); X.stroke(); }
        else check(cx, cy, 46, th.ink, EZ(prog(t, at + 0.2, at + 0.55)));
        text(it.t, cx - 66, cy + 2, Math.min(48, rowH * 0.42), th.dark, 800, 'right');
        X.restore();
      });
    }
    function pChat(p, t) {
      const bs = p.bubbles || []; const H0 = 92, G0 = 16, base = areaB() - 40;
      const shown = bs.map((b, i) => b.at != null ? b.at : p.s + 0.4 + i * 0.5).filter(at => t >= at).length; if (!shown) return;
      const ats = bs.map((b, i) => b.at != null ? b.at : p.s + 0.4 + i * 0.5);
      X.save(); X.beginPath(); X.rect(0, 150, W, base + H0 / 2 + 12 - 150); X.clip();
      for (let i = 0; i < shown; i++) {
        const b = bs[i], k = EZ(prog(t, ats[i], ats[i] + 0.5)); let up = 0;
        for (let j = i + 1; j < shown; j++) up += (H0 + G0) * EZ(prog(t, ats[j], ats[j] + 0.5));
        const y = base - up + (1 - k) * 70, me = b.side === 'me', px = 42;
        const w = tw(b.t, px, 800) + 64, avx = me ? 110 : W - 110, bx = me ? avx + 54 : avx - 54 - w;
        X.save(); X.globalAlpha *= smooth(prog(t, ats[i], ats[i] + 0.28));
        person(avx, y, 32, me ? th.acc : (i % 2 ? th.mut : th.ink));
        X.fillStyle = me ? th.acc : th.ink; rr(bx, y - H0 / 2, w, H0, 32); X.fill();
        text(b.t, bx + w / 2, y + 2, px, me ? th.dark : th.dark, 800);
        X.restore();
      }
      X.restore();
    }
    function pStat(p, t) {
      const at = p.at != null ? p.at : p.s + 0.5, k = EZ(prog(t, at, at + (p.dur || 1.2)));
      const v = Math.round(lerp(p.from || 0, p.to || 0, k));
      const s = (p.prefix || '') + v.toLocaleString('en-US') + (p.suffix || '');
      const cy = 180 + (areaB() - 180) * 0.42, land = k >= 1 ? 1 + 0.06 * Math.sin(Math.PI * prog(t, at + (p.dur || 1.2), at + (p.dur || 1.2) + 0.3)) : 1;
      X.save(); X.translate(W / 2, cy); X.scale(land, land); text(s, 0, 0, 190, th.acc, 900); X.restore();
      if (p.label) { X.save(); X.globalAlpha *= smooth(prog(t, at + 0.3, at + 0.7)); text(p.label, W / 2, cy + 150, 52, th.ink, 700); X.restore(); }
    }
    function pWord(p, t) {   /* كلمة كبيرة بالنص */
      const at = p.at != null ? p.at : p.s, k = EZ(prog(t, at, at + 0.45));
      const y = p.box === false ? (p.y || 760) : 180 + (areaB() - 180) / 2;
      X.save(); X.globalAlpha *= smooth(prog(t, at, at + 0.25)); X.translate(W / 2, y); X.scale(lerp(0.85, 1, k), lerp(0.85, 1, k));
      X.shadowColor = 'rgba(0,0,0,0.45)'; X.shadowBlur = 20 * S; text(p.t || '', 0, 0, p.size || 150, p.color === 'ink' ? th.ink : th.acc, 900); X.restore();
    }
    function pTitle(p, t) {   /* أسطر بلوحات بتنسحب ونص بيطلع من تحت — فوق الفيديو أو البي-رول */
      let y = p.y || 1000;
      (p.lines || []).forEach((ln, i) => {
        const at = ln.at != null ? ln.at : p.s + 0.2 + i * 0.35, size = ln.size || (i === 1 ? 140 : 70);
        const h = size * 1.5; if (i > 0) y += h * 0.5;
        const cy = y; y += h * 0.5 + 18; if (t < at) return;
        const w = tw(ln.t, size, 900) + 64, kp = EZ(prog(t, at, at + 0.5)), x1 = W / 2 + w / 2;
        X.save(); X.fillStyle = ln.plate === 'acc' ? th.acc : th.bg; X.fillRect(x1 - w * kp, cy - h / 2, w * kp, h); X.restore();
        const kt = EZ(prog(t, at + 0.1, at + 0.65));
        X.save(); X.beginPath(); X.rect(0, cy - h / 2, W, h); X.clip(); X.translate(0, (1 - kt) * h);
        text(ln.t, W / 2, cy - size * 0.02, size, ln.plate === 'acc' ? th.dark : (ln.color === 'acc' ? th.acc : th.ink), 900); X.restore();
      });
    }
    function pCta(p, t) {   /* زر فوق مع سهم */
      const at = p.at != null ? p.at : p.s, k = EZ(prog(t, at, at + 0.55)); if (k <= 0) return;
      const s = p.t || 'الرابط في البايو', px = 58, w = tw(s, px, 900) + 110, h = 118, y = 330;
      X.save(); X.beginPath(); X.rect(0, y - h / 2 - 90, W, h + 90); X.clip(); X.translate(0, (1 - k) * (h + 90));
      X.save(); X.shadowColor = 'rgba(0,0,0,0.25)'; X.shadowBlur = 24 * S; X.shadowOffsetY = 10 * S; X.fillStyle = th.acc; rr(W / 2 - w / 2, y - h / 2, w, h, h / 2); X.fill(); X.restore();
      text(s, W / 2, y + 4, px, th.dark, 900); X.restore();
      const b = Math.sin((t - at) * 7) * 8, ka = smooth(prog(t, at + 0.3, at + 0.6)); if (ka > 0) { X.save(); X.globalAlpha *= ka; X.strokeStyle = th.acc; X.lineWidth = 12; X.lineCap = 'round'; X.lineJoin = 'round';
        X.beginPath(); X.moveTo(W / 2, y - h / 2 - 22 + b); X.lineTo(W / 2, y - h / 2 - 90 + b); X.moveTo(W / 2 - 30, y - h / 2 - 60 + b); X.lineTo(W / 2, y - h / 2 - 90 + b); X.lineTo(W / 2 + 30, y - h / 2 - 60 + b); X.stroke(); X.restore(); }
    }
    const PANELS = { list: pList, chat: pChat, stat: pStat, word: pWord, title: pTitle, cta: pCta };
    function drawPanels(t, layer) {
      for (const p of PAN) {
        if (t < p.s || t > p.e) continue; const f = PANELS[p.type]; if (!f) continue;
        const inBox = p.box !== false && (p.type === 'list' || p.type === 'chat' || p.type === 'stat' || p.type === 'word');
        if ((layer === 'box') !== inBox) continue;
        X.save(); X.globalAlpha = panelAlpha(p, t) * (inBox ? boxReady(p, t) : 1);
        if (inBox) { X.beginPath(); X.rect(0, 0, W, Math.max(0, layoutState(t).top - 4)); X.clip(); }
        try { f(p, t); } catch (e) { if (G.console) console.error('ritm panel', p.type, e); }
        X.restore();
      }
    }

    /* ---------- الختام ---------- */
    function drawOutro(t) {
      const o = T.outro; if (!o) return; const s = dur, k = q => EZ(prog(t, s + q, s + q + 0.5)), al = q => smooth(prog(t, s + q, s + q + 0.35));
      X.fillStyle = th.bg; X.fillRect(0, 0, W, H);
      const up = (q, f) => { X.save(); X.globalAlpha = al(q); X.translate(0, (1 - k(q)) * 26); f(); X.restore(); };
      if (o.l1) up(0.05, () => text(o.l1, W / 2, 500, 44, th.mut, 700));
      if (o.l2) up(0.12, () => text(o.l2, W / 2, 566, 44, th.mut, 700));
      (o.chips || []).slice(0, 6).forEach((c, i) => up(0.3 + i * 0.1, () => {
        const cx = i % 2 ? 300 : 780, cy = 700 + Math.floor(i / 2) * 106, w = 430, h = 84;
        X.fillStyle = rgba(th.ink, 0.07); rr(cx - w / 2, cy - h / 2, w, h, h / 2); X.fill();
        check(cx + w / 2 - 46, cy, 40, th.acc, k(0.45 + i * 0.1));
        let px = 38; while (tw(c, px, 700) > w - 130 && px > 26) px--;
        text(c, cx + w / 2 - 84, cy + 3, px, th.ink, 700, 'right');
      }));
      if (o.cta) up(0.8, () => text(o.cta, W / 2, 1110, 92, th.ink, 900));
      if (o.word) up(0.95, () => { const px = 96, w = tw(o.word, px, 900) + 90, h = 140, y = 1250;
        X.fillStyle = th.acc; rr(W / 2 - w / 2, y - h / 2, w, h, 36); X.fill(); text(o.word, W / 2, y + 6, px, th.dark, 900); });
      if (o.sub) up(1.1, () => text(o.sub, W / 2, 1390, 44, th.mut, 700));
      if (th.handle) up(1.25, () => text(th.handle, W / 2, 1520, 36, th.ink, 700));
    }

    function draw(t) {
      X.setTransform(S, 0, 0, S, 0, 0); X.globalAlpha = 1; X.shadowColor = 'transparent'; X.shadowBlur = 0; X.shadowOffsetY = 0;
      X.fillStyle = th.bg; X.fillRect(0, 0, W, H);
      if (t >= dur) {   /* الختام بيطلع من تحت فوق آخر لقطة — مش قطع مفاجئ */
        const k = EZ(prog(t, dur, dur + 0.5));
        if (k < 1) { const t0 = dur - 0.001; drawVideo(t0, layoutState(t0)); X.save(); X.beginPath(); X.rect(0, H * (1 - k), W, H * k); X.clip(); drawOutro(t); X.restore(); }
        else drawOutro(t);
        return; }
      const ls = layoutState(t);
      drawVideo(t, ls);
      drawPanels(t, 'box');
      drawBroll(t);
      drawPanels(t, 'over');
      drawCaption(t, ls);
    }
    return { draw, load(tl) { load(tl); buildEdges(); }, get timeline() { return T; }, W, H, EZ };
  }
  G.Ritm = { create, EZ };
})(typeof window !== 'undefined' ? window : globalThis);

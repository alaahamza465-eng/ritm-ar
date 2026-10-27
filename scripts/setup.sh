#!/usr/bin/env bash
# تجهيز رِتم مرة وحدة: بيفحص ffmpeg وبايثون، وبينزّل المكتبات، وبيولّد الأصوات.
# الاستخدام:  bash scripts/setup.sh
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(dirname "$HERE")"
ok(){ printf '  ✓ %s\n' "$1"; }; no(){ printf '  ✗ %s\n' "$1"; }

echo "▸ بفحص الأدوات…"
if command -v ffmpeg >/dev/null 2>&1; then ok "ffmpeg"; else
  no "ffmpeg مش موجود"
  echo "    ماك:     brew install ffmpeg"
  echo "    ويندوز:  winget install Gyan.FFmpeg"
  echo "    لينكس:   sudo apt install ffmpeg"
  exit 1; fi
PY=python3; command -v $PY >/dev/null 2>&1 || PY=python
if ! $PY -c 'import sys; sys.exit(0 if sys.version_info>=(3,9) else 1)' 2>/dev/null; then no "بدك Python 3.9 أو أحدث"; exit 1; fi
ok "$($PY --version)"

echo "▸ بنزّل المكتبات (أول مرة بتاخد دقايق)…"
PIP="$PY -m pip install -q"
$PIP faster-whisper numpy pillow playwright 2>/dev/null || $PIP --break-system-packages faster-whisper numpy pillow playwright
ok "faster-whisper · numpy · pillow · playwright"

echo "▸ بجهّز متصفح الرندر…"
if $PY - <<'EOF' 2>/dev/null
from playwright.sync_api import sync_playwright
with sync_playwright() as p: p.chromium.launch().close()
EOF
then ok "Chromium جاهز"; else $PY -m playwright install chromium && ok "Chromium انتزل"; fi

echo "▸ بولّد الأصوات الخفيفة…"
$PY "$HERE/make_sfx.py" "$ROOT/assets/sfx" >/dev/null && ok "assets/sfx"

echo ""
echo "✓ رِتم جاهز. ابعت فيديو لـ Claude واحكيله «منتج هالفيديو برِتم»."
[ -z "$PEXELS_API_KEY" ] && echo "  (اختياري) للبي-رول من Pexels: سجّل مفتاح مجاني على pexels.com/api وحطه بـ PEXELS_API_KEY"
exit 0

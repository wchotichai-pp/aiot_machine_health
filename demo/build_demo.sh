#!/usr/bin/env bash
# สร้างหน้าเดโมจากแดชบอร์ดตัวจริง (gateway/static) + เครื่องจำลองในเบราว์เซอร์ (demo/demo-mock.js)
# ใช้หลัง `mkdocs build` : bash demo/build_demo.sh site
set -euo pipefail
out="${1:-site}/demo"
mkdir -p "$out"
cp gateway/static/index.html gateway/static/style.css gateway/static/app.js "$out/"
cp demo/demo-mock.js "$out/"
# โหลด demo-mock.js ก่อน app.js เพื่อแทนที่ fetch("/api/...")
sed -i 's#<script src="app.js"></script>#<script src="demo-mock.js"></script>\n  <script src="app.js"></script>#' "$out/index.html"
grep -q 'demo-mock.js' "$out/index.html" || { echo "ใส่ demo-mock.js ไม่สำเร็จ" >&2; exit 1; }
echo "demo -> $out"

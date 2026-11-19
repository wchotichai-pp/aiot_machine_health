// Telegram Mini App: แดชบอร์ดสุขภาพเครื่องจักร
const tg = window.Telegram?.WebApp;
const inTelegram = Boolean(tg && tg.initData);
const POLL_MS = 2000;
const STATE_COLOR = { normal: "green", warning: "yellow", alarm: "red", learning: "white", maintenance: "blue" };

if (inTelegram) {
  tg.ready();
  tg.expand();
  const u = tg.initDataUnsafe?.user;
  if (u) document.getElementById("greet").textContent = `สวัสดี ${u.first_name} · AIoT Machine Health`;
}

const $ = (id) => document.getElementById(id);
let current = null;      // device_id ที่เลือก
let busy = false;

// เปิดนอก Telegram (เช่นจอในห้องควบคุม) ใช้ API_KEY แทน เก็บไว้ในเบราว์เซอร์เครื่องนี้เท่านั้น
let apiKey = "";
try { apiKey = localStorage.getItem("aiot_api_key") || ""; } catch {}

function headers(extra = {}) {
  const h = { "X-Tunnel-Skip-AntiPhishing-Page": "true", ...extra };
  if (inTelegram) h["X-Telegram-Init-Data"] = tg.initData;   // gateway ตรวจลายเซ็นนี้
  else if (apiKey) h["X-API-Key"] = apiKey;
  return h;
}

async function api(path, opts = {}) {
  const res = await fetch(path, { cache: "no-store", ...opts, headers: headers(opts.headers) });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try { detail = (await res.json()).detail || detail; } catch {}
    const err = new Error(detail); err.status = res.status; throw err;
  }
  return res.json();
}

const fmt = (v, d = 2) => (v == null ? "--" : Number(v).toFixed(d));
const hhmm = (ts) => new Date(ts * 1000).toLocaleTimeString("th-TH", { hour: "2-digit", minute: "2-digit" });

function setConn(ok, text) {
  $("conn").className = "conn " + (ok ? "ok" : "bad");
  $("conn").querySelector("b").textContent = text;
}

function renderMachines(list) {
  const sel = $("machine");
  const ids = list.map((m) => m.device_id);
  if (sel.options.length !== ids.length || [...sel.options].some((o, i) => o.value !== ids[i])) {
    sel.innerHTML = ids.map((d) => `<option value="${d}">${d}</option>`).join("");
  }
  if (!current || !ids.includes(current)) current = ids[0];
  sel.value = current;
  sel.disabled = ids.length < 2;
}

function renderSnapshot(s) {
  const color = STATE_COLOR[s.state] || "white";
  $("hero").className = `hero c-${color} ${s.state || ""}`;
  $("state").textContent = s.online ? s.state_th : `${s.state_th} (ออฟไลน์)`;
  let reason = s.reason || "ยังไม่มีข้อมูลจากบอร์ด";
  if (s.mode === "learning") reason = `กำลังเรียนรู้ค่าปกติ ${s.learn_progress}/${s.learn_target} ค่า — ห้ามแตะเครื่อง`;
  $("reason").textContent = reason;

  const x = s.latest || {};
  $("rms").textContent = fmt(x.vib_rms);
  $("peak").textContent = x.vib_peak == null ? "--" : `${fmt(x.vib_peak)} m/s²`;
  $("temp").textContent = x.temp == null ? "--" : `${fmt(x.temp, 1)} °C`;
  $("rssi").textContent = x.rssi == null ? "--" : `${x.rssi} dBm`;

  const th = s.thresholds;
  $("th-warn").textContent = fmt(th.warn);
  $("th-alarm").textContent = fmt(th.alarm);
  $("th-src").textContent = th.source === "default" ? "(เกณฑ์เริ่มต้น)" : "";
  $("baseline").textContent = s.baseline_rms == null
    ? "ยังไม่ได้เรียนรู้ — กด \"เรียนรู้ค่าปกติ\" ตอนเครื่องทำงานปกติ"
    : `${fmt(s.baseline_rms, 3)} m/s²`;

  document.querySelectorAll("#seg button").forEach((b) => b.classList.toggle("on", b.dataset.level === s.sensitivity));
}

function renderChart(items, th) {
  const svg = $("chart");
  const W = 320, H = 140, top = 6, bottom = 18;
  const vals = items.map((r) => r.vib_rms);
  const maxV = Math.max(th.alarm * 1.15, ...vals, 0.1);
  const y = (v) => top + (H - top - bottom) * (1 - v / maxV);
  let out = "";
  [0.25, 0.5, 0.75, 1].forEach((f) => { out += `<line class="grid" x1="0" x2="${W}" y1="${y(maxV * f)}" y2="${y(maxV * f)}"/>`; });
  out += `<line class="th warn" x1="0" x2="${W}" y1="${y(th.warn)}" y2="${y(th.warn)}"/>`;
  out += `<line class="th alarm" x1="0" x2="${W}" y1="${y(th.alarm)}" y2="${y(th.alarm)}"/>`;
  if (items.length > 1) {
    const t0 = items[0].ts, t1 = items[items.length - 1].ts, span = Math.max(t1 - t0, 1);
    // ข้อมูลขาดช่วงเกิน 5 วินาที (บอร์ดหลุด) = เริ่มเส้นใหม่ ไม่ลากเส้นเชื่อม
    const d = items.map((r, i) => {
      const gap = i === 0 || r.ts - items[i - 1].ts > 5;
      return `${gap ? "M" : "L"}${((r.ts - t0) / span * W).toFixed(1)},${y(r.vib_rms).toFixed(1)}`;
    }).join(" ");
    out += `<path class="line" d="${d}"/>`;
    out += `<text class="tick" x="0" y="${H - 4}">${hhmm(t0)}</text>`;
    out += `<text class="tick" x="${W}" y="${H - 4}" text-anchor="end">${hhmm(t1)}</text>`;
  } else {
    out += `<text class="tick" x="${W / 2}" y="${H / 2}" text-anchor="middle">รอข้อมูล…</text>`;
  }
  out += `<text class="tick" x="2" y="${y(maxV) + 9}">${maxV.toFixed(2)}</text>`;
  svg.innerHTML = out;
}

function renderEvents(items) {
  const ol = $("events");
  if (!items.length) { ol.innerHTML = `<li class="empty">ยังไม่มีเหตุการณ์</li>`; return; }
  ol.innerHTML = items.slice(-8).reverse().map((e) => {
    const li = document.createElement("li");
    li.innerHTML = `<time></time><span></span>`;
    li.querySelector("time").textContent = hhmm(e.ts);
    li.querySelector("span").textContent = e.message;     // textContent กันข้อความแปลก ๆ กลายเป็น HTML
    return li.outerHTML;
  }).join("");
}

async function refresh() {
  try {
    const list = await api("/api/machines");
    if (!list.length) {
      $("main").hidden = true;
      $("notice").textContent = "ยังไม่มีเครื่องจักรส่งข้อมูลเข้ามา — เปิดบอร์ดหรือตัวจำลองก่อน";
      setConn(true, "ออนไลน์");
      return;
    }
    renderMachines(list);
    const [snap, hist, ev] = await Promise.all([
      api(`/api/machines/${current}`),
      api(`/api/machines/${current}/history?minutes=10`),
      api(`/api/events?limit=20&device_id=${current}`),
    ]);
    renderSnapshot(snap);
    renderChart(hist.items, snap.thresholds);
    renderEvents(ev.items);
    $("main").hidden = false;
    $("keyform").hidden = true;
    $("notice").textContent = "อัปเดตล่าสุด " + new Date().toLocaleTimeString("th-TH");
    setConn(true, "ออนไลน์");
  } catch (err) {
    setConn(false, "ออฟไลน์");
    if (err.status === 401 && !inTelegram) {
      $("main").hidden = true;
      $("keyform").hidden = false;
    }
    $("notice").textContent = err.status === 401
      ? (inTelegram ? "Telegram ส่งข้อมูลยืนยันตัวตนไม่ผ่าน ลองปิดแล้วเปิดใหม่" : (apiKey ? "API_KEY ไม่ถูกต้อง" : "ต้องยืนยันตัวตนก่อน"))
      : err.status === 403 ? "บัญชีนี้ไม่มีสิทธิ์ดูข้อมูล (ไม่อยู่ใน ALLOWED_USER_IDS)" : `เชื่อมต่อเซิร์ฟเวอร์ไม่ได้ (${err.message})`;
  }
}

$("keyform").addEventListener("submit", (e) => {
  e.preventDefault();
  apiKey = $("keyinput").value.trim();
  try { localStorage.setItem("aiot_api_key", apiKey); } catch {}
  refresh();
});

function confirmThen(text, fn) {
  if (inTelegram && tg.showConfirm) tg.showConfirm(text, (ok) => ok && fn());
  else if (window.confirm(text)) fn();
}

async function send(cmd) {
  if (busy) return;
  busy = true;
  document.querySelectorAll("button").forEach((b) => (b.disabled = true));
  try {
    const r = await api("/api/command", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...cmd, device_id: current }),
    });
    tg?.HapticFeedback?.notificationOccurred("success");
    if (inTelegram && tg.showAlert) tg.showAlert(r.reply); else $("notice").textContent = r.reply;
  } catch (err) {
    tg?.HapticFeedback?.notificationOccurred("error");
    $("notice").textContent = `สั่งงานไม่สำเร็จ: ${err.message}`;
  } finally {
    busy = false;
    document.querySelectorAll("button").forEach((b) => (b.disabled = false));
    refresh();
  }
}

const CONFIRM = {
  learn_baseline: "เรียนรู้ค่าปกติใหม่? ให้เครื่องทำงานปกติประมาณ 30 วินาที และห้ามแตะเครื่อง",
  maintenance: "เข้าโหมดซ่อมบำรุง 30 นาที? ระหว่างนี้จะไม่แจ้งเตือน",
  resume: "กลับมาเฝ้าระวังตอนนี้?",
};
document.querySelectorAll("[data-cmd]").forEach((b) => b.addEventListener("click", () => {
  const intent = b.dataset.cmd;
  confirmThen(CONFIRM[intent], () => send(intent === "maintenance" ? { intent, minutes: 30 } : { intent }));
}));
document.querySelectorAll("[data-level]").forEach((b) => b.addEventListener("click", () => {
  tg?.HapticFeedback?.selectionChanged();
  send({ intent: "set_sensitivity", level: b.dataset.level });
}));
$("machine").addEventListener("change", (e) => { current = e.target.value; refresh(); });

refresh();
setInterval(refresh, POLL_MS);

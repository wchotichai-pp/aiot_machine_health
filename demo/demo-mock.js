// โหมดเดโมสำหรับ GitHub Pages
// แทนที่ fetch("/api/...") ด้วยเครื่องจำลองในเบราว์เซอร์ จึงเปิดแดชบอร์ดตัวจริง (gateway/static) ได้โดยไม่ต้องมีบอร์ดหรือเซิร์ฟเวอร์
// กฎตัดสินสถานะแปลงมาจาก gateway/app/rules.py (ค่าเริ่มต้นเดียวกัน) เพื่อให้พฤติกรรมเหมือนระบบจริง
(() => {
  "use strict";

  const DEVICE = "demo-01";
  const P = { defWarn: 1.0, defAlarm: 2.5, minWarn: 0.15, tempWarn: 45, tempAlarm: 55, learnN: 30, esc: 3, rec: 5 };
  const SENS = { low: [2.5, 5.0], normal: [2.0, 4.0], high: [1.5, 3.0] };
  const LED = { normal: "green", warning: "yellow", alarm: "red", learning: "white", maintenance: "blue" };
  const TH = { normal: "ปกติ", warning: "เฝ้าระวัง", alarm: "อันตราย", learning: "กำลังเรียนรู้ค่าปกติ", maintenance: "โหมดซ่อมบำรุง" };
  const LEVEL_TH = { low: "ต่ำ", normal: "ปกติ", high: "สูง" };
  const RANK = { normal: 0, warning: 1, alarm: 2 };
  // เหมือน simulator/simulate_machine.py: (ตัวคูณการสั่น, โอกาสกระชาก, อุณหภูมิเพิ่ม)
  const SCENARIOS = { normal: [1.0, 0.0, 0.0], imbalance: [2.6, 0.02, 3.0], fault: [5.5, 0.15, 14.0] };
  const BASE_RMS = 0.25;

  const cfg = { mode: "monitor", baseline: 0.25, sensitivity: "normal", maintUntil: null };
  const tr = { state: "normal", nAlarm: 0, nWarn: 0, nNormal: 0, nBelowAlarm: 0, learn: [] };
  const history = [];
  const events = [];
  let eventId = 0, seq = 0, temp = 31, scenario = "normal", last = null, decision = null;

  const r4 = (x) => Math.round(x * 1e4) / 1e4;
  const uni = (a, b) => a + Math.random() * (b - a);

  function thresholds() {
    if (cfg.baseline == null) return { warn: P.defWarn, alarm: P.defAlarm, source: "default" };
    const [wk, ak] = SENS[cfg.sensitivity];
    const warn = Math.max(cfg.baseline * wk, P.minWarn);
    const alarm = Math.max(cfg.baseline * ak, warn * 1.5);
    return { warn: r4(warn), alarm: r4(alarm), source: "baseline" };
  }

  function rawLevel(v, t, th) {
    if (v >= th.alarm) return ["alarm", `การสั่น ${v.toFixed(2)} m/s² ถึงเกณฑ์อันตราย ${th.alarm.toFixed(2)}`];
    if (t >= P.tempAlarm) return ["alarm", `อุณหภูมิ ${t.toFixed(1)} °C ถึงเกณฑ์อันตราย ${P.tempAlarm}`];
    if (v >= th.warn) return ["warning", `การสั่น ${v.toFixed(2)} m/s² ถึงเกณฑ์เฝ้าระวัง ${th.warn.toFixed(2)}`];
    if (t >= P.tempWarn) return ["warning", `อุณหภูมิ ${t.toFixed(1)} °C ถึงเกณฑ์เฝ้าระวัง ${P.tempWarn}`];
    return ["normal", `การสั่น ${v.toFixed(2)} m/s² ต่ำกว่าเกณฑ์เฝ้าระวัง ${th.warn.toFixed(2)}`];
  }

  function addEvent(ts, kind, state, message) {
    events.push({ id: ++eventId, device_id: DEVICE, ts, kind, state, message });
    if (events.length > 200) events.shift();
  }

  function decide(v, t, now) {
    if (cfg.mode === "maintenance") {
      if (now >= cfg.maintUntil) {
        cfg.mode = "monitor"; cfg.maintUntil = null;
        addEvent(now, "mode", null, "หมดเวลาโหมดซ่อมบำรุง กลับมาเฝ้าระวังอัตโนมัติ");
      } else {
        const left = Math.floor((cfg.maintUntil - now) / 60) + 1;
        return { state: "maintenance", reason: `โหมดซ่อมบำรุง เหลืออีกประมาณ ${left} นาที` };
      }
    }
    if (cfg.mode === "learning") {
      tr.learn.push(v);
      if (tr.learn.length < P.learnN) {
        return { state: "learning", reason: `เก็บค่าปกติแล้ว ${tr.learn.length}/${P.learnN} ค่า` };
      }
      const s = [...tr.learn].sort((a, b) => a - b), m = s.length >> 1;
      cfg.baseline = r4(s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2);
      tr.learn = []; cfg.mode = "monitor";
      Object.assign(tr, { state: "normal", nAlarm: 0, nWarn: 0, nNormal: 0, nBelowAlarm: 0 });
      const th = thresholds();
      addEvent(now, "baseline", "normal",
        `เรียนรู้ค่าปกติเสร็จ: ${cfg.baseline.toFixed(3)} m/s² (เกณฑ์เฝ้าระวัง ${th.warn.toFixed(2)}, อันตราย ${th.alarm.toFixed(2)})`);
    }
    const th = thresholds();
    let [level, reason] = rawLevel(v, t, th);
    tr.nAlarm = level === "alarm" ? tr.nAlarm + 1 : 0;
    tr.nWarn = level !== "normal" ? tr.nWarn + 1 : 0;
    tr.nNormal = level === "normal" ? tr.nNormal + 1 : 0;
    tr.nBelowAlarm = level !== "alarm" ? tr.nBelowAlarm + 1 : 0;
    const prev = tr.state;
    let next = prev;
    if (tr.nAlarm >= P.esc) next = "alarm";
    else if (prev === "alarm" && tr.nBelowAlarm >= P.rec) next = tr.nNormal >= P.rec ? "normal" : "warning";
    else if (prev === "normal" && tr.nWarn >= P.esc) next = "warning";
    else if (prev === "warning" && tr.nNormal >= P.rec) next = "normal";
    if (next !== prev) {
      tr.state = next;
      const arrow = RANK[next] > RANK[prev] ? "เพิ่มขึ้น" : "ลดลง";
      addEvent(now, "state", next, `สถานะ${arrow}: ${TH[prev]} → ${TH[next]} (${reason})`);
    } else if (next !== level) {
      reason += ` — รอยืนยัน (สถานะยังเป็น${TH[next]})`;
    }
    return { state: next, reason };
  }

  function tick(now) {
    const [k, spikeP, dT] = SCENARIOS[scenario];
    let rms = BASE_RMS * k * uni(0.9, 1.1);
    let peak = rms * uni(2.6, 3.2);
    if (Math.random() < spikeP) { peak *= uni(1.8, 2.5); rms *= 1.3; }
    temp += (31 + dT - temp) * 0.05;
    last = {
      seq: seq++, vib_rms: r4(rms), vib_peak: r4(peak), temp: Math.round((temp + uni(-0.1, 0.1)) * 100) / 100,
      hum: Math.round((55 + 3 * Math.sin(seq / 60)) * 10) / 10, rssi: Math.round(uni(-62, -50)),
    };
    decision = decide(last.vib_rms, last.temp, now);
    history.push({ id: seq, device_id: DEVICE, ts: now, ...last, state: decision.state });
    if (history.length > 900) history.shift();
  }

  function snapshot() {
    const state = decision.state;
    return {
      device_id: DEVICE, online: true, last_seen: Date.now() / 1000,
      state, state_th: TH[state], led: LED[state], reason: decision.reason,
      mode: cfg.mode, sensitivity: cfg.sensitivity, baseline_rms: cfg.baseline,
      maintenance_until: cfg.maintUntil,
      learn_progress: cfg.mode === "learning" ? tr.learn.length : null, learn_target: P.learnN,
      thresholds: { ...thresholds(), temp_warn: P.tempWarn, temp_alarm: P.tempAlarm },
      latest: last,
    };
  }

  // ---------- คำสั่ง (allowlist เดียวกับ gateway/app/commands.py) ----------
  function command(body) {
    const intent = body && body.intent;
    const now = Date.now() / 1000;
    let reply;
    if (intent === "learn_baseline") {
      cfg.mode = "learning"; tr.learn = [];
      reply = `⚪ เริ่มเรียนรู้ค่าปกติของ ${DEVICE} (${P.learnN} ค่า ประมาณ ${P.learnN} วินาที)\nระหว่างนี้ให้เครื่องทำงานตามปกติ ห้ามแตะหรือเคาะเครื่อง`;
    } else if (intent === "maintenance") {
      const minutes = body.minutes == null ? 30 : body.minutes;
      if (!Number.isInteger(minutes) || minutes < 5 || minutes > 240) return [422, { detail: "คำสั่งไม่อยู่ใน allowlist: minutes ต้องอยู่ระหว่าง 5–240" }];
      cfg.mode = "maintenance"; cfg.maintUntil = now + minutes * 60;
      reply = `🔵 ${DEVICE} เข้าโหมดซ่อมบำรุง ${minutes} นาที ระหว่างนี้จะไม่แจ้งเตือน`;
    } else if (intent === "resume") {
      cfg.mode = "monitor"; cfg.maintUntil = null; tr.learn = [];
      reply = `🟢 ${DEVICE} กลับมาเฝ้าระวังแล้ว`;
    } else if (intent === "set_sensitivity" && SENS[body.level]) {
      cfg.sensitivity = body.level;
      const th = thresholds();
      reply = `ปรับความไวของ ${DEVICE} เป็น${LEVEL_TH[body.level]}แล้ว\nเกณฑ์เฝ้าระวัง ${th.warn.toFixed(2)} m/s² · อันตราย ${th.alarm.toFixed(2)} m/s²`;
    } else {
      return [422, { detail: "คำสั่งไม่อยู่ใน allowlist" }];
    }
    addEvent(now, "mode", null, reply.split("\n")[0]);
    return [200, { reply, command: body }];
  }

  // ---------- แทนที่ fetch ----------
  const realFetch = window.fetch.bind(window);
  window.fetch = async (input, opts = {}) => {
    const url = new URL(typeof input === "string" ? input : input.url, location.href);
    const m = url.pathname.match(/\/api\/(.+)$/);
    if (!m) return realFetch(input, opts);
    const path = m[1], q = url.searchParams;
    let status = 200, body;
    if (path === "health") body = { ok: true, mode: "demo" };
    else if (path === "machines") body = [snapshot()];
    else if (path === `machines/${DEVICE}`) body = snapshot();
    else if (path === `machines/${DEVICE}/history`) {
      const since = Date.now() / 1000 - Number(q.get("minutes") || 10) * 60;
      body = { device_id: DEVICE, items: history.filter((h) => h.ts >= since) };
    } else if (path === "events") {
      const limit = Number(q.get("limit") || 50);
      body = { last_id: eventId, items: events.slice(-limit) };
    } else if (path === "command" && (opts.method || "GET").toUpperCase() === "POST") {
      [status, body] = command(JSON.parse(opts.body || "{}"));
    } else { status = 404; body = { detail: "ไม่พบ" }; }
    return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
  };

  // ---------- เริ่มต้น: ย้อนเวลาสร้างข้อมูล 3 นาทีให้กราฟมีเส้น ----------
  const start = Date.now() / 1000;
  for (let i = 180; i > 0; i--) tick(start - i);
  addEvent(start - 180, "baseline", "normal", "เรียนรู้ค่าปกติเสร็จ: 0.250 m/s² (เกณฑ์เฝ้าระวัง 0.50, อันตราย 1.00)");
  setInterval(() => tick(Date.now() / 1000), 1000);

  // ---------- แถบเดโมด้านบน ----------
  const LABEL = { normal: "ปกติ", imbalance: "เสียสมดุล", fault: "ชำรุด" };
  function banner() {
    const css = document.createElement("style");
    css.textContent = `
      .demo-bar { background: var(--card); border: 1px dashed var(--accent); border-radius: 14px; padding: 12px; margin-bottom: 14px; font-size: 13px; }
      .demo-bar b { display: block; margin-bottom: 2px; }
      .demo-bar p { color: var(--muted); margin-bottom: 8px; }
      .demo-bar .seg { margin-top: 0; }
      .demo-bar a { color: var(--accent); }`;
    document.head.appendChild(css);
    const bar = document.createElement("section");
    bar.className = "demo-bar";
    bar.innerHTML = `<b>โหมดเดโม</b>
      <p>ข้อมูลจำลองในเบราว์เซอร์ ไม่ได้ต่อบอร์ดจริง กดเลือกสภาพเครื่องแล้วรอประมาณ 3 วินาที สถานะจะเปลี่ยนตามกฎเดียวกับระบบจริง
      · <a href="../">กลับไปหน้าบทเรียน</a></p>
      <div class="seg" role="group" aria-label="จำลองสภาพเครื่อง">
        ${Object.keys(LABEL).map((s) => `<button type="button" data-scenario="${s}">${LABEL[s]}</button>`).join("")}
      </div>`;
    document.body.insertBefore(bar, document.body.firstChild);
    const paint = () => bar.querySelectorAll("[data-scenario]").forEach((b) => b.classList.toggle("on", b.dataset.scenario === scenario));
    bar.addEventListener("click", (e) => {
      const b = e.target.closest("[data-scenario]");
      if (b) { scenario = b.dataset.scenario; paint(); }
    });
    paint();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", banner);
  else banner();
})();

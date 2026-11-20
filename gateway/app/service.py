"""รวมทุกส่วน: รับค่าจากบอร์ด -> ตัดสินด้วยกฎ -> บันทึก -> ตอบกลับ / ทำตามคำสั่ง"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field

from . import replies
from .commands import Command, parse_rules
from .llm import OllamaTranslator, TranslatorError
from .protocol import StateMessage, Telemetry
from .rules import STATE_TH, Decision, MachineConfig, Policy, Tracker, decide, thresholds
from .store import Store

log = logging.getLogger("gateway")


@dataclass
class Machine:
    device_id: str
    cfg: MachineConfig = field(default_factory=MachineConfig)
    tracker: Tracker = field(default_factory=Tracker)
    last_seen: float | None = None
    online: bool | None = None          # จาก Last Will (None = ยังไม่รู้)
    last_decision: Decision | None = None
    last_telemetry: Telemetry | None = None


@dataclass
class ChatResult:
    reply: str
    command: dict
    source: str            # "ai" | "rule" | "rule_fallback"
    engine: str | None
    error: str | None = None


class MachineService:
    def __init__(self, store: Store, policy: Policy, translator: OllamaTranslator | None,
                 offline_after_s: int = 15, clock=time.time):
        self.store = store
        self.policy = policy
        self.translator = translator
        self.offline_after_s = offline_after_s
        self.clock = clock
        self._lock = threading.RLock()
        self.machines: dict[str, Machine] = {
            d: Machine(d, MachineConfig.from_dict(c)) for d, c in store.load_machines().items()
        }
        self.on_event = None   # callback(device_id, kind, state, message) สำหรับส่ง MQTT alert

    # ------------------------------------------------------------------ บอร์ด
    def _machine(self, device_id: str) -> Machine:
        m = self.machines.get(device_id)
        if m is None:
            m = Machine(device_id)
            self.machines[device_id] = m
            self.store.save_machine(device_id, m.cfg.to_dict())
            log.info("พบเครื่องใหม่: %s", device_id)
        return m

    def handle_telemetry(self, t: Telemetry) -> StateMessage:
        now = self.clock()
        with self._lock:
            m = self._machine(t.device_id)
            before = m.cfg.to_dict()
            d = decide(m.cfg, m.tracker, t.vib_rms, t.temp, now, self.policy)
            m.last_seen, m.last_decision, m.last_telemetry = now, d, t
            if m.online is None:
                m.online = True
            if m.cfg.to_dict() != before:
                self.store.save_machine(t.device_id, m.cfg.to_dict())
            self.store.add_reading(t.device_id, now, t.seq, t.vib_rms, t.vib_peak,
                                   t.temp, t.hum, t.rssi, d.state)
            for kind, msg in d.events:
                self._event(t.device_id, kind, d.state, msg)
        return StateMessage(device_id=t.device_id, seq=t.seq, state=d.state, led=d.led, reason=d.reason)

    def set_online(self, device_id: str, online: bool) -> None:
        with self._lock:
            m = self._machine(device_id)
            if m.online is not online:
                m.online = online
                self._event(device_id, "connection", None,
                            "บอร์ดเชื่อมต่อแล้ว" if online else "บอร์ดขาดการเชื่อมต่อ")

    def _event(self, device_id: str, kind: str, state: str | None, message: str) -> None:
        self.store.add_event(device_id, self.clock(), kind, state, message)
        log.info("[%s] %s: %s", device_id, kind, message)
        if self.on_event:
            try:
                self.on_event(device_id, kind, state, message)
            except Exception:  # noqa: BLE001 - การแจ้งเตือนล้มเหลวต้องไม่ทำให้ระบบหยุด
                log.exception("ส่ง alert ไม่สำเร็จ")

    # ------------------------------------------------------------------ สรุปสถานะ
    def is_online(self, m: Machine) -> bool:
        if m.online is False or m.last_seen is None:
            return False
        return self.clock() - m.last_seen <= self.offline_after_s

    def snapshot(self, device_id: str) -> dict | None:
        with self._lock:
            m = self.machines.get(device_id)
            if m is None:
                return None
            th = thresholds(m.cfg, self.policy)
            d, t = m.last_decision, m.last_telemetry
            state = d.state if d else None
            return {
                "device_id": m.device_id,
                "online": self.is_online(m),
                "last_seen": m.last_seen,
                "state": state,
                "state_th": STATE_TH.get(state, "ยังไม่มีข้อมูล") if state else "ยังไม่มีข้อมูล",
                "led": d.led if d else None,
                "reason": d.reason if d else None,
                "mode": m.cfg.mode,
                "sensitivity": m.cfg.sensitivity,
                "baseline_rms": m.cfg.baseline_rms,
                "maintenance_until": m.cfg.maintenance_until,
                "learn_progress": len(m.tracker.learn_buffer) if m.cfg.mode == "learning" else None,
                "learn_target": self.policy.learn_samples,
                "thresholds": {"warn": th.warn, "alarm": th.alarm, "source": th.source,
                               "temp_warn": self.policy.temp_warn, "temp_alarm": self.policy.temp_alarm},
                "latest": None if t is None else {
                    "seq": t.seq, "vib_rms": t.vib_rms, "vib_peak": t.vib_peak,
                    "temp": t.temp, "hum": t.hum, "rssi": t.rssi,
                },
            }

    def device_ids(self) -> list[str]:
        with self._lock:
            return sorted(self.machines)

    # ------------------------------------------------------------------ คำสั่ง
    def execute(self, cmd: Command) -> str:
        """ทำตามคำสั่งที่ผ่าน allowlist แล้ว คืนข้อความตอบกลับภาษาไทย"""
        if cmd.intent == "help":
            return replies.HELP
        if cmd.intent == "none":
            return replies.UNKNOWN

        ids = self.device_ids()
        device_id = cmd.device_id
        if device_id is None:
            if not ids:
                return replies.NO_MACHINES
            if len(ids) > 1 and cmd.intent != "status":
                return replies.which_machine(ids)
        elif device_id not in self.machines:
            return replies.unknown_machine(device_id, ids)

        if cmd.intent == "status":
            targets = [device_id] if device_id else ids
            return "\n\n".join(replies.status(self.snapshot(d)) for d in targets)

        device_id = device_id or ids[0]
        now = self.clock()
        with self._lock:
            m = self.machines[device_id]
            if cmd.intent == "learn_baseline":
                m.cfg.mode = "learning"
                m.tracker.learn_buffer.clear()
                msg = replies.learning_started(device_id, self.policy.learn_samples)
            elif cmd.intent == "maintenance":
                m.cfg.mode = "maintenance"
                m.cfg.maintenance_until = now + cmd.minutes * 60
                msg = replies.maintenance_started(device_id, cmd.minutes)
            elif cmd.intent == "resume":
                was = m.cfg.mode
                m.cfg.mode = "monitor"
                m.cfg.maintenance_until = None
                m.tracker.learn_buffer.clear()
                msg = replies.resumed(device_id, was)
            elif cmd.intent == "set_sensitivity":
                m.cfg.sensitivity = cmd.level
                th = thresholds(m.cfg, self.policy)
                msg = replies.sensitivity_set(device_id, cmd.level, th)
            else:  # pragma: no cover - allowlist ป้องกันไว้แล้ว
                return replies.UNKNOWN
            self.store.save_machine(device_id, m.cfg.to_dict())
            self._event(device_id, "mode", None, msg.split("\n")[0])
        return msg

    def chat(self, text: str) -> ChatResult:
        ids = self.device_ids()
        source, engine, error = "rule", None, None
        cmd = None
        if self.translator is not None:
            try:
                cmd = self.translator.translate(text, ids)
                source, engine = "ai", self.translator.engine
            except TranslatorError as exc:
                error = str(exc)
                source = "rule_fallback"
                log.warning("AI แปลไม่สำเร็จ ใช้กฎแทน: %s", exc)
        if cmd is not None and cmd.intent == "none":
            # AI ตอบ "none" ได้ทั้งตอนที่ไม่ควรทำอะไร และตอนที่แค่ไม่เข้าใจคำนั้น (เช่นโมเดลเล็กกับคำว่า "ช่วยด้วย")
            # จึงถามตัวแปลด้วยกฎอีกครั้ง ถ้ากฎเจอคำสั่งชัดเจนให้ใช้ของกฎ
            # ปลอดภัยเพราะคำสั่งของกฎผ่าน allowlist เดียวกัน และกฎตอบ none เองกับประโยคปฏิเสธ
            rule_cmd = parse_rules(text, ids)
            if rule_cmd.intent != "none":
                log.info("AI ตอบ none แต่กฎเจอ %s: ใช้คำสั่งของกฎ", rule_cmd.intent)
                cmd, source = rule_cmd, "rule_after_ai"
        if cmd is None:
            cmd = parse_rules(text, ids)
        reply = self.execute(cmd)
        return ChatResult(reply, cmd.model_dump(), source, engine, error)

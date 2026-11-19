"""กฎตัดสินสถานะเครื่องจักร — ส่วนที่ "ตัดสินใจ" จริง (AI ไม่มีสิทธิ์เปลี่ยนส่วนนี้)

แนวคิด
1. เรียนรู้ค่าปกติ (baseline) จากค่า vib_rms ช่วงที่เครื่องทำงานปกติ
2. เกณฑ์ = baseline x ตัวคูณ ตามระดับความไว (low / normal / high)
3. ต้องเกินเกณฑ์ติดกันหลายครั้งก่อนเปลี่ยนสถานะ (debounce) และต้องกลับมาปกติติดกัน
   หลายครั้งก่อนลดสถานะ ป้องกันไฟกะพริบไปมาจากค่ากระชาก
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field

LED_FOR_STATE = {
    "normal": "green",
    "warning": "yellow",
    "alarm": "red",
    "learning": "white",
    "maintenance": "blue",
}

STATE_TH = {
    "normal": "ปกติ",
    "warning": "เฝ้าระวัง",
    "alarm": "อันตราย",
    "learning": "กำลังเรียนรู้ค่าปกติ",
    "maintenance": "โหมดซ่อมบำรุง",
}

# ระดับความไว -> (ตัวคูณเกณฑ์เฝ้าระวัง, ตัวคูณเกณฑ์อันตราย)
SENSITIVITY = {
    "low": (2.5, 5.0),
    "normal": (2.0, 4.0),
    "high": (1.5, 3.0),
}

_RANK = {"normal": 0, "warning": 1, "alarm": 2}


@dataclass(frozen=True)
class Policy:
    """ค่าคงที่ของกฎ (ปรับได้ผ่าน environment ใน main.py)

    ค่าเหล่านี้เป็นค่าสำหรับการเรียนการสอนกับบอร์ดราคาถูก ไม่ใช่เกณฑ์มาตรฐานอุตสาหกรรม
    """

    default_warn_rms: float = 1.0     # m/s² ใช้ก่อนเรียนรู้ค่าปกติ
    default_alarm_rms: float = 2.5
    min_warn_rms: float = 0.15        # เกณฑ์ต่ำสุด กันกรณี baseline ใกล้ศูนย์ (สัญญาณรบกวนของ MPU-6050)
    temp_warn: float = 45.0           # °C
    temp_alarm: float = 55.0
    learn_samples: int = 30           # ~30 วินาที
    escalate_after: int = 3           # เกินเกณฑ์ติดกันกี่ครั้งจึงเพิ่มสถานะ
    recover_after: int = 5            # ปกติติดกันกี่ครั้งจึงลดสถานะ


@dataclass
class MachineConfig:
    """ค่าตั้งของเครื่องแต่ละตัว (บันทึกลงฐานข้อมูล)"""

    mode: str = "monitor"             # monitor | learning | maintenance
    baseline_rms: float | None = None
    sensitivity: str = "normal"
    maintenance_until: float | None = None

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "baseline_rms": self.baseline_rms,
            "sensitivity": self.sensitivity,
            "maintenance_until": self.maintenance_until,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "MachineConfig":
        return cls(**{k: d.get(k, getattr(cls(), k)) for k in cls().to_dict()})


@dataclass
class Tracker:
    """สถานะระหว่างทาง (อยู่ในหน่วยความจำ)"""

    state: str = "normal"             # สถานะเฝ้าระวังล่าสุด: normal | warning | alarm
    n_alarm: int = 0                  # จำนวนครั้งติดกันที่ค่าดิบ = alarm
    n_warn_or_more: int = 0           # ... ค่าดิบ >= warning
    n_normal: int = 0                 # ... ค่าดิบ = normal
    n_below_alarm: int = 0            # ... ค่าดิบ < alarm
    learn_buffer: list[float] = field(default_factory=list)


@dataclass(frozen=True)
class Thresholds:
    warn: float
    alarm: float
    source: str                       # "baseline" หรือ "default"


@dataclass(frozen=True)
class Decision:
    state: str
    led: str
    reason: str
    raw_level: str | None = None
    events: tuple[tuple[str, str], ...] = ()   # (kind, ข้อความ) เช่น ("state", ...), ("baseline", ...)
    previous_state: str | None = None


def thresholds(cfg: MachineConfig, policy: Policy) -> Thresholds:
    if cfg.baseline_rms is None:
        return Thresholds(policy.default_warn_rms, policy.default_alarm_rms, "default")
    warn_k, alarm_k = SENSITIVITY.get(cfg.sensitivity, SENSITIVITY["normal"])
    warn = max(cfg.baseline_rms * warn_k, policy.min_warn_rms)
    alarm = max(cfg.baseline_rms * alarm_k, warn * 1.5)
    return Thresholds(round(warn, 4), round(alarm, 4), "baseline")


def raw_level(vib_rms: float, temp: float | None, th: Thresholds, policy: Policy) -> tuple[str, str]:
    """ระดับของค่าที่วัดได้ครั้งเดียว (ยังไม่ผ่าน debounce) พร้อมเหตุผล"""
    if vib_rms >= th.alarm:
        return "alarm", f"การสั่น {vib_rms:.2f} m/s² ถึงเกณฑ์อันตราย {th.alarm:.2f}"
    if temp is not None and temp >= policy.temp_alarm:
        return "alarm", f"อุณหภูมิ {temp:.1f} °C ถึงเกณฑ์อันตราย {policy.temp_alarm:.0f}"
    if vib_rms >= th.warn:
        return "warning", f"การสั่น {vib_rms:.2f} m/s² ถึงเกณฑ์เฝ้าระวัง {th.warn:.2f}"
    if temp is not None and temp >= policy.temp_warn:
        return "warning", f"อุณหภูมิ {temp:.1f} °C ถึงเกณฑ์เฝ้าระวัง {policy.temp_warn:.0f}"
    return "normal", f"การสั่น {vib_rms:.2f} m/s² ต่ำกว่าเกณฑ์เฝ้าระวัง {th.warn:.2f}"


def decide(
    cfg: MachineConfig,
    tr: Tracker,
    vib_rms: float,
    temp: float | None,
    now: float,
    policy: Policy = Policy(),
) -> Decision:
    """ตัดสินสถานะจากค่าที่วัดได้ 1 ครั้ง (แก้ cfg และ tr ในตัว)"""
    events: list[tuple[str, str]] = []

    # 1) โหมดซ่อมบำรุง: ไม่แจ้งเตือนจนหมดเวลา
    if cfg.mode == "maintenance":
        if cfg.maintenance_until is not None and now >= cfg.maintenance_until:
            cfg.mode = "monitor"
            cfg.maintenance_until = None
            events.append(("mode", "หมดเวลาโหมดซ่อมบำรุง กลับมาเฝ้าระวังอัตโนมัติ"))
        else:
            left = 0 if cfg.maintenance_until is None else int((cfg.maintenance_until - now) / 60) + 1
            return Decision("maintenance", LED_FOR_STATE["maintenance"],
                            f"โหมดซ่อมบำรุง เหลืออีกประมาณ {left} นาที", events=tuple(events))

    # 2) โหมดเรียนรู้ค่าปกติ
    if cfg.mode == "learning":
        tr.learn_buffer.append(vib_rms)
        if len(tr.learn_buffer) < policy.learn_samples:
            return Decision("learning", LED_FOR_STATE["learning"],
                            f"เก็บค่าปกติแล้ว {len(tr.learn_buffer)}/{policy.learn_samples} ค่า")
        cfg.baseline_rms = round(statistics.median(tr.learn_buffer), 4)
        tr.learn_buffer.clear()
        cfg.mode = "monitor"
        tr.state, tr.n_alarm, tr.n_warn_or_more, tr.n_normal, tr.n_below_alarm = "normal", 0, 0, 0, 0
        th = thresholds(cfg, policy)
        events.append(("baseline", f"เรียนรู้ค่าปกติเสร็จ: {cfg.baseline_rms:.3f} m/s² "
                                   f"(เกณฑ์เฝ้าระวัง {th.warn:.2f}, อันตราย {th.alarm:.2f})"))

    # 3) โหมดเฝ้าระวัง
    th = thresholds(cfg, policy)
    level, reason = raw_level(vib_rms, temp, th, policy)
    tr.n_alarm = tr.n_alarm + 1 if level == "alarm" else 0
    tr.n_warn_or_more = tr.n_warn_or_more + 1 if level != "normal" else 0
    tr.n_normal = tr.n_normal + 1 if level == "normal" else 0
    tr.n_below_alarm = tr.n_below_alarm + 1 if level != "alarm" else 0

    prev = tr.state
    new = prev
    if tr.n_alarm >= policy.escalate_after:
        new = "alarm"
    elif prev == "alarm" and tr.n_below_alarm >= policy.recover_after:
        new = "normal" if tr.n_normal >= policy.recover_after else "warning"
    elif prev == "normal" and tr.n_warn_or_more >= policy.escalate_after:
        new = "warning"
    elif prev == "warning" and tr.n_normal >= policy.recover_after:
        new = "normal"

    if new != prev:
        tr.state = new
        arrow = "เพิ่มขึ้น" if _RANK[new] > _RANK[prev] else "ลดลง"
        events.append(("state", f"สถานะ{arrow}: {STATE_TH[prev]} → {STATE_TH[new]} ({reason})"))
    elif new != level:
        # ค่าดิบต่างจากสถานะ แต่ยังไม่ครบจำนวนครั้ง
        reason += f" — รอยืนยัน (สถานะยังเป็น{STATE_TH[new]})"

    return Decision(new, LED_FOR_STATE[new], reason, raw_level=level,
                    events=tuple(events), previous_state=prev if new != prev else None)

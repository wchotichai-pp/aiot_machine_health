"""ข้อความตอบกลับ (template ตายตัว — AI ไม่ได้เป็นคนเขียน จึงรายงานตัวเลขผิดไม่ได้)"""
from __future__ import annotations

import time

from .rules import Thresholds

EMOJI = {"normal": "🟢", "warning": "🟡", "alarm": "🔴", "learning": "⚪", "maintenance": "🔵", None: "⚫"}
LEVEL_TH = {"low": "ต่ำ", "normal": "ปกติ", "high": "สูง"}

HELP = (
    "ผมช่วยดูแลเครื่องจักรได้ดังนี้\n"
    "• ถามสถานะ เช่น \"เครื่องเป็นยังไงบ้าง\"\n"
    "• เรียนรู้ค่าปกติ เช่น \"เรียนรู้ค่าปกติใหม่\" (สั่งตอนเครื่องทำงานปกติเท่านั้น)\n"
    "• โหมดซ่อมบำรุง เช่น \"จะซ่อมเครื่อง ปิดแจ้งเตือน 1 ชั่วโมง\"\n"
    "• กลับมาเฝ้าระวัง เช่น \"ซ่อมเสร็จแล้ว\"\n"
    "• ปรับความไว เช่น \"ปรับความไวสูง\" หรือ \"ลดความไว\"\n"
    "เปิดแดชบอร์ดได้จากปุ่ม Dashboard ข้างช่องพิมพ์"
)
UNKNOWN = ("ยังไม่เข้าใจคำสั่งนี้ หรือเป็นคำสั่งที่ระบบไม่อนุญาต จึงยังไม่ได้ทำอะไรครับ\n"
           "พิมพ์ \"ช่วยด้วย\" เพื่อดูคำสั่งที่ใช้ได้")
NO_MACHINES = "ยังไม่มีเครื่องจักรส่งข้อมูลเข้ามาเลยครับ ลองเปิดบอร์ดหรือตัวจำลองก่อน"


def which_machine(ids: list[str]) -> str:
    return "มีหลายเครื่อง ต้องการสั่งเครื่องไหนครับ: " + ", ".join(ids) + "\nพิมพ์ชื่อเครื่องในข้อความได้เลย"


def unknown_machine(device_id: str, ids: list[str]) -> str:
    return f"ไม่พบเครื่อง {device_id} ในระบบ เครื่องที่มี: " + (", ".join(ids) or "-")


def _ago(ts: float | None) -> str:
    if ts is None:
        return "ไม่เคย"
    s = int(time.time() - ts)
    return f"{s} วินาทีที่แล้ว" if s < 120 else f"{s // 60} นาทีที่แล้ว"


def status(s: dict | None) -> str:
    if s is None:
        return "ไม่พบเครื่องนี้"
    head = f"{EMOJI.get(s['state'], '⚫')} {s['device_id']}: {s['state_th']}"
    if not s["online"]:
        head += f" (ออฟไลน์ ข้อมูลล่าสุด {_ago(s['last_seen'])})"
    lines = [head]
    if s["latest"]:
        x = s["latest"]
        lines.append(f"การสั่น RMS {x['vib_rms']:.2f} m/s² (peak {x['vib_peak']:.2f})")
        if x["temp"] is not None:
            lines.append(f"อุณหภูมิ {x['temp']:.1f} °C")
    th = s["thresholds"]
    if s["baseline_rms"] is None:
        lines.append(f"ยังไม่ได้เรียนรู้ค่าปกติ ใช้เกณฑ์เริ่มต้น {th['warn']:.2f} / {th['alarm']:.2f} m/s²")
    else:
        lines.append(f"ค่าปกติ {s['baseline_rms']:.3f} m/s² · เกณฑ์ {th['warn']:.2f} / {th['alarm']:.2f} m/s² "
                     f"(ความไว{LEVEL_TH[s['sensitivity']]})")
    if s["reason"]:
        lines.append(f"เหตุผล: {s['reason']}")
    return "\n".join(lines)


def learning_started(device_id: str, n: int) -> str:
    return (f"⚪ เริ่มเรียนรู้ค่าปกติของ {device_id} ({n} ค่า ประมาณ {n} วินาที)\n"
            "ระหว่างนี้ให้เครื่องทำงานตามปกติ ห้ามแตะหรือเคาะเครื่อง")


def maintenance_started(device_id: str, minutes: int) -> str:
    return (f"🔵 {device_id} เข้าโหมดซ่อมบำรุง {minutes} นาที ระหว่างนี้จะไม่แจ้งเตือน\n"
            "ซ่อมเสร็จแล้วพิมพ์ \"ซ่อมเสร็จแล้ว\" เพื่อกลับมาเฝ้าระวัง")


def resumed(device_id: str, was_mode: str) -> str:
    extra = "" if was_mode != "maintenance" else "\nถ้าเปลี่ยนชิ้นส่วนมา แนะนำให้สั่ง \"เรียนรู้ค่าปกติใหม่\""
    return f"🟢 {device_id} กลับมาเฝ้าระวังแล้ว{extra}"


def sensitivity_set(device_id: str, level: str, th: Thresholds) -> str:
    note = "" if th.source == "baseline" else " (ยังไม่ได้เรียนรู้ค่าปกติ จึงยังใช้เกณฑ์เริ่มต้น)"
    return (f"ปรับความไวของ {device_id} เป็น{LEVEL_TH[level]}แล้ว\n"
            f"เกณฑ์เฝ้าระวัง {th.warn:.2f} m/s² · อันตราย {th.alarm:.2f} m/s²{note}")

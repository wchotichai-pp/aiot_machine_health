"""Allowlist ของคำสั่ง + ตัวแปลข้อความด้วยกฎคำสำคัญ (ใช้เมื่อไม่มี AI หรือ AI ล้มเหลว)

ไม่ว่าข้อความจะมาจากผู้ใช้ จาก AI หรือจากปุ่มใน Mini App
ทุกคำสั่งต้องผ่าน Command.model_validate() ก่อนถูกนำไปทำงาน
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .protocol import DEVICE_ID_PATTERN

Intent = Literal["status", "learn_baseline", "maintenance", "resume", "set_sensitivity", "help", "none"]
INTENTS: tuple[str, ...] = Intent.__args__  # type: ignore[attr-defined]

MAINT_MIN, MAINT_MAX, MAINT_DEFAULT = 5, 240, 30


class Command(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: Intent
    device_id: str | None = Field(default=None, pattern=DEVICE_ID_PATTERN)
    minutes: int | None = Field(default=None, ge=MAINT_MIN, le=MAINT_MAX)
    level: Literal["low", "normal", "high"] | None = None

    @model_validator(mode="after")
    def _fields_match_intent(self) -> "Command":
        if self.intent == "maintenance":
            if self.minutes is None:
                self.minutes = MAINT_DEFAULT
        else:
            self.minutes = None
        if self.intent == "set_sensitivity":
            if self.level is None:
                raise ValueError("set_sensitivity ต้องระบุ level")
        else:
            self.level = None
        if self.intent in ("help", "none"):
            self.device_id = None
        return self


# ---------------------------------------------------------------------------
# ตัวแปลด้วยกฎคำสำคัญ
# ---------------------------------------------------------------------------
NEGATION = ("อย่า", "ไม่ต้อง", "ห้าม", "ยังไม่ต้อง", "don't", "do not", "dont")
KW_RESUME = ("ซ่อมเสร็จ", "กลับมาเฝ้า", "เฝ้าระวังต่อ", "เปิดแจ้งเตือน", "ยกเลิกโหมดซ่อม", "resume")
KW_LEARN = ("เรียนรู้", "ตั้งค่าปกติ", "วัดค่าปกติ", "ค่าปกติใหม่", "calibrate", "baseline")
KW_MAINT = ("ซ่อม", "maintenance", "ปิดแจ้งเตือน", "หยุดแจ้งเตือน", "mute")
KW_SENS = ("ความไว", "sensitivity", "ไวขึ้น", "ไวลง", "ไวน้อย")
KW_STATUS = ("สถานะ", "เป็นยังไง", "เป็นไง", "status", "สั่น", "อุณหภูมิ", "ร้อน", "ปกติไหม",
             "ปกติมั้ย", "โอเคไหม", "ค่าล่าสุด", "เช็ค", "เช็ก")
KW_HELP = ("ช่วย", "help", "ทำอะไรได้", "คำสั่ง", "ใช้ยังไง", "/start")

_MINUTES_RE = re.compile(r"(\d{1,3})\s*(นาที|min|m\b)")
_HOURS_RE = re.compile(r"(\d{1,2})\s*(ชั่วโมง|ชม|hour|hr|h\b)")


def _has(text: str, words: tuple[str, ...]) -> bool:
    return any(w in text for w in words)


def find_device(text: str, known_devices: list[str]) -> str | None:
    t = text.lower()
    for d in sorted(known_devices, key=len, reverse=True):
        if d in t:
            return d
    return None


def _minutes(text: str) -> int:
    if m := _HOURS_RE.search(text):
        val = int(m.group(1)) * 60
    elif m := _MINUTES_RE.search(text):
        val = int(m.group(1))
    else:
        return MAINT_DEFAULT
    return max(MAINT_MIN, min(MAINT_MAX, val))


def _level(text: str) -> str | None:
    if _has(text, ("ไวขึ้น", "สูง", "high", "เพิ่มความไว")):
        return "high"
    if _has(text, ("ไวลง", "ไวน้อย", "ต่ำ", "low", "ลดความไว")):
        return "low"
    if _has(text, ("ปกติ", "normal", "ค่าเริ่มต้น", "default")):
        return "normal"
    return None


def parse_rules(text: str, known_devices: list[str]) -> Command:
    t = text.strip().lower()
    device = find_device(t, known_devices)
    if not t:
        return Command(intent="none")

    if _has(t, KW_RESUME):
        intent = "resume"
    elif _has(t, KW_LEARN):
        intent = "learn_baseline"
    elif _has(t, KW_SENS):
        level = _level(t)
        return Command(intent="set_sensitivity", device_id=device, level=level) if level else Command(intent="none")
    elif _has(t, KW_MAINT):
        intent = "maintenance"
    elif _has(t, KW_STATUS):
        intent = "status"
    elif _has(t, KW_HELP):
        return Command(intent="help")
    else:
        return Command(intent="none")

    # ประโยคปฏิเสธ + คำสั่งที่เปลี่ยนการทำงาน = ไม่ทำอะไร (ถามกลับดีกว่าทำผิด)
    if intent in ("learn_baseline", "maintenance", "resume") and _has(t, NEGATION):
        return Command(intent="none")
    if intent == "maintenance":
        return Command(intent="maintenance", device_id=device, minutes=_minutes(t))
    return Command(intent=intent, device_id=device)

"""รูปแบบข้อความระหว่างบอร์ดกับ gateway (ทุกข้อความต้องผ่านการตรวจที่นี่ก่อนใช้งาน)

Topic (ค่าเริ่มต้น TOPIC_PREFIX = aiot/machines):
  บอร์ด  -> gateway : {prefix}/{device_id}/telemetry   (JSON ทุก 1 วินาที)
  บอร์ด  -> gateway : {prefix}/{device_id}/status      ("online" / "offline", retained + Last Will)
  gateway -> บอร์ด  : {prefix}/{device_id}/state       (JSON สถานะและสีไฟ)
  gateway -> ทุกคน  : {prefix}/{device_id}/alert       (JSON เมื่อสถานะเปลี่ยน)
"""
from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

DEVICE_ID_PATTERN = r"^[a-z0-9][a-z0-9_-]{1,31}$"
MAX_PAYLOAD_BYTES = 1024


class ProtocolError(ValueError):
    pass


class Telemetry(BaseModel):
    """ค่าที่บอร์ดวัดได้ในหน้าต่าง 1 วินาที"""

    model_config = ConfigDict(extra="ignore")

    v: Literal[1] = 1
    device_id: str = Field(pattern=DEVICE_ID_PATTERN)
    seq: int = Field(ge=0)
    vib_rms: float = Field(ge=0, le=200, description="RMS ของความเร่งส่วนที่สั่น (m/s²)")
    vib_peak: float = Field(ge=0, le=400, description="ค่าสูงสุดของความเร่งส่วนที่สั่น (m/s²)")
    temp: float | None = Field(default=None, ge=-40, le=125)
    hum: float | None = Field(default=None, ge=0, le=100)
    rssi: int | None = Field(default=None, ge=-127, le=0)
    uptime_s: int | None = Field(default=None, ge=0)


class StateMessage(BaseModel):
    """คำตอบที่ gateway ส่งกลับให้บอร์ด (บอร์ดตรวจ field เหล่านี้ก่อนเปลี่ยนสีไฟ)"""

    v: Literal[1] = 1
    device_id: str
    seq: int
    state: Literal["normal", "warning", "alarm", "learning", "maintenance"]
    led: Literal["green", "yellow", "red", "white", "blue"]
    reason: str


def topic_device(topic: str, prefix: str) -> tuple[str, str]:
    """แยก device_id และชนิดข้อความออกจาก topic เช่น aiot/machines/pump-01/telemetry"""
    head = prefix + "/"
    if not topic.startswith(head):
        raise ProtocolError(f"topic ไม่อยู่ใต้ {prefix}: {topic}")
    parts = topic[len(head):].split("/")
    if len(parts) != 2:
        raise ProtocolError(f"รูปแบบ topic ไม่ถูกต้อง: {topic}")
    return parts[0], parts[1]


def parse_telemetry(topic_device_id: str, payload: bytes) -> Telemetry:
    if len(payload) > MAX_PAYLOAD_BYTES:
        raise ProtocolError(f"payload ใหญ่เกิน {MAX_PAYLOAD_BYTES} ไบต์")
    try:
        data = json.loads(payload)
        t = Telemetry.model_validate(data)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ProtocolError(f"ไม่ใช่ JSON: {exc}") from exc
    except ValidationError as exc:
        raise ProtocolError(f"ข้อมูลไม่ผ่านการตรวจ: {exc.errors()[0]['msg']}") from exc
    if t.device_id != topic_device_id:
        raise ProtocolError("device_id ใน payload ไม่ตรงกับ topic")
    return t

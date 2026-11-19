import pytest
from pydantic import ValidationError

from app.commands import Command, parse_rules

DEV = ["pump-01", "fan-02"]


@pytest.mark.parametrize("text,intent", [
    ("เครื่องเป็นยังไงบ้าง", "status"),
    ("สั่นแรงไหม", "status"),
    ("status", "status"),
    ("เรียนรู้ค่าปกติใหม่", "learn_baseline"),
    ("calibrate pump-01", "learn_baseline"),
    ("จะซ่อมเครื่อง ปิดแจ้งเตือนหน่อย", "maintenance"),
    ("ซ่อมเสร็จแล้ว", "resume"),
    ("ช่วยด้วย ใช้ยังไง", "help"),
    ("สั่งกาแฟให้หน่อย", "none"),
    ("", "none"),
])
def test_rule_intents(text, intent):
    assert parse_rules(text, DEV).intent == intent


def test_negation_blocks_actions():
    assert parse_rules("อย่าเพิ่งเรียนรู้ค่าปกตินะ", DEV).intent == "none"
    assert parse_rules("ไม่ต้องเข้าโหมดซ่อม", DEV).intent == "none"


def test_device_and_minutes():
    c = parse_rules("pump-01 เข้าโหมดซ่อม 1 ชั่วโมง", DEV)
    assert (c.intent, c.device_id, c.minutes) == ("maintenance", "pump-01", 60)
    assert parse_rules("ปิดแจ้งเตือน 999 นาที", DEV).minutes == 240   # ถูกจำกัดช่วง
    assert parse_rules("ปิดแจ้งเตือน", DEV).minutes == 30


def test_sensitivity_levels():
    assert parse_rules("ปรับความไวสูง", DEV).level == "high"
    assert parse_rules("ลดความไวลง", DEV).level == "low"
    assert parse_rules("ปรับความไวเป็นปกติ", DEV).level == "normal"
    assert parse_rules("ความไว", DEV).intent == "none"


@pytest.mark.parametrize("bad", [
    {"intent": "shutdown"},
    {"intent": "maintenance", "minutes": 1000},
    {"intent": "set_sensitivity"},
    {"intent": "status", "device_id": "../etc"},
    {"intent": "status", "extra": 1},
])
def test_allowlist_rejects(bad):
    with pytest.raises(ValidationError):
        Command.model_validate(bad)


def test_irrelevant_fields_are_cleared():
    c = Command.model_validate({"intent": "status", "minutes": 30, "level": "high"})
    assert c.minutes is None and c.level is None

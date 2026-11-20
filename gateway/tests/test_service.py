"""AI ตอบ "none" แล้วระบบต้องถามตัวแปลด้วยกฎต่อ (ปัญหาที่พบตอนทดสอบกับ Gemma จริง: "ช่วยด้วย" -> none)"""
from app.commands import Command
from app.protocol import Telemetry
from app.rules import Policy
from app.service import MachineService
from app.store import Store


class AlwaysNone:
    """แทน Gemma ที่ตอบ none ทุกข้อความ"""
    engine = "fake"

    def translate(self, text, known_devices):
        return Command(intent="none")


def service():
    svc = MachineService(Store(":memory:"), Policy(), AlwaysNone())
    svc.handle_telemetry(Telemetry(device_id="pump-01", seq=0, vib_rms=0.2, vib_peak=0.6, temp=30))
    return svc


def test_ai_none_but_rules_understand_uses_rules():
    r = service().chat("ช่วยด้วย")
    assert r.command["intent"] == "help"
    assert r.source == "rule_after_ai"


def test_ai_none_and_rules_none_stays_none():
    r = service().chat("สั่งกาแฟให้หน่อย")
    assert r.command["intent"] == "none"
    assert r.source == "ai"


def test_negation_still_does_nothing():
    svc = service()
    r = svc.chat("อย่าเพิ่งเรียนรู้ค่าปกตินะ")
    assert r.command["intent"] == "none"
    assert svc.snapshot("pump-01")["mode"] == "monitor"

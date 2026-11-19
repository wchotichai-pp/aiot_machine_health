# สถาปัตยกรรมและ API

## บริการใน docker compose

| บริการ | image / โค้ด | พอร์ต | หน้าที่ |
| --- | --- | --- | --- |
| `mosquitto` | `eclipse-mosquitto:2` | 1883 | MQTT broker |
| `ollama` | `ollama/ollama` | (ภายใน) 11434 | รันโมเดล Gemma |
| `model-init` | `ollama/ollama` | — | ดาวน์โหลดโมเดลครั้งแรก แล้วจบ |
| `gateway` | `gateway/` (FastAPI) | 8000 | กฎ, ฐานข้อมูล SQLite, MQTT bridge, REST API, แดชบอร์ด |
| `bot` | `bot/` (python-telegram-bot) | — | แชท, แจ้งเตือน, ปุ่ม Mini App |

ข้อมูลถาวรอยู่ในโฟลเดอร์ `data/` (ฐานข้อมูล `aiot.db` และรายชื่อแชทที่รับแจ้งเตือน) และ volume `ollama` (ไฟล์โมเดล)

## MQTT

ทุก topic อยู่ใต้ `aiot/machines/{device_id}/` โดย `device_id` ต้องตรงรูปแบบ `^[a-z0-9][a-z0-9_-]{1,31}$`

| Topic | ทิศทาง | QoS / retain | เนื้อหา |
| --- | --- | --- | --- |
| `…/telemetry` | บอร์ด → gateway | 0 | JSON ทุก 1 วินาที |
| `…/status` | บอร์ด → gateway | 1 / retained | `online` หรือ `offline` (Last Will) |
| `…/state` | gateway → บอร์ด | 0 | JSON สถานะและสีไฟ ตอบทุก telemetry |
| `…/alert` | gateway → ทุกคน | 1 | JSON เมื่อเกิดเหตุการณ์ (ใช้ต่อกับ Node-RED ได้) |

**telemetry** (ตรวจโดย `gateway/app/protocol.py`, ขนาดไม่เกิน 1 KB)

```json
{"v": 1, "device_id": "pump-01", "seq": 128, "vib_rms": 0.2481, "vib_peak": 0.7312,
 "temp": 31.42, "hum": 55.1, "rssi": -57, "uptime_s": 129}
```

| field | ช่วงที่ยอมรับ | หน่วย |
| --- | --- | --- |
| `vib_rms` | 0–200 | m/s² |
| `vib_peak` | 0–400 | m/s² |
| `temp` | −40–125 (ไม่บังคับ) | °C |
| `hum` | 0–100 (ไม่บังคับ) | % |
| `rssi` | −127–0 (ไม่บังคับ) | dBm |

**state** (บอร์ดตรวจ `v`, `device_id` และ `led` ก่อนเปลี่ยนไฟ)

```json
{"v": 1, "device_id": "pump-01", "seq": 128, "state": "warning", "led": "yellow",
 "reason": "การสั่น 0.62 m/s² ถึงเกณฑ์เฝ้าระวัง 0.50"}
```

## REST API

ทุกเส้นทางใต้ `/api` ยกเว้น `/api/health` ต้องยืนยันตัวตน (ดู[ความปลอดภัย](security.md)) เอกสารแบบโต้ตอบอยู่ที่ `/docs`

| Method | Path | ใช้ทำอะไร |
| --- | --- | --- |
| GET | `/api/health` | สถานะ MQTT, ตัวแปลข้อความ, โมเดลพร้อมหรือไม่ |
| GET | `/api/machines` | รายการเครื่องพร้อมสถานะล่าสุด เกณฑ์ และค่าที่วัดได้ |
| GET | `/api/machines/{id}` | รายละเอียดเครื่องเดียว |
| GET | `/api/machines/{id}/history?minutes=10&limit=900` | ค่าที่วัดได้ย้อนหลัง (มีเวลา `ts` ทุกแถว) |
| GET | `/api/events?after_id=0&limit=50&device_id=` | เหตุการณ์ (`state`, `baseline`, `mode`, `connection`) |
| POST | `/api/command` | คำสั่งจากปุ่ม เช่น `{"intent":"maintenance","device_id":"pump-01","minutes":30}` |
| POST | `/api/chat` | ข้อความภาษาพูด `{"message":"..."}` → `reply`, `command`, `source`, `engine` |

## คำสั่ง (allowlist)

| intent | field เพิ่มเติม | ผล |
| --- | --- | --- |
| `status` | `device_id?` | รายงานสถานะ (ไม่ระบุเครื่อง = ทุกเครื่อง) |
| `learn_baseline` | `device_id?` | เข้าโหมดเรียนรู้ เก็บ `LEARN_SAMPLES` ค่า แล้วใช้มัธยฐานเป็น baseline |
| `maintenance` | `device_id?`, `minutes` 5–240 (ค่าเริ่มต้น 30) | ปิดแจ้งเตือนชั่วคราว ไฟน้ำเงิน |
| `resume` | `device_id?` | กลับมาเฝ้าระวัง |
| `set_sensitivity` | `device_id?`, `level` low/normal/high | เปลี่ยนตัวคูณเกณฑ์ |
| `help`, `none` | — | ไม่เปลี่ยนสถานะระบบ |

ถ้ามีหลายเครื่องแล้วไม่ระบุ `device_id` ในคำสั่งที่เปลี่ยนการทำงาน ระบบจะถามกลับแทนการเดา

## ไฟล์สำคัญ

| ไฟล์ | หน้าที่ |
| --- | --- |
| `gateway/app/rules.py` | `decide()` ตัดสินสถานะ, `thresholds()`, debounce/hysteresis |
| `gateway/app/service.py` | รวมทุกส่วน, `execute()` ทำคำสั่ง, `chat()` |
| `gateway/app/protocol.py` | ตรวจข้อความจากบอร์ด |
| `gateway/app/commands.py` | allowlist และตัวแปลด้วยกฎ |
| `gateway/app/llm.py` | เรียก Ollama ด้วย JSON schema |
| `gateway/app/security.py` | ตรวจ API key และ Telegram initData |
| `gateway/app/store.py` | SQLite: `machines`, `readings`, `events` |
| `gateway/static/` | แดชบอร์ด / Telegram Mini App (HTML, CSS, JS) |
| `bot/bot.py` | บอท Telegram |
| `firmware/cucumber_vibration/src/main.cpp` | เฟิร์มแวร์ |
| `simulator/simulate_machine.py` | ตัวจำลอง |

## ทดสอบ

```bash
cd gateway
pip install -r requirements.txt pytest
python -m pytest
```

ชุดทดสอบครอบคลุมกฎตัดสินสถานะ allowlist ตัวแปลด้วยกฎ การปฏิเสธคำตอบที่ไม่ดีของ AI การตรวจลายเซ็น Telegram และการทำงานของ API
GitHub Actions รันชุดทดสอบนี้และคอมไพล์เฟิร์มแวร์ทุกครั้งที่ push

# AIoT เฝ้าระวังเครื่องจักร (AIoT Machine Health)

ชุดเรียนรู้ AIoT สำหรับช่างซ่อมบำรุงและวิศวกรโรงงาน: ติดบอร์ด **Cucumber RS (ESP32-S2)** บนเครื่องจักร
วัดการสั่นด้วย MPU-6050 ให้ระบบเรียนรู้ค่าปกติแล้วแจ้งเตือนผ่าน **Telegram** และสั่งงานเป็นภาษาไทยผ่าน **AI ที่รันบน PC** (Gemma + Ollama)

📖 **เว็บไซต์บทเรียน:** https://wchotichai-pp.github.io/aiot_machine_health/
🖥️ **เดโมแดชบอร์ด (ข้อมูลจำลอง ไม่ต้องมีบอร์ด):** https://wchotichai-pp.github.io/aiot_machine_health/demo/

📝 **บันทึกการพัฒนาด้วย AI:** https://wchotichai-pp.github.io/aiot_machine_health/ai-dev-log/
<!-- 🎬 **คลิปอธิบาย flow การสั่งและตรวจงานกับ AI:** (เพิ่มลิงก์เมื่ออัปโหลดแล้ว) -->

ต่อยอดจาก [AIoT for Beginners](https://vsupacha.github.io/aiot-for-beginners/) โดยใช้หลักเดียวกันคือ **AI เสนอ ระบบตัดสิน**

## ระบบจริงกับเดโม

| | ระบบจริง | เดโมบน GitHub Pages |
| --- | --- | --- |
| ข้อมูลการสั่น | บอร์ด Cucumber RS + MPU-6050 | ข้อมูลจำลองในเบราว์เซอร์ |
| ตัดสินสถานะ | gateway บน PC | กฎชุดเดียวกัน แปลงเป็น JavaScript |
| AI | Gemma ผ่าน Ollama บน PC | ไม่มี |
| หน้าจอ | Telegram (แชท + Mini App) | แดชบอร์ดตัวเดียวกับ Mini App |

ผลทดสอบกับบอร์ดและบริการจริงอยู่ท้าย[บันทึกการพัฒนาด้วย AI](https://wchotichai-pp.github.io/aiot_machine_health/ai-dev-log/#hardware-check)

## เริ่มเร็ว

```bash
git clone https://github.com/wchotichai-pp/aiot_machine_health.git
cd aiot_machine_health
cp .env.example .env              # แก้ API_KEY และค่า Telegram
docker compose up -d --build      # mosquitto + ollama + gateway + bot
pip install paho-mqtt
python simulator/simulate_machine.py --demo
```

เปิด http://localhost:8000 แล้วใส่ `API_KEY` เพื่อดูแดชบอร์ด

## โครงสร้าง

| โฟลเดอร์ | เนื้อหา |
| --- | --- |
| `firmware/cucumber_vibration/` | เฟิร์มแวร์ PlatformIO |
| `gateway/` | FastAPI: กฎตัดสินสถานะ, SQLite, MQTT, REST API, แดชบอร์ด Telegram Mini App, ชุดทดสอบ |
| `bot/` | บอท Telegram |
| `simulator/` | ตัวจำลองเครื่องจักร |
| `mosquitto/` | ค่าตั้ง MQTT broker |
| `docs/` | เว็บไซต์บทเรียน (MkDocs Material) |
| `demo/` | หน้าเดโมบน GitHub Pages: ใช้แดชบอร์ดตัวจริง + เครื่องจำลองในเบราว์เซอร์ |

## ทดสอบ

```bash
cd gateway && pip install -r requirements.txt pytest && python -m pytest
```

GitHub Actions รันชุดทดสอบ คอมไพล์เฟิร์มแวร์ และ deploy เว็บไซต์ทุกครั้งที่ push ขึ้น `main`

## การพัฒนาด้วย AI

โปรเจกต์นี้พัฒนาร่วมกับ AI โดยบันทึกคำสั่ง ผลงาน และวิธีตรวจทุกขั้นไว้ใน [docs/ai-dev-log.md](docs/ai-dev-log.md)

# แก้ปัญหา

## ระบบบน PC

| อาการ | สาเหตุที่พบบ่อย | วิธีแก้ |
| --- | --- | --- |
| `no configuration file provided: not found` | รัน `docker compose` นอกโฟลเดอร์ของ repo | `cd` เข้าโฟลเดอร์ที่มี `docker-compose.yml` |
| `env file .env not found` | ยังไม่ได้สร้าง `.env` | `cp .env.example .env` |
| `/api/health` ได้ `mqtt_connected: false` | broker ยังไม่ขึ้น | `docker compose logs mosquitto` |
| `model_ready: false` นานมาก | โมเดลยังดาวน์โหลดไม่เสร็จ หรือเน็ตหลุด | `docker compose logs model-init` แล้ว `docker compose up -d model-init` |
| แชทตอบช้า และขึ้น `📏 กฎ (AI ไม่ตอบ)` | CPU ช้า หรือโมเดลเพิ่งโหลดครั้งแรก | เพิ่ม `AI_TIMEOUT_S` หรือใช้ `TRANSLATOR=rules` ระหว่างสอน |
| แดชบอร์ดขึ้น "ต้องยืนยันตัวตนก่อน" | เปิดนอก Telegram | ใส่ `API_KEY` จาก `.env` |
| แดชบอร์ดขึ้น "API_KEY ไม่ถูกต้อง" | พิมพ์ผิด หรือแก้ `.env` แต่ยังไม่ `up -d` | ตรวจค่า แล้ว `docker compose up -d` |

## บอร์ด Cucumber

| อาการใน Serial Monitor | สาเหตุ | วิธีแก้ |
| --- | --- | --- |
| `ไม่พบ MPU-6050` และไฟแดงกะพริบเร็ว | I2C ใช้ขาผิด หรือบอร์ดไม่มี MPU-6050 | ตรวจว่าเป็น Cucumber RS และใช้ `Wire.begin(41, 40)` |
| ค้างที่ `WiFi -> ...` | WiFi 5 GHz, รหัสผิด | ใช้ WiFi 2.4 GHz และตรวจ `secrets.h` |
| `MQTT ... failed rc=-2` | ต่อ broker ไม่ได้ | ตรวจ `MQTT_HOST` = IP ของ PC, firewall เปิดพอร์ต 1883, อยู่ WiFi วงเดียวกัน |
| ส่ง `sent` แต่ไม่มีบรรทัด `<-` | gateway ไม่ทำงาน หรือ `DEVICE_ID` มีตัวพิมพ์ใหญ่ | `docker compose logs gateway` ดูข้อความ "ข้อความถูกปฏิเสธ" |
| ไฟม่วงค้าง | ไม่ได้รับคำตอบจาก gateway เกิน 10 วินาที | ตรวจตามแถวด้านบน |
| ค่า RMS กระโดดไปมามาก | บอร์ดยึดไม่แน่น | ยึดใหม่ให้แน่น แล้วเรียนรู้ค่าปกติใหม่ |

!!! tip "Windows Firewall"
    ถ้าบอร์ดต่อ MQTT ไม่ได้ทั้งที่ IP ถูก ให้อนุญาตพอร์ต 1883 ใน Windows Defender Firewall สำหรับเครือข่ายแบบ Private
    (Docker Desktop มักถามให้อนุญาตตอนเปิดครั้งแรก)

## Telegram

| อาการ | วิธีแก้ |
| --- | --- |
| บอทไม่ตอบเลย | `docker compose logs bot` ถ้าเห็น "ยังไม่ได้ตั้ง TELEGRAM_TOKEN" ให้ใส่ token แล้ว `up -d` |
| บอทตอบ "ยังไม่มีสิทธิ์" | ใส่ user id ที่บอทแจ้งลงใน `ALLOWED_USER_IDS` |
| ไม่มีปุ่ม Dashboard | `MINIAPP_URL` ว่างหรือไม่ขึ้นต้นด้วย `https://` |
| Mini App ขึ้นหน้าล็อกอิน Microsoft/GitHub | Port Visibility ของ Dev Tunnel ยังเป็น Private |
| Mini App ขึ้น "บัญชีนี้ไม่มีสิทธิ์" | user id ไม่อยู่ใน `ALLOWED_USER_IDS` |
| ไม่ได้รับแจ้งเตือน | พิมพ์ `/start` ในแชทนั้นก่อน (แชทที่พิมพ์ `/stop` จะไม่ได้รับ) |

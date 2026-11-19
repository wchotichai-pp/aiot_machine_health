# ความปลอดภัย

ระบบนี้ออกแบบมาเพื่อการเรียนการสอน มีการป้องกันพื้นฐานที่ควรมีในระบบ AIoT ทุกระบบ แต่ยังไม่พร้อมใช้กับเครื่องจักรจริงโดยไม่ปรับเพิ่ม

## สิ่งที่ระบบป้องกันแล้ว

| ความเสี่ยง | การป้องกัน | ไฟล์ |
| --- | --- | --- |
| คนนอกเปิด URL ของ tunnel แล้วดูหรือสั่งเครื่อง | ทุกคำขอต้องมี `initData` ที่ Telegram เซ็นด้วย bot token หรือ `X-API-Key` และ initData อายุไม่เกิน 24 ชั่วโมง | `gateway/app/security.py` |
| คนอื่นที่หาบอทเจอสั่งงาน | `ALLOWED_USER_IDS` ตรวจทั้งที่บอทและที่ gateway | `bot/bot.py`, `security.py` |
| AI ถูกชักจูงให้ทำเกินหน้าที่ (prompt injection) | allowlist, จำกัดช่วงตัวเลข, ตรวจชื่อเครื่อง, AI ไม่ได้สั่งไฟหรือเขียนคำตอบ | `commands.py`, `llm.py` |
| ข้อความ MQTT ผิดรูปแบบหรือปลอม topic | ตรวจ JSON, ช่วงค่า, ขนาดไม่เกิน 1 KB, `device_id` ต้องตรงกับ topic | `protocol.py` |
| gateway ส่งคำสั่งแปลก ๆ ให้บอร์ด | บอร์ดตรวจ `v`, `device_id` และสีไฟใน allowlist ก่อนทำตาม | `main.cpp` |
| ข้อความในเหตุการณ์ถูกตีความเป็น HTML ในแดชบอร์ด | แสดงด้วย `textContent` | `static/app.js` |
| ความลับหลุดขึ้น GitHub | `.env` และ `secrets.h` อยู่ใน `.gitignore` | `.gitignore` |
| ข้อความแชทหลุดออกนอกโรงงาน | AI รันบน PC ในเครื่อง ไม่ส่งข้อความไปบริการภายนอก (ยกเว้น Telegram เอง) | `docker-compose.yml` |

## สิ่งที่ยังไม่ได้ป้องกัน (หัวข้อต่อยอด)

| ความเสี่ยง | ทำไมยังเสี่ยง | แนวทางแก้ |
| --- | --- | --- |
| ใครใน WiFi เดียวกันก็ส่ง MQTT ปลอมได้ | `allow_anonymous true` | เปิด `password_file` ใน Mosquitto และให้แต่ละบอร์ดมีรหัสของตัวเอง |
| MQTT ไม่เข้ารหัส | ใช้พอร์ต 1883 แบบ plain text | ใช้ TLS พอร์ต 8883 และฝัง CA ในเฟิร์มแวร์ (แบบเดียวกับที่ทำกับ Firebase) |
| `API_KEY` คีย์เดียวทำได้ทุกอย่าง | ใครมีคีย์ = ผู้ดูแล | แยกคีย์อ่านอย่างเดียวกับคีย์สั่งงาน |
| ไม่จำกัดจำนวนคำขอ | ส่งข้อความรัว ๆ ทำให้ AI ทำงานหนัก | ใส่ rate limit ต่อผู้ใช้ |
| บันทึกการสั่งงานยังไม่ระบุตัวคน | `events` บันทึกว่าทำอะไร แต่ไม่บันทึก user id | เพิ่ม user id ลงใน event (audit log) |
| URL ของ Dev Tunnel เปลี่ยนได้ และต้องเปิด VS Code ค้าง | เหมาะกับการสาธิตเท่านั้น | ใช้ tunnel แบบถาวร หรือเซิร์ฟเวอร์ที่มีโดเมนและ HTTPS ของตัวเอง |

## เปิดรหัสผ่าน MQTT (แบบฝึกหัด)

```bash
docker compose exec mosquitto mosquitto_passwd -c -b /mosquitto/config/passwd pump-01 รหัสผ่าน
```

ไฟล์ `passwd` จะอยู่ในโฟลเดอร์ `mosquitto/` ของ repo (compose ผูกโฟลเดอร์นี้เข้า container ไว้แล้ว และ `.gitignore` กันไม่ให้ขึ้น GitHub)
จากนั้นแก้ `mosquitto/mosquitto.conf` แล้วรัน `docker compose restart mosquitto`

```ini
allow_anonymous false
password_file /mosquitto/config/passwd
```

แล้วแก้เฟิร์มแวร์ ตัวจำลอง และ gateway ให้ส่ง username/password ตอนเชื่อมต่อ ข้อนี้เป็นแบบฝึกหัดต่อยอด ยังไม่ได้ทำไว้ในโค้ด

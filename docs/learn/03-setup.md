# 3. เตรียมเครื่องมือ

**เป้าหมายของบท:** ติดตั้งโปรแกรมที่ต้องใช้ทั้งหมดบน PC ให้พร้อมก่อนเริ่มลงมือ

## รายการโปรแกรม

| โปรแกรม | ใช้ทำอะไร | หมายเหตุ |
| --- | --- | --- |
| [Git](https://git-scm.com/downloads) | ดาวน์โหลดโค้ดจาก GitHub | |
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) | รัน MQTT broker, gateway, AI และบอท | Windows ต้องเปิด WSL 2 |
| [VS Code](https://code.visualstudio.com/) | แก้โค้ด และทำ port forwarding (Dev Tunnels) | |
| PlatformIO (ส่วนขยายของ VS Code) | คอมไพล์และอัปโหลดเฟิร์มแวร์ | ไม่ต้องใช้ถ้าใช้ตัวจำลอง |
| Python 3.10 ขึ้นไป | รันตัวจำลองเครื่องจักร | |
| Telegram | แชทกับระบบ รับแจ้งเตือน | ใช้บนมือถือหรือ Telegram Desktop |

## ขั้นตอน

1. ติดตั้ง Git, Docker Desktop, VS Code และ Python ตามลิงก์ในตาราง
2. ใน VS Code ไปที่ Extensions แล้วติดตั้ง **PlatformIO IDE**
3. เปิด Docker Desktop ให้ทำงาน แล้วตรวจใน PowerShell หรือ Terminal

    ```bash
    docker --version
    docker compose version
    python --version
    ```

4. ดาวน์โหลดโค้ดของชุดเรียนรู้

    ```bash
    git clone https://github.com/wchotichai-pp/aiot_machine_health.git
    cd aiot_machine_health
    ```

5. ติดตั้งไลบรารีของตัวจำลอง

    ```bash
    pip install paho-mqtt
    ```

## ตรวจความพร้อมของ PC

- RAM อย่างน้อย 8 GB (โมเดล AI ใช้หน่วยความจำราว 1–2 GB ขณะทำงาน)
- พื้นที่ว่างอย่างน้อย 5 GB สำหรับ Docker image และไฟล์โมเดล
- PC และบอร์ดอยู่ใน **WiFi 2.4 GHz วงเดียวกัน** และเครือข่ายไม่ได้กั้นให้อุปกรณ์มองไม่เห็นกัน (client isolation)
- ดู IP ของ PC เพื่อใช้ในบทที่ 5: Windows ใช้ `ipconfig` ส่วน macOS/Linux ใช้ `ip a` หรือ `ifconfig`

!!! tip "ไม่มีสิทธิ์ติดตั้งโปรแกรมบนเครื่องของบริษัท"
    ผู้สอนเตรียม PC หนึ่งเครื่องเป็น gateway ของทั้งห้องได้ ผู้เรียนใช้แค่บอร์ดกับ Telegram ดู[แผนการสอน](../instructor/lesson-plan.md)

**ถัดไป:** [4. เปิดระบบด้วย Docker](04-run-system.md)

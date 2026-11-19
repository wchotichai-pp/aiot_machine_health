"""ตัวจำลองเครื่องจักร — ใช้แทนบอร์ด Cucumber เมื่อยังไม่มีบอร์ด หรือใช้สาธิตในห้องเรียน

ส่งข้อความแบบเดียวกับเฟิร์มแวร์ทุกประการ (topic, JSON, Last Will) แล้วพิมพ์สีไฟที่ gateway สั่งกลับมา

ติดตั้ง:  pip install paho-mqtt
ตัวอย่าง:
  python simulate_machine.py                       # เครื่องปกติ
  python simulate_machine.py --mode imbalance      # เสียสมดุล (สั่นมากขึ้นสม่ำเสมอ)
  python simulate_machine.py --mode fault          # ชำรุด (สั่นแรง + กระชาก + ร้อนขึ้น)
  python simulate_machine.py --demo                # วนครบทุกแบบอัตโนมัติ สำหรับสาธิต
  python simulate_machine.py --device fan-02 --host 192.168.1.20
"""
from __future__ import annotations

import argparse
import json
import math
import random
import time

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

MODES = {
    # mode: (ตัวคูณการสั่นจากค่าปกติ, โอกาสกระชาก, อุณหภูมิที่เพิ่มขึ้น °C)
    "normal": (1.0, 0.00, 0.0),
    "imbalance": (2.6, 0.02, 3.0),
    "fault": (5.5, 0.15, 14.0),
}
DEMO_PLAN = [("normal", 45), ("imbalance", 40), ("fault", 30), ("normal", 40)]
LED_ICON = {"green": "🟢", "yellow": "🟡", "red": "🔴", "white": "⚪", "blue": "🔵"}


def demo_mode(elapsed: float) -> str:
    total = sum(d for _, d in DEMO_PLAN)
    t = elapsed % total
    for mode, dur in DEMO_PLAN:
        if t < dur:
            return mode
        t -= dur
    return "normal"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=1883)
    ap.add_argument("--prefix", default="aiot/machines")
    ap.add_argument("--device", default="sim-01")
    ap.add_argument("--mode", choices=list(MODES), default="normal")
    ap.add_argument("--demo", action="store_true", help="วน normal → imbalance → fault → normal")
    ap.add_argument("--base", type=float, default=0.25, help="ค่า RMS ตอนปกติ (m/s²)")
    ap.add_argument("--interval", type=float, default=1.0)
    ap.add_argument("--count", type=int, default=0, help="ส่งกี่ครั้งแล้วหยุด (0 = ไม่หยุด)")
    a = ap.parse_args()

    base = f"{a.prefix}/{a.device}"
    client = mqtt.Client(CallbackAPIVersion.VERSION2, client_id=f"sim-{a.device}-{random.randint(0, 9999)}")
    client.will_set(f"{base}/status", "offline", qos=1, retain=True)

    def on_connect(c, u, flags, rc, props):
        print(f"เชื่อม MQTT {a.host}:{a.port} -> {rc}")
        c.subscribe(f"{base}/state")
        c.publish(f"{base}/status", "online", qos=1, retain=True)

    def on_message(c, u, msg):
        try:
            s = json.loads(msg.payload)
            if s.get("device_id") == a.device:
                print(f"   ← gateway: {LED_ICON.get(s['led'], '?')} {s['state']:<11} {s['reason']}")
        except (ValueError, KeyError):
            pass

    client.on_connect, client.on_message = on_connect, on_message
    client.connect(a.host, a.port, 30)
    client.loop_start()

    seq, start, temp = 0, time.time(), 31.0
    try:
        while a.count == 0 or seq < a.count:
            mode = demo_mode(time.time() - start) if a.demo else a.mode
            k, spike_p, dtemp = MODES[mode]
            rms = a.base * k * random.uniform(0.9, 1.1)
            peak = rms * random.uniform(2.6, 3.2)               # crest factor ปกติราว 3
            if random.random() < spike_p:
                peak *= random.uniform(1.8, 2.5)                 # กระชากจากลูกปืนชำรุด
                rms *= 1.3
            temp += (31.0 + dtemp - temp) * 0.05                 # อุณหภูมิค่อย ๆ เปลี่ยน
            payload = {
                "v": 1, "device_id": a.device, "seq": seq,
                "vib_rms": round(rms, 4), "vib_peak": round(peak, 4),
                "temp": round(temp + random.uniform(-0.1, 0.1), 2),
                "hum": round(55 + 3 * math.sin(seq / 60), 1),
                "rssi": random.randint(-62, -50), "uptime_s": int(time.time() - start),
            }
            client.publish(f"{base}/telemetry", json.dumps(payload))
            print(f"→ [{mode:<9}] seq={seq:<5} rms={payload['vib_rms']:.3f} peak={payload['vib_peak']:.3f} "
                  f"temp={payload['temp']:.1f}")
            seq += 1
            time.sleep(a.interval)
    except KeyboardInterrupt:
        pass
    finally:
        client.publish(f"{base}/status", "offline", qos=1, retain=True).wait_for_publish(2)
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()

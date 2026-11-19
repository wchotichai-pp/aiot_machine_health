"""เชื่อม MQTT broker: รับ telemetry/status จากบอร์ด แล้วส่ง state/alert กลับ"""
from __future__ import annotations

import json
import logging

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

from .protocol import ProtocolError, parse_telemetry, topic_device
from .service import MachineService

log = logging.getLogger("gateway.mqtt")


class MqttBridge:
    def __init__(self, service: MachineService, host: str, port: int, prefix: str):
        self.service = service
        self.host, self.port, self.prefix = host, port, prefix
        self.client = mqtt.Client(CallbackAPIVersion.VERSION2, client_id="aiot-gateway")
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.reconnect_delay_set(1, 10)
        self.connected = False
        service.on_event = self.publish_alert

    def start(self) -> None:
        self.client.connect_async(self.host, self.port, keepalive=30)
        self.client.loop_start()

    def stop(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        self.connected = not reason_code.is_failure
        log.info("MQTT %s:%s -> %s", self.host, self.port, reason_code)
        client.subscribe(f"{self.prefix}/+/telemetry", qos=0)
        client.subscribe(f"{self.prefix}/+/status", qos=1)

    def _on_message(self, client, userdata, msg):
        try:
            device_id, kind = topic_device(msg.topic, self.prefix)
            if kind == "telemetry":
                t = parse_telemetry(device_id, msg.payload)
                state = self.service.handle_telemetry(t)
                client.publish(f"{self.prefix}/{device_id}/state", state.model_dump_json(), qos=0)
            elif kind == "status":
                text = msg.payload.decode("utf-8", "replace").strip().lower()
                if text in ("online", "offline"):
                    self.service.set_online(device_id, text == "online")
        except ProtocolError as exc:
            log.warning("ข้อความถูกปฏิเสธ (%s): %s", msg.topic, exc)
        except Exception:  # noqa: BLE001 - ข้อความเดียวพังต้องไม่ทำให้ gateway หยุด
            log.exception("จัดการข้อความไม่สำเร็จ: %s", msg.topic)

    def publish_alert(self, device_id: str, kind: str, state: str | None, message: str) -> None:
        payload = json.dumps({"v": 1, "device_id": device_id, "kind": kind, "state": state,
                              "message": message}, ensure_ascii=False)
        self.client.publish(f"{self.prefix}/{device_id}/alert", payload, qos=1)

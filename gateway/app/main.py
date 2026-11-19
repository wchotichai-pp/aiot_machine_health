"""จุดเริ่มต้นของ gateway: REST API + Mini App + MQTT

รัน:  uvicorn app.main:app --host 0.0.0.0 --port 8000
เอกสาร API อัตโนมัติ:  http://localhost:8000/docs
"""
from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

from .commands import Command
from .config import Settings, load_settings
from .llm import OllamaTranslator
from .mqtt_bridge import MqttBridge
from .rules import Policy
from .security import Auth
from .service import MachineService
from .store import Store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("gateway")

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def policy_from_env() -> Policy:
    d = Policy()
    f = lambda name, default: type(default)(os.getenv(name, default))  # noqa: E731
    return Policy(
        default_warn_rms=f("DEFAULT_WARN_RMS", d.default_warn_rms),
        default_alarm_rms=f("DEFAULT_ALARM_RMS", d.default_alarm_rms),
        min_warn_rms=f("MIN_WARN_RMS", d.min_warn_rms),
        temp_warn=f("TEMP_WARN", d.temp_warn),
        temp_alarm=f("TEMP_ALARM", d.temp_alarm),
        learn_samples=f("LEARN_SAMPLES", d.learn_samples),
        escalate_after=f("ESCALATE_AFTER", d.escalate_after),
        recover_after=f("RECOVER_AFTER", d.recover_after),
    )


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=300)


def create_app(settings: Settings | None = None, start_mqtt: bool = True) -> FastAPI:
    s = settings or load_settings()
    store = Store(s.db_path, s.retention_days)
    translator = None
    if s.translator == "ollama":
        translator = OllamaTranslator(s.ollama_url, s.ollama_model, s.ai_timeout_s)
    service = MachineService(store, policy_from_env(), translator, s.offline_after_s)
    bridge = MqttBridge(service, s.mqtt_host, s.mqtt_port, s.topic_prefix) if start_mqtt else None
    auth = Auth(s)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if not s.auth_enabled:
            log.warning("ไม่ได้ตั้ง API_KEY / TELEGRAM_TOKEN: API เปิดให้ทุกคน (ใช้ทดลองในเครื่องเท่านั้น)")
        if s.api_key.startswith("change-me"):
            log.warning("API_KEY ยังเป็นค่าตัวอย่าง ให้เปลี่ยนใน .env ก่อนเปิด tunnel")
        log.info("ตัวแปลข้อความ: %s", f"ollama ({s.ollama_model})" if translator else "rules")
        if bridge:
            bridge.start()
        yield
        if bridge:
            bridge.stop()

    app = FastAPI(title="AIoT Machine Health Gateway", version="1.0", lifespan=lifespan)
    app.state.service = service

    @app.get("/api/health")
    def health():
        return {
            "ok": True,
            "mqtt_connected": bool(bridge and bridge.connected),
            "translator": "ollama" if translator else "rules",
            "model": s.ollama_model if translator else None,
            "model_ready": translator.ping() if translator else None,
            "auth": "on" if s.auth_enabled else "open",
        }

    @app.get("/api/machines")
    def machines(_=Depends(auth)):
        return [service.snapshot(d) for d in service.device_ids()]

    @app.get("/api/machines/{device_id}")
    def machine(device_id: str, _=Depends(auth)):
        snap = service.snapshot(device_id)
        if snap is None:
            raise HTTPException(404, "ไม่พบเครื่องนี้")
        return snap

    @app.get("/api/machines/{device_id}/history")
    def history(device_id: str, minutes: float = Query(10, gt=0, le=1440),
                limit: int = Query(900, ge=1, le=5000), _=Depends(auth)):
        if service.snapshot(device_id) is None:
            raise HTTPException(404, "ไม่พบเครื่องนี้")
        return {"device_id": device_id,
                "items": store.history(device_id, time.time() - minutes * 60, limit)}

    @app.get("/api/events")
    def events(after_id: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=500),
               device_id: str | None = None, _=Depends(auth)):
        return {"last_id": store.last_event_id(), "items": store.events(after_id, limit, device_id)}

    @app.post("/api/command")
    def command(body: dict, who=Depends(auth)):
        """คำสั่งจากปุ่มใน Mini App — ต้องผ่าน allowlist เดียวกับแชท"""
        try:
            cmd = Command.model_validate(body)
        except ValidationError as exc:
            raise HTTPException(422, f"คำสั่งไม่อยู่ใน allowlist: {exc.errors()[0]['msg']}") from exc
        return {"reply": service.execute(cmd), "command": cmd.model_dump()}

    @app.post("/api/chat")
    def chat(body: ChatIn, who=Depends(auth)):
        r = service.chat(body.message)
        return {"reply": r.reply, "command": r.command, "source": r.source,
                "engine": r.engine, "error": r.error}

    if STATIC_DIR.is_dir():
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="miniapp")
    return app


app = create_app() if os.getenv("AIOT_NO_AUTOAPP") != "1" else None

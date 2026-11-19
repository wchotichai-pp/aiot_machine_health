import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.protocol import Telemetry
from app.security import verify_init_data

TOKEN = "123456:TEST-TOKEN"


def settings(**kw):
    base = dict(mqtt_host="x", mqtt_port=1883, topic_prefix="aiot/machines", db_path=":memory:",
                retention_days=7, offline_after_s=15, translator="rules", ollama_url="http://x",
                ollama_model="m", ai_timeout_s=1, api_key="", telegram_token="",
                allowed_user_ids=frozenset(), protect_reads=True)
    base.update(kw)
    return Settings(**base)


def feed(app, device="pump-01", values=(0.2,) * 3):
    svc = app.state.service
    for i, v in enumerate(values):
        svc.handle_telemetry(Telemetry(device_id=device, seq=i, vib_rms=v, vib_peak=v * 2, temp=30))


def init_data(user_id=42, token=TOKEN, auth_date=None):
    fields = {"auth_date": str(auth_date or int(time.time())), "query_id": "q",
              "user": json.dumps({"id": user_id, "first_name": "P"})}
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


def test_open_mode_flow():
    app = create_app(settings(), start_mqtt=False)
    c = TestClient(app)
    assert c.post("/api/chat", json={"message": "สถานะ"}).json()["reply"].startswith("ยังไม่มีเครื่อง")
    feed(app)
    r = c.get("/api/machines").json()
    assert r[0]["device_id"] == "pump-01" and r[0]["state"] == "normal"
    assert len(c.get("/api/machines/pump-01/history").json()["items"]) == 3
    r = c.post("/api/chat", json={"message": "จะซ่อม ปิดแจ้งเตือน 1 ชม"}).json()
    assert r["command"]["intent"] == "maintenance" and r["source"] == "rule"
    assert c.get("/api/machines/pump-01").json()["mode"] == "maintenance"
    r = c.post("/api/command", json={"intent": "resume", "device_id": "pump-01"}).json()
    assert "กลับมาเฝ้าระวัง" in r["reply"]
    assert c.post("/api/command", json={"intent": "self_destruct"}).status_code == 422
    assert c.get("/api/events").json()["items"]


def test_auth_required_when_configured():
    app = create_app(settings(api_key="k", telegram_token=TOKEN, allowed_user_ids=frozenset({42})),
                     start_mqtt=False)
    c = TestClient(app)
    assert c.get("/api/machines").status_code == 401
    assert c.get("/api/machines", headers={"X-API-Key": "wrong"}).status_code == 401
    assert c.get("/api/machines", headers={"X-API-Key": "k"}).status_code == 200
    assert c.get("/api/machines", headers={"X-Telegram-Init-Data": init_data(42)}).status_code == 200
    assert c.get("/api/machines", headers={"X-Telegram-Init-Data": init_data(7)}).status_code == 403
    forged = init_data(42, token="999:OTHER")
    assert c.get("/api/machines", headers={"X-Telegram-Init-Data": forged}).status_code == 401
    assert c.post("/api/chat", json={"message": "hi"},
                  headers={"X-API-Key": "k", "X-Telegram-User-Id": "7"}).status_code == 403
    assert c.get("/api/health").status_code == 200


def test_init_data_expiry():
    old = init_data(42, auth_date=int(time.time()) - 3 * 86400)
    assert verify_init_data(old, TOKEN) is None
    assert verify_init_data(init_data(42), TOKEN)["id"] == 42
    assert verify_init_data("garbage", TOKEN) is None


def test_multiple_machines_asks_which():
    app = create_app(settings(), start_mqtt=False)
    feed(app, "pump-01")
    feed(app, "fan-02")
    c = TestClient(app)
    assert "เครื่องไหน" in c.post("/api/chat", json={"message": "เรียนรู้ค่าปกติใหม่"}).json()["reply"]
    r = c.post("/api/chat", json={"message": "เรียนรู้ค่าปกติ fan-02"}).json()
    assert r["command"]["device_id"] == "fan-02"
    assert c.get("/api/machines/fan-02").json()["mode"] == "learning"


def test_ai_failure_falls_back_to_rules():
    app = create_app(settings(translator="ollama", ollama_url="http://127.0.0.1:9", ai_timeout_s=0.5),
                     start_mqtt=False)
    feed(app)
    r = TestClient(app).post("/api/chat", json={"message": "สถานะ"}).json()
    assert r["source"] == "rule_fallback" and r["command"]["intent"] == "status"
    assert r["error"]

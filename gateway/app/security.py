"""ตรวจว่าใครเป็นผู้เรียก API

ผ่านได้ 2 ทาง
1. บอท Telegram (เครื่องเดียวกันใน Docker) ส่ง header  X-API-Key  ที่ตรงกับ API_KEY
2. Telegram Mini App ส่ง header  X-Telegram-Init-Data  ซึ่ง Telegram เซ็นด้วย bot token
   gateway ตรวจลายเซ็นตามวิธีใน https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app

ถ้ากำหนด ALLOWED_USER_IDS ไว้ ผู้ใช้ต้องอยู่ในรายชื่อนั้นด้วย
ถ้าไม่ได้ตั้ง API_KEY และ TELEGRAM_TOKEN เลย จะเป็น "โหมดเปิด" สำหรับทดลองในเครื่องเท่านั้น
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

from fastapi import HTTPException, Request, Security
from fastapi.security import APIKeyHeader

from .config import Settings

INIT_DATA_MAX_AGE_S = 24 * 3600
# ประกาศไว้ให้หน้า /docs มีปุ่ม Authorize สำหรับใส่ API_KEY
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_init_data(init_data: str, bot_token: str, now: float | None = None,
                     max_age_s: int = INIT_DATA_MAX_AGE_S) -> dict | None:
    """คืนข้อมูลผู้ใช้ถ้าลายเซ็นถูกต้องและยังไม่หมดอายุ ไม่งั้นคืน None"""
    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=True))
    except ValueError:
        return None
    received = pairs.pop("hash", None)
    if not received or not bot_token:
        return None
    check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received):
        return None
    try:
        auth_date = int(pairs.get("auth_date", "0"))
    except ValueError:
        return None
    if (now or time.time()) - auth_date > max_age_s:
        return None
    try:
        return json.loads(pairs.get("user", "{}"))
    except ValueError:
        return None


class Auth:
    def __init__(self, settings: Settings):
        self.s = settings

    def _check_user(self, user_id: int | None) -> None:
        if self.s.allowed_user_ids and user_id not in self.s.allowed_user_ids:
            raise HTTPException(status_code=403, detail=f"ผู้ใช้ {user_id} ไม่อยู่ใน ALLOWED_USER_IDS")

    def __call__(self, request: Request, key: str | None = Security(api_key_header)) -> dict:
        """dependency ของ FastAPI คืน {"via": ..., "user_id": ...}"""
        if not self.s.auth_enabled:
            return {"via": "open", "user_id": None}
        if request.method == "GET" and not self.s.protect_reads:
            return {"via": "public-read", "user_id": None}

        key = key or ""
        if self.s.api_key and key and hmac.compare_digest(key, self.s.api_key):
            uid = request.headers.get("x-telegram-user-id")
            user_id = int(uid) if uid and uid.isdigit() else None
            if user_id is not None:
                self._check_user(user_id)
            return {"via": "api-key", "user_id": user_id}

        init_data = request.headers.get("x-telegram-init-data", "")
        if init_data and self.s.telegram_token:
            user = verify_init_data(init_data, self.s.telegram_token)
            if user is not None:
                self._check_user(user.get("id"))
                return {"via": "telegram", "user_id": user.get("id")}

        raise HTTPException(status_code=401, detail="ต้องเปิดจาก Telegram Mini App หรือส่ง X-API-Key")

"""ค่าตั้งทั้งหมดของ gateway อ่านจาก environment variable (ตั้งใน .env ของ docker compose)"""
from __future__ import annotations

import os
from dataclasses import dataclass


def _float(name: str, default: float) -> float:
    return float(os.getenv(name, default))


def _int(name: str, default: int) -> int:
    return int(os.getenv(name, default))


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    # MQTT
    mqtt_host: str
    mqtt_port: int
    topic_prefix: str
    # ฐานข้อมูล
    db_path: str
    retention_days: int
    offline_after_s: int
    # AI
    translator: str          # "rules" หรือ "ollama"
    ollama_url: str
    ollama_model: str
    ai_timeout_s: float
    # ความปลอดภัย
    api_key: str
    telegram_token: str
    allowed_user_ids: frozenset[int]
    protect_reads: bool

    @property
    def auth_enabled(self) -> bool:
        return bool(self.api_key or self.telegram_token)


def load_settings() -> Settings:
    allowed = {
        int(x) for x in os.getenv("ALLOWED_USER_IDS", "").replace(" ", "").split(",") if x
    }
    return Settings(
        mqtt_host=os.getenv("MQTT_HOST", "localhost"),
        mqtt_port=_int("MQTT_PORT", 1883),
        topic_prefix=os.getenv("TOPIC_PREFIX", "aiot/machines").rstrip("/"),
        db_path=os.getenv("DB_PATH", "data/aiot.db"),
        retention_days=_int("RETENTION_DAYS", 7),
        offline_after_s=_int("OFFLINE_AFTER_S", 15),
        translator=os.getenv("TRANSLATOR", "ollama").strip().lower(),
        ollama_url=os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/"),
        ollama_model=os.getenv("OLLAMA_MODEL", "gemma3:1b"),
        ai_timeout_s=_float("AI_TIMEOUT_S", 15),
        api_key=os.getenv("API_KEY", ""),
        telegram_token=os.getenv("TELEGRAM_TOKEN", ""),
        allowed_user_ids=frozenset(allowed),
        protect_reads=_bool("PROTECT_READS", True),
    )

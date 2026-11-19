"""บอท Telegram: ส่งข้อความไปให้ gateway แปลเป็นคำสั่ง + แจ้งเตือนเมื่อสถานะเครื่องเปลี่ยน

ตัวแปรที่ต้องตั้ง (ใน .env):
  TELEGRAM_TOKEN    token จาก @BotFather
  GATEWAY_URL       ที่อยู่ gateway (ใน docker compose คือ http://gateway:8000)
  API_KEY           รหัสลับที่ใช้ร่วมกับ gateway
  MINIAPP_URL       (ไม่บังคับ) URL แบบ https ของแดชบอร์ด เช่น Dev Tunnel ของพอร์ต 8000
  ALLOWED_USER_IDS  (แนะนำ) user id ที่อนุญาต คั่นด้วยจุลภาค
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

import httpx
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, MenuButtonWebApp, Update, WebAppInfo
from telegram.ext import Application, ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

logging.basicConfig(format="%(asctime)s %(levelname)s bot: %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)   # กัน log พิมพ์ URL ที่มี token
log = logging.getLogger("bot")

TOKEN = os.getenv("TELEGRAM_TOKEN", "")
GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8000").rstrip("/")
API_KEY = os.getenv("API_KEY", "")
MINIAPP_URL = os.getenv("MINIAPP_URL", "").strip()
ALLOWED = {int(x) for x in os.getenv("ALLOWED_USER_IDS", "").replace(" ", "").split(",") if x}
SUBSCRIBERS_FILE = Path(os.getenv("SUBSCRIBERS_FILE", "data/subscribers.json"))
ALERT_KINDS = {"state", "baseline", "connection"}

gateway = httpx.AsyncClient(base_url=GATEWAY_URL, timeout=30, headers={"X-API-Key": API_KEY})


# ---------------------------------------------------------------- ผู้รับแจ้งเตือน
def load_subscribers() -> set[int]:
    try:
        return set(json.loads(SUBSCRIBERS_FILE.read_text()))
    except (FileNotFoundError, ValueError):
        return set()


def save_subscribers(ids: set[int]) -> None:
    SUBSCRIBERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SUBSCRIBERS_FILE.write_text(json.dumps(sorted(ids)))


def allowed(update: Update) -> bool:
    return not ALLOWED or (update.effective_user and update.effective_user.id in ALLOWED)


async def deny(update: Update) -> None:
    uid = update.effective_user.id if update.effective_user else "?"
    await update.effective_message.reply_text(
        f"บัญชีนี้ยังไม่มีสิทธิ์ใช้งาน (user id: {uid})\nให้ผู้ดูแลเพิ่มเลขนี้ใน ALLOWED_USER_IDS")


def miniapp_ok() -> bool:
    return MINIAPP_URL.startswith("https://")


# ---------------------------------------------------------------- คำสั่ง
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update):
        return await deny(update)
    subs = load_subscribers()
    subs.add(update.effective_chat.id)
    save_subscribers(subs)
    markup = None
    if miniapp_ok():
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("📈 เปิดแดชบอร์ด", web_app=WebAppInfo(url=MINIAPP_URL))]])
    await update.message.reply_text(
        "สวัสดีครับ ผมเป็นผู้ช่วยเฝ้าระวังเครื่องจักร\n"
        "แชทนี้จะได้รับแจ้งเตือนเมื่อสถานะเครื่องเปลี่ยน (พิมพ์ /stop เพื่อหยุดรับ)\n\n"
        "ลองพิมพ์ว่า \"เครื่องเป็นยังไงบ้าง\" หรือ \"ช่วยด้วย\" เพื่อดูคำสั่งทั้งหมด\n\n"
        f"(user id ของคุณ: {update.effective_user.id})",
        reply_markup=markup)


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    subs = load_subscribers()
    subs.discard(update.effective_chat.id)
    save_subscribers(subs)
    await update.message.reply_text("หยุดส่งแจ้งเตือนในแชทนี้แล้ว พิมพ์ /start เพื่อรับใหม่")


async def ask_gateway(update: Update, text: str) -> None:
    await update.effective_chat.send_action("typing")
    try:
        r = await gateway.post("/api/chat", json={"message": text[:300]},
                               headers={"X-Telegram-User-Id": str(update.effective_user.id)})
        r.raise_for_status()
        data = r.json()
    except httpx.HTTPError as exc:
        log.warning("เรียก gateway ไม่สำเร็จ: %s", exc)
        return await update.effective_message.reply_text("ติดต่อ gateway ไม่ได้ ลองใหม่อีกครั้งครับ")
    tag = {"ai": "🤖 AI", "rule": "📏 กฎ", "rule_fallback": "📏 กฎ (AI ไม่ตอบ)"}.get(data["source"], data["source"])
    cmd = data["command"]
    detail = cmd["intent"] + "".join(f" {k}={v}" for k, v in cmd.items() if k != "intent" and v is not None)
    await update.effective_message.reply_text(f"{data['reply']}\n\n— แปลโดย {tag}: {detail}")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update):
        return await deny(update)
    await ask_gateway(update, "status")


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update):
        return await deny(update)
    await ask_gateway(update, "help")


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update):
        return await deny(update)
    await ask_gateway(update, update.message.text)


# ---------------------------------------------------------------- แจ้งเตือน
async def poll_events(context: ContextTypes.DEFAULT_TYPE):
    last_id = context.bot_data.get("last_event_id")
    try:
        r = await gateway.get("/api/events", params={"after_id": last_id or 0, "limit": 50})
        r.raise_for_status()
        data = r.json()
    except httpx.HTTPError as exc:
        log.debug("poll events: %s", exc)
        return
    if last_id is None:                       # รอบแรก: ไม่ส่งของเก่าย้อนหลัง
        context.bot_data["last_event_id"] = data["last_id"]
        return
    for e in data["items"]:
        context.bot_data["last_event_id"] = e["id"]
        if e["kind"] not in ALERT_KINDS:
            continue
        icon = {"alarm": "🔴", "warning": "🟡", "normal": "🟢"}.get(e["state"], "ℹ️")
        text = f"{icon} {e['device_id']} · {time.strftime('%H:%M:%S', time.localtime(e['ts']))}\n{e['message']}"
        for chat_id in load_subscribers():
            try:
                await context.bot.send_message(chat_id, text)
            except Exception as exc:  # noqa: BLE001
                log.warning("ส่งแจ้งเตือนถึง %s ไม่สำเร็จ: %s", chat_id, exc)


async def post_init(app: Application):
    if miniapp_ok():
        await app.bot.set_chat_menu_button(menu_button=MenuButtonWebApp("Dashboard", WebAppInfo(MINIAPP_URL)))
        log.info("ปุ่ม Dashboard -> %s", MINIAPP_URL)
    else:
        log.warning("ยังไม่ได้ตั้ง MINIAPP_URL แบบ https:// — ใช้แชทได้ แต่ยังไม่มีปุ่มแดชบอร์ด")
    if not ALLOWED:
        log.warning("ALLOWED_USER_IDS ว่าง: ทุกคนที่หาบอทเจอสั่งงานได้ (ควรตั้งก่อนใช้งานจริง)")


def main() -> None:
    if not TOKEN:
        log.error("ยังไม่ได้ตั้ง TELEGRAM_TOKEN ใน .env — ปิดบอทไว้ก่อน (ส่วนอื่นของระบบยังทำงานปกติ)")
        while True:
            time.sleep(3600)
    app = ApplicationBuilder().token(TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.job_queue.run_repeating(poll_events, interval=3, first=2)
    log.info("บอทเริ่มทำงาน gateway=%s", GATEWAY_URL)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

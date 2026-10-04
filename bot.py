"""
Telegram-бот для управления ключами доступа к фейк-гифт странице Roblox.

УСТАНОВКА:
  pip install python-telegram-bot==20.7

ЗАПУСК:
  export BOT_TOKEN=<ваш токен от @BotFather>
  export ADMIN_TOKEN=<admin token из server.mjs — смотри в логах при старте>
  export SITE_URL=https://your-render-app.onrender.com
  python bot.py

КОМАНДЫ БОТА (только для @ADMIN_USERNAME):
  /start            — приветствие
  /ключ @username 50000 VisualNick 1ч — выдать временный ключ
  /keys             — список всех ключей
  /config           — посмотреть/изменить глобальные настройки

НАСТРОЙКИ перед выдачей ключа (через /set):
  /set robux 50000        — установить количество RB для следующего ключа
  /set nick Astrix_Gaming — установить ник профиля
  /set name Astrix        — установить отображаемое имя
  /set item "Headless Horseman"  — название предмета
  /set price 31000        — цена предмета
"""

import os
import logging
import asyncio
import re
import time
import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_TOKEN = os.environ["ADMIN_TOKEN"]
SITE_URL = os.environ.get("SITE_URL", "http://localhost:10000").rstrip("/")

# Telegram username или ID администраторов (добавь свои)
ADMIN_IDS: set[int] = set()
ADMIN_USERNAMES: set[str] = set()

# ── загружаем из переменных окружения ──────────────────────────────────────
raw_admin_ids = os.environ.get("ADMIN_IDS", "")
for part in raw_admin_ids.split(","):
    part = part.strip()
    if part.isdigit():
        ADMIN_IDS.add(int(part))
    elif part.startswith("@"):
        ADMIN_USERNAMES.add(part.lstrip("@").lower())
    elif part:
        ADMIN_USERNAMES.add(part.lower())

# ── временные настройки на каждого пользователя (для следующего ключа) ──────
pending_settings: dict[int, dict] = {}

def default_settings() -> dict:
    return {
        "robuxBalance": 150000,
        "profileUsername": "Builderman",
        "profileDisplayName": "Builderman",
        "itemName": "Headless Horseman",
        "itemPrice": 31000,
    }

def get_settings(user_id: int) -> dict:
    if user_id not in pending_settings:
        pending_settings[user_id] = default_settings()
    return pending_settings[user_id]


def is_admin(update: Update) -> bool:
    user = update.effective_user
    if user is None:
        return False
    if user.id in ADMIN_IDS:
        return True
    if user.username and user.username.lower() in ADMIN_USERNAMES:
        return True
    # Никогда не назначаем администратора автоматически.
    return False


async def api_post(endpoint: str, payload: dict) -> dict:
    payload["admin_token"] = ADMIN_TOKEN
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(f"{SITE_URL}{endpoint}", json=payload)
        r.raise_for_status()
        return r.json()


async def api_get(endpoint: str, params: dict | None = None) -> dict:
    p = dict(params or {})
    p["admin_token"] = ADMIN_TOKEN
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(f"{SITE_URL}{endpoint}", params=p)
        r.raise_for_status()
        return r.json()


# ── /start ──────────────────────────────────────────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not is_admin(update):
        await update.message.reply_text(
            "👋 Привет! Этот бот для выдачи ключей к фейк-гифт странице.\n"
            "Напиши администратору, чтобы получить ключ."
        )
        return

    await update.message.reply_html(
        f"👋 Привет, <b>{user.first_name}</b>!\n\n"
        "Доступные команды:\n"
        "• /give @username — выдать ключ пользователю\n"
        "• /set robux 50000 — кол-во RB для следующего ключа\n"
        "• /set nick Username — ник профиля\n"
        "• /set name DisplayName — отображаемое имя\n"
        "• /set item Название — название предмета\n"
        "• /set price 31000 — цена предмета\n"
        "• /settings — текущие настройки\n"
        "• /keys — список всех ключей\n"
        "• /update — обновить глобальный конфиг сайта\n\n"
        f"🌐 Сайт: {SITE_URL}\n"
        f"🔑 Страница входа: {SITE_URL}/login"
    )


# ── /settings ───────────────────────────────────────────────────────────────
async def settings_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        return
    s = get_settings(update.effective_user.id)
    text = (
        "⚙️ <b>Настройки следующего ключа:</b>\n\n"
        f"💎 RB: <code>{s['robuxBalance']:,}</code>\n"
        f"👤 Ник: <code>{s['profileUsername']}</code>\n"
        f"📛 Имя: <code>{s['profileDisplayName']}</code>\n"
        f"🎁 Предмет: <code>{s['itemName']}</code>\n"
        f"💰 Цена: <code>{s['itemPrice']:,}</code> RB\n\n"
        "Меняй через /set ключ значение\n"
        "Например: /set robux 50000"
    )
    await update.message.reply_html(text)


# ── /set ─────────────────────────────────────────────────────────────────────
async def set_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        return
    args = ctx.args
    if not args or len(args) < 2:
        await update.message.reply_text(
            "Использование:\n"
            "/set robux 50000\n"
            "/set nick Username\n"
            "/set name DisplayName\n"
            "/set item Headless Horseman\n"
            "/set price 31000"
        )
        return

    s = get_settings(update.effective_user.id)
    key = args[0].lower()
    value = " ".join(args[1:])

    mapping = {
        "robux": ("robuxBalance", int, "💎 RB установлен: {v:,}"),
        "nick": ("profileUsername", str, "👤 Ник установлен: {v}"),
        "name": ("profileDisplayName", str, "📛 Имя установлено: {v}"),
        "item": ("itemName", str, "🎁 Предмет: {v}"),
        "price": ("itemPrice", int, "💰 Цена: {v:,} RB"),
    }

    if key not in mapping:
        await update.message.reply_text(
            f"Неизвестный параметр: {key}\n"
            "Доступны: robux, nick, name, item, price"
        )
        return

    field, cast, msg_fmt = mapping[key]
    try:
        s[field] = cast(value)
        msg = msg_fmt.replace("{v}", str(s[field]))
        # For int formatting
        if cast == int:
            msg = msg_fmt.format(v=s[field])
        await update.message.reply_text(f"✅ {msg}")
    except (ValueError, TypeError):
        await update.message.reply_text(f"❌ Неверное значение: {value}")


# ── /give @username ──────────────────────────────────────────────────────────
def parse_duration(value: str) -> int | None:
    """Возвращает длительность в миллисекундах."""
    m = re.fullmatch(r"(\d+)(ч|д|мес|м|год)", value.strip().lower())
    if not m:
        return None
    amount = int(m.group(1))
    unit = m.group(2)
    multipliers = {
        "м": 60_000,
        "ч": 3_600_000,
        "д": 86_400_000,
        "мес": 30 * 86_400_000,
        "год": 365 * 86_400_000,
    }
    return amount * multipliers[unit]


async def give_key(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Админская выдача временного ключа.

    Формат:
      /ключ @username 50000 VisualNick 1ч
      /ключ 123456789 50000 Visual Nick 1мес
    Последний аргумент — срок, предпоследние аргументы — визуальный ник.
    """
    if not is_admin(update):
        return

    args = ctx.args
    if len(args) < 4:
        await update.message.reply_text(
            "Использование:\n"
            "/ключ @username 50000 VisualNick 1ч\n"
            "/ключ 123456789 50000 Visual Nick 1мес\n\n"
            "Срок: 1ч, 1д, 1м, 1мес, 1год."
        )
        return

    recipient_tg = args[0].lstrip("@")
    try:
        robux = int(args[1].replace(",", "").replace(" ", ""))
    except ValueError:
        await update.message.reply_text("❌ Сумма Robux должна быть числом.")
        return

    duration_text = args[-1]
    duration_ms = parse_duration(duration_text)
    if duration_ms is None or duration_ms <= 0:
        await update.message.reply_text(
            "❌ Неверный срок. Примеры: 1ч, 1д, 1м, 1мес, 1год."
        )
        return

    display_name = " ".join(args[2:-1]).strip()
    if not display_name:
        await update.message.reply_text("❌ Укажи визуальный никнейм.")
        return

    expires_at = int(time.time() * 1000) + duration_ms
    s = get_settings(update.effective_user.id)

    msg = await update.message.reply_text("⏳ Создаю временный ключ...")
    try:
        data = await api_post("/api/bot/create-key", {
            **s,
            "recipientTg": recipient_tg,
            "robuxBalance": robux,
            "profileDisplayName": display_name,
            "expiresAt": expires_at,
        })
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка при создании ключа:\n{e}")
        return

    key = data["key"]
    cfg = data["config"]
    login_url = f"{SITE_URL}/login"

    admin_text = (
        "✅ <b>Временный ключ создан</b>\n\n"
        f"👤 Получатель: <code>{recipient_tg}</code>\n"
        f"🔑 Ключ: <code>{key}</code>\n"
        f"💎 RB: <b>{cfg['robuxBalance']:,}</b>\n"
        f"📛 Визуальный ник: <code>{cfg['profileDisplayName']}</code>\n"
        f"⏱ Срок: <b>{duration_text}</b>\n"
        f"🌐 Вход: {login_url}"
    )
    await msg.edit_text(admin_text, parse_mode="HTML")

    recipient_msg = (
        "🔑 Ваш временный ключ доступа:\n\n"
        f"<code>{key}</code>\n\n"
        f"⏱ Срок: <b>{duration_text}</b>\n"
        f"🌐 {login_url}"
    )
    try:
        if recipient_tg.isdigit():
            user_id = int(recipient_tg)
        else:
            user_id = ctx.bot_data.get(f"username:{recipient_tg.lower()}")

        if user_id:
            await ctx.bot.send_message(
                chat_id=user_id,
                text=recipient_msg,
                parse_mode="HTML",
            )
            await update.message.reply_text("✅ Ключ отправлен получателю.")
        else:
            await update.message.reply_text(
                "⚠️ Получатель ещё не писал этому боту.\n"
                "Передай ему ключ вручную:\n\n" + recipient_msg,
                parse_mode="HTML",
            )
    except Exception as e:
        await update.message.reply_text(
            f"⚠️ Не удалось отправить автоматически.\n"
            f"Ключ: <code>{key}</code>\n"
            f"Ссылка: {login_url}\n"
            f"Причина: <code>{e}</code>",
            parse_mode="HTML",
        )


# ── /keys ─────────────────────────────────────────────────────────────────────
async def keys_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        return
    try:
        data = await api_get("/api/bot/keys")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")
        return

    keys = data.get("keys", {})
    if not keys:
        await update.message.reply_text("Ключей нет.")
        return

    lines = [f"🔑 <b>Всего ключей: {len(keys)}</b>\n"]
    for k, v in list(keys.items())[-10:]:  # last 10
        status = "✅ использован" if v.get("used") else "🟢 активен"
        recipient = v.get("recipientTg", "—")
        lines.append(
            f"• <code>{k}</code>\n"
            f"  👤 @{recipient} | {status}\n"
            f"  💎 {v.get('robuxBalance', '?'):,} RB | {v.get('profileUsername', '?')}"
        )
    await update.message.reply_html("\n".join(lines))


# ── /update — обновить глобальный конфиг ────────────────────────────────────
async def update_config(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        return
    s = get_settings(update.effective_user.id)
    try:
        data = await api_post("/api/bot/update-config", s)
        await update.message.reply_html(
            f"✅ Глобальный конфиг обновлён:\n"
            f"💎 RB: <code>{s.get('robuxBalance', '?'):,}</code>\n"
            f"👤 Ник: <code>{s.get('profileUsername', '?')}</code>"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")


# ── Сохраняем username → user_id при любом сообщении ────────────────────────
async def track_user(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user and user.username:
        ctx.bot_data[f"username:{user.username.lower()}"] = user.id


# ── MAIN ─────────────────────────────────────────────────────────────────────
def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(MessageHandler(filters.ALL, track_user), group=-1)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("settings", settings_cmd))
    app.add_handler(CommandHandler("set", set_cmd))
    app.add_handler(CommandHandler(["ключ", "key", "give"], give_key))
    app.add_handler(CommandHandler("keys", keys_cmd))
    app.add_handler(CommandHandler("update", update_config))

    print(f"🤖 Bot started. Site: {SITE_URL}")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

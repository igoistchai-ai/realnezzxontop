"""
Telegram admin bot for a clearly labeled visual/demo site.
Requires: python-telegram-bot==20.7, httpx
Environment: BOT_TOKEN, ADMIN_TOKEN, SITE_URL, ADMIN_IDS
"""
import os
import re
import time
import html
import logging
import secrets
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    ConversationHandler, ContextTypes, filters,
)
import httpx

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("demo_admin_bot")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "").strip()
SITE_URL = os.getenv("SITE_URL", "http://localhost:10000").rstrip("/")
ADMIN_IDS = {
    int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
}
ADMIN_USERNAMES = {
    x.strip().lstrip("@").lower()
    for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip() and not x.strip().isdigit()
}

# Per-admin settings for the next demo key. These reset when the bot restarts.
pending_settings: dict[int, dict] = {}
WAIT_RECIPIENT, WAIT_AMOUNT, WAIT_NICK, WAIT_DURATION = range(4)

def defaults():
    return {
        "robuxBalance": 150000,
        "profileUsername": "Builderman",
        "profileDisplayName": "Builderman",
        "itemName": "Demo item",
        "itemPrice": 31000,
    }

def settings_for(uid):
    return pending_settings.setdefault(uid, defaults().copy())

def is_admin(update: Update):
    user = update.effective_user
    return bool(user and (
        user.id in ADMIN_IDS or
        (user.username and user.username.lower() in ADMIN_USERNAMES)
    ))

def admin_only(fn):
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if not is_admin(update):
            if update.callback_query:
                await update.callback_query.answer("Нет доступа", show_alert=True)
            elif update.effective_message:
                await update.effective_message.reply_text("⛔ Нет доступа.")
            return
        return await fn(update, context, *args, **kwargs)
    return wrapped

def menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔑 Выдать демо-ключ", callback_data="give")],
        [InlineKeyboardButton("📋 Список ключей", callback_data="keys"),
         InlineKeyboardButton("⚙️ Настройки", callback_data="settings")],
        [InlineKeyboardButton("🌐 Обновить конфиг сайта", callback_data="update"),
         InlineKeyboardButton("ℹ️ Помощь", callback_data="help")],
    ])

async def api(method, endpoint, payload=None):
    if not ADMIN_TOKEN:
        raise RuntimeError("Не задан ADMIN_TOKEN в Render Environment")
    headers = {}
    params = {"admin_token": ADMIN_TOKEN}
    async with httpx.AsyncClient(timeout=20) as client:
        if method == "POST":
            body = dict(payload or {})
            body["admin_token"] = ADMIN_TOKEN
            response = await client.post(SITE_URL + endpoint, json=body, headers=headers)
        else:
            response = await client.get(SITE_URL + endpoint, params=params)
        response.raise_for_status()
        try:
            return response.json()
        except ValueError:
            return {}

async def send_or_edit(update, text, keyboard=None, parse_mode=None):
    if update.callback_query:
        q = update.callback_query
        await q.answer()
        await q.edit_message_text(text, reply_markup=keyboard, parse_mode=parse_mode)
    else:
        await update.effective_message.reply_text(text, reply_markup=keyboard, parse_mode=parse_mode)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.effective_message.reply_text(
            "Привет! Это бот управления демонстрационным сайтом. "
            "Обратитесь к администратору за доступом."
        )
        return
    await update.effective_message.reply_text(
        f"👋 <b>Панель управления демо-сайтом</b>\n\nСайт: {html.escape(SITE_URL)}",
        reply_markup=menu(), parse_mode="HTML"
    )

async def help_cmd(update, context):
    if not is_admin(update):
        return
    await update.effective_message.reply_text(
        "Кнопки меню управляют демо-сайтом.\n\n"
        "/give — мастер создания тестового ключа\n"
        "/keys — список ключей\n"
        "/settings — настройки следующего ключа\n"
        "/set ПАРАМЕТР ЗНАЧЕНИЕ — изменить настройку\n"
        "/update — отправить настройки на сайт\n"
        "/cancel — отменить мастер\n\n"
        "Параметры: robux, nick, name, item, price.\n"
        "Все балансы и награды здесь — только визуальные демонстрационные данные.",
        reply_markup=menu()
    )

async def settings_text(uid):
    s = settings_for(uid)
    return (
        "⚙️ <b>Настройки следующего демо-ключа</b>\n\n"
        f"💎 Визуальный баланс: <code>{s['robuxBalance']:,}</code>\n"
        f"👤 Ник: <code>{html.escape(str(s['profileUsername']))}</code>\n"
        f"📛 Имя: <code>{html.escape(str(s['profileDisplayName']))}</code>\n"
        f"🎁 Демо-предмет: <code>{html.escape(str(s['itemName']))}</code>\n"
        f"💰 Визуальная цена: <code>{s['itemPrice']:,}</code>\n\n"
        "Изменить: /set robux 50000 или кнопкой ниже."
    )

async def settings_cmd(update, context):
    if not is_admin(update): return
    await update.effective_message.reply_text(
        await settings_text(update.effective_user.id),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💎 Баланс", callback_data="edit:robux"),
             InlineKeyboardButton("👤 Ник", callback_data="edit:nick")],
            [InlineKeyboardButton("📛 Имя", callback_data="edit:name"),
             InlineKeyboardButton("🎁 Предмет", callback_data="edit:item")],
            [InlineKeyboardButton("💰 Цена", callback_data="edit:price")],
            [InlineKeyboardButton("⬅️ Меню", callback_data="menu")],
        ])
    )

async def set_cmd(update, context):
    if not is_admin(update): return
    if len(context.args) < 2:
        await update.effective_message.reply_text(
            "Формат: /set robux 50000\nПараметры: robux, nick, name, item, price"
        ); return
    field, value = context.args[0].lower(), " ".join(context.args[1:])
    mapping = {
        "robux": ("robuxBalance", int), "nick": ("profileUsername", str),
        "name": ("profileDisplayName", str), "item": ("itemName", str),
        "price": ("itemPrice", int),
    }
    if field not in mapping:
        await update.effective_message.reply_text("Неизвестный параметр."); return
    target, cast = mapping[field]
    try:
        parsed = cast(value)
        if cast is int and parsed < 0: raise ValueError
        settings_for(update.effective_user.id)[target] = parsed
    except ValueError:
        await update.effective_message.reply_text("Нужно указать корректное неотрицательное число."); return
    await update.effective_message.reply_text(
        "✅ Сохранено.\n\n" + await settings_text(update.effective_user.id),
        parse_mode="HTML", reply_markup=menu()
    )

def parse_duration(value):
    match = re.fullmatch(r"(\d+)(ч|д|м|мес|год)", value.strip().lower())
    if not match: return None
    n, unit = int(match.group(1)), match.group(2)
    mult = {"ч":3600000, "д":86400000, "м":60000,
            "мес":30*86400000, "год":365*86400000}
    return n * mult[unit] if n > 0 else None

@admin_only
async def give_start(update, context):
    context.user_data["give"] = {}
    await update.effective_message.reply_text(
        "Кому выдать тестовый ключ?\nОтправь Telegram ID или username (например @name).",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Отмена", callback_data="cancel")]])
    )
    return WAIT_RECIPIENT

async def got_recipient(update, context):
    context.user_data["give"]["recipient"] = update.message.text.strip().lstrip("@")
    await update.message.reply_text("Укажи визуальный баланс (число):")
    return WAIT_AMOUNT

async def got_amount(update, context):
    try:
        amount = int(update.message.text.replace(",", "").strip())
        if amount < 0: raise ValueError
    except ValueError:
        await update.message.reply_text("Введи неотрицательное число.")
        return WAIT_AMOUNT
    context.user_data["give"]["amount"] = amount
    await update.message.reply_text("Укажи отображаемое имя для демо-профиля:")
    return WAIT_NICK

async def got_nick(update, context):
    nick = update.message.text.strip()
    if not nick or len(nick) > 64:
        await update.message.reply_text("Имя должно содержать от 1 до 64 символов.")
        return WAIT_NICK
    context.user_data["give"]["nick"] = nick
    await update.message.reply_text("Срок действия: например 1ч, 1д, 1мес или 1год:")
    return WAIT_DURATION

async def got_duration(update, context):
    duration_text = update.message.text.strip()
    duration_ms = parse_duration(duration_text)
    if not duration_ms:
        await update.message.reply_text("Неверный срок. Примеры: 1ч, 1д, 1мес, 1год.")
        return WAIT_DURATION
    data = context.user_data.pop("give", {})
    settings = settings_for(update.effective_user.id).copy()
    settings["robuxBalance"] = data["amount"]
    settings["profileDisplayName"] = data["nick"]
    payload = {
        **settings,
        "recipientTg": data["recipient"],
        "robuxBalance": data["amount"],
        "profileDisplayName": data["nick"],
        "expiresAt": int(time.time()*1000) + duration_ms,
    }
    status = await update.message.reply_text("⏳ Создаю тестовый ключ…")
    try:
        result = await api("POST", "/api/bot/create-key", payload)
        key = html.escape(str(result.get("key", "—")))
        await status.edit_text(
            "✅ <b>Тестовый ключ создан</b>\n\n"
            f"Получатель: <code>{html.escape(data['recipient'])}</code>\n"
            f"Ключ: <code>{key}</code>\n"
            f"Срок: <b>{html.escape(duration_text)}</b>\n"
            f"Страница демо: {html.escape(SITE_URL + '/login')}\n\n"
            "Это демонстрационный доступ, не настоящая награда Roblox.",
            parse_mode="HTML", reply_markup=menu()
        )
    except Exception as exc:
        log.exception("create-key failed")
        await status.edit_text(f"❌ Не удалось создать ключ: {html.escape(str(exc))}")
    return ConversationHandler.END

async def cancel(update, context):
    context.user_data.pop("give", None)
    await update.effective_message.reply_text("Создание ключа отменено.", reply_markup=menu())
    return ConversationHandler.END

async def keys_cmd(update, context):
    if not is_admin(update): return
    try:
        data = await api("GET", "/api/bot/keys")
        items = data.get("keys", {})
        if not items:
            await update.effective_message.reply_text("Ключей пока нет.", reply_markup=menu()); return
        lines = [f"🔑 <b>Ключей: {len(items)}</b>"]
        for key, info in list(items.items())[-15:]:
            info = info if isinstance(info, dict) else {}
            state = "использован" if info.get("used") else "активен"
            lines.append(
                f"\n• <code>{html.escape(str(key))}</code> — {state}\n"
                f"  Получатель: <code>{html.escape(str(info.get('recipientTg','—')))}</code>\n"
                f"  Визуальный баланс: {info.get('robuxBalance','—')}"
            )
        await update.effective_message.reply_text(
            "\n".join(lines), parse_mode="HTML", reply_markup=menu()
        )
    except Exception as exc:
        log.exception("keys failed")
        await update.effective_message.reply_text(f"❌ Ошибка API: {exc}", reply_markup=menu())

async def update_config(update, context):
    if not is_admin(update): return
    try:
        s = settings_for(update.effective_user.id).copy()
        result = await api("POST", "/api/bot/update-config", s)
        await update.effective_message.reply_text(
            "✅ Конфигурация демо-сайта отправлена.\n"
            f"Визуальный баланс: {s['robuxBalance']:,}\n"
            f"Профиль: {s['profileUsername']}",
            reply_markup=menu()
        )
    except Exception as exc:
        log.exception("update-config failed")
        await update.effective_message.reply_text(f"❌ Ошибка API: {exc}", reply_markup=menu())

async def callbacks(update, context):
    q = update.callback_query
    if not is_admin(update):
        await q.answer("Нет доступа", show_alert=True); return
    data = q.data or ""
    if data == "menu":
        await q.answer()
        await q.edit_message_text("🛠 Панель управления демо-сайтом", reply_markup=menu())
    elif data == "help":
        await q.answer()
        await q.edit_message_text(
            "Команды: /give, /keys, /settings, /set, /update, /cancel",
            reply_markup=menu()
        )
    elif data == "keys":
        await q.answer()
        try:
            result = await api("GET", "/api/bot/keys")
            items = result.get("keys", {})
            lines = [f"🔑 Ключей: {len(items)}"]
            for key, info in list(items.items())[-10:]:
                info = info if isinstance(info, dict) else {}
                lines.append(f"\n{key} — {'использован' if info.get('used') else 'активен'}")
            await q.edit_message_text("\n".join(lines), reply_markup=menu())
        except Exception as exc:
            await q.edit_message_text(f"Ошибка API: {exc}", reply_markup=menu())
    elif data == "settings":
        await q.answer()
        uid = update.effective_user.id
        await q.edit_message_text(
            await settings_text(uid), parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💎 Баланс", callback_data="edit:robux"),
                 InlineKeyboardButton("👤 Ник", callback_data="edit:nick")],
                [InlineKeyboardButton("📛 Имя", callback_data="edit:name"),
                 InlineKeyboardButton("🎁 Предмет", callback_data="edit:item")],
                [InlineKeyboardButton("💰 Цена", callback_data="edit:price")],
                [InlineKeyboardButton("⬅️ Меню", callback_data="menu")],
            ])
        )
    elif data.startswith("edit:"):
        await q.answer()
        field = data.split(":",1)[1]
        await q.message.reply_text(f"Чтобы изменить поле, отправь: /set {field} новое_значение")
    elif data == "update":
        await q.answer()
        try:
            s = settings_for(update.effective_user.id).copy()
            await api("POST", "/api/bot/update-config", s)
            await q.edit_message_text("✅ Конфигурация демо-сайта обновлена.", reply_markup=menu())
        except Exception as exc:
            await q.edit_message_text(f"❌ Ошибка API: {exc}", reply_markup=menu())
    elif data == "give":
        await q.answer()
        await q.message.reply_text("Запусти мастер командой /give.")
    elif data == "cancel":
        await q.answer()
        context.user_data.pop("give", None)
        await q.edit_message_text("Отменено.", reply_markup=menu())

async def error_handler(update, context):
    log.exception("Unhandled bot error", exc_info=context.error)

def main():
    if not BOT_TOKEN:
        raise RuntimeError("Не задан BOT_TOKEN в Render Environment")
    if not ADMIN_TOKEN:
        raise RuntimeError("Не задан ADMIN_TOKEN в Render Environment")
    app = Application.builder().token(BOT_TOKEN).build()
    conv = ConversationHandler(
        entry_points=[CommandHandler("give", give_start)],
        states={
            WAIT_RECIPIENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_recipient)],
            WAIT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_amount)],
            WAIT_NICK: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_nick)],
            WAIT_DURATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_duration)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )
    app.add_handler(conv)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("settings", settings_cmd))
    app.add_handler(CommandHandler("set", set_cmd))
    # Telegram command names must be Latin; /ключ is not registered.
    app.add_handler(CommandHandler(["key", "givekey"], give_start))
    app.add_handler(CommandHandler("keys", keys_cmd))
    app.add_handler(CommandHandler("update", update_config))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CallbackQueryHandler(callbacks))
    app.add_error_handler(error_handler)
    log.info("Bot starting; site=%s", SITE_URL)
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()

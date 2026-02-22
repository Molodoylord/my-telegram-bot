"""
TENEVERSIYA Sound Design Bot
============================
Telegram Mini App Backend for Render.com
"""
import asyncio
import json
import logging
import hashlib
import hmac
import os
import signal
import sys
from datetime import datetime
from urllib.parse import parse_qsl
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    WebAppInfo
)
from aiogram.enums import ParseMode

# ============================================
# CONFIGURATION
# ============================================

# Берём токен из переменных окружения (безопасно!)
TOKEN = os.environ.get('BOT_TOKEN', '')
ADMIN_ID = int(os.environ.get('ADMIN_ID', '0'))
WEB_APP_URL = os.environ.get('WEB_APP_URL', 'https://molodoylord.github.io/teneversiya-app/')

# Порт для health-check (Render требует открытый порт)
PORT = int(os.environ.get('PORT', 10000))

# ============================================
# LOGGING SETUP
# ============================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# ============================================
# BOT INITIALIZATION (БЕЗ прокси — на Render не нужен)
# ============================================
bot = Bot(token=TOKEN)
dp = Dispatcher()

# ============================================
# HEALTH-CHECK HTTP SERVER
# Render.com пингует сервис — если нет ответа, убивает процесс.
# Это простой HTTP сервер, который отвечает "OK" на любой запрос.
# ============================================

async def health_check(request):
    """Health check endpoint for Render"""
    return web.Response(text="OK", status=200)


async def start_health_server():
    """Start minimal HTTP server for Render health checks"""
    app = web.Application()
    app.router.add_get('/', health_check)
    app.router.add_get('/health', health_check)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logger.info(f"Health-check server started on port {PORT}")
    return runner


# ============================================
# SECURITY: Validate Telegram WebApp Data
# ============================================
def validate_init_data(init_data: str, bot_token: str) -> bool:
    """
    Validate Telegram WebApp init data to prevent spoofing.
    """
    try:
        parsed_data = dict(parse_qsl(init_data))

        if 'hash' not in parsed_data:
            return False

        received_hash = parsed_data.pop('hash')

        data_check_string = '\n'.join(
            f"{k}={v}" for k, v in sorted(parsed_data.items())
        )

        secret_key = hmac.new(
            b"WebAppData",
            bot_token.encode(),
            hashlib.sha256
        ).digest()

        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(received_hash, calculated_hash)

    except Exception as e:
        logger.error(f"Validation error: {e}")
        return False


# ============================================
# SERVICE & GENRE NAMES (for report)
# ============================================
SERVICE_NAMES = {
    'mixing': '🎚 Сведение',
    'lyrics': '✍️ Создание текста',
    'arrangement': '🎹 Аранжировка',
    'help': '🤝 Помощь с треком',
    'fulltrack': '⭐️ Трек под ключ'
}

GENRE_NAMES = {
    'pop': '🎤 Поп',
    'rock': '🎸 Рок',
    'poprock': '🎵 Поп-рок',
    'electronic': '🎧 Электронная',
    'alternative': '🌙 Альтернатива'
}

QUALITY_NAMES = {
    'basic': '📦 Базовое (-10%)',
    'medium': '📊 Среднее (-5%)',
    'best': '💎 Наилучшее (+5%)'
}


# ============================================
# HANDLERS
# ============================================

@dp.message(F.text == "/start")
async def cmd_start(message: Message):
    """Handle /start command"""

    logger.info(f"User {message.from_user.id} started the bot")

    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(
                text="🕯 Сделать заказ",
                web_app=WebAppInfo(url=WEB_APP_URL)
            )]
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )

    welcome_text = """
<b>🌑 TENEVERSIYA</b>
<i>Sound Design Studio</i>

━━━━━━━━━━━━━━━━━━━━

Добро пожаловать в мир тёмного звука.

Мы создаём:
• Сведение и мастеринг
• Авторские тексты
• Аранжировки любой сложности
• Треки под ключ

━━━━━━━━━━━━━━━━━━━━

<b>Нажми кнопку ниже, чтобы оформить заказ</b>
"""

    await message.answer(
        welcome_text,
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML
    )


@dp.message(F.text == "/help")
async def cmd_help(message: Message):
    """Handle /help command"""

    help_text = """
<b>📖 Помощь</b>

<b>Как сделать заказ:</b>
1. Нажми кнопку «🕯 Сделать заказ»
2. Заполни форму в приложении
3. Дождись подтверждения

<b>Команды:</b>
/start - Главное меню
/help - Эта справка
"""

    await message.answer(help_text, parse_mode=ParseMode.HTML)


@dp.message(F.web_app_data)
async def handle_webapp_data(message: Message):
    """Handle data received from WebApp"""

    try:
        data = json.loads(message.web_app_data.data)

        logger.info(f"Received order from user {message.from_user.id}: {data}")

        name = data.get('name', 'Не указано')
        phone = data.get('phone', 'Не указан')
        username = data.get('username', 'Скрыт')
        user_id = data.get('userId', message.from_user.id)

        service = data.get('service', 'N/A')
        service_name = data.get('serviceName', SERVICE_NAMES.get(service, service))
        need_lyrics = data.get('needLyrics', False)

        genre = data.get('genre', 'N/A')
        genre_name = data.get('genreName', GENRE_NAMES.get(genre, genre))

        quality = data.get('quality', 'N/A')
        quality_name = data.get('qualityName', QUALITY_NAMES.get(quality, quality))

        price = data.get('price', 0)
        comment = data.get('comment', '')
        timestamp = data.get('timestamp', datetime.now().isoformat())

        lyrics_info = "✅ Да" if need_lyrics else "❌ Нет"

        admin_report = f"""
<b>🌑 НОВЫЙ ЗАКАЗ</b>
━━━━━━━━━━━━━━━━━━━━

<b>👤 Клиент:</b>
├ Имя: <code>{name}</code>
├ Телефон: <code>{phone}</code>
├ Username: @{username}
└ ID: <code>{user_id}</code>

<b>📋 Заказ:</b>
├ Услуга: {service_name}
├ Нужен текст: {lyrics_info}
├ Жанр: {genre_name}
└ Качество: {quality_name}

<b>💰 Итоговая цена:</b>
<code>{price:,} ₽</code>

<b>💬 Комментарий:</b>
<i>{comment if comment else 'Не указан'}</i>

━━━━━━━━━━━━━━━━━━━━
<i>🕐 {timestamp}</i>
"""

        await bot.send_message(
            ADMIN_ID,
            admin_report,
            parse_mode=ParseMode.HTML
        )

        user_confirmation = f"""
<b>✅ Заказ принят!</b>

Спасибо, <b>{name}</b>!

Твой заказ на <b>{service_name}</b> успешно оформлен.

<b>Итоговая стоимость:</b> <code>{price:,} ₽</code>

Мы свяжемся с тобой в ближайшее время для обсуждения деталей.

<i>🌑 TENEVERSIYA</i>
"""

        await message.answer(
            user_confirmation,
            parse_mode=ParseMode.HTML
        )

        logger.info(f"Order processed successfully for user {message.from_user.id}")

    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {e}")
        await message.answer(
            "❌ Ошибка при обработке заказа. Попробуй ещё раз.",
            parse_mode=ParseMode.HTML
        )

    except Exception as e:
        logger.error(f"Error processing order: {e}")
        await message.answer(
            "❌ Произошла ошибка. Пожалуйста, попробуй позже или напиши нам напрямую.",
            parse_mode=ParseMode.HTML
        )


@dp.message()
async def handle_unknown(message: Message):
    """Handle unknown messages"""

    await message.answer(
        "🌑 Используй кнопку <b>«🕯 Сделать заказ»</b> для оформления заказа.\n\n"
        "Или напиши /help для справки.",
        parse_mode=ParseMode.HTML
    )


# ============================================
# MAIN FUNCTION
# ============================================
async def main():
    """Main function to run the bot"""

    logger.info("=" * 50)
    logger.info("Starting TENEVERSIYA Bot on Render.com...")
    logger.info(f"PORT: {PORT}")
    logger.info(f"WEB_APP_URL: {WEB_APP_URL}")
    logger.info(f"ADMIN_ID: {ADMIN_ID}")
    logger.info(f"BOT_TOKEN: {'SET' if TOKEN else 'NOT SET!'}")
    logger.info("=" * 50)

    if not TOKEN:
        logger.error("BOT_TOKEN is not set! Add it to Render environment variables.")
        sys.exit(1)

    if not ADMIN_ID:
        logger.error("ADMIN_ID is not set! Add it to Render environment variables.")
        sys.exit(1)

    # Start health-check HTTP server (Render needs this!)
    health_runner = await start_health_server()

    # Delete webhook and start polling
    await bot.delete_webhook(drop_pending_updates=True)

    logger.info("Bot is running! Polling started.")

    try:
        await dp.start_polling(bot)
    finally:
        logger.info("Shutting down...")
        await health_runner.cleanup()
        await bot.session.close()


# ============================================
# ENTRY POINT
# ============================================
if __name__ == "__main__":
    asyncio.run(main())

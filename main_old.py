import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from core.config import settings
from bot.handlers import (
    start_handler,
    generation_handler,
    payment_handler,
    balance_handler,
    settings_handler,
    admin_handler,
    support_handler,
    utm_admin_handler
)
from bot.middlewares import (
    ThrottlingMiddleware,
    LoggingMiddleware,
    AuthMiddleware,
    I18nMiddleware
)
from services.database import DatabaseService, init_database
from services.api_monitor import api_monitor

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def setup_logging():
    """Настройка логирования"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

# Создаем экземпляр базы данных
db = DatabaseService()

async def setup_bot_commands(bot: Bot):
    """Настройка команд бота"""
    # Команды для русского языка
    ru_commands = [
        BotCommand(command="start", description="🚀 Начать работу"),
        BotCommand(command="menu", description="🏠 Главное меню"),
        BotCommand(command="generate", description="🎬 Создать видео"),
        BotCommand(command="balance", description="💰 Мой баланс"),
        BotCommand(command="buy", description="🛒 Купить кредиты"),
        BotCommand(command="history", description="📜 История генераций"),
        BotCommand(command="referral", description="👥 Пригласить друга"),
        BotCommand(command="settings", description="⚙️ Настройки"),
        BotCommand(command="help", description="❓ Помощь"),
        BotCommand(command="support", description="💬 Поддержка")
    ]
    
    # Команды для английского языка
    en_commands = [
        BotCommand(command="start", description="🚀 Start working"),
        BotCommand(command="menu", description="🏠 Main menu"),
        BotCommand(command="generate", description="🎬 Create video"),
        BotCommand(command="balance", description="💰 My balance"),
        BotCommand(command="buy", description="🛒 Buy credits"),
        BotCommand(command="history", description="📜 Generation history"),
        BotCommand(command="referral", description="👥 Invite friend"),
        BotCommand(command="settings", description="⚙️ Settings"),
        BotCommand(command="help", description="❓ Help"),
        BotCommand(command="support", description="💬 Support")
    ]
    
    # Устанавливаем команды для разных языков
    await bot.set_my_commands(ru_commands, language_code="ru")
    await bot.set_my_commands(en_commands, language_code="en")
    await bot.set_my_commands(ru_commands)  # По умолчанию

async def on_startup(bot: Bot):
    """Действия при запуске бота"""
    try:
        # Создание необходимых директорий
        import os
        os.makedirs(settings.TEMP_FILES_DIR, exist_ok=True)
        os.makedirs(settings.LOCALES_DIR, exist_ok=True)
        logger.info("Directories created")
        
        # Инициализация БД
        await init_database()
        logger.info("Database initialized")
        
        # Установка команд
        await setup_bot_commands(bot)
        
        if not settings.DEBUG:
            # Установка вебхука для production
            await bot.set_webhook(
                url=settings.WEBHOOK_URL,
                drop_pending_updates=True,
                allowed_updates=["message", "callback_query", "pre_checkout_query", "my_chat_member"]
            )
            logger.info(f"Webhook set to {settings.WEBHOOK_URL}")
        
        logger.info("Bot started successfully")
        
    except Exception as e:
        logger.error(f"Error during startup: {e}")
        raise

async def on_shutdown(bot: Bot):
    """Действия при остановке бота"""
    try:
        if not settings.DEBUG:
            await bot.delete_webhook()
        
        await bot.session.close()
        logger.info("Bot stopped")
        
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")

def register_routers(dp: Dispatcher):
    """Регистрация всех роутеров"""
    dp.include_router(start_handler)
    dp.include_router(generation_handler)
    dp.include_router(payment_handler)
    dp.include_router(balance_handler)
    dp.include_router(settings_handler)
    dp.include_router(support_handler)
    dp.include_router(utm_admin_handler)
    dp.include_router(admin_handler)  # Админ роутер в конце

def register_middlewares(dp: Dispatcher):
    """Регистрация middleware"""
    # Throttling - защита от спама
    dp.message.middleware(ThrottlingMiddleware(rate_limit=0.5))
    dp.callback_query.middleware(ThrottlingMiddleware(rate_limit=0.3))
    
    # Логирование
    dp.message.middleware(LoggingMiddleware())
    dp.callback_query.middleware(LoggingMiddleware())
    
    # Авторизация и проверки
    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())
    
    # Мультиязычность
    dp.message.middleware(I18nMiddleware())
    dp.callback_query.middleware(I18nMiddleware())

async def create_bot_instance():
    """Создание экземпляра бота"""
    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode="HTML")
    )
    return bot

async def create_dispatcher():
    """Создание диспетчера"""
    # Redis storage для FSM
    if settings.REDIS_URL:
        try:
            storage = RedisStorage.from_url(settings.REDIS_URL)
            logger.info("Using RedisStorage")
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}, falling back to MemoryStorage")
            from aiogram.fsm.storage.memory import MemoryStorage
            storage = MemoryStorage()
    else:
        from aiogram.fsm.storage.memory import MemoryStorage
        storage = MemoryStorage()
        logger.warning("Using MemoryStorage - not recommended for production!")
    
    dp = Dispatcher(storage=storage)
    
    # Регистрация компонентов
    register_middlewares(dp)
    register_routers(dp)
    
    # Регистрация событий
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    
    return dp

def create_web_app():
    """Создание веб-приложения для webhook режима"""
    async def create_app():
        bot = await create_bot_instance()
        dp = await create_dispatcher()
        
        app = web.Application()
        
        # Настройка вебхука
        webhook_handler = SimpleRequestHandler(
            dispatcher=dp,
            bot=bot
        )
        webhook_handler.register(app, path=settings.WEBHOOK_PATH)
        setup_application(app, dp, bot=bot)
        
        return app
    
    return create_app()

async def main_polling():
    """Запуск в режиме polling (для разработки)"""
    logger.info("Starting bot in polling mode...")
    
    bot = await create_bot_instance()
    dp = await create_dispatcher()
    
    # Удаляем вебхук если был установлен
    await bot.delete_webhook(drop_pending_updates=True)
    
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

async def main():
    """Главная функция"""
    # Инициализируем логирование
    setup_logging()
    
    # Проверяем подключение к БД
    try:
        await db.check_connection()
        logger.info("Database connection established")
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return
    
    # Создаем бота и диспетчер
    bot = Bot(token=settings.BOT_TOKEN)
    dp = Dispatcher()
    
    # Регистрируем роутеры
    register_routers(dp)
    
    # Регистрируем middleware
    register_middlewares(dp)
    
    # Запускаем задачу восстановления потерянных видео
    try:
        from bot.tasks import recover_lost_videos_task
        logger.info("Starting lost videos recovery task")
        await recover_lost_videos_task()
    except Exception as e:
        logger.error(f"Error starting recovery task: {e}")
    
    # Запускаем мониторинг API
    api_monitor_task = asyncio.create_task(api_monitor.run_monitoring(bot))
    
    try:
        logger.info("Bot started")
        await dp.start_polling(bot)
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    finally:
        api_monitor_task.cancel()
        await bot.session.close()

def main():
    """Основная функция запуска"""
    if settings.DEBUG:
        # Режим разработки - polling
        try:
            asyncio.run(main_polling())
        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
    else:
        # Production режим - webhook
        app = create_web_app()
        web.run_app(
            app,
            host="0.0.0.0",
            port=settings.WEBHOOK_PORT
        )

if __name__ == "__main__":
    main()
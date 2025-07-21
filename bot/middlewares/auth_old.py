import logging
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

from services.database import db
from core.config import settings

logger = logging.getLogger(__name__)

class AuthMiddleware(BaseMiddleware):
    """Middleware для проверки авторизации и банов"""
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        """Проверка пользователя перед обработкой"""
        user = data.get("event_from_user")
        
        if not user:
            return await handler(event, data)
        
        # Проверяем, не забанен ли пользователь
        db_user = await db.get_user(user.id)
        
        if db_user and db_user.is_banned:
            # Пользователь забанен
            ban_message = (
                "🚫 <b>Ваш аккаунт заблокирован</b>\n\n"
                "Если вы считаете, что это ошибка, обратитесь к администратору:\n"
                f"@{settings.BOT_USERNAME}"
            )
            
            if isinstance(event, Message):
                await event.answer(ban_message)
            elif isinstance(event, CallbackQuery):
                await event.answer(
                    "🚫 Ваш аккаунт заблокирован",
                    show_alert=True
                )
            
            logger.warning(f"Banned user {user.id} tried to access bot")
            return
        
        # Проверяем обязательную подписку на канал (если настроено)
        if getattr(settings, 'CHANNEL_USERNAME', None) and settings.CHANNEL_USERNAME.strip():
            if not await self.check_subscription(event, user.id):
                return
        
        # Добавляем пользователя в контекст
        data['db_user'] = db_user
        
        # Продолжаем обработку
        return await handler(event, data)
    
    async def check_subscription(self, event: TelegramObject, user_id: int) -> bool:
        """Проверка подписки на обязательный канал"""
        try:
            # Проверяем статус пользователя в канале
            member = await event.bot.get_chat_member(
                chat_id=f"@{settings.CHANNEL_USERNAME}",
                user_id=user_id
            )
            
            # Проверяем, является ли пользователь участником
            if member.status not in ["member", "administrator", "creator"]:
                subscription_message = (
                    "📢 <b>Требуется подписка</b>\n\n"
                    f"Для использования бота необходимо подписаться на канал:\n"
                    f"👉 @{settings.CHANNEL_USERNAME}\n\n"
                    "После подписки нажмите /start"
                )
                
                from aiogram.utils.keyboard import InlineKeyboardBuilder
                builder = InlineKeyboardBuilder()
                builder.button(
                    text="📢 Подписаться",
                    url=f"https://t.me/{settings.CHANNEL_USERNAME}"
                )
                builder.button(
                    text="✅ Я подписался",
                    callback_data="check_subscription"
                )
                builder.adjust(1)
                
                if isinstance(event, Message):
                    await event.answer(
                        subscription_message,
                        reply_markup=builder.as_markup()
                    )
                elif isinstance(event, CallbackQuery):
                    await event.message.edit_text(
                        subscription_message,
                        reply_markup=builder.as_markup()
                    )
                    await event.answer()
                
                return False
                
        except Exception as e:
            logger.error(f"Error checking subscription: {e}")
            # В случае ошибки пропускаем проверку
            return True
        
        return True

class PermissionMiddleware(BaseMiddleware):
    """Middleware для проверки прав доступа"""
    
    def __init__(self, required_permission: str = None):
        self.required_permission = required_permission
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        """Проверка прав доступа"""
        user = data.get("event_from_user")
        
        if not user:
            return await handler(event, data)
        
        # Получаем пользователя из БД
        db_user = data.get('db_user')
        if not db_user:
            db_user = await db.get_user(user.id)
        
        # Проверяем права
        has_permission = False
        
        if self.required_permission == "admin":
            has_permission = user.id in settings.ADMIN_IDS or (db_user and db_user.is_admin)
        elif self.required_permission == "premium":
            has_permission = db_user and db_user.is_premium
        else:
            # Если нет специальных требований, пропускаем
            has_permission = True
        
        if not has_permission:
            error_message = "❌ У вас нет доступа к этой функции"
            
            if isinstance(event, Message):
                await event.answer(error_message)
            elif isinstance(event, CallbackQuery):
                await event.answer(error_message, show_alert=True)
            
            logger.warning(
                f"User {user.id} tried to access {self.required_permission} function"
            )
            return
        
        return await handler(event, data)

# Обработчик проверки подписки
from aiogram import Router, F
from aiogram.types import CallbackQuery

subscription_router = Router()

@subscription_router.callback_query(F.data == "check_subscription")
async def check_subscription_callback(callback: CallbackQuery):
    """Проверка подписки после нажатия кнопки"""
    user_id = callback.from_user.id
    
    try:
        # Проверяем подписку
        member = await callback.bot.get_chat_member(
            chat_id=f"@{settings.CHANNEL_USERNAME}",
            user_id=user_id
        )
        
        if member.status in ["member", "administrator", "creator"]:
            # Подписка подтверждена
            await callback.message.edit_text(
                "✅ <b>Спасибо за подписку!</b>\n\n"
                "Теперь вы можете использовать все функции бота.\n"
                "Нажмите /start для начала работы."
            )
            await callback.answer("✅ Подписка подтверждена!")
        else:
            # Все еще не подписан
            await callback.answer(
                "❌ Вы еще не подписались на канал!",
                show_alert=True
            )
            
    except Exception as e:
        logger.error(f"Error checking subscription: {e}")
        await callback.answer(
            "❌ Ошибка проверки подписки",
            show_alert=True
        )
# Декоратор для проверки админских прав
def admin_required(handler):
    """
    Декоратор для проверки админских прав
    """
    import functools
    from aiogram.types import Message, CallbackQuery
    from core.config import settings
    
    @functools.wraps(handler)
    async def wrapper(*args, **kwargs):
        # Найти объект с пользователем (Message или CallbackQuery)
        event = None
        for arg in args:
            if isinstance(arg, (Message, CallbackQuery)):
                event = arg
                break
        
        if not event:
            return await handler(*args, **kwargs)
        
        user_id = event.from_user.id
        
        # Проверяем админские права
        if user_id not in settings.ADMIN_IDS:
            # Получаем пользователя из БД для дополнительной проверки
            db_user = await db.get_user(user_id)
            if not (db_user and db_user.is_admin):
                error_message = "❌ У вас нет прав администратора"
                
                if isinstance(event, Message):
                    await event.answer(error_message)
                elif isinstance(event, CallbackQuery):
                    await event.answer(error_message, show_alert=True)
                
                logger.warning(f"Non-admin user {user_id} tried to access admin function")
                return
        
        return await handler(*args, **kwargs)
    
    return wrapper

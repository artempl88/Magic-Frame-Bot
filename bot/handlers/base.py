import logging
from typing import Tuple, Union, Optional
from aiogram.types import Message, CallbackQuery
from aiogram import Bot
from models.models import User, AdminLog
from services.database import db
from bot.middlewares.i18n import get_translator
from datetime import datetime

logger = logging.getLogger(__name__)

class BaseHandler:
    """Базовый класс для обработчиков с общими методами"""
    
    @staticmethod
    async def get_user_and_translator(event: Union[Message, CallbackQuery]) -> Tuple[Optional[User], callable]:
        """
        Получить пользователя и переводчик из события
        
        Args:
            event: Message или CallbackQuery
            
        Returns:
            Tuple[User, translator]: Пользователь и функция переводчика
        """
        try:
            user_id = event.from_user.id
            
            # Получаем пользователя из БД
            user = await db.get_user(user_id)
            
            # Получаем переводчик (по умолчанию русский)
            translator = get_translator(user.language if user else 'ru')
            
            return user, translator
            
        except Exception as e:
            logger.error(f"Ошибка при получении пользователя {user_id}: {e}")
            # Возвращаем переводчик по умолчанию
            return None, get_translator('ru')
    
    @staticmethod
    async def answer_callback(callback: CallbackQuery, text: str = "✅", show_alert: bool = False) -> None:
        """
        Ответить на callback query
        
        Args:
            callback: CallbackQuery для ответа
            text: Текст ответа
            show_alert: Показать как алерт
        """
        try:
            await callback.answer(text=text, show_alert=show_alert)
        except Exception as e:
            logger.error(f"Ошибка при ответе на callback: {e}")
            # Игнорируем ошибки ответа на callback
            pass
    
    @staticmethod
    async def log_admin_action(
        admin_id: int,
        action: str,
        details: str = "",
        target_user_id: Optional[int] = None
    ) -> None:
        """
        Логировать действие администратора
        
        Args:
            admin_id: ID администратора
            action: Тип действия
            details: Детали действия
            target_user_id: ID целевого пользователя (если применимо)
        """
        try:
            admin_log = AdminLog(
                admin_id=admin_id,
                action=action,
                details=details,
                target_user_id=target_user_id,
                timestamp=datetime.utcnow()
            )
            await db.save_admin_log(admin_log)
            
            logger.info(f"Админ {admin_id} выполнил действие: {action} | {details}")
            
        except Exception as e:
            logger.error(f"Ошибка при логировании действия админа: {e}")
    
    @staticmethod
    async def send_safe_message(
        chat_id: int,
        text: str,
        bot: Bot,
        parse_mode: str = "HTML",
        **kwargs
    ) -> bool:
        """
        Безопасная отправка сообщения с обработкой ошибок
        
        Args:
            chat_id: ID чата
            text: Текст сообщения
            bot: Экземпляр бота
            parse_mode: Режим парсинга
            **kwargs: Дополнительные параметры
            
        Returns:
            bool: True если отправлено успешно
        """
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=parse_mode,
                **kwargs
            )
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения в чат {chat_id}: {e}")
            return False
    
    @staticmethod
    async def edit_safe_message(
        callback: CallbackQuery,
        text: str,
        reply_markup=None,
        parse_mode: str = "HTML"
    ) -> bool:
        """
        Безопасное редактирование сообщения
        
        Args:
            callback: CallbackQuery
            text: Новый текст
            reply_markup: Клавиатура
            parse_mode: Режим парсинга
            
        Returns:
            bool: True если отредактировано успешно
        """
        try:
            await callback.message.edit_text(
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при редактировании сообщения: {e}")
            return False 
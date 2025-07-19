import time
from typing import Callable, Dict, Any, Awaitable, Optional
from functools import wraps
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject
import logging

logger = logging.getLogger(__name__)

class ThrottlingMiddleware(BaseMiddleware):
    """Middleware для защиты от спама"""
    
    def __init__(self, rate_limit: float = 0.5):
        """
        Args:
            rate_limit: Минимальное время между запросами в секундах
        """
        self.rate_limit = rate_limit
        self.user_timestamps: Dict[int, float] = {}
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        """Обработка события"""
        user = data.get("event_from_user")
        if not user:
            return await handler(event, data)
        
        user_id = user.id
        current_time = time.time()
        
        # Проверяем время последнего запроса
        if user_id in self.user_timestamps:
            time_passed = current_time - self.user_timestamps[user_id]
            
            if time_passed < self.rate_limit:
                # Слишком частые запросы
                if isinstance(event, Message):
                    await event.answer(
                        "⏱ Слишком много запросов. Подождите немного...",
                        show_alert=False
                    )
                elif isinstance(event, CallbackQuery):
                    await event.answer(
                        "⏱ Подождите немного...",
                        show_alert=True
                    )
                
                logger.warning(f"Rate limit exceeded for user {user_id}")
                return
        
        # Обновляем время последнего запроса
        self.user_timestamps[user_id] = current_time
        
        # Очищаем старые записи (более 1 часа)
        if len(self.user_timestamps) > 1000:
            current_time = time.time()
            self.user_timestamps = {
                uid: timestamp 
                for uid, timestamp in self.user_timestamps.items()
                if current_time - timestamp < 3600
            }
        
        return await handler(event, data)

class UserThrottling:
    """Класс для управления throttling по пользователям"""
    
    def __init__(self):
        self.limits: Dict[str, Dict[int, list]] = {}
    
    def check_limit(
        self,
        user_id: int,
        key: str,
        limit: int,
        window: int = 3600
    ) -> bool:
        """
        Проверка лимита для пользователя
        
        Args:
            user_id: ID пользователя
            key: Ключ лимита (например, 'generations')
            limit: Максимальное количество действий
            window: Временное окно в секундах
            
        Returns:
            True если лимит не превышен
        """
        current_time = time.time()
        
        if key not in self.limits:
            self.limits[key] = {}
        
        if user_id not in self.limits[key]:
            self.limits[key][user_id] = []
        
        # Удаляем старые записи
        self.limits[key][user_id] = [
            timestamp for timestamp in self.limits[key][user_id]
            if current_time - timestamp < window
        ]
        
        # Проверяем лимит
        if len(self.limits[key][user_id]) >= limit:
            return False
        
        # Добавляем новую запись
        self.limits[key][user_id].append(current_time)
        return True
    
    def get_remaining_time(
        self,
        user_id: int,
        key: str,
        window: int = 3600
    ) -> int:
        """Получить время до сброса лимита в секундах"""
        if key not in self.limits or user_id not in self.limits[key]:
            return 0
        
        if not self.limits[key][user_id]:
            return 0
        
        oldest_timestamp = min(self.limits[key][user_id])
        time_passed = time.time() - oldest_timestamp
        remaining = window - time_passed
        
        return max(0, int(remaining))

# Глобальный экземпляр
user_throttling = UserThrottling()

def rate_limit(
    key: Optional[str] = None,
    limit: int = 1,
    window: int = 60
):
    """
    Декоратор для ограничения частоты вызовов
    
    Args:
        key: Ключ для группировки (если None, используется имя функции)
        limit: Максимальное количество вызовов
        window: Временное окно в секундах
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(
            update: Message | CallbackQuery,
            *args,
            **kwargs
        ):
            user_id = update.from_user.id
            limit_key = key or func.__name__
            
            if not user_throttling.check_limit(user_id, limit_key, limit, window):
                remaining = user_throttling.get_remaining_time(user_id, limit_key, window)
                
                if remaining > 60:
                    time_text = f"{remaining // 60} мин"
                else:
                    time_text = f"{remaining} сек"
                
                text = (
                    f"⏱ Превышен лимит ({limit} за {window // 60} мин)\n"
                    f"Попробуйте через {time_text}"
                )
                
                if isinstance(update, Message):
                    await update.answer(text)
                else:
                    await update.answer(text, show_alert=True)
                
                return
            
            return await func(update, *args, **kwargs)
        
        return wrapper
    return decorator

class GenerationThrottling:
    """Специальный throttling для генераций"""
    
    @staticmethod
    async def check_generation_limit(user_id: int) -> tuple[bool, str]:
        """
        Проверка лимитов генерации
        
        Returns:
            (allowed, error_message)
        """
        # Проверяем лимит в минуту
        if not user_throttling.check_limit(
            user_id,
            'generation_per_minute',
            limit=3,
            window=60
        ):
            return False, "Максимум 3 генерации в минуту"
        
        # Проверяем лимит в час
        if not user_throttling.check_limit(
            user_id,
            'generation_per_hour',
            limit=30,
            window=3600
        ):
            remaining = user_throttling.get_remaining_time(
                user_id,
                'generation_per_hour',
                3600
            )
            return False, f"Превышен часовой лимит. Попробуйте через {remaining // 60} мин"
        
        return True, ""
    
    @staticmethod
    def cancel_generation_limit(user_id: int):
        """
        Отменить последний лимит генерации (при неудачной генерации)
        """
        # Удаляем последнюю запись из лимитов
        for key in ['generation_per_minute', 'generation_per_hour']:
            if (key in user_throttling.limits and 
                user_id in user_throttling.limits[key] and 
                user_throttling.limits[key][user_id]):
                user_throttling.limits[key][user_id].pop()  # Удаляем последнюю запись
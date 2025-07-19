import logging
import time
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

logger = logging.getLogger(__name__)

class LoggingMiddleware(BaseMiddleware):
    """Middleware для логирования всех событий"""
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        """Обработка события с логированием"""
        start_time = time.time()
        user = data.get("event_from_user")
        
        # Определяем тип события
        event_type = "unknown"
        event_data = ""
        
        if isinstance(event, Message):
            event_type = "message"
            if event.text:
                event_data = event.text[:50]
            elif event.photo:
                event_data = "photo"
            elif event.video:
                event_data = "video"
            else:
                event_data = str(event.content_type)
                
        elif isinstance(event, CallbackQuery):
            event_type = "callback"
            event_data = event.data or "no_data"
        
        # Логируем начало обработки
        if user:
            logger.info(
                f"Event start | Type: {event_type} | "
                f"User: {user.id} (@{user.username}) | "
                f"Data: {event_data}"
            )
        
        try:
            # Обрабатываем событие
            result = await handler(event, data)
            
            # Логируем успешное завершение
            processing_time = time.time() - start_time
            logger.info(
                f"Event success | Type: {event_type} | "
                f"User: {user.id if user else 'unknown'} | "
                f"Time: {processing_time:.2f}s"
            )
            
            # Обновляем активность пользователя
            if user and hasattr(event, 'bot'):
                from services.database import db
                try:
                    await db.update_user_activity(user.id)
                except Exception as e:
                    logger.error(f"Failed to update user activity: {e}")
            
            return result
            
        except Exception as e:
            # Логируем ошибку
            processing_time = time.time() - start_time
            logger.error(
                f"Event error | Type: {event_type} | "
                f"User: {user.id if user else 'unknown'} | "
                f"Time: {processing_time:.2f}s | "
                f"Error: {str(e)}",
                exc_info=True
            )
            
            # Отправляем пользователю сообщение об ошибке
            try:
                error_text = (
                    "❌ Произошла ошибка при обработке запроса.\n"
                    "Попробуйте позже или обратитесь в поддержку."
                )
                
                if isinstance(event, Message):
                    await event.answer(error_text)
                elif isinstance(event, CallbackQuery):
                    await event.answer(error_text, show_alert=True)
                    
            except Exception as notify_error:
                logger.error(f"Failed to notify user about error: {notify_error}")
            
            # Перебрасываем исключение
            raise

class UserActivityLogger:
    """Класс для логирования активности пользователей"""
    
    @staticmethod
    async def log_action(
        user_id: int,
        action: str,
        details: Dict[str, Any] = None
    ):
        """Логирование действия пользователя"""
        logger.info(
            f"User action | User: {user_id} | "
            f"Action: {action} | "
            f"Details: {details or {}}"
        )
        
        # Можно добавить сохранение в БД для аналитики
        try:
            from services.database import db
            from models.models import UserAction
            
            async with db.async_session() as session:
                action_log = UserAction(
                    user_id=user_id,
                    action=action,
                    details=details
                )
                session.add(action_log)
                await session.commit()
                
        except Exception as e:
            logger.error(f"Failed to save user action to DB: {e}")

class PerformanceLogger:
    """Класс для логирования производительности"""
    
    def __init__(self):
        self.metrics = {}
    
    def log_metric(self, name: str, value: float):
        """Логирование метрики"""
        if name not in self.metrics:
            self.metrics[name] = []
        
        self.metrics[name].append(value)
        
        # Оставляем только последние 1000 значений
        if len(self.metrics[name]) > 1000:
            self.metrics[name] = self.metrics[name][-1000:]
    
    def get_average(self, name: str) -> float:
        """Получить среднее значение метрики"""
        if name not in self.metrics or not self.metrics[name]:
            return 0.0
        
        return sum(self.metrics[name]) / len(self.metrics[name])
    
    def get_report(self) -> Dict[str, Dict[str, float]]:
        """Получить отчет по всем метрикам"""
        report = {}
        
        for name, values in self.metrics.items():
            if values:
                report[name] = {
                    'average': sum(values) / len(values),
                    'min': min(values),
                    'max': max(values),
                    'count': len(values)
                }
        
        return report

# Глобальный экземпляр для метрик
performance_logger = PerformanceLogger()
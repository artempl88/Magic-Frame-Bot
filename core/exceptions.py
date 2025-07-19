"""
Кастомные исключения для Seedance Bot
"""
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class SeedanceBotError(Exception):
    """Базовое исключение для бота"""
    def __init__(self, message: str = None, user_message: str = None, **kwargs):
        super().__init__(message)
        self.user_message = user_message or message
        self.extra = kwargs

class DatabaseError(SeedanceBotError):
    """Ошибка работы с базой данных"""
    pass

class ConnectionError(DatabaseError):
    """Ошибка подключения к БД"""
    pass

class IntegrityError(DatabaseError):
    """Ошибка целостности данных"""
    pass

class APIError(SeedanceBotError):
    """Ошибка работы с API"""
    def __init__(self, message: str = None, status_code: int = None, response: Dict[str, Any] = None, **kwargs):
        super().__init__(message, **kwargs)
        self.status_code = status_code
        self.response = response

class WaveSpeedAPIError(APIError):
    """Ошибка WaveSpeed API"""
    pass

class GenerationError(SeedanceBotError):
    """Ошибка генерации видео"""
    pass

class QueueFullError(GenerationError):
    """Очередь генерации переполнена"""
    def __init__(self, queue_size: int = None):
        super().__init__(
            f"Generation queue is full: {queue_size} tasks",
            user_message="Очередь генерации переполнена. Попробуйте позже."
        )
        self.queue_size = queue_size

class GenerationTimeoutError(GenerationError):
    """Превышено время ожидания генерации"""
    def __init__(self, timeout: int = None):
        super().__init__(
            f"Generation timeout: {timeout}s",
            user_message="Превышено время ожидания. Попробуйте еще раз."
        )
        self.timeout = timeout

class PaymentError(SeedanceBotError):
    """Ошибка платежа"""
    pass

class InsufficientCreditsError(PaymentError):
    """Недостаточно кредитов"""
    def __init__(self, required: int, available: int):
        self.required = required
        self.available = available
        super().__init__(
            f"Insufficient credits: required {required}, available {available}",
            user_message=f"Недостаточно кредитов. Требуется: {required}, доступно: {available}"
        )

class PaymentProviderError(PaymentError):
    """Ошибка платежного провайдера"""
    pass

class RefundError(PaymentError):
    """Ошибка возврата платежа"""
    pass

class ValidationError(SeedanceBotError):
    """Ошибка валидации данных"""
    def __init__(self, field: str = None, value: Any = None, message: str = None):
        self.field = field
        self.value = value
        super().__init__(
            message or f"Validation error for field {field}: {value}",
            user_message=message or "Неверные данные"
        )

class PromptValidationError(ValidationError):
    """Ошибка валидации промпта"""
    pass

class ImageValidationError(ValidationError):
    """Ошибка валидации изображения"""
    pass

class RateLimitError(SeedanceBotError):
    """Превышен лимит запросов"""
    def __init__(self, retry_after: int = None, limit_type: str = None):
        self.retry_after = retry_after
        self.limit_type = limit_type
        
        if retry_after:
            message = f"Rate limit exceeded. Retry after {retry_after} seconds"
            user_message = f"Слишком много запросов. Попробуйте через {retry_after} сек."
        else:
            message = "Rate limit exceeded"
            user_message = "Слишком много запросов. Попробуйте позже."
        
        super().__init__(message, user_message)

class AuthorizationError(SeedanceBotError):
    """Ошибка авторизации"""
    pass

class UserBannedError(AuthorizationError):
    """Пользователь забанен"""
    def __init__(self, reason: str = None):
        self.reason = reason
        super().__init__(
            f"User is banned: {reason}",
            user_message=f"Ваш аккаунт заблокирован. Причина: {reason or 'Нарушение правил'}"
        )

class SubscriptionRequiredError(AuthorizationError):
    """Требуется подписка на канал"""
    def __init__(self, channel_username: str):
        self.channel_username = channel_username
        super().__init__(
            f"Subscription to @{channel_username} required",
            user_message=f"Для использования бота необходимо подписаться на @{channel_username}"
        )

class PermissionDeniedError(AuthorizationError):
    """Недостаточно прав"""
    def __init__(self, required_permission: str = None):
        self.required_permission = required_permission
        super().__init__(
            f"Permission denied: {required_permission} required",
            user_message="У вас недостаточно прав для выполнения этого действия"
        )

class ConfigurationError(SeedanceBotError):
    """Ошибка конфигурации"""
    pass

class MediaError(SeedanceBotError):
    """Ошибка обработки медиа"""
    pass

class VideoProcessingError(MediaError):
    """Ошибка обработки видео"""
    pass

class DownloadError(MediaError):
    """Ошибка загрузки файла"""
    pass

class LocalizationError(SeedanceBotError):
    """Ошибка локализации"""
    def __init__(self, key: str = None, language: str = None):
        self.key = key
        self.language = language
        super().__init__(
            f"Localization error: key={key}, language={language}",
            user_message="Ошибка перевода"
        )

class CacheError(SeedanceBotError):
    """Ошибка кеширования"""
    pass

class TaskError(SeedanceBotError):
    """Ошибка выполнения задачи"""
    pass

class WebhookError(SeedanceBotError):
    """Ошибка вебхука"""
    pass

# Декоратор для обработки исключений
def handle_exceptions(exceptions_map: Dict[type, str] = None, log_errors: bool = True):
    """
    Декоратор для обработки исключений в хендлерах
    
    Usage:
        @handle_exceptions({
            InsufficientCreditsError: "Недостаточно кредитов для операции",
            WaveSpeedAPIError: "Сервис генерации временно недоступен"
        })
        async def handler(message: Message):
            ...
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                # Логируем ошибку если нужно
                if log_errors:
                    logger.error(f"Error in {func.__name__}: {e}", exc_info=True)
                
                # Получаем объект сообщения/коллбека
                update = None
                for arg in args:
                    from aiogram.types import Message, CallbackQuery
                    if isinstance(arg, (Message, CallbackQuery)):
                        update = arg
                        break
                
                # Определяем текст ошибки
                error_text = "❌ Произошла ошибка"
                
                # Проверяем кастомную карту исключений
                if exceptions_map and type(e) in exceptions_map:
                    error_text = exceptions_map[type(e)]
                # Используем user_message из исключения если есть
                elif isinstance(e, SeedanceBotError) and e.user_message:
                    error_text = f"❌ {e.user_message}"
                # Для известных исключений используем стандартные сообщения
                elif isinstance(e, InsufficientCreditsError):
                    error_text = f"❌ Недостаточно кредитов. Требуется: {e.required}, доступно: {e.available}"
                elif isinstance(e, RateLimitError):
                    if e.retry_after:
                        error_text = f"⏱ Слишком много запросов. Попробуйте через {e.retry_after} сек."
                    else:
                        error_text = "⏱ Слишком много запросов. Попробуйте позже."
                elif isinstance(e, UserBannedError):
                    error_text = "🚫 Ваш аккаунт заблокирован"
                elif isinstance(e, ValidationError):
                    error_text = f"❌ Неверные данные: {e.user_message or str(e)}"
                
                # Отправляем сообщение об ошибке
                if update:
                    from aiogram.types import Message, CallbackQuery
                    
                    try:
                        if isinstance(update, Message):
                            await update.answer(error_text)
                        elif isinstance(update, CallbackQuery):
                            await update.answer(error_text, show_alert=True)
                    except Exception as send_error:
                        logger.error(f"Failed to send error message: {send_error}")
                
                # Перебрасываем исключение для middleware
                raise
        
        return wrapper
    return decorator

# Функция для создания безопасного обработчика
def safe_handler(func):
    """
    Создает безопасный обработчик с базовой обработкой ошибок
    
    Usage:
        @safe_handler
        async def my_handler(message: Message):
            ...
    """
    return handle_exceptions()(func)
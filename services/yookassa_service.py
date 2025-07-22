import logging
import uuid
from decimal import Decimal
from typing import Optional, Dict, Any, Tuple
from datetime import datetime

try:
    from yookassa import Configuration, Payment
    from yookassa.domain.exceptions import ApiError
    YOOKASSA_AVAILABLE = True
except ImportError:
    YOOKASSA_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("YooKassa module not installed. Install it with: pip install yookassa")

from core.config import settings

logger = logging.getLogger(__name__)

class YooKassaService:
    """Сервис для работы с платежами ЮКассы"""
    
    def __init__(self):
        self.is_configured = False
        
        if not YOOKASSA_AVAILABLE:
            logger.warning("YooKassa module is not available")
            return
            
        if settings.ENABLE_YOOKASSA and settings.YOOKASSA_SHOP_ID and settings.YOOKASSA_SECRET_KEY:
            Configuration.account_id = settings.YOOKASSA_SHOP_ID
            Configuration.secret_key = settings.YOOKASSA_SECRET_KEY
            self.is_configured = True
            logger.info("YooKassa service initialized")
        else:
            logger.warning("YooKassa service is not configured")
    
    def is_available(self) -> bool:
        """Проверить доступность ЮКассы"""
        return YOOKASSA_AVAILABLE and self.is_configured and settings.ENABLE_YOOKASSA
    
    async def create_payment(
        self,
        amount: Decimal,
        description: str,
        return_url: str,
        user_id: int,
        package_id: str,
        transaction_id: int
    ) -> Tuple[bool, Dict[str, Any], Optional[str]]:
        """
        Создать платеж в ЮКассе
        
        Returns:
            Tuple[success, payment_data, error_message]
        """
        if not self.is_available():
            return False, {}, "ЮКасса не настроена или не установлена"
        
        try:
            # Генерируем уникальный ключ идемпотентности
            idempotency_key = str(uuid.uuid4())
            
            # Создаем платеж
            payment = Payment.create({
                "amount": {
                    "value": str(amount),
                    "currency": "RUB"
                },
                "confirmation": {
                    "type": "redirect",
                    "return_url": return_url
                },
                "capture": True,  # Автоматическое списание
                "description": description[:128],  # YooKassa ограничение
                "metadata": {
                    "user_id": str(user_id),
                    "package_id": package_id,
                    "transaction_id": str(transaction_id),
                    "source": "magic_frame_bot"
                }
            }, idempotency_key)
            
            # Извлекаем данные платежа
            payment_data = {
                "payment_id": payment.id,
                "status": payment.status,
                "confirmation_url": payment.confirmation.confirmation_url if payment.confirmation else None,
                "created_at": payment.created_at,
                "expires_at": getattr(payment, 'expires_at', None)
            }
            
            logger.info(f"YooKassa payment created: {payment.id} for user {user_id}")
            return True, payment_data, None
            
        except ApiError as e:
            error_msg = f"YooKassa API error: {e}"
            logger.error(error_msg)
            return False, {}, self._format_api_error(e)
        except Exception as e:
            error_msg = f"YooKassa unexpected error: {e}"
            logger.error(error_msg, exc_info=True)
            return False, {}, "Неожиданная ошибка при создании платежа"
    
    async def get_payment_info(self, payment_id: str) -> Tuple[bool, Dict[str, Any], Optional[str]]:
        """
        Получить информацию о платеже
        
        Returns:
            Tuple[success, payment_info, error_message]
        """
        if not self.is_available():
            return False, {}, "ЮКасса не настроена или не установлена"
        
        try:
            payment = Payment.find_one(payment_id)
            
            payment_info = {
                "payment_id": payment.id,
                "status": payment.status,
                "amount": float(payment.amount.value) if payment.amount else 0,
                "currency": payment.amount.currency if payment.amount else "RUB",
                "description": payment.description,
                "created_at": payment.created_at,
                "captured_at": getattr(payment, 'captured_at', None),
                "paid": payment.paid,
                "metadata": payment.metadata if payment.metadata else {}
            }
            
            # Добавляем информацию о способе оплаты
            if hasattr(payment, 'payment_method') and payment.payment_method:
                payment_info["payment_method"] = {
                    "type": payment.payment_method.type,
                    "id": payment.payment_method.id,
                    "saved": getattr(payment.payment_method, 'saved', False)
                }
            
            # Добавляем ссылку на чек
            if hasattr(payment, 'receipt_registration') and payment.receipt_registration:
                payment_info["receipt_url"] = getattr(payment.receipt_registration, 'url', None)
            
            # Добавляем причину отмены если есть
            if hasattr(payment, 'cancellation_details') and payment.cancellation_details:
                payment_info["cancellation_reason"] = getattr(payment.cancellation_details, 'reason', None)
            
            return True, payment_info, None
            
        except ApiError as e:
            error_msg = f"YooKassa API error: {e}"
            logger.error(error_msg)
            return False, {}, self._format_api_error(e)
        except Exception as e:
            error_msg = f"YooKassa unexpected error: {e}"
            logger.error(error_msg, exc_info=True)
            return False, {}, "Неожиданная ошибка при получении информации о платеже"
    
    async def cancel_payment(self, payment_id: str, reason: str = "Отмена пользователем") -> Tuple[bool, Optional[str]]:
        """
        Отменить платеж
        
        Returns:
            Tuple[success, error_message]
        """
        if not self.is_available():
            return False, "ЮКасса не настроена или не установлена"
        
        try:
            # Проверяем статус платежа
            payment = Payment.find_one(payment_id)
            
            if payment.status not in ["pending", "waiting_for_capture"]:
                return False, f"Нельзя отменить платеж со статусом {payment.status}"
            
            # Генерируем ключ идемпотентности для отмены
            idempotency_key = str(uuid.uuid4())
            
            # Отменяем платеж
            payment = Payment.cancel(payment_id, idempotency_key)
            
            logger.info(f"YooKassa payment cancelled: {payment_id}")
            return True, None
            
        except ApiError as e:
            error_msg = f"YooKassa API error: {e}"
            logger.error(error_msg)
            return False, self._format_api_error(e)
        except Exception as e:
            error_msg = f"YooKassa unexpected error: {e}"
            logger.error(error_msg, exc_info=True)
            return False, "Неожиданная ошибка при отмене платежа"
    
    async def create_refund(
        self,
        payment_id: str,
        amount: Optional[Decimal] = None,
        reason: str = "Возврат по запросу"
    ) -> Tuple[bool, Dict[str, Any], Optional[str]]:
        """
        Создать возврат платежа
        
        Returns:
            Tuple[success, refund_data, error_message]
        """
        if not self.is_available():
            return False, {}, "ЮКасса не настроена или не установлена"
        
        try:
            from yookassa import Refund
            
            # Создаем возврат
            refund_data = {
                "payment_id": payment_id,
                "description": reason[:128]  # YooKassa ограничение
            }
            
            if amount:
                refund_data["amount"] = {
                    "value": str(amount),
                    "currency": "RUB"
                }
            
            # Генерируем ключ идемпотентности для возврата
            idempotency_key = str(uuid.uuid4())
            
            refund = Refund.create(refund_data, idempotency_key)
            
            result_data = {
                "refund_id": refund.id,
                "status": refund.status,
                "amount": float(refund.amount.value) if refund.amount else 0,
                "created_at": refund.created_at,
                "payment_id": refund.payment_id
            }
            
            logger.info(f"YooKassa refund created: {refund.id} for payment {payment_id}")
            return True, result_data, None
            
        except ApiError as e:
            error_msg = f"YooKassa API error: {e}"
            logger.error(error_msg)
            return False, {}, self._format_api_error(e)
        except Exception as e:
            error_msg = f"YooKassa unexpected error: {e}"
            logger.error(error_msg, exc_info=True)
            return False, {}, "Неожиданная ошибка при создании возврата"
    
    def validate_webhook_signature(
        self,
        request_body: bytes,
        signature: str
    ) -> bool:
        """
        Проверить подпись webhook от ЮКассы
        
        Args:
            request_body: Тело запроса в байтах
            signature: Подпись из заголовка HTTP_X_YOOKASSA_SIGNATURE
        
        Returns:
            bool: True если подпись валидна
        """
        if not self.is_available():
            return False
        
        try:
            import hmac
            import hashlib
            
            # Вычисляем подпись
            secret = settings.YOOKASSA_SECRET_KEY.encode('utf-8')
            calculated_signature = hmac.new(
                secret,
                request_body,
                hashlib.sha256
            ).hexdigest()
            
            # Сравниваем подписи
            return hmac.compare_digest(calculated_signature, signature)
            
        except Exception as e:
            logger.error(f"Webhook signature validation error: {e}")
            return False
    
    def parse_webhook_event(self, event_json: str) -> Tuple[bool, Dict[str, Any], Optional[str]]:
        """
        Парсить событие webhook
        
        Returns:
            Tuple[success, event_data, error_message]
        """
        try:
            import json
            event_data = json.loads(event_json)
            
            # Извлекаем основную информацию
            event_type = event_data.get("event")
            payment_object = event_data.get("object", {})
            
            parsed_data = {
                "event_type": event_type,
                "payment_id": payment_object.get("id"),
                "status": payment_object.get("status"),
                "amount": float(payment_object.get("amount", {}).get("value", 0)),
                "currency": payment_object.get("amount", {}).get("currency", "RUB"),
                "metadata": payment_object.get("metadata", {}),
                "created_at": payment_object.get("created_at"),
                "captured_at": payment_object.get("captured_at"),
                "payment_method": payment_object.get("payment_method", {}),
                "refundable": payment_object.get("refundable", False),
                "test": payment_object.get("test", False),
                "raw_data": event_data
            }
            
            # Добавляем информацию о возврате если это событие возврата
            if "refund" in event_type:
                refund_object = event_data.get("object", {})
                parsed_data.update({
                    "refund_id": refund_object.get("id"),
                    "refund_status": refund_object.get("status"),
                    "refund_amount": float(refund_object.get("amount", {}).get("value", 0))
                })
            
            return True, parsed_data, None
            
        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON in webhook: {e}"
            logger.error(error_msg)
            return False, {}, "Неверный формат данных webhook"
        except Exception as e:
            error_msg = f"Webhook parsing error: {e}"
            logger.error(error_msg)
            return False, {}, "Ошибка при разборе данных webhook"
    
    def _format_api_error(self, api_error: 'ApiError') -> str:
        """Форматировать ошибку API для пользователя"""
        if not YOOKASSA_AVAILABLE:
            return "YooKassa не установлена"
            
        error_code = getattr(api_error, 'code', 'unknown')
        
        error_messages = {
            'invalid_credentials': 'Неверные учетные данные ЮКассы',
            'invalid_request': 'Неверный запрос к ЮКассе',
            'invalid_amount': 'Неверная сумма платежа',
            'payment_not_found': 'Платеж не найден',
            'operation_not_allowed': 'Операция не разрешена',
            'insufficient_funds': 'Недостаточно средств',
            'internal_server_error': 'Внутренняя ошибка ЮКассы'
        }
        
        return error_messages.get(error_code, f'Ошибка ЮКассы: {error_code}')
    
    async def get_balance(self) -> Tuple[bool, Optional[float], Optional[str]]:
        """
        Получить баланс магазина в ЮКассе
        
        Returns:
            Tuple[success, balance, error_message]
        """
        if not self.is_available():
            return False, None, "ЮКасса не настроена или не установлена"
        
        try:
            # В текущей версии YooKassa API нет прямого метода для получения баланса
            # Это заглушка для будущей реализации
            logger.warning("YooKassa balance check is not implemented in current API version")
            return False, None, "Проверка баланса не поддерживается текущей версией API"
            
        except Exception as e:
            error_msg = f"Error checking YooKassa balance: {e}"
            logger.error(error_msg)
            return False, None, "Ошибка при проверке баланса"
    
    async def test_connection(self) -> Tuple[bool, Optional[str]]:
        """
        Проверить соединение с ЮКассой
        
        Returns:
            Tuple[success, error_message]
        """
        if not YOOKASSA_AVAILABLE:
            return False, "Модуль YooKassa не установлен"
            
        if not self.is_configured:
            return False, "ЮКасса не настроена"
        
        try:
            # Пытаемся создать тестовый платеж с минимальной суммой
            test_payment = Payment.create({
                "amount": {
                    "value": "1.00",
                    "currency": "RUB"
                },
                "confirmation": {
                    "type": "redirect",
                    "return_url": "https://example.com"
                },
                "capture": False,
                "test": True,
                "description": "Test connection"
            }, str(uuid.uuid4()))
            
            # Если платеж создан, отменяем его
            if test_payment and test_payment.id:
                try:
                    Payment.cancel(test_payment.id, str(uuid.uuid4()))
                except:
                    pass  # Игнорируем ошибки отмены тестового платежа
            
            logger.info("YooKassa connection test successful")
            return True, None
            
        except ApiError as e:
            error_msg = self._format_api_error(e)
            logger.error(f"YooKassa connection test failed: {e}")
            return False, error_msg
        except Exception as e:
            error_msg = f"Connection test error: {e}"
            logger.error(error_msg)
            return False, "Ошибка при проверке соединения"


# Глобальный экземпляр сервиса
yookassa_service = YooKassaService()
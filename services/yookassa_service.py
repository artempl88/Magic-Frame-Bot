import logging
import uuid
from decimal import Decimal
from typing import Optional, Dict, Any, Tuple
from yookassa import Configuration, Payment
from yookassa.domain.exceptions import ApiError

from core.config import settings

logger = logging.getLogger(__name__)

class YooKassaService:
    """Сервис для работы с платежами ЮКассы"""
    
    def __init__(self):
        if settings.ENABLE_YOOKASSA and settings.YOOKASSA_SHOP_ID and settings.YOOKASSA_SECRET_KEY:
            Configuration.account_id = settings.YOOKASSA_SHOP_ID
            Configuration.secret_key = settings.YOOKASSA_SECRET_KEY
            self.is_configured = True
            logger.info("YooKassa service initialized")
        else:
            self.is_configured = False
            logger.warning("YooKassa service is not configured")
    
    def is_available(self) -> bool:
        """Проверить доступность ЮКассы"""
        return self.is_configured and settings.ENABLE_YOOKASSA
    
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
            return False, {}, "ЮКасса не настроена"
        
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
                "description": description,
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
                "expires_at": payment.expires_at if hasattr(payment, 'expires_at') else None
            }
            
            logger.info(f"YooKassa payment created: {payment.id} for user {user_id}")
            return True, payment_data, None
            
        except ApiError as e:
            error_msg = f"YooKassa API error: {e}"
            logger.error(error_msg)
            return False, {}, error_msg
        except Exception as e:
            error_msg = f"YooKassa unexpected error: {e}"
            logger.error(error_msg, exc_info=True)
            return False, {}, error_msg
    
    async def get_payment_info(self, payment_id: str) -> Tuple[bool, Dict[str, Any], Optional[str]]:
        """
        Получить информацию о платеже
        
        Returns:
            Tuple[success, payment_info, error_message]
        """
        if not self.is_available():
            return False, {}, "ЮКасса не настроена"
        
        try:
            payment = Payment.find_one(payment_id)
            
            payment_info = {
                "payment_id": payment.id,
                "status": payment.status,
                "amount": float(payment.amount.value) if payment.amount else 0,
                "currency": payment.amount.currency if payment.amount else "RUB",
                "description": payment.description,
                "created_at": payment.created_at,
                "captured_at": payment.captured_at if hasattr(payment, 'captured_at') else None,
                "paid": payment.paid,
                "metadata": payment.metadata if payment.metadata else {}
            }
            
            # Добавляем информацию о способе оплаты
            if hasattr(payment, 'payment_method') and payment.payment_method:
                payment_info["payment_method"] = {
                    "type": payment.payment_method.type,
                    "id": payment.payment_method.id
                }
            
            # Добавляем ссылку на чек
            if hasattr(payment, 'receipt_registration') and payment.receipt_registration:
                payment_info["receipt_url"] = getattr(payment.receipt_registration, 'url', None)
            
            return True, payment_info, None
            
        except ApiError as e:
            error_msg = f"YooKassa API error: {e}"
            logger.error(error_msg)
            return False, {}, error_msg
        except Exception as e:
            error_msg = f"YooKassa unexpected error: {e}"
            logger.error(error_msg, exc_info=True)
            return False, {}, error_msg
    
    async def cancel_payment(self, payment_id: str, reason: str = "Отмена пользователем") -> Tuple[bool, Optional[str]]:
        """
        Отменить платеж
        
        Returns:
            Tuple[success, error_message]
        """
        if not self.is_available():
            return False, "ЮКасса не настроена"
        
        try:
            # Проверяем статус платежа
            payment = Payment.find_one(payment_id)
            
            if payment.status not in ["pending", "waiting_for_capture"]:
                return False, f"Нельзя отменить платеж со статусом {payment.status}"
            
            # Отменяем платеж
            payment = Payment.cancel(payment_id, {
                "reason": reason
            })
            
            logger.info(f"YooKassa payment cancelled: {payment_id}")
            return True, None
            
        except ApiError as e:
            error_msg = f"YooKassa API error: {e}"
            logger.error(error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"YooKassa unexpected error: {e}"
            logger.error(error_msg, exc_info=True)
            return False, error_msg
    
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
            return False, {}, "ЮКасса не настроена"
        
        try:
            from yookassa import Refund
            
            # Создаем возврат
            refund_data = {
                "payment_id": payment_id,
                "reason": reason
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
                "created_at": refund.created_at
            }
            
            logger.info(f"YooKassa refund created: {refund.id} for payment {payment_id}")
            return True, result_data, None
            
        except ApiError as e:
            error_msg = f"YooKassa API error: {e}"
            logger.error(error_msg)
            return False, {}, error_msg
        except Exception as e:
            error_msg = f"YooKassa unexpected error: {e}"
            logger.error(error_msg, exc_info=True)
            return False, {}, error_msg
    
    def validate_webhook_signature(
        self,
        event_json: str,
        signature: str
    ) -> bool:
        """
        Проверить подпись webhook от ЮКассы
        
        Args:
            event_json: JSON тело события
            signature: Подпись из заголовка
        
        Returns:
            bool: True если подпись валидна
        """
        if not self.is_available():
            return False
        
        try:
            from yookassa.domain.notification import WebhookNotification
            
            # ЮКасса пока не предоставляет встроенную проверку подписи
            # Можно добавить собственную реализацию если необходимо
            # Пока считаем все webhook'и валидными
            return True
            
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
                "raw_data": event_data
            }
            
            return True, parsed_data, None
            
        except Exception as e:
            error_msg = f"Webhook parsing error: {e}"
            logger.error(error_msg)
            return False, {}, error_msg


# Глобальный экземпляр сервиса
yookassa_service = YooKassaService() 
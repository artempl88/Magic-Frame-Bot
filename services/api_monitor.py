import logging
import asyncio
import aiohttp
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from core.config import settings
from services.database import db

logger = logging.getLogger(__name__)

class APIBalanceMonitor:
    """Сервис для мониторинга баланса API"""
    
    def __init__(self):
        self.api_key = settings.WAVESPEED_API_KEY
        self.api_url = "https://api.wavespeed.ai/api/v3/balance"
        self.low_balance_threshold = 10.0  # $10
        self.critical_balance_threshold = 0.0  # $0
        self._last_notification = {}  # Кеш последних уведомлений
        
    async def check_balance(self) -> Optional[float]:
        """Проверить баланс API"""
        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                
                async with session.get(self.api_url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        if data.get('code') == 200:
                            balance = data.get('data', {}).get('balance')
                            if balance is not None:
                                logger.info(f"API Balance: ${balance}")
                                return float(balance)
                        else:
                            logger.error(f"API balance check failed: {data.get('message', 'Unknown error')}")
                    else:
                        logger.error(f"API balance request failed with status {response.status}")
                        
        except Exception as e:
            logger.error(f"Error checking API balance: {e}")
            
        return None
    
    async def check_and_notify(self, bot=None) -> Dict[str, Any]:
        """Проверить баланс и отправить уведомления при необходимости"""
        balance = await self.check_balance()
        
        if balance is None:
            return {
                'status': 'error',
                'balance': None,
                'message': 'Failed to check API balance'
            }
        
        # Определяем статус
        if balance <= self.critical_balance_threshold:
            status = 'critical'
            message = '🚨 КРИТИЧНО: Баланс API исчерпан ($0)! Генерация видео временно недоступна.'
        elif balance <= self.low_balance_threshold:
            status = 'low'
            message = f'⚠️ ВНИМАНИЕ: Низкий баланс API (${balance})! Требуется пополнение.'
        else:
            status = 'ok'
            message = f'✅ Баланс API в норме (${balance})'
        
        # Отправляем уведомления админам (избегаем спама)
        if status in ['critical', 'low'] and bot:
            await self._notify_admins(bot, balance, status, message)
        
        return {
            'status': status,
            'balance': balance,
            'message': message
        }
    
    async def _notify_admins(self, bot, balance: float, status: str, message: str):
        """Отправить уведомление админам (с защитой от спама)"""
        now = datetime.now()
        
        # Проверяем, не отправляли ли мы уже уведомление недавно
        last_notification = self._last_notification.get(status)
        if last_notification:
            # Для критичного статуса - уведомляем каждые 30 минут
            # Для низкого баланса - каждые 2 часа
            cooldown = timedelta(minutes=30) if status == 'critical' else timedelta(hours=2)
            
            if now - last_notification < cooldown:
                return
        
        # Формируем подробное сообщение для админов
        admin_message = f"""
🔔 <b>УВЕДОМЛЕНИЕ О БАЛАНСЕ API</b>

{message}

📊 <b>Детали:</b>
💰 Текущий баланс: ${balance}
📅 Время проверки: {now.strftime('%d.%m.%Y %H:%M:%S')}
🎯 Пороговые значения:
   • Критичный: ${self.critical_balance_threshold}
   • Низкий: ${self.low_balance_threshold}

{'🚨 <b>ТРЕБУЕТСЯ НЕМЕДЛЕННОЕ ДЕЙСТВИЕ!</b>' if status == 'critical' else '⚠️ <b>Рекомендуется пополнить баланс</b>'}
"""
        
        # Отправляем всем админам
        for admin_id in settings.ADMIN_IDS:
            try:
                await bot.send_message(
                    chat_id=admin_id,
                    text=admin_message,
                    parse_mode='HTML'
                )
                logger.info(f"Balance notification sent to admin {admin_id}")
            except Exception as e:
                logger.error(f"Failed to send balance notification to admin {admin_id}: {e}")
        
        # Обновляем время последнего уведомления
        self._last_notification[status] = now
    
    def is_service_available(self, balance: Optional[float]) -> bool:
        """Проверить, доступен ли сервис генерации"""
        if balance is None:
            return False  # Если не удалось проверить баланс, считаем сервис недоступным
        return balance > self.critical_balance_threshold
    
    def get_maintenance_message(self) -> str:
        """Получить сообщение о технических работах"""
        return (
            "⚠️ <b>Временные технические неполадки</b>\n\n"
            "В данный момент сервис генерации видео временно недоступен "
            "из-за технических работ.\n\n"
            "🔧 Мы уже работаем над устранением проблемы\n"
            "⏰ Сервис будет восстановлен в ближайшее время\n\n"
            "Приносим извинения за неудобства!"
        )

# Глобальный экземпляр монитора
api_monitor = APIBalanceMonitor() 
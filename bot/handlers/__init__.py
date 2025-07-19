"""
Обработчики команд для Seedance Bot
"""

from . import start
from . import generation
from . import payment
from . import balance
from . import settings
from . import support
from . import admin

# Экспортируем роутеры в правильном порядке
# start должен быть первым для обработки /start
# admin должен быть последним для catch-all обработчика
start_handler = start.router
generation_handler = generation.router
payment_handler = payment.router
balance_handler = balance.router
settings_handler = settings.router
support_handler = support.router
admin_handler = admin.router

__all__ = [
    'start_handler',
    'generation_handler', 
    'payment_handler',
    'balance_handler',
    'settings_handler',
    'support_handler',
    'admin_handler'
]
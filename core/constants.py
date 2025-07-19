from enum import Enum
from dataclasses import dataclass
from typing import Dict, List, Optional

# Курсы валют
CURRENCY_RATES = {
    'USD_TO_RUB': 80,
    'STAR_TO_RUB': 1.79,  # 100 Stars = 179 RUB
    'STAR_TO_USD': 0.02,  # Примерный курс
}

# Модели
class ModelType(str, Enum):
    # Seedance V1 Pro
    PRO_T2V_480P = "seedance-v1-pro-t2v-480p"
    PRO_T2V_1080P = "seedance-v1-pro-t2v-1080p"
    PRO_I2V_480P = "seedance-v1-pro-i2v-480p"
    PRO_I2V_1080P = "seedance-v1-pro-i2v-1080p"
    
    # Seedance V1 Lite
    LITE_T2V_480P = "seedance-v1-lite-t2v-480p"
    LITE_T2V_720P = "seedance-v1-lite-t2v-720p"
    LITE_T2V_1080P = "seedance-v1-lite-t2v-1080p"
    LITE_I2V_480P = "seedance-v1-lite-i2v-480p"
    LITE_I2V_720P = "seedance-v1-lite-i2v-720p"
    LITE_I2V_1080P = "seedance-v1-lite-i2v-1080p"
    
    # Google Veo3
    VEO3_T2V = "veo3"
    
    # Google Veo3 Fast
    VEO3_FAST_T2V = "veo3-fast"

# Стоимость генерации в кредитах
GENERATION_COSTS = {
    # Seedance V1 Pro Text-to-Video
    ModelType.PRO_T2V_480P: {5: 15, 10: 25},
    ModelType.PRO_T2V_1080P: {5: 65, 10: 130},
    
    # Seedance V1 Pro Image-to-Video
    ModelType.PRO_I2V_480P: {5: 15, 10: 25},
    ModelType.PRO_I2V_1080P: {5: 65, 10: 130},
    
    # Seedance V1 Lite Text-to-Video
    ModelType.LITE_T2V_480P: {5: 5, 10: 10},
    ModelType.LITE_T2V_720P: {5: 10, 10: 20},
    ModelType.LITE_T2V_1080P: {5: 25, 10: 50},
    
    # Seedance V1 Lite Image-to-Video
    ModelType.LITE_I2V_480P: {5: 5, 10: 10},
    ModelType.LITE_I2V_720P: {5: 10, 10: 20},
    ModelType.LITE_I2V_1080P: {5: 25, 10: 50},
    
    # Google Veo3 (8 секунд фиксированно, примерно 100 кредитов по API)
    ModelType.VEO3_T2V: {8: 100},
    
    # Google Veo3 Fast (8 секунд фиксированно, примерно 20 кредитов по API)
    ModelType.VEO3_FAST_T2V: {8: 20},
}

# Упрощенный доступ к стоимости
def get_generation_cost(model: str, duration: int) -> int:
    """Получить стоимость генерации по модели и длительности"""
    try:
        model_type = ModelType(model)
        return GENERATION_COSTS.get(model_type, {}).get(duration, 0)
    except ValueError:
        # Если модель не найдена, пробуем найти по частичному совпадению
        for mt in ModelType:
            if mt.value in model or model in mt.value:
                return GENERATION_COSTS.get(mt, {}).get(duration, 0)
        return 0

# Информация о моделях
MODEL_INFO = {
    "lite": {
        "name": "Seedance V1 Lite",
        "emoji": "🥈",
        "description": "Экономичная модель с отличным качеством",
        "features": [
            "💰 Низкая стоимость",
            "⚡ Быстрая генерация",
            "📊 Хорошее качество"
        ]
    },
    "pro": {
        "name": "Seedance V1 Pro",
        "emoji": "🥇",
        "description": "Премиум модель с максимальным качеством",
        "features": [
            "🎯 Максимальное качество",
            "🎬 Кинематографичность",
            "🌟 Лучшая детализация"
        ]
    },
    "veo3": {
        "name": "Google Veo3",
        "emoji": "🚀",
        "description": "Революционная модель от Google DeepMind",
        "features": [
            "🎭 Синхронизация губ и диалогов",
            "🎵 Нативная генерация аудио",
            "🎬 Кинематографическое качество",
            "⚡ 8 секунд видео"
        ]
    },
    "veo3_fast": {
        "name": "Google Veo3 Fast",
        "emoji": "⚡",
        "description": "Быстрая и экономичная версия Veo3",
        "features": [
            "🏎️ На 30% быстрее обычного Veo3",
            "💰 До 80% экономии кредитов",
            "🎵 Встроенная генерация аудио",
            "⚡ 8 секунд видео"
        ]
    }
}

# Пакеты кредитов
@dataclass
class CreditPackage:
    id: str
    credits: int
    stars: int
    name: str
    emoji: str
    description: str
    badge: Optional[str] = None
    discount: int = 0
    popular: bool = False
    limited: bool = False

CREDIT_PACKAGES = [
    CreditPackage(
        id='pack_50',
        credits=50,
        stars=180,
        name='Пробный',
        emoji='🌟',
        description='Попробуйте возможности бота\n• ~3-5 видео в Lite 480p\n• Идеально для теста'
    ),
    CreditPackage(
        id='pack_100',
        credits=100,
        stars=350,
        name='Стартовый',
        emoji='🥉',
        description='Идеально для начала\n• ~10-20 видео в Lite 480p\n• ~5-10 видео в Lite 720p'
    ),
    CreditPackage(
        id='pack_300',
        credits=300,
        stars=1000,
        name='Популярный',
        emoji='🥈',
        description='Самый выбираемый пакет\n• ~30-60 видео в Lite 480p\n• ~15-30 видео в Lite 720p',
        badge='🔥 ХИТ',
        popular=True
    ),
    CreditPackage(
        id='pack_500',
        credits=500,
        stars=1600,
        name='Оптимальный',
        emoji='🥇',
        description='Для активных пользователей\n• ~50-100 видео в Lite 480p\n• ~20-50 видео в Lite 1080p',
        badge='💎 -5%',
        discount=5
    ),
    CreditPackage(
        id='pack_1000',
        credits=1000,
        stars=3000,
        name='Продвинутый',
        emoji='💎',
        description='Для профессионалов\n• ~100-200 видео в Lite\n• ~15-40 видео в Pro 480p',
        badge='🎯 -10%',
        discount=10
    ),
    CreditPackage(
        id='pack_2000',
        credits=2000,
        stars=5500,
        name='Профи',
        emoji='🚀',
        description='Максимум возможностей\n• ~200-400 видео в Lite\n• ~30-80 видео в Pro 480p',
        badge='⭐ -15%',
        discount=15
    ),
    CreditPackage(
        id='pack_5000',
        credits=5000,
        stars=13000,
        name='Максимальный',
        emoji='👑',
        description='VIP пакет\n• ~500-1000 видео в Lite\n• ~75-200 видео в Pro 480p',
        badge='🎁 -20%',
        discount=20
    )
]

# Специальные предложения
SPECIAL_OFFERS = [
    {
        'id': 'new_user',
        'name': '🎁 Подарок новичку',
        'credits': 30,
        'stars': 99,
        'condition': 'one_time',
        'description': 'Единоразовое предложение для новых пользователей\n• Только один раз\n• Действует 24 часа'
    },
    {
        'id': 'referral_bonus',
        'name': '👥 Бонус за друга',
        'credits': 20,
        'stars': 0,
        'condition': 'per_referral',
        'description': 'Получите 20 кредитов за каждого приглашенного друга'
    }
]

# Статусы генерации
class GenerationStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

# Типы транзакций
class TransactionType(str, Enum):
    PURCHASE = "purchase"
    BONUS = "bonus"
    REFERRAL = "referral"
    ADMIN_GIFT = "admin_gift"
    REFUND = "refund"
    GENERATION = "generation"  # Добавлен для списания за генерацию

# Соотношения сторон
ASPECT_RATIOS = {
    "16:9": "🖥 Широкий (YouTube, ТВ)",
    "9:16": "📱 Вертикальный (Reels, TikTok)",
    "1:1": "⬜ Квадратный (Instagram)"
}

# Разрешения
RESOLUTIONS = {
    "480p": {
        "name": "480p", 
        "emoji": "📱", 
        "description": "Базовое качество",
        "width": 854,
        "height": 480
    },
    "720p": {
        "name": "720p HD", 
        "emoji": "📺", 
        "description": "Высокое качество",
        "width": 1280,
        "height": 720
    },
    "1080p": {
        "name": "1080p Full HD", 
        "emoji": "🎬", 
        "description": "Максимальное качество",
        "width": 1920,
        "height": 1080
    }
}

# Длительность
DURATIONS = {
    5: {"name": "5 секунд", "emoji": "⚡", "description": "Короткое видео"},
    10: {"name": "10 секунд", "emoji": "⏱", "description": "Стандартное видео"}
}

# Языки (только русский и английский)
LANGUAGES = {
    "ru": {
        "name": "Русский",
        "native_name": "Русский",
        "emoji": "🇷🇺",
        "code": "ru"
    },
    "en": {
        "name": "English",
        "native_name": "English",
        "emoji": "🇬🇧",
        "code": "en"
    }
}

# Бонусы
WELCOME_BONUS_CREDITS = 10
NEW_USER_BONUS = WELCOME_BONUS_CREDITS  # Псевдоним для совместимости

# Эмодзи для статусов
STATUS_EMOJIS = {
    GenerationStatus.PENDING: "⏳",
    GenerationStatus.PROCESSING: "🔄",
    GenerationStatus.COMPLETED: "✅",
    GenerationStatus.FAILED: "❌",
    GenerationStatus.CANCELLED: "🚫"
}

# Лимиты
LIMITS = {
    "max_prompt_length": 2000,
    "min_prompt_length": 10,
    "max_image_size": 10 * 1024 * 1024,  # 10 MB
    "min_image_dimension": 300,
    "max_image_dimension": 4096,
    "max_queue_size": 100,
    "generations_per_minute": 3,
    "generations_per_hour": 30,
    "max_file_age_days": 30,  # Хранение файлов
    "max_user_generations": 1000,  # Максимум генераций на пользователя
}

# Промокоды (пример)
PROMO_CODES = {
    "WELCOME2024": {
        "type": "percentage",
        "value": 20,
        "min_amount": 500,
        "max_uses": 1000,
        "expires": "2024-12-31",
        "description": "Скидка 20% для новых пользователей"
    },
    "SEEDANCE": {
        "type": "percentage",
        "value": 10,
        "min_amount": 300,
        "max_uses": None,  # Безлимитный
        "expires": "2024-12-31",
        "description": "Постоянная скидка 10%"
    },
    "BONUS50": {
        "type": "fixed",
        "value": 50,  # 50 кредитов бонусом
        "min_amount": 1000,
        "max_uses": 500,
        "expires": "2024-06-30",
        "description": "Бонус 50 кредитов при покупке от 1000"
    }
}

# Настройки очереди
QUEUE_SETTINGS = {
    "max_concurrent_generations": 10,
    "priority_boost_premium": 2,  # Приоритет для премиум пользователей
    "retry_attempts": 3,
    "retry_delay": 60,  # секунд
}

# Категории поддержки
SUPPORT_CATEGORIES = {
    "payment": "💳 Проблемы с оплатой",
    "generation": "🎬 Проблемы с генерацией",
    "technical": "🐛 Технические проблемы",
    "suggestion": "💡 Предложения",
    "other": "❓ Другое"
}

# Роли пользователей
class UserRole(str, Enum):
    USER = "user"
    PREMIUM = "premium"
    VIP = "vip"
    MODERATOR = "moderator"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"

# Права доступа по ролям
ROLE_PERMISSIONS = {
    UserRole.USER: ["generate", "view_history", "buy_credits"],
    UserRole.PREMIUM: ["generate", "view_history", "buy_credits", "priority_queue"],
    UserRole.VIP: ["generate", "view_history", "buy_credits", "priority_queue", "extended_limits"],
    UserRole.MODERATOR: ["generate", "view_history", "buy_credits", "view_reports", "ban_users"],
    UserRole.ADMIN: ["all"],
    UserRole.SUPER_ADMIN: ["all", "system_settings"]
}
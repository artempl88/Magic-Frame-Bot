import os
from typing import List, Optional
from pydantic import field_validator
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

class Settings(BaseSettings):
    """Настройки приложения"""
    
    # Telegram
    BOT_TOKEN: str = "test_token"
    BOT_USERNAME: str = "MagicFrameBot"
    
    # WaveSpeed API
    WAVESPEED_API_KEY: str = "test_key"
    WAVESPEED_BASE_URL: str = "https://api.wavespeed.ai"
    
    # Database
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "seedance_bot"
    DB_USER: str = "seedance"
    DB_PASSWORD: str = "test_password"
    
    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
    
    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: Optional[str] = None
    REDIS_DB: int = 0
    
    @property
    def REDIS_URL(self) -> str:
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
    
    # Webhook (Production)
    WEBHOOK_HOST: Optional[str] = None
    WEBHOOK_PATH: str = "/webhook"
    WEBHOOK_PORT: int = 8080
    
    @property
    def WEBHOOK_URL(self) -> Optional[str]:
        if self.WEBHOOK_HOST:
            return f"{self.WEBHOOK_HOST}{self.WEBHOOK_PATH}"
        return None
    
    # Settings
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    
    # Admin
    ADMIN_IDS: List[int] = []
    ADMIN_CHANNEL_ID: Optional[int] = None  # Канал для уведомлений админам
    
    @field_validator('ADMIN_IDS', mode='before')
    @classmethod
    def parse_admin_ids(cls, v):
        if isinstance(v, str):
            # Убираем комментарии и пробелы
            clean_str = v.split('#')[0].strip()
            if not clean_str:
                return []
            return [int(id.strip()) for id in clean_str.split(',') if id.strip().isdigit()]
        elif isinstance(v, int):
            return [v]
        return v or []
    
    @field_validator('ADMIN_CHANNEL_ID', mode='before')
    @classmethod
    def parse_admin_channel_id(cls, v):
        if v is None or v == '':
            return None
        if isinstance(v, str):
            # Поддерживаем формат @channel_name или -100xxxxx
            if v.startswith('@'):
                return v
            if v.startswith('-100') and v[4:].isdigit():
                return int(v)
            if v.isdigit():
                return int(v)
        return v
    
    # Support
    SUPPORT_CHAT_ID: Optional[int] = None
    CHANNEL_USERNAME: Optional[str] = None  # Канал для обязательной подписки
    
    @field_validator('SUPPORT_CHAT_ID', mode='before')
    @classmethod
    def parse_support_chat_id(cls, v):
        if v is None or v == '':
            return None
        if isinstance(v, str):
            if v.startswith('#') or not v.strip().lstrip('-').isdigit():
                return None
            return int(v)
        return v
    
    # Payments
    PAYMENT_PROVIDER_TOKEN: Optional[str] = None  # Для других платежных систем (не Stars)
    ENABLE_TELEGRAM_STARS: bool = True
    
    # YooKassa (ЮКасса) - ТЕСТОВЫЕ ДАННЫЕ!
    # ⚠️ ВАЖНО: Для продакшена обязательно замените на реальные креденшиалы!
    YOOKASSA_SHOP_ID: Optional[str] = "381764678"  # Тестовый магазин
    YOOKASSA_SECRET_KEY: Optional[str] = "TEST:132257"  # Тестовый ключ
    ENABLE_YOOKASSA: bool = True  # Включаем для тестирования
    YOOKASSA_WEBHOOK_URL: Optional[str] = "/yookassa/webhook"  # URL для получения уведомлений от ЮКассы
    
    @property
    def YOOKASSA_WEBHOOK_ENDPOINT(self) -> Optional[str]:
        """Полный URL для webhook ЮКассы"""
        if self.WEBHOOK_HOST and self.YOOKASSA_WEBHOOK_URL:
            return f"{self.WEBHOOK_HOST}/yookassa/webhook"
        return None
    
    # Files
    MAX_FILE_SIZE: int = 10 * 1024 * 1024  # 10 MB
    ALLOWED_IMAGE_TYPES: List[str] = ["image/jpeg", "image/jpg", "image/png"]
    TEMP_FILES_DIR: str = "/app/temp_files"
    
    # Generation limits
    MAX_PROMPT_LENGTH: int = 2000
    MIN_PROMPT_LENGTH: int = 10
    MIN_GENERATION_DURATION: int = 5
    MAX_GENERATION_DURATION: int = 10
    MAX_QUEUE_SIZE: int = 100
    GENERATION_TIMEOUT: int = 300  # 5 минут
    
    # Rate limits
    GENERATIONS_PER_MINUTE: int = 3
    GENERATIONS_PER_HOUR: int = 30
    API_REQUESTS_PER_SECOND: float = 10.0
    
    # Celery
    CELERY_BROKER_URL: Optional[str] = None
    CELERY_RESULT_BACKEND: Optional[str] = None
    CELERY_TASK_TIME_LIMIT: int = 300
    CELERY_TASK_SOFT_TIME_LIMIT: int = 240
    
    @property
    def CELERY_CONFIG(self) -> dict:
        return {
            'broker_url': self.CELERY_BROKER_URL or f"{self.REDIS_URL}/1",
            'result_backend': self.CELERY_RESULT_BACKEND or f"{self.REDIS_URL}/1",
            'task_serializer': 'json',
            'accept_content': ['json'],
            'result_serializer': 'json',
            'timezone': 'UTC',
            'enable_utc': True,
            'task_track_started': True,
            'task_time_limit': self.CELERY_TASK_TIME_LIMIT,
            'task_soft_time_limit': self.CELERY_TASK_SOFT_TIME_LIMIT,
        }
    
    # Monitoring
    SENTRY_DSN: Optional[str] = None
    ENABLE_METRICS: bool = True
    METRICS_PORT: int = 9090
    
    # Security
    SECRET_KEY: str = "test_secret_key_12345"
    ENVIRONMENT: str = "production"
    ENABLE_CORS: bool = False
    ALLOWED_ORIGINS: List[str] = []
    
    # Новые пользователи и бонусы
    WELCOME_BONUS_CREDITS: int = 10
    REFERRAL_BONUS_CREDITS: int = 20  # Бонус рефереру
    REFERRAL_FRIEND_BONUS_CREDITS: int = 10  # Бонус приглашенному другу
    MAX_REFERRAL_BONUS_PER_DAY: int = 100  # Максимум реферальных бонусов в день
    
    # Кеширование
    CACHE_TTL: int = 3600  # 1 час
    USER_CACHE_TTL: int = 300  # 5 минут
    STATS_CACHE_TTL: int = 600  # 10 минут
    
    # Локализация
    DEFAULT_LANGUAGE: str = "ru"
    LOCALES_DIR: str = "/app/locales"
    
    # Медиа
    CDN_URL: Optional[str] = None
    ENABLE_VIDEO_COMPRESSION: bool = False
    VIDEO_QUALITY_PRESET: str = "medium"  # low, medium, high
    
    # Аналитика
    ENABLE_ANALYTICS: bool = True
    ANALYTICS_SAMPLE_RATE: float = 0.1  # 10% выборка
    
    # Резервное копирование
    BACKUP_ENABLED: bool = True
    BACKUP_INTERVAL_HOURS: int = 24
    BACKUP_RETENTION_DAYS: int = 7
    
    model_config = {
        "env_file": ".env",
        "case_sensitive": True,
        "extra": "ignore"
    }

# Создаем экземпляр настроек
settings = Settings()

# Настройка логирования
import logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Настройка Sentry если указан DSN
if settings.SENTRY_DSN and settings.SENTRY_DSN.startswith('https://'):
    try:
        import sentry_sdk
        from sentry_sdk.integrations.aiohttp import AioHttpIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
        
        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            integrations=[
                AioHttpIntegration(),
                SqlalchemyIntegration(),
            ],
            environment=settings.ENVIRONMENT,
            traces_sample_rate=0.1 if settings.ENVIRONMENT == "production" else 1.0,
            profiles_sample_rate=0.1 if settings.ENVIRONMENT == "production" else 1.0,
        )
        logging.info("Sentry initialized successfully")
    except Exception as e:
        logging.error(f"Failed to initialize Sentry: {e}")

# Создание директорий перенесено в main.py
# чтобы избежать проблем с правами в Celery контейнерах
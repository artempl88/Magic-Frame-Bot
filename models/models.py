from sqlalchemy import Column, Integer, BigInteger, String, DateTime, Boolean, JSON, Float, Text, ForeignKey, Index, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

Base = declarative_base()

# Перечисления для статусов
class GenerationStatusEnum(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class TransactionStatusEnum(str, enum.Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"

class TransactionTypeEnum(str, enum.Enum):
    PURCHASE = "purchase"
    BONUS = "bonus"
    REFERRAL = "referral"
    ADMIN_GIFT = "admin_gift"
    REFUND = "refund"
    GENERATION = "generation"

class TicketStatusEnum(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String(100), nullable=True, index=True)  # Добавлен индекс для поиска
    first_name = Column(String(100), nullable=True, index=True)  # Добавлен индекс для поиска
    last_name = Column(String(100), nullable=True)
    language_code = Column(String(10), default='ru')
    
    # Баланс и статистика
    balance = Column(Integer, default=0)  # Баланс устанавливается в create_user
    total_spent = Column(Integer, default=0)
    total_bought = Column(Integer, default=0)
    total_bonuses = Column(Integer, default=0)  # Добавлено для отслеживания бонусов
    
    # Реферальная система
    referrer_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    referral_count = Column(Integer, default=0)
    referral_earnings = Column(Integer, default=0)
    
    # Статусы
    is_banned = Column(Boolean, default=False, index=True)
    ban_reason = Column(String(500), nullable=True)  # Добавлено
    banned_at = Column(DateTime, nullable=True)  # Добавлено
    is_admin = Column(Boolean, default=False)
    is_premium = Column(Boolean, default=False)
    premium_until = Column(DateTime, nullable=True)  # Добавлено для временного премиума
    
    # Настройки
    settings = Column(JSON, default=lambda: {
        'notifications': True,
        'language': 'ru',
        'quality_preference': '720p',
        'show_tips': True,
        'show_in_stats': True,
        'allow_messages': True
    })
    
    # Даты
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    last_active = Column(DateTime, default=datetime.utcnow)
    first_purchase_at = Column(DateTime, nullable=True)
    
    # Отношения
    generations = relationship("Generation", back_populates="user", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="user", cascade="all, delete-orphan")
    tickets = relationship("SupportTicket", back_populates="user", cascade="all, delete-orphan")
    promo_usages = relationship("PromoCodeUsage", back_populates="user", cascade="all, delete-orphan")
    actions = relationship("UserAction", back_populates="user", cascade="all, delete-orphan")
    
    # Самоссылка для рефералов
    referrals = relationship("User", backref="referrer", remote_side=[id])
    
    # Индексы для оптимизации
    __table_args__ = (
        Index('idx_user_referrer', 'referrer_id'),
        Index('idx_user_created', 'created_at'),
        Index('idx_user_active', 'last_active'),
        Index('idx_user_balance', 'balance'),
    )

class Generation(Base):
    __tablename__ = 'generations'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    
    # Параметры генерации
    mode = Column(String(10))  # t2v или i2v
    model = Column(String(50))  # seedance-v1-lite-t2v-480p и т.д.
    resolution = Column(String(10))  # 480p, 720p, 1080p
    duration = Column(Integer)  # 5 или 10
    aspect_ratio = Column(String(10))  # 16:9, 9:16, 1:1
    
    # Контент
    prompt = Column(Text)
    negative_prompt = Column(Text, nullable=True)
    image_url = Column(String(500), nullable=True)  # Исходное изображение
    video_url = Column(String(500), nullable=True)  # URL сгенерированного видео
    video_file_id = Column(String(200), nullable=True)  # Telegram file_id для быстрой отправки
    thumbnail_url = Column(String(500), nullable=True)
    
    # Параметры генерации
    seed = Column(Integer, default=-1)
    
    # Статистика
    cost = Column(Integer)  # Стоимость в кредитах
    used_bonus_credits = Column(Boolean, default=False)  # Использованы ли бонусные кредиты
    file_size = Column(Float, nullable=True)  # Размер в МБ
    generation_time = Column(Float, nullable=True)  # Время генерации в секундах
    queue_time = Column(Float, nullable=True)  # Время в очереди
    
    # Статус
    status = Column(Enum(GenerationStatusEnum), default=GenerationStatusEnum.PENDING, index=True)
    error_message = Column(Text, nullable=True)
    error_code = Column(String(50), nullable=True)
    
    # WaveSpeed API
    task_id = Column(String(100), nullable=True, index=True)
    queue_position = Column(Integer, nullable=True)
    progress = Column(Integer, default=0)  # Прогресс генерации 0-100
    
    # Оценка пользователя
    rating = Column(Integer, nullable=True)  # Оценка от 1 до 5
    feedback = Column(Text, nullable=True)
    
    # Даты
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    # Отношения
    user = relationship("User", back_populates="generations")
    
    # Индексы
    __table_args__ = (
        Index('idx_generation_user', 'user_id'),
        Index('idx_generation_status', 'status'),
        Index('idx_generation_created', 'created_at'),
        Index('idx_generation_task', 'task_id'),
    )

class Transaction(Base):
    __tablename__ = 'transactions'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    
    # Тип и сумма
    type = Column(Enum(TransactionTypeEnum), nullable=False, index=True)
    amount = Column(Integer)  # Количество кредитов (может быть отрицательным)
    balance_before = Column(Integer, nullable=True)  # Баланс до транзакции
    balance_after = Column(Integer)  # Баланс после транзакции
    
    # Платежная информация
    stars_paid = Column(Integer, nullable=True)  # Оплачено Stars
    package_id = Column(String(50), nullable=True)
    payment_id = Column(String(100), nullable=True)  # Telegram payment ID
    telegram_charge_id = Column(String(200), nullable=True, index=True)  # Для возвратов
    
    # Связанные объекты
    generation_id = Column(Integer, ForeignKey('generations.id'), nullable=True)
    promo_code_id = Column(Integer, ForeignKey('promo_codes.id'), nullable=True)
    
    # Дополнительная информация
    description = Column(String(500), nullable=True)
    meta_data = Column(JSON, nullable=True)
    
    # Статус
    status = Column(Enum(TransactionStatusEnum), default=TransactionStatusEnum.PENDING, index=True)
    
    # Даты
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    completed_at = Column(DateTime, nullable=True)
    refunded_at = Column(DateTime, nullable=True)
    
    # Отношения
    user = relationship("User", back_populates="transactions")
    generation = relationship("Generation", backref="transaction")
    promo_code = relationship("PromoCode", backref="transactions")
    
    # Индексы
    __table_args__ = (
        Index('idx_transaction_user', 'user_id'),
        Index('idx_transaction_type', 'type'),
        Index('idx_transaction_status', 'status'),
        Index('idx_transaction_created', 'created_at'),
        Index('idx_transaction_charge', 'telegram_charge_id'),
    )

class PromoCode(Base):
    __tablename__ = 'promo_codes'
    
    id = Column(Integer, primary_key=True)
    code = Column(String(50), unique=True, nullable=False, index=True)
    
    # Параметры промокода
    type = Column(String(20))  # percentage, fixed, bonus
    value = Column(Integer)  # Процент скидки или количество кредитов
    min_amount = Column(Integer, nullable=True)  # Минимальная сумма покупки
    
    # Ограничения
    max_uses = Column(Integer, nullable=True)  # Максимальное количество использований
    uses_count = Column(Integer, default=0)
    max_uses_per_user = Column(Integer, default=1)
    
    # Активность
    is_active = Column(Boolean, default=True, index=True)
    expires_at = Column(DateTime, nullable=True, index=True)
    
    # Даты
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(Integer, nullable=True)  # ID админа
    
    # Отношения
    usages = relationship("PromoCodeUsage", back_populates="promo_code", cascade="all, delete-orphan")

class PromoCodeUsage(Base):
    __tablename__ = 'promo_code_usages'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    promo_code_id = Column(Integer, ForeignKey('promo_codes.id'), nullable=False)
    transaction_id = Column(Integer, ForeignKey('transactions.id'), nullable=True)
    
    # Информация об использовании
    discount_amount = Column(Integer, nullable=True)  # Сумма скидки
    bonus_amount = Column(Integer, nullable=True)  # Сумма бонуса
    
    used_at = Column(DateTime, default=datetime.utcnow)
    
    # Отношения
    user = relationship("User", back_populates="promo_usages")
    promo_code = relationship("PromoCode", back_populates="usages")
    transaction = relationship("Transaction", backref="promo_usage")
    
    # Уникальность использования промокода пользователем
    __table_args__ = (
        Index('idx_promo_usage_unique', 'user_id', 'promo_code_id', unique=True),
    )

class SupportTicket(Base):
    __tablename__ = 'support_tickets'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    
    # Информация о тикете
    subject = Column(String(200))
    message = Column(Text)
    category = Column(String(50))  # technical, payment, generation, suggestion, other
    
    # Статус
    status = Column(Enum(TicketStatusEnum), default=TicketStatusEnum.OPEN, index=True)
    priority = Column(String(20), default='normal')  # low, normal, high, urgent
    
    # Ответ поддержки
    admin_id = Column(Integer, nullable=True)
    admin_response = Column(Text, nullable=True)
    admin_notes = Column(Text, nullable=True)  # Внутренние заметки
    
    # Даты
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)
    response_time = Column(Float, nullable=True)  # Время ответа в часах
    
    # Отношения
    user = relationship("User", back_populates="tickets")
    
    # Индексы
    __table_args__ = (
        Index('idx_ticket_user', 'user_id'),
        Index('idx_ticket_status', 'status'),
        Index('idx_ticket_created', 'created_at'),
    )

class Statistics(Base):
    __tablename__ = 'statistics'
    
    id = Column(Integer, primary_key=True)
    date = Column(DateTime, unique=True, nullable=False, index=True)
    
    # Пользователи
    new_users = Column(Integer, default=0)
    active_users = Column(Integer, default=0)
    paying_users = Column(Integer, default=0)
    
    # Генерации
    total_generations = Column(Integer, default=0)
    successful_generations = Column(Integer, default=0)
    failed_generations = Column(Integer, default=0)
    cancelled_generations = Column(Integer, default=0)
    
    # Финансы
    revenue_stars = Column(Integer, default=0)
    revenue_credits = Column(Integer, default=0)
    refunds_count = Column(Integer, default=0)
    refunds_amount = Column(Integer, default=0)
    
    # Средние показатели
    avg_generation_time = Column(Float, nullable=True)
    avg_queue_time = Column(Float, nullable=True)
    avg_purchase_amount = Column(Float, nullable=True)
    avg_user_balance = Column(Float, nullable=True)
    
    # Дополнительная статистика
    total_api_calls = Column(Integer, default=0)
    api_errors = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=datetime.utcnow)

class AdminLog(Base):
    __tablename__ = 'admin_logs'
    
    id = Column(Integer, primary_key=True)
    admin_id = Column(BigInteger, nullable=False, index=True)
    action = Column(String(100), index=True)
    target_user_id = Column(BigInteger, nullable=True, index=True)
    
    # Детали действия
    details = Column(JSON, nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Индекс для поиска по админу и дате
    __table_args__ = (
        Index('idx_admin_log_admin_date', 'admin_id', 'created_at'),
    )

class UserAction(Base):
    __tablename__ = 'user_actions'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    
    # Информация о действии
    action = Column(String(100), nullable=False, index=True)
    category = Column(String(50), nullable=True)  # navigation, generation, payment, etc
    details = Column(JSON, nullable=True)
    
    # Контекст
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    session_id = Column(String(100), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Отношения
    user = relationship("User", back_populates="actions")
    
    # Индексы
    __table_args__ = (
        Index('idx_user_action_user', 'user_id'),
        Index('idx_user_action_action', 'action'),
        Index('idx_user_action_created', 'created_at'),
        Index('idx_user_action_session', 'session_id'),
    )

# =================== UTM АНАЛИТИКА ===================

class UTMCampaign(Base):
    """UTM кампании - сгенерированные ссылки"""
    __tablename__ = 'utm_campaigns'
    
    id = Column(Integer, primary_key=True)
    
    # UTM параметры
    utm_source = Column(String(100), nullable=False, index=True)  # vk, telegram, youtube
    utm_medium = Column(String(100), nullable=False, index=True)  # cpc, banner, post
    utm_campaign = Column(String(200), nullable=False, index=True)  # summer_promo_2024
    utm_content = Column(String(200), nullable=True)  # button_top, banner_main
    utm_term = Column(String(200), nullable=True)  # ключевые слова (опционально)
    
    # Метаданные кампании
    name = Column(String(200), nullable=False)  # Понятное название кампании
    description = Column(Text, nullable=True)  # Описание кампании
    action_type = Column(String(50), nullable=False, default='registration')  # registration, purchase, visit
    
    # Сгенерированная ссылка
    utm_link = Column(Text, nullable=False)  # Полная сгенерированная ссылка
    short_code = Column(String(20), unique=True, nullable=False, index=True)  # Короткий код для ссылки
    
    # Администрирование
    created_by_admin_id = Column(BigInteger, nullable=False)  # ID админа, создавшего кампанию
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True, index=True)
    
    # Статистика (денормализация для быстроты)
    total_clicks = Column(Integer, default=0)
    total_registrations = Column(Integer, default=0)
    total_purchases = Column(Integer, default=0)
    total_revenue = Column(Float, default=0.0)
    
    # Связи
    utm_clicks = relationship("UTMClick", back_populates="campaign", cascade="all, delete-orphan")
    utm_events = relationship("UTMEvent", back_populates="campaign", cascade="all, delete-orphan")
    
    # Индексы
    __table_args__ = (
        Index('idx_utm_campaign_source', 'utm_source'),
        Index('idx_utm_campaign_medium', 'utm_medium'),
        Index('idx_utm_campaign_name', 'utm_campaign'),
        Index('idx_utm_campaign_created', 'created_at'),
        Index('idx_utm_campaign_active', 'is_active'),
        Index('idx_utm_campaign_admin', 'created_by_admin_id'),
    )

class UTMClick(Base):
    """Клики по UTM ссылкам"""
    __tablename__ = 'utm_clicks'
    
    id = Column(Integer, primary_key=True)
    
    # Связи
    campaign_id = Column(Integer, ForeignKey('utm_campaigns.id'), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True, index=True)  # Может быть NULL для анонимов
    
    # Данные клика
    telegram_id = Column(BigInteger, nullable=True, index=True)  # ID пользователя в Telegram
    clicked_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Техническая информация
    user_agent = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True)  # IPv6 поддержка
    referrer = Column(Text, nullable=True)
    
    # Дополнительные UTM параметры (если переданы)
    additional_params = Column(JSON, nullable=True)  # Любые дополнительные параметры
    
    # Флаги
    is_first_visit = Column(Boolean, default=True, index=True)  # Первый ли это визит пользователя
    is_registered_user = Column(Boolean, default=False, index=True)  # Зарегистрированный ли пользователь
    
    # Связи
    campaign = relationship("UTMCampaign", back_populates="utm_clicks")
    user = relationship("User", backref="utm_clicks")
    
    # Индексы
    __table_args__ = (
        Index('idx_utm_click_campaign', 'campaign_id'),
        Index('idx_utm_click_user', 'user_id'),
        Index('idx_utm_click_telegram', 'telegram_id'),
        Index('idx_utm_click_date', 'clicked_at'),
        Index('idx_utm_click_first', 'is_first_visit'),
    )

class UTMEvent(Base):
    """События пользователей, привязанные к UTM кампаниям"""
    __tablename__ = 'utm_events'
    
    id = Column(Integer, primary_key=True)
    
    # Связи
    campaign_id = Column(Integer, ForeignKey('utm_campaigns.id'), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    click_id = Column(Integer, ForeignKey('utm_clicks.id'), nullable=True, index=True)  # Связь с кликом
    
    # Данные события
    event_type = Column(String(50), nullable=False, index=True)  # registration, purchase, generation, etc
    event_data = Column(JSON, nullable=True)  # Дополнительные данные события
    
    # Временные метки
    event_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Ценностные метрики
    revenue = Column(Float, nullable=True)  # Выручка от события (для покупок)
    credits_spent = Column(Integer, nullable=True)  # Потрачено кредитов
    credits_purchased = Column(Integer, nullable=True)  # Куплено кредитов
    
    # Метаданные
    session_id = Column(String(100), nullable=True, index=True)  # ID сессии пользователя
    time_from_click = Column(Integer, nullable=True)  # Время от клика до события (в секундах)
    
    # Связи
    campaign = relationship("UTMCampaign", back_populates="utm_events")
    user = relationship("User", backref="utm_events")
    click = relationship("UTMClick", backref="utm_events")
    
    # Индексы
    __table_args__ = (
        Index('idx_utm_event_campaign', 'campaign_id'),
        Index('idx_utm_event_user', 'user_id'),
        Index('idx_utm_event_type', 'event_type'),
        Index('idx_utm_event_date', 'event_at'),
        Index('idx_utm_event_click', 'click_id'),
        Index('idx_utm_event_session', 'session_id'),
    )
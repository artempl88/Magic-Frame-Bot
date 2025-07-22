from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from typing import List, Optional

from core.constants import (
    LANGUAGES, CREDIT_PACKAGES, RESOLUTIONS, 
    DURATIONS, ASPECT_RATIOS, MODEL_INFO
)

# Импортируем i18n глобально для оптимизации
from bot.middlewares.i18n import i18n as global_i18n

def get_language_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора языка"""
    builder = InlineKeyboardBuilder()
    
    for code, lang_info in LANGUAGES.items():
        builder.button(
            text=f"{lang_info['emoji']} {lang_info['name']}",
            callback_data=f"set_language_{code}"
        )
    
    builder.adjust(2)
    return builder.as_markup()

def get_aspect_ratio_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """Выбор соотношения сторон"""
    _ = lambda key, **kwargs: global_i18n.get(key, language, **kwargs)
    
    builder = InlineKeyboardBuilder()
    
    for ratio, description in ASPECT_RATIOS.items():
        builder.button(
            text=description,
            callback_data=f"ratio_{ratio.replace(':', '_')}"
        )
    
    builder.button(
        text=f"◀️ {_('common.back')}",
        callback_data="back_to_duration"
    )
    
    builder.adjust(1)
    return builder.as_markup()

def get_generation_confirm_keyboard(cost: int, language: str = "ru") -> InlineKeyboardMarkup:
    """Подтверждение генерации"""
    _ = lambda key, **kwargs: global_i18n.get(key, language, **kwargs)
    
    builder = InlineKeyboardBuilder()
    
    builder.button(
        text=f"✅ {_('generation.confirm')} ({cost} {_('common.credits', default='кредитов')})",
        callback_data="confirm_generation"
    )
    builder.button(
        text=f"❌ {_('common.cancel')}",
        callback_data="cancel_generation"
    )
    
    builder.adjust(1)
    return builder.as_markup()

def get_shop_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """Магазин кредитов"""
    _ = lambda key, **kwargs: global_i18n.get(key, language, **kwargs)
    
    builder = InlineKeyboardBuilder()
    
    for package in CREDIT_PACKAGES:
        button_text = f"{package.emoji} {package.credits} {_('common.credits')}"
        if package.badge:
            button_text += f" {package.badge}"
        
        builder.button(
            text=button_text,
            callback_data=f"buy_{package.id}"
        )
    
    builder.button(
        text=f"🎁 {_('shop.special_offers')}",
        callback_data="special_offers"
    )
    
    builder.button(
        text=f"◀️ {_('menu.main_menu')}",
        callback_data="back_to_menu"
    )
    
    # Размещаем пакеты по 2 в ряд, остальные кнопки по одной
    rows = []
    for i in range(0, len(CREDIT_PACKAGES), 2):
        rows.append(2)
    rows.extend([1, 1])  # Для последних двух кнопок
    
    builder.adjust(*rows)
    return builder.as_markup()

def get_package_details_keyboard(package_id: str, language: str = "ru") -> InlineKeyboardMarkup:
    """Детали пакета"""
    _ = lambda key, **kwargs: global_i18n.get(key, language, **kwargs)
    
    builder = InlineKeyboardBuilder()
    
    builder.button(
        text=f"💳 {_('shop.pay', default='Оплатить')}",
        callback_data=f"pay_{package_id}"
    )
    builder.button(
        text=f"◀️ {_('shop.back_to_packages', default='Назад к пакетам')}",
        callback_data="shop"
    )
    
    builder.adjust(1)
    return builder.as_markup()

def get_payment_keyboard(url: str, language: str = "ru") -> InlineKeyboardMarkup:
    """Кнопка оплаты"""
    _ = lambda key, **kwargs: global_i18n.get(key, language, **kwargs)
    
    builder = InlineKeyboardBuilder()
    
    builder.button(
        text=f"💳 {_('payment.pay_with_stars', default='Оплатить через Telegram Stars')}",
        url=url
    )
    builder.button(
        text=f"❌ {_('common.cancel')}",
        callback_data="shop"
    )
    
    builder.adjust(1)
    return builder.as_markup()

def get_generation_rating_keyboard(generation_id: int, language: str = "ru") -> InlineKeyboardMarkup:
    """Оценка генерации"""
    _ = lambda key, **kwargs: global_i18n.get(key, language, **kwargs)
    
    builder = InlineKeyboardBuilder()
    
    # Звездочки для оценки
    for i in range(1, 6):
        builder.button(
            text="⭐" * i,
            callback_data=f"rate_{generation_id}_{i}"
        )
    
    builder.button(
        text=_("generation.skip_rating", default="Пропустить"),
        callback_data="skip_rating"
    )
    
    builder.adjust(5, 1)
    return builder.as_markup()

def get_history_keyboard(
    generations: List,
    page: int = 1,
    total_pages: int = 1,
    language: str = "ru"
) -> InlineKeyboardMarkup:
    """История генераций"""
    _ = lambda key, **kwargs: global_i18n.get(key, language, **kwargs)
    
    builder = InlineKeyboardBuilder()
    
    # Кнопки для каждой генерации
    for gen in generations:
        from core.constants import STATUS_EMOJIS
        status_emoji = STATUS_EMOJIS.get(gen.status, "❓")
        builder.button(
            text=f"{status_emoji} {gen.created_at.strftime('%d.%m %H:%M')} - {gen.resolution}",
            callback_data=f"gen_details_{gen.id}"
        )
    
    # Навигация по страницам
    nav_buttons = []
    if page > 1:
        nav_buttons.append(
            InlineKeyboardButton(
                text="◀️",
                callback_data=f"history_page_{page-1}"
            )
        )
    
    nav_buttons.append(
        InlineKeyboardButton(
            text=f"{page}/{total_pages}",
            callback_data="noop"
        )
    )
    
    if page < total_pages:
        nav_buttons.append(
            InlineKeyboardButton(
                text="▶️",
                callback_data=f"history_page_{page+1}"
            )
        )
    
    builder.row(*nav_buttons)
    builder.row(
        InlineKeyboardButton(
            text=f"◀️ {_('menu.main_menu')}",
            callback_data="back_to_menu"
        )
    )
    
    return builder.as_markup()

def get_settings_keyboard(user_settings: dict, language: str = "ru") -> InlineKeyboardMarkup:
    """Настройки пользователя"""
    _ = lambda key, **kwargs: global_i18n.get(key, language, **kwargs)
    
    builder = InlineKeyboardBuilder()
    
    # Язык
    current_lang = LANGUAGES.get(user_settings.get('language', language), {}).get('name', 'Русский')
    builder.button(
        text=f"🌐 {_('settings.language')}: {current_lang}",
        callback_data="change_language"
    )
    
    # Уведомления
    notif_status = "✅" if user_settings.get('notifications', True) else "❌"
    builder.button(
        text=f"🔔 {_('settings.notifications')}: {notif_status}",
        callback_data="toggle_notifications"
    )
    
    # Качество по умолчанию
    quality = user_settings.get('quality_preference', '720p')
    builder.button(
        text=f"📊 {_('settings.quality_preference')}: {quality}",
        callback_data="change_quality"
    )
    
    # Показывать подсказки
    tips_status = "✅" if user_settings.get('show_tips', True) else "❌"
    builder.button(
        text=f"💡 {_('settings.tips')}: {tips_status}",
        callback_data="toggle_tips"
    )
    
    # Информация об аккаунте
    builder.button(
        text=f"👤 {_('settings.account_info', default='Информация об аккаунте')}",
        callback_data="account_info"
    )
    
    # Настройки приватности
    builder.button(
        text=f"🔐 {_('settings.privacy', default='Приватность')}",
        callback_data="privacy_settings"
    )
    
    builder.button(
        text=f"◀️ {_('menu.main_menu')}",
        callback_data="back_to_menu"
    )
    
    builder.adjust(1)
    return builder.as_markup()

def get_admin_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """Админ панель"""
    _ = lambda key, **kwargs: global_i18n.get(key, language, **kwargs)
    
    builder = InlineKeyboardBuilder()
    
    builder.button(text=f"📊 {_('admin.statistics')}", callback_data="admin_stats")
    builder.button(text=f"👥 {_('admin.users.title')}", callback_data="admin_users")
    builder.button(text=f"📢 {_('admin.broadcast.title')}", callback_data="admin_broadcast")
    builder.button(text=f"🎁 {_('admin.credits.title')}", callback_data="admin_give_credits")
    builder.button(text=f"🚫 {_('admin.bans.title')}", callback_data="admin_bans")
    builder.button(text=f"💾 {_('admin.backup.title', default='Бэкапы БД')}", callback_data="admin_backup")
    builder.button(text=f"💰 {_('admin.prices.title', default='Управление ценами')}", callback_data="admin_prices")
    builder.button(text=f"🧩 UTM Аналитика", callback_data="utm_analytics")
    builder.button(text=f"💰 {_('admin.api_balance')}", callback_data="admin_api_balance")
    builder.button(text=f"📋 {_('admin.logs.title')}", callback_data="admin_logs")
    builder.button(text=f"◀️ {_('menu.main_menu')}", callback_data="back_to_menu")
    
    builder.adjust(2, 2, 2, 2, 2, 1)
    return builder.as_markup()

def get_support_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """Поддержка"""
    _ = lambda key, **kwargs: global_i18n.get(key, language, **kwargs)
    
    builder = InlineKeyboardBuilder()
    
    builder.button(
        text=f"❓ {_('support.faq')}",
        callback_data="faq"
    )
    builder.button(
        text=f"✍️ {_('support.new_ticket')}",
        callback_data="new_ticket"
    )
    builder.button(
        text=f"📋 {_('support.my_tickets', default='Мои обращения')}",
        callback_data="my_tickets"
    )
    
    builder.button(
        text=f"◀️ {_('menu.main_menu')}",
        callback_data="back_to_menu"
    )
    
    builder.adjust(1)
    return builder.as_markup()

def get_price_management_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура управления ценами"""
    _ = lambda key, **kwargs: global_i18n.get(key, language, **kwargs)
    
    builder = InlineKeyboardBuilder()
    
    builder.button(text=f"📊 {_('admin.prices.view', default='Текущие цены')}", callback_data="price_view")
    builder.button(text=f"✏️ {_('admin.prices.edit', default='Изменить цены')}", callback_data="price_edit")
    builder.button(text=f"💳 {_('admin.prices.yookassa', default='Настройки ЮКассы')}", callback_data="price_yookassa")
    builder.button(text=f"📈 {_('admin.prices.history', default='История цен')}", callback_data="price_history")
    builder.button(text=f"🔄 {_('admin.prices.reset', default='Сбросить цены')}", callback_data="price_reset")
    builder.button(text="◀️ Админ-панель", callback_data="admin_panel")
    
    builder.adjust(2, 2, 1, 1)
    return builder.as_markup()

def get_package_edit_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура выбора пакета для редактирования"""
    _ = lambda key, **kwargs: global_i18n.get(key, language, **kwargs)
    
    builder = InlineKeyboardBuilder()
    
    for package in CREDIT_PACKAGES:
        builder.button(
            text=f"{package.emoji} {package.name}",
            callback_data=f"price_edit_{package.id}"
        )
    
    builder.button(text=f"◀️ {_('admin.back')}", callback_data="admin_prices")
    
    builder.adjust(2, 1)
    return builder.as_markup()

def get_price_edit_options_keyboard(package_id: str, language: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура опций редактирования цены"""
    _ = lambda key, **kwargs: global_i18n.get(key, language, **kwargs)
    
    builder = InlineKeyboardBuilder()
    
    builder.button(text=f"⭐ {_('price.edit_stars', default='Цена в Stars')}", callback_data=f"price_stars_{package_id}")
    builder.button(text=f"💳 {_('price.edit_rub', default='Цена в рублях')}", callback_data=f"price_rub_{package_id}")
    builder.button(text=f"📝 {_('price.edit_note', default='Добавить заметку')}", callback_data=f"price_note_{package_id}")
    builder.button(text=f"🗑 {_('price.delete', default='Удалить кастомную цену')}", callback_data=f"price_delete_{package_id}")
    builder.button(text=f"◀️ {_('admin.back')}", callback_data="price_edit")
    
    builder.adjust(2, 1, 1, 1)
    return builder.as_markup()

def get_backup_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура управления бэкапами"""
    _ = lambda key, **kwargs: global_i18n.get(key, language, **kwargs)
    
    builder = InlineKeyboardBuilder()
    
    builder.button(
        text=f"➕ {_('admin.backup.create', default='Создать бэкап')}",
        callback_data="backup_create"
    )
    builder.button(
        text=f"📁 {_('admin.backup.list', default='Список бэкапов')}",
        callback_data="backup_list"
    )
    builder.button(
        text=f"📊 {_('admin.backup.stats', default='Статистика')}",
        callback_data="backup_stats"
    )
    builder.button(
        text=f"🧹 {_('admin.backup.cleanup', default='Очистить старые')}",
        callback_data="backup_cleanup"
    )
    builder.button(
        text=f"◀️ {_('common.back')}",
        callback_data="admin_panel"
    )
    
    builder.adjust(2, 2, 1)
    return builder.as_markup()

def get_backup_list_keyboard(backups: list, language: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура со списком бэкапов"""
    _ = lambda key, **kwargs: global_i18n.get(key, language, **kwargs)
    
    builder = InlineKeyboardBuilder()
    
    # Показываем только последние 10 бэкапов
    for backup in backups[:10]:
        created_at = backup['created_at'].strftime('%d.%m %H:%M')
        size_mb = backup['size_mb']
        button_text = f"📄 {backup['filename'][:20]}... ({size_mb:.1f}MB)"
        
        builder.button(
            text=button_text,
            callback_data=f"backup_info_{backup['filename']}"
        )
    
    builder.button(
        text=f"🔄 {_('common.refresh')}",
        callback_data="backup_list"
    )
    builder.button(
        text=f"◀️ {_('common.back')}",
        callback_data="admin_backup"
    )
    
    builder.adjust(1)
    return builder.as_markup()

def get_backup_info_keyboard(filename: str, language: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура для действий с конкретным бэкапом"""
    _ = lambda key, **kwargs: global_i18n.get(key, language, **kwargs)
    
    builder = InlineKeyboardBuilder()
    
    builder.button(
        text=f"🗑️ {_('admin.backup.delete', default='Удалить')}",
        callback_data=f"backup_delete_{filename}"
    )
    builder.button(
        text=f"⚠️ {_('admin.backup.restore', default='Восстановить')}",
        callback_data=f"backup_restore_{filename}"
    )
    builder.button(
        text=f"◀️ {_('common.back')}",
        callback_data="backup_list"
    )
    
    builder.adjust(2, 1)
    return builder.as_markup()

def get_cancel_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """Кнопка отмены для генерации"""
    _ = lambda key, **kwargs: global_i18n.get(key, language, **kwargs)
    
    builder = InlineKeyboardBuilder()
    builder.button(text=f"❌ {_('common.cancel')}", callback_data="cancel_generation")
    return builder.as_markup()

def get_simple_cancel_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """Простая кнопка отмены для общих случаев"""
    _ = lambda key, **kwargs: global_i18n.get(key, language, **kwargs)
    
    builder = InlineKeyboardBuilder()
    builder.button(text=f"❌ {_('common.cancel')}", callback_data="cancel")
    return builder.as_markup()

def get_back_keyboard(callback_data: str = "back", language: str = "ru") -> InlineKeyboardMarkup:
    """Простая кнопка назад"""
    _ = lambda key, **kwargs: global_i18n.get(key, language, **kwargs)
    
    builder = InlineKeyboardBuilder()
    builder.button(text=f"◀️ {_('common.back')}", callback_data=callback_data)
    return builder.as_markup()

def get_main_menu(language: str = "ru", balance: int = 0) -> InlineKeyboardMarkup:
    """Главное меню"""
    _ = lambda key, **kwargs: global_i18n.get(key, language, **kwargs)
    
    builder = InlineKeyboardBuilder()
    
    # Основные кнопки
    builder.button(text=f"🎬 {_('menu.generate')}", callback_data="generate")
    builder.button(text=f"💰 {_('menu.balance', balance=balance)}", callback_data="balance")
    builder.button(text=f"💎 {_('menu.buy_credits')}", callback_data="shop")
    builder.button(text=f"📜 {_('menu.history')}", callback_data="history")
    builder.button(text=f"⚙️ {_('menu.settings')}", callback_data="settings")
    builder.button(text=f"❓ {_('menu.help')}", callback_data="help_menu")
    builder.button(text=f"💬 {_('menu.support')}", callback_data="support")
    
    builder.adjust(2, 2, 2, 1)
    return builder.as_markup()

def get_generation_mode_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """Выбор режима генерации"""
    _ = lambda key, **kwargs: global_i18n.get(key, language, **kwargs)
    
    builder = InlineKeyboardBuilder()
    
    builder.button(
        text=f"📝 {_('generation.text_to_video')}",
        callback_data="mode_t2v"
    )
    builder.button(
        text=f"🖼 {_('generation.image_to_video')}",
        callback_data="mode_i2v"
    )
    builder.button(
        text=f"❌ {_('common.cancel')}",
        callback_data="back_to_menu"
    )
    
    builder.adjust(1)
    return builder.as_markup()

def get_model_selection_keyboard(mode: str, language: str = "ru") -> InlineKeyboardMarkup:
    """Выбор модели"""
    _ = lambda key, **kwargs: global_i18n.get(key, language, **kwargs)
    
    builder = InlineKeyboardBuilder()
    
    # Только для Text-to-Video показываем Google Veo3
    if mode == "t2v":
        # Google Veo3 Fast
        veo3_fast_info = MODEL_INFO["veo3_fast"]
        builder.button(
            text=f"{veo3_fast_info['emoji']} {veo3_fast_info['name']}",
            callback_data=f"model_veo3_fast_{mode}"
        )
        
        # Google Veo3
        veo3_info = MODEL_INFO["veo3"]
        builder.button(
            text=f"{veo3_info['emoji']} {veo3_info['name']}",
            callback_data=f"model_veo3_{mode}"
        )
    
    # Lite модель
    lite_info = MODEL_INFO["lite"]
    builder.button(
        text=f"{lite_info['emoji']} {lite_info['name']}",
        callback_data=f"model_lite_{mode}"
    )
    
    # Pro модель
    pro_info = MODEL_INFO["pro"]
    builder.button(
        text=f"{pro_info['emoji']} {pro_info['name']}",
        callback_data=f"model_pro_{mode}"
    )
    
    builder.button(
        text=f"🤔 {_('models.compare')}",
        callback_data="compare_models"
    )
    
    builder.button(
        text=f"◀️ {_('common.back')}",
        callback_data="generate"
    )
    
    builder.adjust(1)
    return builder.as_markup()

def get_resolution_keyboard(model_type: str, language: str = "ru") -> InlineKeyboardMarkup:
    """Выбор разрешения"""
    _ = lambda key, **kwargs: global_i18n.get(key, language, **kwargs)
    
    builder = InlineKeyboardBuilder()
    
    # Для Pro версии убираем 720p
    available_resolutions = RESOLUTIONS.copy()
    if model_type == "pro":
        available_resolutions.pop("720p", None)
    
    for res_id, res_info in available_resolutions.items():
        builder.button(
            text=f"{res_info['emoji']} {res_info['name']}",
            callback_data=f"res_{res_id}"
        )
    
    builder.button(
        text=f"◀️ {_('common.back')}",
        callback_data="back_to_model"
    )
    
    builder.adjust(1)
    return builder.as_markup()

def get_duration_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """Выбор длительности"""
    _ = lambda key, **kwargs: global_i18n.get(key, language, **kwargs)
    
    builder = InlineKeyboardBuilder()
    
    for duration, dur_info in DURATIONS.items():
        builder.button(
            text=f"{dur_info['emoji']} {dur_info['name']}",
            callback_data=f"dur_{duration}"
        )
    
    builder.button(
        text=f"◀️ {_('common.back')}",
        callback_data="back_to_resolution"
    )
    
    builder.adjust(2)
    return builder.as_markup()
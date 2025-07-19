import logging
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.middlewares.i18n import I18n, LanguageManager
from services.database import db
from core.config import settings

logger = logging.getLogger(__name__)

# Глобальная функция локализации для настроек
i18n = I18n()

class SettingsStates(StatesGroup):
    changing_language = State()

router = Router(name="settings")

@router.callback_query(F.data == "settings")
async def show_settings(update: CallbackQuery | Message, state: FSMContext = None):
    """Показать настройки пользователя"""
    await state.clear() if state else None
    
    if isinstance(update, CallbackQuery):
        if not await db.get_user(update.from_user.id):
            await update.answer(i18n.get('errors.use_start', lang='ru'), show_alert=True)
            return
    else:
        if not await db.get_user(update.from_user.id):
            await update.answer(i18n.get('errors.please_use_start', lang='ru'))
            return
    
    user = await db.get_user(update.from_user.id)
    user_lang = user.language_code or 'ru'
    
    # Создаем функцию перевода для текущего пользователя
    def _(key, **kwargs):
        return i18n.get(key, lang=user_lang, **kwargs)
    
    # Получаем настройки пользователя
    settings_dict = user.settings or {}
    
    # Формируем текст
    text = f"⚙️ <b>{_('settings.title')}</b>\n\n"
    text += f"{_('settings.description')}\n\n"
    
    # Язык
    current_lang = user.language_code or 'ru'
    lang_names = {
        'ru': '🇷🇺 Русский',
        'en': '🇬🇧 English'
    }
    text += f"🌐 {_('settings.language')}: {lang_names.get(current_lang, current_lang)}\n"
    
    # Уведомления
    notifications_on = settings_dict.get('notifications', True)
    notifications_status = _('settings.enabled') if notifications_on else _('settings.disabled')
    text += f"🔔 {_('settings.notifications')}: {notifications_status}\n"
    
    # Подсказки
    tips_on = settings_dict.get('show_tips', True)
    tips_status = _('settings.enabled') if tips_on else _('settings.disabled')
    text += f"💡 {_('settings.tips')}: {tips_status}\n"
    
    # Качество по умолчанию
    default_quality = settings_dict.get('default_quality', '720p')
    text += f"🎬 {_('settings.quality_preference')}: {default_quality}\n"
    
    # Кнопки
    builder = InlineKeyboardBuilder()
    builder.button(text=f"🌐 {_('settings.change_language')}", callback_data="change_language")
    builder.button(text=f"🔔 {_('settings.toggle_notifications')}", callback_data="toggle_notifications")
    builder.button(text=f"🎬 {_('settings.change_quality')}", callback_data="change_quality")
    builder.button(text=f"💡 {_('settings.toggle_tips')}", callback_data="toggle_tips")
    builder.button(text=f"👤 {_('settings.account_info')}", callback_data="account_info")
    builder.button(text=f"🔒 {_('settings.privacy_settings')}", callback_data="privacy_settings")
    builder.button(text=f"◀️ {_('common.back')}", callback_data="back_to_menu")
    builder.adjust(2, 2, 1, 1, 1)
    
    if isinstance(update, CallbackQuery):
        await update.message.edit_text(text, reply_markup=builder.as_markup())
        await update.answer()
    else:
        await update.answer(text, reply_markup=builder.as_markup())

@router.callback_query(F.data == "change_language")
async def change_language(callback: CallbackQuery, state: FSMContext):
    """Изменить язык интерфейса"""
    user = await db.get_user(callback.from_user.id)
    user_lang = user.language_code or 'ru'
    
    def _(key, **kwargs):
        return i18n.get(key, lang=user_lang, **kwargs)
    
    keyboard = LanguageManager.get_language_keyboard()
    
    await callback.message.edit_text(
        f"🌐 <b>{_('settings.change_language')}</b>\n\n"
        f"{_('welcome.choose_language')}",
        reply_markup=keyboard
    )
    
    await state.set_state(SettingsStates.changing_language)
    await callback.answer()

@router.callback_query(SettingsStates.changing_language, F.data.startswith("lang_"))
async def save_language(callback: CallbackQuery, state: FSMContext):
    """Сохранить выбранный язык"""
    try:
        lang_code = callback.data.split("_")[1]
        
        # Проверяем валидность языка
        available_languages = i18n.get_available_languages()
        if lang_code not in available_languages:
            await callback.answer("Неподдерживаемый язык", show_alert=True)
            return
        
        # Обновляем язык в БД
        success = await LanguageManager.set_user_language(callback.from_user.id, lang_code)
        
        if success:
            # Создаем функцию перевода для нового языка
            new_lang_translate = lambda key, **kwargs: i18n.get(key, lang=lang_code, **kwargs)
            
            await callback.message.edit_text(
                f"✅ {new_lang_translate('settings.language_changed')}\n\n"
                f"{new_lang_translate('menu.choose_action')}",
                reply_markup=InlineKeyboardBuilder()
                .button(text=new_lang_translate('common.back'), callback_data="settings")
                .as_markup()
            )
        else:
            await callback.answer("Ошибка сохранения языка", show_alert=True)
        
        await state.clear()
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error changing language: {e}")
        await callback.answer("Ошибка", show_alert=True)

@router.callback_query(F.data == "toggle_notifications")
async def toggle_notifications(callback: CallbackQuery):
    """Переключить уведомления"""
    try:
        user = await db.get_user(callback.from_user.id)
        if not user:
            await callback.answer(i18n.get('settings.error_loading', lang='ru'), show_alert=True)
            return
        
        user_lang = user.language_code or 'ru'
        def _(key, **kwargs):
            return i18n.get(key, lang=user_lang, **kwargs)
        
        # Получаем текущие настройки
        settings_dict = user.settings or {}
        current_state = settings_dict.get('notifications', True)
        
        # Переключаем
        settings_dict['notifications'] = not current_state
        
        # Сохраняем
        await db.update_user_settings(user.id, settings_dict)
        
        # Показываем результат
        new_state = not current_state
        status = _('settings.enabled') if new_state else _('settings.disabled')
        message = _('settings.notifications_status', status=status)
        
        await callback.answer(message)
        
        # Обновляем экран настроек
        await show_settings(callback)
        
    except Exception as e:
        logger.error(f"Error toggling notifications: {e}")
        await callback.answer(i18n.get('settings.error_loading', lang='ru'), show_alert=True)

@router.callback_query(F.data == "change_quality")
async def change_quality(callback: CallbackQuery):
    """Изменить качество по умолчанию"""
    user = await db.get_user(callback.from_user.id)
    user_lang = user.language_code or 'ru'
    
    def _(key, **kwargs):
        return i18n.get(key, lang=user_lang, **kwargs)
    
    builder = InlineKeyboardBuilder()
    
    qualities = [
        ("480p", _('settings.quality_480p')),
        ("720p", _('settings.quality_720p')),
        ("1080p", _('settings.quality_1080p'))
    ]
    
    for quality, description in qualities:
        builder.button(text=description, callback_data=f"set_quality_{quality}")
    
    builder.button(text=f"◀️ {_('common.back')}", callback_data="settings")
    builder.adjust(1)
    
    await callback.message.edit_text(
        f"🎬 <b>{_('settings.change_quality')}</b>\n\n"
        f"{_('settings.quality_description')}",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@router.callback_query(F.data.startswith("set_quality_"))
async def save_quality(callback: CallbackQuery):
    """Сохранить качество по умолчанию"""
    try:
        quality = callback.data.split("_")[2]
        
        user = await db.get_user(callback.from_user.id)
        if not user:
            await callback.answer(i18n.get('settings.error_loading', lang='ru'), show_alert=True)
            return
        
        user_lang = user.language_code or 'ru'
        def _(key, **kwargs):
            return i18n.get(key, lang=user_lang, **kwargs)
        
        # Обновляем настройки
        settings_dict = user.settings or {}
        settings_dict['default_quality'] = quality
        
        await db.update_user_settings(user.id, settings_dict)
        
        await callback.answer(f"✅ {_('settings.quality_changed', quality=quality)}")
        
        # Возвращаемся к настройкам
        await show_settings(callback)
        
    except Exception as e:
        logger.error(f"Error changing quality: {e}")
        await callback.answer(i18n.get('settings.error_loading', lang='ru'), show_alert=True)

@router.callback_query(F.data == "toggle_tips")
async def toggle_tips(callback: CallbackQuery):
    """Переключить показ подсказок"""
    try:
        user = await db.get_user(callback.from_user.id)
        if not user:
            await callback.answer(i18n.get('settings.error_loading', lang='ru'), show_alert=True)
            return
        
        user_lang = user.language_code or 'ru'
        def _(key, **kwargs):
            return i18n.get(key, lang=user_lang, **kwargs)
        
        # Получаем текущие настройки
        settings_dict = user.settings or {}
        current_state = settings_dict.get('show_tips', True)
        
        # Переключаем
        settings_dict['show_tips'] = not current_state
        
        # Сохраняем
        await db.update_user_settings(user.id, settings_dict)
        
        # Показываем результат
        new_state = not current_state
        status = _('settings.enabled') if new_state else _('settings.disabled')
        message = _('settings.tips_status', status=status)
        
        await callback.answer(message)
        
        # Обновляем экран настроек
        await show_settings(callback)
        
    except Exception as e:
        logger.error(f"Error toggling tips: {e}")
        await callback.answer(i18n.get('settings.error_loading', lang='ru'), show_alert=True)

@router.callback_query(F.data == "account_info")
async def account_info(callback: CallbackQuery):
    """Показать информацию об аккаунте"""
    try:
        user = await db.get_user(callback.from_user.id)
        if not user:
            await callback.answer(i18n.get('settings.error_loading', lang='ru'), show_alert=True)
            return
        
        user_lang = user.language_code or 'ru'
        def _(key, **kwargs):
            return i18n.get(key, lang=user_lang, **kwargs)
        
        # Получаем статистику пользователя
        total_generations = await db.get_user_total_generations(user.id)
        total_spent = await db.get_user_total_spent(user.id)
        
        # Форматируем дату регистрации
        registration_date = user.created_at.strftime("%d.%m.%Y")
        
        # Получаем имя языка
        lang_names = {
            'ru': _('languages.ru'),
            'en': _('languages.en')
        }
        
        user_name = user.first_name or _('common.user')
        language_name = lang_names.get(user_lang, user_lang)
        
        text = _('settings.account_info_text',
                user_id=user.id,
                name=user_name,
                language=language_name,
                date=registration_date,
                balance=user.balance,
                spent=total_spent,
                generations=total_generations
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text=f"🗑 {_('settings.delete_account')}", callback_data="delete_account_confirm")
        builder.button(text=f"◀️ {_('common.back')}", callback_data="settings")
        builder.adjust(1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error in account info: {e}")
        await callback.answer(i18n.get('settings.error_loading', lang='ru'), show_alert=True)

@router.callback_query(F.data == "delete_account_confirm")
async def delete_account_confirm(callback: CallbackQuery):
    """Подтверждение удаления аккаунта"""
    user = await db.get_user(callback.from_user.id)
    user_lang = user.language_code or 'ru'
    
    def _(key, **kwargs):
        return i18n.get(key, lang=user_lang, **kwargs)
    
    builder = InlineKeyboardBuilder()
    builder.button(text=f"🗑 {_('settings.delete_confirm')}", callback_data="delete_account_final")
    builder.button(text=f"✅ {_('settings.keep_account')}", callback_data="account_info")
    builder.adjust(1)
    
    await callback.message.edit_text(
        _('settings.delete_warning'),
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@router.callback_query(F.data == "delete_account_final")
async def delete_account_final(callback: CallbackQuery):
    """Удаление аккаунта"""
    try:
        user = await db.get_user(callback.from_user.id)
        user_lang = user.language_code or 'ru'
        
        def _(key, **kwargs):
            return i18n.get(key, lang=user_lang, **kwargs)
        
        user_id = callback.from_user.id
        
        # Удаляем пользователя
        success = await db.delete_user(user_id)
        
        if success:
            await callback.message.edit_text(_('settings.delete_final'))
        else:
            await callback.answer(_('settings.delete_error'), show_alert=True)
            
    except Exception as e:
        logger.error(f"Error deleting account: {e}")
        await callback.answer(i18n.get('settings.delete_error', lang='ru'), show_alert=True)

@router.callback_query(F.data == "privacy_settings")
async def privacy_settings(callback: CallbackQuery):
    """Настройки приватности"""
    try:
        user = await db.get_user(callback.from_user.id)
        user_lang = user.language_code or 'ru'
        
        def _(key, **kwargs):
            return i18n.get(key, lang=user_lang, **kwargs)
        
        text = _('settings.privacy_description')
        
        builder = InlineKeyboardBuilder()
        builder.button(text=f"◀️ {_('common.back')}", callback_data="settings")
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error in privacy settings: {e}")
        await callback.answer(i18n.get('settings.privacy_error', lang='ru'), show_alert=True)

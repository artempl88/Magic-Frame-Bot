import re
import logging
from datetime import datetime, timezone
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.keyboard.inline import get_main_menu, get_language_keyboard
from bot.utils.messages import MessageTemplates
from services.database import db
from core.config import settings
from core.constants import LANGUAGES, NEW_USER_BONUS
from bot.middlewares.i18n import i18n

logger = logging.getLogger(__name__)

router = Router(name="start")

async def determine_user_language(telegram_user) -> str:
    """Определяет язык пользователя на основе языка Telegram"""
    if not hasattr(telegram_user, 'language_code') or not telegram_user.language_code:
        return 'ru'  # По умолчанию русский
    
    lang_code = telegram_user.language_code.lower()
    
    # Прямое соответствие
    if lang_code in LANGUAGES:
        return lang_code
    
    # Обработка языков с региональными кодами
    base_lang = lang_code.split('-')[0].split('_')[0]
    if base_lang in LANGUAGES:
        return base_lang
    
    # Специальная обработка для региональных кодов (только ru и en)
    lang_mapping = {
        'en': ['en-us', 'en_us', 'en-gb', 'en_gb'],
        'ru': ['ru-ru', 'ru_ru']
    }
    
    for supported_lang, variants in lang_mapping.items():
        if lang_code in variants:
            return supported_lang
    
    # По умолчанию русский
    return 'ru'

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """Обработчик команды /start"""
    
    # Очищаем состояние FSM
    await state.clear()
    
    user_id = message.from_user.id
    
    # Проверяем реферальную ссылку
    referrer_id = None
    if len(message.text.split()) > 1:
        ref_match = re.match(r'/start ref_(\d+)', message.text)
        if ref_match:
            potential_referrer = int(ref_match.group(1))
            if potential_referrer != user_id:  # Нельзя быть рефералом самого себя
                referrer_id = potential_referrer
    
    # Получаем или создаем пользователя
    user = await db.get_user(user_id)
    is_new_user = user is None
    
    if is_new_user:
        # Определяем язык для нового пользователя
        detected_lang = await determine_user_language(message.from_user)
        
        # Создаем нового пользователя с бонусом
        user = await db.create_user(
            user_id=user_id,  # telegram_id
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
            language_code=detected_lang
        )
        
        # Приветственное сообщение для нового пользователя
        _ = lambda key, **kwargs: i18n.get(key, detected_lang, **kwargs)
        
        # Используем готовое приветственное сообщение с правильной подстановкой кредитов
        welcome_text = _("welcome.title", credits=NEW_USER_BONUS)
        
        await message.answer(
            welcome_text,
            reply_markup=get_main_menu(detected_lang, user.balance)
        )
    else:
        # Для существующего пользователя используем сохраненный язык
        user_lang = user.language_code or 'ru'
        
        # Обновляем последнюю активность
        await db.update_user_activity(user_id)
        
        # Показываем главное меню
        await show_main_menu(message, user)

@router.callback_query(F.data.startswith("set_language_"))
async def handle_language_selection(callback: CallbackQuery):
    """Обработчик выбора языка"""
    lang_code = callback.data.split("_")[-1]
    
    if lang_code not in LANGUAGES:
        await callback.answer("Invalid language", show_alert=True)
        return
    
    # Обновляем язык пользователя в базе данных
    await db.update_user(callback.from_user.id, language_code=lang_code)
    
    # Получаем обновленного пользователя
    user = await db.get_user(callback.from_user.id)
    
    # Функция перевода с новым языком
    _ = lambda key, **kwargs: i18n.get(key, lang_code, **kwargs)
    
    # Показываем красивое главное меню с новым языком
    await show_main_menu(callback, user, new_message=False)
    
    await callback.answer(_("settings.language_changed"))

@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery, state: FSMContext):
    """Возврат в главное меню"""
    # Очищаем состояние
    await state.clear()
    
    user_id = callback.from_user.id
    user = await db.get_user(user_id)
    
    if not user:
        await callback.answer(_('errors.use_start'), show_alert=True)
        return
    
    # Удаляем старое сообщение и показываем новое меню
    try:
        await callback.message.delete()
    except:
        pass
    
    await show_main_menu(callback.message, user, new_message=True)
    await callback.answer()

async def show_main_menu(message_or_callback, user, new_message: bool = False):
    """Показать красивое главное меню"""
    # Получаем функцию перевода
    _ = lambda key, **kwargs: i18n.get(key, user.language_code or 'ru', **kwargs)
    
    # Получаем статистику пользователя
    stats = await db.get_user_statistics(user.telegram_id)
    
    # Определяем имя пользователя
    user_name = user.first_name or user.username or _("common.user", default="Пользователь")
    if len(user_name) > 15:
        user_name = user_name[:15] + "..."
    
    # Определяем приветствие (новый пользователь или возвращающийся)
    is_new_user = stats.get('total_generations', 0) == 0 and user.total_bought == 0
    welcome_key = "menu.beautiful.welcome" if is_new_user else "menu.beautiful.welcome_back"
    
    # Форматируем время последнего видео
    last_generation = stats.get('last_generation_date')
    if last_generation:
        # Конвертируем в UTC если нужно
        if last_generation.tzinfo is None:
            last_generation = last_generation.replace(tzinfo=timezone.utc)
        
        # Форматируем время
        now = datetime.now(timezone.utc)
        diff = now - last_generation
        
        if diff.days == 0:
            if diff.seconds < 3600:  # меньше часа
                minutes = diff.seconds // 60
                time_str = f"{minutes}{_('time.min_ago', default='м назад')}"
            else:  # меньше дня
                hours = diff.seconds // 3600
                time_str = f"{hours}{_('time.hour_ago', default='ч назад')}"
        elif diff.days == 1:
            time_str = _("time.yesterday", default="вчера")
        else:
            time_str = f"{diff.days}{_('time.days_ago', default='д назад')}"
    else:
        time_str = _("menu.beautiful.never")
    
    # Статус пользователя
    status = _("menu.beautiful.status_premium") if user.is_premium else _("menu.beautiful.status_active")
    
    # Создаем красивое сообщение
    text = f"""
{_("menu.beautiful.divider")}
{_(welcome_key, name=user_name)}
{_("menu.beautiful.divider")}

{_("menu.beautiful.dashboard")}

{_("menu.beautiful.wallet")}
💰 <b>{user.balance:,}</b> {_("menu.beautiful.credits_label")}
{status}

{_("menu.beautiful.video_stats")}
🎬 <b>{stats.get('total_generations', 0)}</b> {_("menu.beautiful.videos_label")}
📅 {_("menu.beautiful.last_video", time=time_str)}

{_("menu.beautiful.divider")}
"""
    
    # Добавляем специальное предложение для новичков
    if is_new_user:
        text += f"\n{_('menu.beautiful.special_offer')}\n\n"
    
    text += f"{_('menu.beautiful.quick_actions')}\n{_('menu.beautiful.lets_create')}"
    
    keyboard = get_main_menu(user.language_code or 'ru', user.balance)
    
    # Определяем тип объекта и отправляем соответствующим образом
    if isinstance(message_or_callback, CallbackQuery):
        # Это CallbackQuery - редактируем сообщение
        await message_or_callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    elif new_message:
        # Отправляем новое сообщение
        await message_or_callback.bot.send_message(
            message_or_callback.chat.id,
            text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    else:
        # Это Message - отвечаем на него
        await message_or_callback.answer(text, reply_markup=keyboard, parse_mode="HTML")

@router.message(Command("menu"))
async def menu_command(message: Message):
    """Команда /menu - показать главное меню"""
    user = await db.get_user(message.from_user.id)
    
    if user:
        await show_main_menu(message, user)
    else:
        await message.answer(_('errors.please_use_start', default="Пожалуйста, сначала выполните команду /start"))

@router.message(Command("help"))
async def help_command(message: Message):
    """Команда /help - помощь"""
    user = await db.get_user(message.from_user.id)
    if not user:
        await message.answer(_('errors.please_use_start', default="Пожалуйста, используйте /start"))
        return
    
    _ = lambda key, **kwargs: i18n.get(key, user.language_code or 'ru', **kwargs)
    
    help_text = f"""
❓ <b>{_('menu.help')}</b>

<b>{_('help.commands', default='Доступные команды')}:</b>
/start - {_('help.start', default='Начать работу с ботом')}
/menu - {_('menu.main')}
/generate - {_('menu.generate')}
/balance - {_('help.balance', default='Показать баланс')}
/buy - {_('menu.buy_credits')}
/history - {_('menu.history')}
/settings - {_('menu.settings')}
/help - {_('menu.help')}
/support - {_('menu.support')}

<b>{_('help.how_to_create', default='Как создать видео')}:</b>
1. {_('help.step1', default='Нажмите "Создать видео" в главном меню')}
2. {_('help.step2', default='Выберите режим: Текст→Видео или Изображение→Видео')}
3. {_('help.step3', default='Выберите модель (Lite или Pro)')}
4. {_('help.step4', default='Настройте параметры')}
5. {_('help.step5', default='Опишите желаемое видео')}
6. {_('help.step6', default='Подтвердите создание')}

<b>{_('help.need_help', default='Нужна помощь?')}</b>
{_('help.contact_support', default='Обратитесь в поддержку')}: /support
"""
    
    # Кнопка меню
    builder = InlineKeyboardBuilder()
    builder.button(text=_("menu.main_menu"), callback_data="back_to_menu")
    
    await message.answer(help_text, reply_markup=builder.as_markup())

@router.callback_query(F.data == "help_menu")
async def help_menu_callback(callback: CallbackQuery):
    """Обработчик кнопки помощи из главного меню"""
    user = await db.get_user(callback.from_user.id)
    if not user:
        await callback.answer(_('errors.please_use_start', default="Пожалуйста, используйте /start"), show_alert=True)
        return
    
    _ = lambda key, **kwargs: i18n.get(key, user.language_code or 'ru', **kwargs)
    
    help_text = f"""
❓ <b>{_('menu.help')}</b>

<b>{_('help.commands', default='Доступные команды')}:</b>
/start - {_('help.start', default='Начать работу с ботом')}
/menu - {_('menu.main')}
/generate - {_('menu.generate')}
/balance - {_('help.balance', default='Показать баланс')}
/buy - {_('menu.buy_credits')}
/history - {_('menu.history')}
/settings - {_('menu.settings')}
/help - {_('menu.help')}
/support - {_('menu.support')}

<b>{_('help.how_to_create', default='Как создать видео')}:</b>
1. {_('help.step1', default='Нажмите "Создать видео" в главном меню')}
2. {_('help.step2', default='Выберите режим: Текст→Видео или Изображение→Видео')}
3. {_('help.step3', default='Выберите модель (Lite или Pro)')}
4. {_('help.step4', default='Настройте параметры')}
5. {_('help.step5', default='Опишите желаемое видео')}
6. {_('help.step6', default='Подтвердите создание')}

<b>{_('help.need_help', default='Нужна помощь?')}</b>
{_('help.contact_support', default='Обратитесь в поддержку')}: /support
"""
    
    # Кнопка меню
    builder = InlineKeyboardBuilder()
    builder.button(text=_("menu.main_menu"), callback_data="back_to_menu")
    
    await callback.message.edit_text(help_text, reply_markup=builder.as_markup())
    await callback.answer()

@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    """Команда /cancel - отмена текущего действия"""
    current_state = await state.get_state()
    
    user = await db.get_user(message.from_user.id)
    _ = lambda key, **kwargs: i18n.get(key, user.language_code or 'ru' if user else 'ru', **kwargs)
    
    if current_state is None:
        await message.answer(_("cancel.nothing", default="Нечего отменять 🤷‍♂️"))
        return
    
    await state.clear()
    await message.answer(
        _("cancel.cancelled", default="❌ Действие отменено"),
        reply_markup=get_main_menu(user.language_code or 'ru' if user else 'ru', user.balance if user else 0)
    )

@router.callback_query(F.data == "cancel")
async def process_cancel(callback: CallbackQuery, state: FSMContext):
    """Обработка кнопки отмены"""
    await state.clear()
    
    user = await db.get_user(callback.from_user.id)
    if not user:
        await callback.answer(_('errors.use_start'), show_alert=True)
        return
    
    _ = lambda key, **kwargs: i18n.get(key, user.language_code or 'ru', **kwargs)
    
    try:
        await callback.message.delete()
    except:
        pass
    
    await show_main_menu(callback.message, user, new_message=True)
    await callback.answer(_("cancel.cancelled", default="❌ Отменено"))

@router.message(Command("lang"))
async def language_command(message: Message):
    """Команда /lang - быстрая смена языка"""
    user = await db.get_user(message.from_user.id)
    if not user:
        await message.answer("Please use /start first")
        return
    
    await message.answer(
        "🌐 <b>Выберите язык / Choose language:</b>",
        reply_markup=get_language_keyboard()
    )

# Обработчик для inline-запросов выбора языка
@router.callback_query(F.data == "choose_language")
async def show_language_selection(callback: CallbackQuery):
    """Показать выбор языка"""
    await callback.message.edit_text(
        "🌐 <b>Выберите язык / Choose language:</b>",
        reply_markup=get_language_keyboard()
    )
    await callback.answer()
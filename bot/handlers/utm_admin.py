import logging
import io
import csv
from datetime import datetime, timedelta
from typing import List, Dict

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from services.database import db
from services.utm_analytics import utm_service
from bot.middlewares.auth import admin_required
from bot.middlewares.i18n import i18n

logger = logging.getLogger(__name__)

router = Router(name="utm_admin")

class UTMStates(StatesGroup):
    creating_campaign = State()
    entering_name = State()
    entering_source = State()
    entering_medium = State()
    entering_campaign = State()
    entering_content = State()
    entering_description = State()
    viewing_analytics = State()

# =================== ГЛАВНОЕ МЕНЮ UTM ===================

@router.callback_query(F.data == "utm_analytics")
@admin_required
async def show_utm_menu(callback: CallbackQuery, state: FSMContext):
    """Главное меню UTM аналитики"""
    await state.clear()
    
    user = await db.get_user(callback.from_user.id)
    _ = lambda key, **kwargs: i18n.get(key, user.language_code or 'ru', **kwargs)
    
    text = f"""
🧩 <b>UTM Аналитика</b>

📊 Отслеживание маркетинговых кампаний:
• Генерация UTM-ссылок
• Трекинг переходов и конверсий
• Детальная аналитика по источникам

💡 <i>Создавайте отслеживаемые ссылки для измерения эффективности рекламных кампаний.</i>
"""
    
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Создать кампанию", callback_data="utm_create_campaign")
    builder.button(text="📋 Список кампаний", callback_data="utm_list_campaigns")
    builder.button(text="📊 Общая аналитика", callback_data="utm_general_analytics")
    builder.button(text="🏆 Топ источники", callback_data="utm_top_sources")
    builder.button(text="◀️ Назад", callback_data="admin_menu")
    builder.adjust(2, 2, 1)
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()

# =================== СОЗДАНИЕ КАМПАНИИ ===================

@router.callback_query(F.data == "utm_create_campaign")
@admin_required
async def start_create_campaign(callback: CallbackQuery, state: FSMContext):
    """Начало создания UTM кампании"""
    
    user = await db.get_user(callback.from_user.id)
    _ = lambda key, **kwargs: i18n.get(key, user.language_code or 'ru', **kwargs)
    
    text = f"""
➕ <b>Создание UTM кампании</b>

📝 <b>Шаг 1 из 6: Название кампании</b>

Введите понятное название для вашей кампании.
Это название будет отображаться в админке.

<i>Пример: "Летняя акция ВКонтакте"</i>
"""
    
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data="utm_analytics")
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await state.set_state(UTMStates.entering_name)
    await callback.answer()

@router.message(UTMStates.entering_name)
async def enter_campaign_name(message: Message, state: FSMContext):
    """Ввод названия кампании"""
    
    if len(message.text) > 200:
        await message.answer("❌ Название слишком длинное (максимум 200 символов)")
        return
    
    await state.update_data(name=message.text)
    
    text = f"""
➕ <b>Создание UTM кампании</b>

📝 <b>Шаг 2 из 6: UTM Source</b>

Укажите источник трафика (utm_source).

<b>Примеры:</b>
• <code>vk</code> - ВКонтакте
• <code>telegram</code> - Telegram
• <code>youtube</code> - YouTube
• <code>instagram</code> - Instagram
• <code>google</code> - Google Ads
"""
    
    builder = InlineKeyboardBuilder()
    builder.button(text="vk", callback_data="utm_source_vk")
    builder.button(text="telegram", callback_data="utm_source_telegram")
    builder.button(text="youtube", callback_data="utm_source_youtube")
    builder.button(text="instagram", callback_data="utm_source_instagram")
    builder.button(text="✏️ Свой вариант", callback_data="utm_source_custom")
    builder.button(text="❌ Отмена", callback_data="utm_analytics")
    builder.adjust(2, 2, 1, 1)
    
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await state.set_state(UTMStates.entering_source)

@router.callback_query(UTMStates.entering_source, F.data.startswith("utm_source_"))
async def select_utm_source(callback: CallbackQuery, state: FSMContext):
    """Выбор UTM source"""
    
    source_type = callback.data.split("_")[-1]
    
    if source_type == "custom":
        text = "✏️ Введите свой источник трафика (utm_source):"
        await callback.message.edit_text(text, parse_mode="HTML")
        await callback.answer()
        return
    
    # Предустановленный источник
    await state.update_data(utm_source=source_type)
    
    text = f"""
➕ <b>Создание UTM кампании</b>

📝 <b>Шаг 3 из 6: UTM Medium</b>

Источник: <code>{source_type}</code>

Укажите тип трафика (utm_medium).

<b>Примеры:</b>
• <code>cpc</code> - Контекстная реклама
• <code>banner</code> - Баннерная реклама
• <code>post</code> - Пост в соцсети
• <code>story</code> - Сториз
• <code>email</code> - Email рассылка
"""
    
    builder = InlineKeyboardBuilder()
    builder.button(text="cpc", callback_data="utm_medium_cpc")
    builder.button(text="banner", callback_data="utm_medium_banner")
    builder.button(text="post", callback_data="utm_medium_post")
    builder.button(text="story", callback_data="utm_medium_story")
    builder.button(text="✏️ Свой вариант", callback_data="utm_medium_custom")
    builder.button(text="❌ Отмена", callback_data="utm_analytics")
    builder.adjust(2, 2, 1, 1)
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await state.set_state(UTMStates.entering_medium)
    await callback.answer()

@router.message(UTMStates.entering_source)
async def enter_custom_source(message: Message, state: FSMContext):
    """Ввод кастомного источника"""
    
    if len(message.text) > 100:
        await message.answer("❌ Источник слишком длинный (максимум 100 символов)")
        return
    
    source = message.text.lower().replace(' ', '_')
    await state.update_data(utm_source=source)
    
    text = f"""
➕ <b>Создание UTM кампании</b>

📝 <b>Шаг 3 из 6: UTM Medium</b>

Источник: <code>{source}</code>

Укажите тип трафика (utm_medium).
"""
    
    builder = InlineKeyboardBuilder()
    builder.button(text="cpc", callback_data="utm_medium_cpc")
    builder.button(text="banner", callback_data="utm_medium_banner") 
    builder.button(text="post", callback_data="utm_medium_post")
    builder.button(text="story", callback_data="utm_medium_story")
    builder.button(text="✏️ Свой вариант", callback_data="utm_medium_custom")
    builder.button(text="❌ Отмена", callback_data="utm_analytics")
    builder.adjust(2, 2, 1, 1)
    
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await state.set_state(UTMStates.entering_medium)

@router.callback_query(UTMStates.entering_medium, F.data.startswith("utm_medium_"))
async def select_utm_medium(callback: CallbackQuery, state: FSMContext):
    """Выбор UTM medium"""
    
    medium_type = callback.data.split("_")[-1]
    
    if medium_type == "custom":
        text = "✏️ Введите свой тип трафика (utm_medium):"
        await callback.message.edit_text(text, parse_mode="HTML")
        await callback.answer()
        return
    
    await state.update_data(utm_medium=medium_type)
    data = await state.get_data()
    
    text = f"""
➕ <b>Создание UTM кампании</b>

📝 <b>Шаг 4 из 6: UTM Campaign</b>

Источник: <code>{data['utm_source']}</code>
Тип: <code>{medium_type}</code>

Введите название кампании (utm_campaign).

<b>Примеры:</b>
• <code>summer_sale_2024</code>
• <code>new_year_promo</code>
• <code>black_friday</code>

<i>Используйте английские буквы, цифры и подчеркивания.</i>
"""
    
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data="utm_analytics")
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await state.set_state(UTMStates.entering_campaign)
    await callback.answer()

@router.message(UTMStates.entering_medium)
async def enter_custom_medium(message: Message, state: FSMContext):
    """Ввод кастомного medium"""
    
    if len(message.text) > 100:
        await message.answer("❌ Тип трафика слишком длинный (максимум 100 символов)")
        return
    
    medium = message.text.lower().replace(' ', '_')
    await state.update_data(utm_medium=medium)
    data = await state.get_data()
    
    text = f"""
➕ <b>Создание UTM кампании</b>

📝 <b>Шаг 4 из 6: UTM Campaign</b>

Источник: <code>{data['utm_source']}</code>
Тип: <code>{medium}</code>

Введите название кампании (utm_campaign).
"""
    
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data="utm_analytics")
    
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await state.set_state(UTMStates.entering_campaign)

@router.message(UTMStates.entering_campaign)
async def enter_utm_campaign(message: Message, state: FSMContext):
    """Ввод UTM campaign"""
    
    if len(message.text) > 200:
        await message.answer("❌ Название кампании слишком длинное (максимум 200 символов)")
        return
    
    campaign = message.text.lower().replace(' ', '_')
    await state.update_data(utm_campaign=campaign)
    data = await state.get_data()
    
    text = f"""
➕ <b>Создание UTM кампании</b>

📝 <b>Шаг 5 из 6: UTM Content (необязательно)</b>

Источник: <code>{data['utm_source']}</code>
Тип: <code>{data['utm_medium']}</code>
Кампания: <code>{campaign}</code>

Введите дополнительный идентификатор (utm_content).

<b>Примеры:</b>
• <code>banner_top</code> - Верхний баннер
• <code>button_cta</code> - CTA кнопка
• <code>link_bio</code> - Ссылка в био

Или нажмите "Пропустить", если не нужно.
"""
    
    builder = InlineKeyboardBuilder()
    builder.button(text="⏭️ Пропустить", callback_data="utm_skip_content")
    builder.button(text="❌ Отмена", callback_data="utm_analytics")
    builder.adjust(1)
    
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await state.set_state(UTMStates.entering_content)

@router.callback_query(UTMStates.entering_content, F.data == "utm_skip_content")
async def skip_utm_content(callback: CallbackQuery, state: FSMContext):
    """Пропуск UTM content"""
    await ask_for_description(callback, state)

@router.message(UTMStates.entering_content)
async def enter_utm_content(message: Message, state: FSMContext):
    """Ввод UTM content"""
    
    if len(message.text) > 200:
        await message.answer("❌ Контент слишком длинный (максимум 200 символов)")
        return
    
    content = message.text.lower().replace(' ', '_')
    await state.update_data(utm_content=content)
    
    # Переходим к описанию
    await ask_for_description_message(message, state)

async def ask_for_description(callback: CallbackQuery, state: FSMContext):
    """Запрос описания кампании"""
    data = await state.get_data()
    
    text = f"""
➕ <b>Создание UTM кампании</b>

📝 <b>Шаг 6 из 6: Описание (необязательно)</b>

<b>Параметры кампании:</b>
• Источник: <code>{data['utm_source']}</code>
• Тип: <code>{data['utm_medium']}</code>
• Кампания: <code>{data['utm_campaign']}</code>
• Контент: <code>{data.get('utm_content', 'не указан')}</code>

Введите описание кампании или нажмите "Создать".
"""
    
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Создать кампанию", callback_data="utm_create_final")
    builder.button(text="❌ Отмена", callback_data="utm_analytics")
    builder.adjust(1)
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await state.set_state(UTMStates.entering_description)
    await callback.answer()

async def ask_for_description_message(message: Message, state: FSMContext):
    """Запрос описания кампании (из сообщения)"""
    data = await state.get_data()
    
    text = f"""
➕ <b>Создание UTM кампании</b>

📝 <b>Шаг 6 из 6: Описание (необязательно)</b>

<b>Параметры кампании:</b>
• Источник: <code>{data['utm_source']}</code>
• Тип: <code>{data['utm_medium']}</code>
• Кампания: <code>{data['utm_campaign']}</code>
• Контент: <code>{data.get('utm_content', 'не указан')}</code>

Введите описание кампании или нажмите "Создать".
"""
    
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Создать кампанию", callback_data="utm_create_final")
    builder.button(text="❌ Отмена", callback_data="utm_analytics")
    builder.adjust(1)
    
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await state.set_state(UTMStates.entering_description)

@router.callback_query(UTMStates.entering_description, F.data == "utm_create_final")
async def create_campaign_final(callback: CallbackQuery, state: FSMContext):
    """Финальное создание кампании"""
    await create_campaign_with_data(callback, state, None)

@router.message(UTMStates.entering_description)
async def enter_description_and_create(message: Message, state: FSMContext):
    """Ввод описания и создание кампании"""
    
    if len(message.text) > 500:
        await message.answer("❌ Описание слишком длинное (максимум 500 символов)")
        return
    
    await create_campaign_with_data(None, state, message.text, message)

async def create_campaign_with_data(callback: CallbackQuery, state: FSMContext, description: str, message: Message = None):
    """Создание кампании с данными"""
    
    data = await state.get_data()
    admin_id = (callback.from_user.id if callback else message.from_user.id)
    
    try:
        # Создаем кампанию
        campaign = await utm_service.create_utm_campaign(
            admin_id=admin_id,
            name=data['name'],
            utm_source=data['utm_source'],
            utm_medium=data['utm_medium'],
            utm_campaign=data['utm_campaign'],
            utm_content=data.get('utm_content'),
            description=description
        )
        
        text = f"""
✅ <b>Кампания создана!</b>

📋 <b>Детали кампании:</b>
• ID: <code>{campaign.id}</code>
• Название: <b>{campaign.name}</b>
• Источник: <code>{campaign.utm_source}</code>
• Тип: <code>{campaign.utm_medium}</code>
• Кампания: <code>{campaign.utm_campaign}</code>
• Контент: <code>{campaign.utm_content or 'не указан'}</code>

🔗 <b>UTM ссылка:</b>
<code>{campaign.utm_link}</code>

💡 <b>Короткий код:</b> <code>{campaign.short_code}</code>

<i>Используйте эту ссылку в ваших рекламных материалах для отслеживания переходов.</i>
"""
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📊 Аналитика", callback_data=f"utm_view_campaign_{campaign.id}")
        builder.button(text="📋 Список кампаний", callback_data="utm_list_campaigns")
        builder.button(text="◀️ Меню UTM", callback_data="utm_analytics")
        builder.adjust(1)
        
        if callback:
            await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
            await callback.answer("✅ Кампания успешно создана!")
        else:
            await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        
        await state.clear()
        
    except Exception as e:
        logger.error(f"Error creating UTM campaign: {e}")
        error_text = "❌ Ошибка при создании кампании. Попробуйте еще раз."
        
        if callback:
            await callback.answer(error_text, show_alert=True)
        else:
            await message.answer(error_text)

# =================== СПИСОК КАМПАНИЙ ===================

@router.callback_query(F.data == "utm_list_campaigns")
@admin_required
async def list_campaigns(callback: CallbackQuery, state: FSMContext):
    """Список UTM кампаний"""
    await state.clear()
    
    try:
        campaigns = await utm_service.get_campaigns_list(limit=10)
        
        if not campaigns:
            text = """
📋 <b>Список кампаний</b>

🔍 Кампании не найдены.

Создайте первую UTM кампанию для отслеживания трафика.
"""
            builder = InlineKeyboardBuilder()
            builder.button(text="➕ Создать кампанию", callback_data="utm_create_campaign")
            builder.button(text="◀️ Назад", callback_data="utm_analytics")
            builder.adjust(1)
            
            await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
            await callback.answer()
            return
        
        text = "📋 <b>UTM Кампании</b>\n\n"
        
        builder = InlineKeyboardBuilder()
        
        for campaign in campaigns:
            status_emoji = "🟢" if campaign.is_active else "🔴"
            short_name = campaign.name[:30] + "..." if len(campaign.name) > 30 else campaign.name
            
            text += f"{status_emoji} <b>{short_name}</b>\n"
            text += f"   📊 {campaign.total_clicks} кликов, {campaign.total_registrations} регистраций\n"
            text += f"   🏷️ {campaign.utm_source}/{campaign.utm_medium}\n\n"
            
            builder.button(
                text=f"{status_emoji} {short_name}",
                callback_data=f"utm_view_campaign_{campaign.id}"
            )
        
        builder.button(text="➕ Создать кампанию", callback_data="utm_create_campaign")
        builder.button(text="◀️ Назад", callback_data="utm_analytics")
        builder.adjust(1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error listing UTM campaigns: {e}")
        await callback.answer("❌ Ошибка при загрузке кампаний", show_alert=True)

# =================== ПРОСМОТР КАМПАНИИ ===================

@router.callback_query(F.data.startswith("utm_view_campaign_"))
@admin_required
async def view_campaign(callback: CallbackQuery, state: FSMContext):
    """Просмотр детальной информации о кампании"""
    await state.clear()
    
    campaign_id = int(callback.data.split("_")[-1])
    
    try:
        analytics = await utm_service.get_campaign_analytics(campaign_id)
        
        if not analytics:
            await callback.answer("❌ Кампания не найдена", show_alert=True)
            return
        
        campaign = analytics.get('campaign', {})
        clicks = analytics.get('clicks', {})
        events = analytics.get('events', {})
        conversions = analytics.get('conversions', {})
        
        status_emoji = "🟢" if campaign.get('is_active', False) else "🔴"
        
        text = f"""
📊 <b>Аналитика кампании</b>

{status_emoji} <b>{campaign.get('name', 'Без названия')}</b>

🏷️ <b>UTM параметры:</b>
• Источник: <code>{campaign.get('utm_source', 'не указан')}</code>
• Тип: <code>{campaign.get('utm_medium', 'не указан')}</code>
• Кампания: <code>{campaign.get('utm_campaign', 'не указан')}</code>
• Контент: <code>{campaign.get('utm_content') or 'не указан'}</code>

📈 <b>Статистика:</b>
• 👥 Всего кликов: <b>{clicks.get('total_clicks', 0)}</b>
• 🆔 Уникальных пользователей: <b>{clicks.get('unique_users', 0)}</b>
• 🆕 Первые посещения: <b>{clicks.get('first_visits', 0)}</b>

🎯 <b>События:</b>
"""
        
        for event_type, event_data in events.items():
            event_emoji = {
                'registration': '📝',
                'purchase': '💰',
                'generation': '🎬'
            }.get(event_type, '📊')
            
            text += f"• {event_emoji} {event_type}: <b>{event_data.get('count', 0)}</b>"
            if event_data.get('total_revenue', 0) > 0:
                text += f" (💰 {event_data['total_revenue']:.2f}₽)"
            text += "\n"
        
        text += f"""
📊 <b>Конверсии:</b>
• Регистрация: <b>{conversions.get('registration_rate', 0)}%</b>
• Покупка: <b>{conversions.get('purchase_rate', 0)}%</b>

📅 <b>Создана:</b> {datetime.fromisoformat(campaign.get('created_at', '2025-01-01T00:00:00')).strftime('%d.%m.%Y %H:%M') if campaign.get('created_at') else 'Неизвестно'}
"""
        
        builder = InlineKeyboardBuilder()
        
        # Переключение активности
        toggle_text = "🔴 Деактивировать" if campaign.get('is_active', False) else "🟢 Активировать"
        builder.button(text=toggle_text, callback_data=f"utm_toggle_{campaign_id}")
        
        builder.button(text="🗑️ Удалить кампанию", callback_data=f"utm_delete_{campaign_id}")
        builder.button(text="📋 Список кампаний", callback_data="utm_list_campaigns")
        builder.button(text="◀️ Меню UTM", callback_data="utm_analytics")
        builder.adjust(1, 1, 1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error viewing UTM campaign {campaign_id}: {e}")
        await callback.answer("❌ Ошибка при загрузке аналитики", show_alert=True)

@router.callback_query(F.data.startswith("utm_toggle_"))
@admin_required
async def toggle_campaign(callback: CallbackQuery):
    """Переключение активности кампании"""
    
    campaign_id = int(callback.data.split("_")[-1])
    admin_id = callback.from_user.id
    
    try:
        success = await utm_service.toggle_campaign_status(campaign_id, admin_id)
        
        if success:
            await callback.answer("✅ Статус кампании изменен")
            # Обновляем отображение
            await view_campaign(callback, FSMContext())
        else:
            await callback.answer("❌ Кампания не найдена", show_alert=True)
            
    except Exception as e:
        logger.error(f"Error toggling UTM campaign {campaign_id}: {e}")
        await callback.answer("❌ Ошибка при изменении статуса", show_alert=True)

# =================== ЭКСПОРТ ДАННЫХ ===================

@router.callback_query(F.data.startswith("utm_export_"))
@admin_required 
async def export_campaign_data(callback: CallbackQuery):
    """Экспорт детальных данных кампании в CSV"""
    
    # Проверяем, что это не summary экспорт
    if "utm_export_summary_" in callback.data:
        return
    
    campaign_id = int(callback.data.split("_")[-1])
    
    try:
        # Получаем данные за последние 30 дней
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=30)
        
        data = await utm_service.export_campaign_data(campaign_id, start_date, end_date)
        
        if not data:
            await callback.answer("📝 Нет данных для экспорта", show_alert=True)
            return
        
        # Создаем CSV с расширенными полями
        output = io.StringIO()
        
        # Определяем поля для детального экспорта
        fieldnames = [
            'f"Кампания_{campaign_id}"', 'utm_source', 'utm_medium', 'utm_campaign', 'utm_content',
            'click_id', 'clicked_at', 'click_date', 'click_hour', 'click_day_of_week',
            'telegram_id', 'username', 'first_name', 'last_name', 'language_code',
            'is_first_visit', 'is_registered_user', 'is_premium', 'user_credits_balance',
            'user_registration_date', 'user_agent', 'ip_address', 'referrer',
            'event_type', 'event_at', 'revenue', 'credits_spent', 'credits_purchased',
            'time_from_click_seconds', 'time_from_click_minutes', 'time_from_click_hours',
            'has_converted', 'conversion_type', 'export_timestamp'
        ]
        
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)
        
        # Создаем файл для отправки
        csv_content = output.getvalue().encode('utf-8')
        filename = f"utm_detailed_{campaign_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        file = BufferedInputFile(csv_content, filename=filename)
        
        # Получаем название кампании из данных
        campaign_name = data[0]['f"Кампания_{campaign_id}"'] if data else f"Campaign {campaign_id}"
        total_clicks = len(set(row['click_id'] for row in data))
        total_events = len([row for row in data if row['event_type']])
        total_revenue = sum(float(row['revenue']) for row in data)
        
        await callback.message.answer_document(
            file,
            caption=f"""📊 <b>Детальные данные UTM кампании</b>

📋 <b>Кампания:</b> {f"Кампания_{campaign_id}"}
📅 <b>Период:</b> {start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}
📝 <b>Записей в файле:</b> {len(data)}
👥 <b>Уникальных кликов:</b> {total_clicks}
🎯 <b>События:</b> {total_events}
💰 <b>Общая выручка:</b> {total_revenue:.2f}₽

<i>Файл содержит подробные данные по каждому клику и событию, включая информацию о пользователях, времени конверсий и источниках трафика.</i>""",
            parse_mode="HTML"
        )
        
        await callback.answer("✅ Детальные данные экспортированы")
        
    except Exception as e:
        logger.error(f"Error exporting UTM campaign {campaign_id}: {e}")
        await callback.answer("❌ Ошибка при экспорте данных", show_alert=True)

@router.callback_query(F.data == "utm_general_analytics")
@admin_required
async def show_general_analytics(callback: CallbackQuery):
    """Общая аналитика по всем кампаниям"""
    
    try:
        # Получаем данные за последние 30 дней
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=30)
        
        top_sources = await utm_service.get_top_sources_analytics(start_date, end_date, limit=5)
        
        text = f"""
📊 <b>Общая UTM аналитика</b>

📅 <b>Период:</b> {start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}

🏆 <b>Топ источники трафика:</b>

"""
        
        if top_sources:
            for i, source in enumerate(top_sources, 1):
                emoji = ['🥇', '🥈', '🥉', '4️⃣', '5️⃣'][i-1]
                text += f"{emoji} <b>{source['source']}/{source['medium']}</b>\n"
                text += f"   👥 {source['clicks']} кликов ({source['unique_users']} уникальных)\n"
                text += f"   📊 {source['events']} событий (конверсия: {source['conversion_rate']}%)\n"
                if source['revenue'] > 0:
                    text += f"   💰 Выручка: {source['revenue']:.2f}₽\n"
                text += "\n"
        else:
            text += "🔍 Нет данных за выбранный период."
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🏆 Топ источники", callback_data="utm_top_sources")
        builder.button(text="◀️ Меню UTM", callback_data="utm_analytics")
        builder.adjust(1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error showing general UTM analytics: {e}")
        await callback.answer("❌ Ошибка при загрузке аналитики", show_alert=True)

@router.callback_query(F.data == "utm_top_sources")
@admin_required
async def show_top_sources(callback: CallbackQuery):
    """Детальная аналитика по источникам"""
    
    try:
        # Получаем данные за последние 7, 30 и 90 дней
        periods = [
            (7, "7 дней"),
            (30, "30 дней"),
            (90, "90 дней")
        ]
        
        text = "🏆 <b>Топ источники трафика</b>\n\n"
        
        for days, period_name in periods:
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days)
            
            top_sources = await utm_service.get_top_sources_analytics(start_date, end_date, limit=3)
            
            text += f"📅 <b>{period_name}:</b>\n"
            
            if top_sources:
                for i, source in enumerate(top_sources, 1):
                    emoji = ['🥇', '🥈', '🥉'][i-1]
                    text += f"{emoji} {source['source']}/{source['medium']} - {source['clicks']} кликов ({source['conversion_rate']}%)\n"
            else:
                text += "🔍 Нет данных\n"
            
            text += "\n"
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📊 Общая аналитика", callback_data="utm_general_analytics")
        builder.button(text="◀️ Меню UTM", callback_data="utm_analytics")
        builder.adjust(1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error showing top sources: {e}")
        await callback.answer("❌ Ошибка при загрузке данных", show_alert=True) 
@router.callback_query(F.data.startswith("utm_delete_"))
@admin_required
async def delete_campaign(callback: CallbackQuery):
    """Обработчик удаления UTM кампании"""
    campaign_id = int(callback.data.split("_")[-1])
    admin_id = callback.from_user.id
    
    try:
        success = await utm_service.delete_utm_campaign(campaign_id, admin_id)
        
        if success:
            await callback.answer("✅ Кампания успешно удалена", show_alert=True)
            await list_campaigns(callback, FSMContext())
        else:
            await callback.answer("❌ Ошибка при удалении кампании", show_alert=True)
        
    except Exception as e:
        logger.error(f"Error deleting UTM campaign {campaign_id}: {e}")
        await callback.answer("❌ Ошибка при удалении кампании", show_alert=True)


@router.callback_query(F.data.startswith("utm_detailed_"))
@admin_required
async def show_detailed_analytics(callback: CallbackQuery):
    """Показать подробную аналитику с временными графиками"""
    campaign_id = int(callback.data.split("_")[-1])
    
    try:
        analytics = await utm_service.get_campaign_analytics(campaign_id)
        
        if not analytics:
            await callback.answer("❌ Кампания не найдена", show_alert=True)
            return
        
        campaign = analytics['campaign']
        timeline = analytics['timeline']
        events = analytics['events']
        
        text = f"""
📈 <b>Подробная аналитика: {campaign['name']}</b>

📅 <b>Активность по дням (последние записи):</b>
"""
        
        # Показываем последние 7 дней активности
        daily_stats = timeline['daily_stats'][-7:] if timeline['daily_stats'] else []
        
        if daily_stats:
            for day_data in daily_stats:
                date_obj = datetime.fromisoformat(day_data['date'])
                date_str = date_obj.strftime('%d.%m')
                weekday = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'][date_obj.weekday()]
                text += f"• {date_str} ({weekday}): {day_data['clicks']} кликов, {day_data['unique_users']} польз.\\n"
        else:
            text += "📊 Нет данных за последние дни\\n"
        
        text += f"\\n🕐 <b>Пиковые часы активности:</b>\\n"
        if timeline['top_hours']:
            for i, hour_data in enumerate(timeline['top_hours'], 1):
                text += f"{i}. {hour_data['hour']} - {hour_data['clicks']} кликов\\n"
        else:
            text += "📊 Нет данных о часах активности\\n"
        
        # Детализация по событиям
        text += f"\\n⏱️ <b>Время до конверсии:</b>\\n"
        for event_type, event_data in events.items():
            if event_data.get('avg_time_to_convert_minutes', 0) > 0:
                event_name = {'registration': 'Регистрация', 'purchase': 'Покупка', 'generation': 'Генерация'}.get(event_type, event_type)
                text += f"• {event_name}:\\n"
                text += f"  - Среднее: {event_data['avg_time_to_convert_minutes']:.1f} мин\\n"
                text += f"  - Минимум: {event_data['min_time_to_convert_seconds']//60:.0f} мин\\n"
                text += f"  - Максимум: {event_data['max_time_to_convert_seconds']//60:.0f} мин\\n"
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📊 Основная аналитика", callback_data=f"utm_view_campaign_{campaign_id}")
        builder.button(text="📥 Экспорт всех данных", callback_data=f"utm_export_{campaign_id}")
        builder.button(text="◀️ Назад", callback_data=f"utm_view_campaign_{campaign_id}")
        builder.adjust(2, 1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error showing detailed analytics for campaign {campaign_id}: {e}")
        await callback.answer("❌ Ошибка при загрузке детальной аналитики", show_alert=True)

@router.callback_query(F.data.startswith("utm_export_summary_"))
@admin_required
async def export_campaign_summary(callback: CallbackQuery):
    """Экспорт сводки по кампании в CSV"""
    
    campaign_id = int(callback.data.split("_")[-1])
    
    try:
        # Получаем данные за последние 30 дней
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=30)
        
        data = await utm_service.export_campaign_data(campaign_id, start_date, end_date)
        
        if not data:
            await callback.answer("📝 Нет данных для экспорта", show_alert=True)
            return
        
        # Создаем CSV
        output = io.StringIO()
        
        # Определяем поля для сводки
        fieldnames = [
            'f"Кампания_{campaign_id}"', 'utm_source', 'utm_medium', 'utm_campaign', 'utm_content',
            'total_clicks', 'unique_users', 'first_visits', 'registered_users_clicks', 'new_users_clicks',
            'registrations', 'purchases', 'generations', 'total_revenue',
            'revenue_per_click', 'revenue_per_user',
            'click_to_registration_rate', 'click_to_purchase_rate', 'registration_to_purchase_rate',
            'avg_time_to_convert_minutes', 'is_active', 'created_at', 'export_date'
        ]
        
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)
        
        # Создаем файл для отправки
        csv_content = output.getvalue().encode('utf-8')
        filename = f"utm_summary_{campaign_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        file = BufferedInputFile(csv_content, filename=filename)
        
        await callback.message.answer_document(
            file,
            caption=f"""📊 <b>Сводка по UTM кампании</b>

📋 <b>Кампания:</b> {data[0]['f"Кампания_{campaign_id}"']}
📅 <b>Период:</b> {start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}
📈 <b>Кликов:</b> {data[0]['total_clicks']}
👥 <b>Уникальных:</b> {data[0]['unique_users']}
💰 <b>Выручка:</b> {data[0]['total_revenue']:.2f}₽

<i>Файл содержит сводную аналитику кампании с основными метриками</i>""",
            parse_mode="HTML"
        )
        
        await callback.answer("✅ Сводка экспортирована")
        
    except Exception as e:
        logger.error(f"Error exporting UTM campaign summary {campaign_id}: {e}")
        await callback.answer("❌ Ошибка при экспорте сводки", show_alert=True)


@router.callback_query(F.data.startswith("utm_credits_"))
@admin_required
async def show_credit_details(callback: CallbackQuery):
    """Показать детальную аналитику по кредитам и покупкам"""
    campaign_id = int(callback.data.split("_")[-1])
    
    try:
        credit_analytics = await utm_service.get_campaign_credit_analytics(campaign_id)
        
        text = f"""
💳 <b>Детальная аналитика кредитов</b>
📋 <b>Кампания #{campaign_id}</b>

📊 <b>Сводка:</b>
• Всего покупок: <b>{credit_analytics['summary']['total_purchases']}</b>
• Куплено кредитов: <b>{credit_analytics['summary']['total_credits_bought']}</b>
• Потрачено кредитов: <b>{credit_analytics['summary']['total_credits_spent']}</b>
• Средняя покупка: <b>{credit_analytics['summary']['avg_purchase_amount']:.0f}</b> кредитов

💰 <b>Выручка по методам оплаты:</b>
• Telegram Stars: <b>{credit_analytics['total_revenue']['stars']}</b>
• ЮКасса (рубли): <b>{credit_analytics['total_revenue']['rub']:.2f}₽</b>

"""
        
        # Топ покупаемые пакеты
        if credit_analytics['purchase_packages']:
            text += "🏆 <b>Популярные пакеты кредитов:</b>\\n"
            for i, package in enumerate(credit_analytics['purchase_packages'][:5], 1):
                package_name = package['package_id'] or f"{package['amount']} кредитов"
                text += f"{i}. <b>{package_name}</b>\\n"
                text += f"   📦 {package['transaction_count']} покупок"
                text += f" • {package['total_credits']} кредитов"
                if package['total_stars_paid'] > 0:
                    text += f" • ⭐{package['total_stars_paid']}"
                if package['total_rub_paid'] > 0:
                    text += f" • {package['total_rub_paid']:.2f}₽"
                text += "\\n\\n"
        
        # Бонусные кредиты по промо-кодам
        if credit_analytics['bonus_events']:
            text += "🎁 <b>Бонусные кредиты:</b>\\n"
            for bonus in credit_analytics['bonus_events']:
                promo_data = bonus.get('event_data', {})
                if isinstance(promo_data, str):
                    import json
                    try:
                        promo_data = json.loads(promo_data)
                    except:
                        promo_data = {}
                
                promo_code = promo_data.get('promo_code', 'Неизвестен')
                text += f"• <code>{promo_code}</code>: {bonus['usage_count']}x по {bonus['credits_amount']} кредитов\\n"
        
        # Паттерны трат
        if credit_analytics['spending_patterns']:
            text += "\\n💸 <b>Паттерны трат:</b>\\n"
            for pattern in credit_analytics['spending_patterns'][:3]:
                text += f"• {abs(pattern['amount'])} кредитов: {pattern['transaction_count']} транзакций\\n"
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📥 Экспорт кредитов", callback_data=f"utm_export_{campaign_id}")
        builder.button(text="📊 Основная аналитика", callback_data=f"utm_view_campaign_{campaign_id}")
        builder.button(text="◀️ Назад", callback_data=f"utm_view_campaign_{campaign_id}")
        builder.adjust(2, 1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error showing credit details for campaign {campaign_id}: {e}")
        await callback.answer("❌ Ошибка при загрузке аналитики кредитов", show_alert=True)


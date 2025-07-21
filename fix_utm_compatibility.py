# Читаем файл
with open('bot/handlers/utm_admin.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Найдем функцию view_campaign и заменим её на безопасную версию
view_start = content.find('@router.callback_query(F.data.startswith("utm_view_campaign_"))')
view_end = content.find('@router.callback_query', view_start + 1)
if view_end == -1:
    view_end = content.find('\n\n# =================== УПРАВЛЕНИЕ КАМПАНИЕЙ ===================', view_start)

# Простая безопасная версия view_campaign
safe_view_campaign = '''@router.callback_query(F.data.startswith("utm_view_campaign_"))
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
            text += "\\n"
        
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
        
        builder.button(text="📥 Экспорт данных", callback_data=f"utm_export_{campaign_id}")
        builder.button(text="🗑️ Удалить кампанию", callback_data=f"utm_delete_{campaign_id}")
        builder.button(text="📋 Список кампаний", callback_data="utm_list_campaigns")
        builder.button(text="◀️ Меню UTM", callback_data="utm_analytics")
        builder.adjust(2, 1, 1, 1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error viewing UTM campaign {campaign_id}: {e}")
        await callback.answer("❌ Ошибка при загрузке аналитики", show_alert=True)

'''

# Заменяем функцию
if view_end != -1:
    content = content[:view_start] + safe_view_campaign + content[view_end:]

# Записываем обновленный файл
with open('bot/handlers/utm_admin.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Создана безопасная версия просмотра кампаний для совместимости")

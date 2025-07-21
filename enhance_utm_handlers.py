# Читаем файл
with open('bot/handlers/utm_admin.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Найдем функцию view_campaign
view_start = content.find('@router.callback_query(F.data.startswith("utm_view_campaign_"))')
view_end = content.find('@router.callback_query', view_start + 1)
if view_end == -1:
    view_end = content.find('\n\n# =================== УПРАВЛЕНИЕ КАМПАНИЕЙ ===================', view_start)

# Новая расширенная версия view_campaign
new_view_campaign = '''@router.callback_query(F.data.startswith("utm_view_campaign_"))
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
        
        campaign = analytics['campaign']
        clicks = analytics['clicks']
        events = analytics['events']
        conversions = analytics['conversions']
        revenue = analytics['revenue']
        timeline = analytics['timeline']
        
        status_emoji = "🟢" if campaign['is_active'] else "🔴"
        
        # Форматирование времени конверсии
        avg_convert_time = ""
        if events.get('registration', {}).get('avg_time_to_convert_minutes', 0) > 0:
            minutes = events['registration']['avg_time_to_convert_minutes']
            hours = events['registration']['avg_time_to_convert_hours']
            if hours >= 1:
                avg_convert_time = f"⏱️ Среднее время до регистрации: {hours:.1f}ч\\n"
            else:
                avg_convert_time = f"⏱️ Среднее время до регистрации: {minutes:.1f}мин\\n"
        
        text = f"""
📊 <b>Детальная аналитика кампании</b>

{status_emoji} <b>{campaign['name']}</b>

🏷️ <b>UTM параметры:</b>
• Источник: <code>{campaign['utm_source']}</code>
• Тип: <code>{campaign['utm_medium']}</code>
• Кампания: <code>{campaign['utm_campaign']}</code>
• Контент: <code>{campaign['utm_content'] or 'не указан'}</code>

📈 <b>Статистика трафика:</b>
• 👥 Всего кликов: <b>{clicks['total_clicks']}</b>
• 🆔 Уникальных пользователей: <b>{clicks['unique_users']}</b>
• 🆕 Первые посещения: <b>{clicks['first_visits']}</b>
• 📱 Зарегистрированных: <b>{clicks['registered_users_clicks']}</b>
• ✨ Новых пользователей: <b>{clicks['new_users_clicks']}</b>
• 🔄 Возвратов: <b>{clicks['total_clicks'] - clicks['first_visits']}</b> ({clicks['return_visitor_rate']}%)

🎯 <b>События и конверсии:</b>"""
        
        for event_type, event_data in events.items():
            event_emoji = {
                'registration': '📝',
                'purchase': '💰',
                'generation': '🎬'
            }.get(event_type, '📊')
            
            event_name = {
                'registration': 'Регистрации',
                'purchase': 'Покупки', 
                'generation': 'Генерации'
            }.get(event_type, event_type.title())
            
            text += f"\\n• {event_emoji} {event_name}: <b>{event_data['count']}</b>"
            if event_data['total_revenue'] > 0:
                text += f" (💰 {event_data['total_revenue']:.2f}₽)"
            
            if event_data.get('avg_time_to_convert_minutes', 0) > 0:
                if event_data['avg_time_to_convert_hours'] >= 1:
                    text += f" ⏱️ {event_data['avg_time_to_convert_hours']:.1f}ч"
                else:
                    text += f" ⏱️ {event_data['avg_time_to_convert_minutes']:.0f}мин"
        
        text += f"""

📊 <b>Коэффициенты конверсии:</b>
• Клики → Регистрации: <b>{conversions['click_to_registration']}%</b>
• Клики → Покупки: <b>{conversions['click_to_purchase']}%</b>
• Регистрации → Покупки: <b>{conversions['registration_to_purchase']}%</b>
• Уникальные → Регистрации: <b>{conversions['unique_to_registration']}%</b>

💰 <b>Монетизация:</b>
• Общая выручка: <b>{revenue['total']:.2f}₽</b>
• Выручка с клика: <b>{revenue['per_click']:.2f}₽</b>
• Выручка с пользователя: <b>{revenue['per_user']:.2f}₽</b>"""

        if revenue['per_registration'] > 0:
            text += f"\\n• ARPU: <b>{revenue['per_registration']:.2f}₽</b>"

        # Добавляем топ часы активности если есть данные
        if timeline['top_hours']:
            text += f"\\n\\n🕐 <b>Топ часы активности:</b>\\n"
            for i, hour_data in enumerate(timeline['top_hours'][:3], 1):
                text += f"{i}. {hour_data['hour']} - {hour_data['clicks']} кликов\\n"

        text += f"""

📅 <b>Создана:</b> {datetime.fromisoformat(campaign['created_at']).strftime('%d.%m.%Y %H:%M')}
🔗 <b>Код:</b> <code>{campaign['short_code']}</code>
"""
        
        builder = InlineKeyboardBuilder()
        
        # Переключение активности
        toggle_text = "🔴 Деактивировать" if campaign['is_active'] else "🟢 Активировать"
        builder.button(text=toggle_text, callback_data=f"utm_toggle_{campaign_id}")
        
        builder.button(text="📊 Подробная аналитика", callback_data=f"utm_detailed_{campaign_id}")
        builder.button(text="📥 Экспорт (детальный)", callback_data=f"utm_export_{campaign_id}")
        builder.button(text="📋 Экспорт (сводка)", callback_data=f"utm_export_summary_{campaign_id}")
        builder.button(text="🗑️ Удалить кампанию", callback_data=f"utm_delete_{campaign_id}")
        builder.button(text="📋 Список кампаний", callback_data="utm_list_campaigns")
        builder.button(text="◀️ Меню UTM", callback_data="utm_analytics")
        builder.adjust(2, 2, 1, 1, 1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error viewing UTM campaign {campaign_id}: {e}")
        await callback.answer("❌ Ошибка при загрузке аналитики", show_alert=True)

'''

# Заменяем функцию
if view_end != -1:
    content = content[:view_start] + new_view_campaign + content[view_end:]

# Записываем обновленный файл
with open('bot/handlers/utm_admin.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Обновлен обработчик просмотра кампании с расширенной аналитикой")

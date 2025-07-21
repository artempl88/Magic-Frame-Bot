# Читаем файл
with open('bot/handlers/utm_admin.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Найдем старый обработчик экспорта
export_start = content.find('@router.callback_query(F.data.startswith("utm_export_"))')
# Ищем конец, но не захватываем новый utm_export_summary_
export_end = content.find('@router.callback_query', export_start + 1)
while export_end != -1 and 'utm_export_summary_' in content[export_end:export_end+100]:
    export_end = content.find('@router.callback_query', export_end + 1)

# Новая версия обработчика экспорта
new_export_handler = '''@router.callback_query(F.data.startswith("utm_export_"))
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
        
        data = await utm_service.export_campaign_data(campaign_id, start_date, end_date, export_format="detailed")
        
        if not data:
            await callback.answer("📝 Нет данных для экспорта", show_alert=True)
            return
        
        # Создаем CSV с расширенными полями
        output = io.StringIO()
        
        # Определяем поля для детального экспорта
        fieldnames = [
            'campaign_name', 'utm_source', 'utm_medium', 'utm_campaign', 'utm_content',
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
        campaign_name = data[0]['campaign_name'] if data else f"Campaign {campaign_id}"
        total_clicks = len(set(row['click_id'] for row in data))
        total_events = len([row for row in data if row['event_type']])
        total_revenue = sum(float(row['revenue']) for row in data)
        
        await callback.message.answer_document(
            file,
            caption=f"""📊 <b>Детальные данные UTM кампании</b>

📋 <b>Кампания:</b> {campaign_name}
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

'''

# Заменяем только если нашли старый обработчик
if export_end != -1 and 'utm_export_' in content[export_start:export_start+100]:
    content = content[:export_start] + new_export_handler + content[export_end:]
elif 'utm_export_' in content[export_start:export_start+100]:
    # Если не нашли конец, добавляем в конец
    content = content[:export_start] + new_export_handler + '\n\n'

# Записываем обновленный файл
with open('bot/handlers/utm_admin.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Обновлен обработчик экспорта с поддержкой расширенных данных")

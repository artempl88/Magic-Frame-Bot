# Fix for admin_detailed_stats handler - to be added to admin.py

@router.callback_query(F.data == "admin_detailed_stats")
@admin_only
async def show_detailed_admin_stats(callback: CallbackQuery):
    """Показать детальную статистику бота"""
    try:
        # Получаем расширенную статистику
        stats = await db.get_bot_statistics()
        detailed_stats = await db.get_detailed_statistics()
        
        # Форматируем детальное сообщение
        text = format_detailed_stats_message(stats, detailed_stats)
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔄 Обновить", callback_data="admin_detailed_stats")
        builder.button(text="📊 Краткая", callback_data="admin_stats")
        builder.button(text="📥 Экспорт", callback_data="admin_export_stats")
        builder.button(text="◀️ Назад", callback_data="admin_menu")
        builder.adjust(2, 1, 1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
        await BaseHandler.answer_callback(callback)
        
    except Exception as e:
        logger.error(f"Error loading detailed admin stats: {e}")
        await callback.answer("❌ Ошибка загрузки детальной статистики", show_alert=True)

def format_detailed_stats_message(stats: dict, detailed_stats: dict) -> str:
    """Форматировать детальное сообщение со статистикой"""
    try:
        text = f"""
📊 <b>Детальная статистика бота</b>

👥 <b>Пользователи:</b>
├ Всего: {stats['users']['total']}
├ Активных сегодня: {stats['users']['active_today']}
├ Новых сегодня: {stats['users']['new_today']}
├ Новых за неделю: {detailed_stats.get('users', {}).get('new_week', 0)}
├ Новых за месяц: {detailed_stats.get('users', {}).get('new_month', 0)}
└ Средний баланс: {detailed_stats.get('users', {}).get('avg_balance', 0):.1f} кредитов

🎬 <b>Генерации:</b>
├ Всего: {stats['generations']['total']}
├ Сегодня: {stats['generations']['today']}
├ В обработке: {stats['generations']['pending']}
├ Успешных: {detailed_stats.get('generations', {}).get('completed', 0)}
├ Отмененных: {detailed_stats.get('generations', {}).get('cancelled', 0)}
└ Средняя длительность: {detailed_stats.get('generations', {}).get('avg_duration', 0):.1f} мин

💰 <b>Финансы:</b>
├ Доходы сегодня: {stats['finance']['revenue_today']} Stars
├ Общие доходы: {stats['finance']['total_revenue']} Stars
├ Потрачено кредитов сегодня: {detailed_stats.get('finance', {}).get('credits_spent_today', 0)}
├ Куплено кредитов сегодня: {detailed_stats.get('finance', {}).get('credits_bought_today', 0)}
└ Средний чек: {detailed_stats.get('finance', {}).get('avg_purchase', 0):.2f} Stars

⚡ <b>Производительность:</b>
├ API запросов сегодня: {detailed_stats.get('performance', {}).get('api_requests_today', 0)}
├ Среднее время ответа: {detailed_stats.get('performance', {}).get('avg_response_time', 0):.2f} сек
├ Ошибок API: {detailed_stats.get('performance', {}).get('api_errors_today', 0)}
└ Нагрузка системы: {detailed_stats.get('performance', {}).get('system_load', 0):.1f}%

📅 <b>Обновлено:</b> {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}
"""
        return text
    except Exception as e:
        logger.error(f"Error formatting detailed stats: {e}")
        return "❌ Ошибка форматирования статистики"

@router.callback_query(F.data == "admin_export_stats")
@admin_only
async def export_admin_stats(callback: CallbackQuery):
    """Экспорт статистики в файл"""
    try:
        await callback.answer("📊 Подготавливаю экспорт...")
        
        # Получаем данные для экспорта
        stats = await db.get_bot_statistics()
        detailed_stats = await db.get_detailed_statistics()
        
        # Создаем CSV с данными
        import io
        import csv
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Заголовки
        writer.writerow(['Метрика', 'Значение', 'Описание'])
        
        # Пользователи
        writer.writerow(['Всего пользователей', stats['users']['total'], 'Общее количество пользователей'])
        writer.writerow(['Активных сегодня', stats['users']['active_today'], 'Пользователей активных сегодня'])
        writer.writerow(['Новых сегодня', stats['users']['new_today'], 'Новых регистраций сегодня'])
        
        # Генерации
        writer.writerow(['Всего генераций', stats['generations']['total'], 'Общее количество генераций'])
        writer.writerow(['Генераций сегодня', stats['generations']['today'], 'Генераций сегодня'])
        writer.writerow(['В обработке', stats['generations']['pending'], 'Генераций в обработке'])
        
        # Финансы
        writer.writerow(['Доход сегодня (Stars)', stats['finance']['revenue_today'], 'Доход за сегодня'])
        writer.writerow(['Общий доход (Stars)', stats['finance']['total_revenue'], 'Общий доход'])
        
        # Создаем файл для отправки
        csv_content = output.getvalue().encode('utf-8')
        filename = f"bot_stats_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        from aiogram.types import BufferedInputFile
        file = BufferedInputFile(csv_content, filename=filename)
        
        await callback.message.answer_document(
            file,
            caption=f"📊 Экспорт статистики бота\n📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        )
        
        await callback.answer("✅ Статистика экспортирована")
        
    except Exception as e:
        logger.error(f"Error exporting admin stats: {e}")
        await callback.answer("❌ Ошибка при экспорте статистики", show_alert=True)

#!/usr/bin/env python3

import re

def add_detailed_stats_handler():
    # Read the admin.py file
    with open('./bot/handlers/admin.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Find the position after the show_admin_stats function
    pattern = r'(@router\.callback_query\(F\.data == "admin_stats"\)\n@admin_only\nasync def show_admin_stats.*?)(\n\n@router\.callback_query)'
    
    # The new handler code
    new_handler = '''
@router.callback_query(F.data == "admin_detailed_stats")
@admin_only
async def show_detailed_admin_stats(callback: CallbackQuery):
    """Показать детальную статистику бота"""
    try:
        # Получаем расширенную статистику
        stats = await db.get_bot_statistics()
        
        # Получаем дополнительную статистику
        try:
            detailed_stats = await get_detailed_statistics()
        except Exception as e:
            logger.warning(f"Could not get detailed stats: {e}")
            detailed_stats = {}
        
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

@router.callback_query(F.data == "admin_export_stats")
@admin_only
async def export_admin_stats(callback: CallbackQuery):
    """Экспорт статистики в файл"""
    try:
        await callback.answer("📊 Подготавливаю экспорт...")
        
        # Получаем данные для экспорта
        stats = await db.get_bot_statistics()
        
        # Создаем CSV с данными
        import io
        import csv
        from aiogram.types import BufferedInputFile
        
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
        
        file = BufferedInputFile(csv_content, filename=filename)
        
        await callback.message.answer_document(
            file,
            caption=f"📊 Экспорт статистики бота\\n📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        )
        
        await callback.answer("✅ Статистика экспортирована")
        
    except Exception as e:
        logger.error(f"Error exporting admin stats: {e}")
        await callback.answer("❌ Ошибка при экспорте статистики", show_alert=True)'''

    # Find the right place to insert the new handlers (after show_admin_stats)
    match = re.search(pattern, content, re.DOTALL)
    if match:
        # Insert the new handler after show_admin_stats
        new_content = content[:match.end(1)] + new_handler + content[match.start(2):]
    else:
        # If pattern not found, add at the end before helper functions
        helper_functions_pattern = r'(\n# Вспомогательные функции)'
        match = re.search(helper_functions_pattern, content)
        if match:
            new_content = content[:match.start(1)] + new_handler + content[match.start(1):]
        else:
            # Add at the end
            new_content = content + new_handler
    
    # Add helper functions
    helper_functions = '''
async def get_detailed_statistics() -> dict:
    """Получить детальную статистику"""
    try:
        # Здесь можно добавить более детальные запросы к БД
        # Пока возвращаем заглушку
        return {
            'users': {
                'new_week': 0,
                'new_month': 0,
                'avg_balance': 0.0
            },
            'generations': {
                'completed': 0,
                'cancelled': 0,
                'avg_duration': 0.0
            },
            'finance': {
                'credits_spent_today': 0,
                'credits_bought_today': 0,
                'avg_purchase': 0.0
            },
            'performance': {
                'api_requests_today': 0,
                'avg_response_time': 0.0,
                'api_errors_today': 0,
                'system_load': 0.0
            }
        }
    except Exception as e:
        logger.error(f"Error getting detailed statistics: {e}")
        return {}

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
'''
    
    # Add helper functions at the end before other helper functions
    helper_pattern = r'(\n# Вспомогательные функции\n)'
    match = re.search(helper_pattern, new_content)
    if match:
        new_content = new_content[:match.end(1)] + helper_functions + new_content[match.end(1):]
    else:
        new_content = new_content + helper_functions
    
    # Write the updated content
    with open('./bot/handlers/admin.py', 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print("✅ Added admin_detailed_stats and admin_export_stats handlers")

if __name__ == "__main__":
    add_detailed_stats_handler()

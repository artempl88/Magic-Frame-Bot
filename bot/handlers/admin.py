import logging
import asyncio
from datetime import datetime, timedelta
from typing import Union, Optional
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, func

from bot.handlers.base import BaseHandler
from bot.keyboard.inline import (
    get_admin_keyboard, get_cancel_keyboard, get_backup_keyboard,
    get_backup_list_keyboard, get_backup_info_keyboard
)
from bot.utils.messages import MessageTemplates
from services.database import db
from services.api_monitor import api_monitor
from services.backup_service import backup_service
from bot.middlewares.i18n import i18n
from core.config import settings
from models.models import User, AdminLog, Generation, Transaction, SupportTicket
from core.constants import GenerationStatus

logger = logging.getLogger(__name__)

class AdminStates(StatesGroup):
    broadcast_message = State()
    give_credits_user = State()
    give_credits_amount = State()
    user_search = State()
    ban_search = State()
    backup_description = State()
    backup_restore_confirm = State()
    
    # Управление ценами
    price_edit_stars = State()
    price_edit_rub = State()
    price_edit_note = State()

router = Router(name="admin")

# Декоратор для проверки админских прав
def admin_only(func):
    """Декоратор для ограничения доступа только админам"""
    from functools import wraps
    
    @wraps(func)
    async def wrapper(update: Union[Message, CallbackQuery], *args, **kwargs):
        if update.from_user.id not in settings.ADMIN_IDS:
            if isinstance(update, CallbackQuery):
                await update.answer("❌ Доступ запрещен", show_alert=True)
            else:
                await update.answer("❌ У вас нет прав администратора")
            return
        return await func(update, *args, **kwargs)
    return wrapper

# Добавляем декоратор для проверки пользователя
def ensure_user(func):
    """Декоратор для проверки существования пользователя"""
    from functools import wraps
    
    @wraps(func)
    async def wrapper(update: Union[Message, CallbackQuery], *args, **kwargs):
        user, translator = await BaseHandler.get_user_and_translator(update)
        if not user:
            text = "❌ Пользователь не найден. Используйте /start"
            if isinstance(update, CallbackQuery):
                await update.answer(text, show_alert=True)
            else:
                await update.answer(text)
            return
        kwargs['user'] = user
        kwargs['_'] = translator
        return await func(update, *args, **kwargs)
    return wrapper

@router.message(F.text == "/admin")
@admin_only
@ensure_user
async def admin_panel(message: Message, user: User, **kwargs):
    """Админ панель"""
    await message.answer(
        f"👑 <b>Панель администратора</b>\n\nВыберите действие:",
        reply_markup=get_admin_keyboard(user.language_code or 'ru')
    )

@router.callback_query(F.data == "admin_stats")
@admin_only
async def show_admin_stats(callback: CallbackQuery, **kwargs):
    """Показать статистику бота"""
    try:
        stats = await db.get_bot_statistics()
        
        text = format_stats_message(stats)
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔄 Обновить", callback_data="admin_stats")
        builder.button(text="📊 Детальная", callback_data="admin_detailed_stats")
        builder.button(text="◀️ Назад", callback_data="admin_menu")
        builder.adjust(2, 1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
        
        await BaseHandler.answer_callback(callback)
        
    except Exception as e:
        logger.error(f"Error loading admin stats: {e}")
        await callback.answer("❌ Ошибка загрузки статистики", show_alert=True)
@router.callback_query(F.data == "admin_detailed_stats")
@admin_only
async def show_detailed_admin_stats(callback: CallbackQuery, **kwargs):
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
async def export_admin_stats(callback: CallbackQuery, **kwargs):
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
            caption=f"📊 Экспорт статистики бота\n📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        )
        
        await callback.answer("✅ Статистика экспортирована")
        
    except Exception as e:
        logger.error(f"Error exporting admin stats: {e}")
        await callback.answer("❌ Ошибка при экспорте статистики", show_alert=True)

@router.callback_query(F.data == "admin_menu")
@admin_only
@ensure_user
async def show_admin_menu(callback: CallbackQuery, user: User, **kwargs):
    """Показать админ меню"""
    await callback.message.edit_text(
        f"👑 <b>Панель администратора</b>\n\nВыберите действие:",
        reply_markup=get_admin_keyboard(user.language_code or 'ru')
    )
    await BaseHandler.answer_callback(callback)

@router.callback_query(F.data == "admin_broadcast")
@admin_only
async def admin_broadcast(callback: CallbackQuery, state: FSMContext):
    """Начать рассылку"""
    await callback.message.edit_text(
        "📢 <b>Массовая рассылка</b>\n\n"
        "Отправьте сообщение для рассылки всем пользователям:",
        reply_markup=InlineKeyboardBuilder()
            .button(text="❌ Отмена", callback_data="admin_menu")
            .as_markup()
    )
    
    await state.set_state(AdminStates.broadcast_message)
    await BaseHandler.answer_callback(callback)

@router.message(AdminStates.broadcast_message)
@admin_only
async def handle_broadcast_message(message: Message, state: FSMContext):
    """Обработка сообщения для рассылки"""
    await state.update_data(broadcast_message=message.message_id)
    
    # Получаем количество пользователей
    async with db.async_session() as session:
        from sqlalchemy import func, select
        from models.models import User
        
        result = await session.execute(select(func.count(User.id)))
        users_count = result.scalar()
    
    confirm_text = f"""
📢 <b>Подтверждение рассылки</b>

Получателей: {users_count}
Сообщение готово к отправке.

⚠️ Сообщение будет отправлено {users_count} пользователям!
"""
    
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Начать рассылку", callback_data="broadcast_confirm")
    builder.button(text="❌ Отмена", callback_data="admin_menu")
    builder.adjust(1)
    
    await message.answer(confirm_text, reply_markup=builder.as_markup())

@router.callback_query(F.data == "broadcast_confirm")
@admin_only
async def confirm_broadcast(callback: CallbackQuery, state: FSMContext):
    """Подтверждение и запуск рассылки"""
    data = await state.get_data()
    broadcast_message_id = data.get("broadcast_message")
    
    if not broadcast_message_id:
        await callback.answer("❌ Сообщение не найдено", show_alert=True)
        return
    
    # Запускаем рассылку
    await callback.message.edit_text("📢 <b>Рассылка запущена...</b>")
    
    success_count = await broadcast_to_users(
        callback.bot,
        callback.from_user.id,
        broadcast_message_id
    )
    
    await callback.message.edit_text(
        f"✅ <b>Рассылка завершена</b>\n\n"
        f"Успешно отправлено: {success_count}",
        reply_markup=InlineKeyboardBuilder()
            .button(text="◀️ Назад", callback_data="admin_menu")
            .as_markup()
    )
    
    await state.clear()

@router.callback_query(F.data == "admin_give_credits")
@admin_only
async def give_credits(callback: CallbackQuery, state: FSMContext):
    """Начать выдачу кредитов"""
    await callback.message.edit_text(
        "💰 <b>Выдача кредитов</b>\n\n"
        "Отправьте ID пользователя или его @username:",
        reply_markup=InlineKeyboardBuilder()
            .button(text="❌ Отмена", callback_data="admin_menu")
            .as_markup()
    )
    
    await state.set_state(AdminStates.give_credits_user)
    await BaseHandler.answer_callback(callback)

@router.message(AdminStates.give_credits_user)
@admin_only
async def handle_give_credits_user(message: Message, state: FSMContext):
    """Обработка пользователя для выдачи кредитов"""
    user = await find_user_by_input(message.text.strip())
    
    if not user:
        await message.answer(
            "❌ Пользователь не найден",
            reply_markup=InlineKeyboardBuilder()
                .button(text="❌ Отмена", callback_data="admin_menu")
                .as_markup()
        )
        return
    
    await state.update_data(target_user_id=user.id)
    
    await message.answer(
        f"👤 <b>Пользователь найден</b>\n\n"
        f"Имя: {user.first_name or 'Без имени'}\n"
        f"Баланс: {user.balance} кредитов\n\n"
        "Введите количество кредитов (положительное или отрицательное):",
        reply_markup=InlineKeyboardBuilder()
            .button(text="❌ Отмена", callback_data="admin_menu")
            .as_markup()
    )
    
    await state.set_state(AdminStates.give_credits_amount)

@router.message(AdminStates.give_credits_amount)
@admin_only
async def handle_give_credits_amount(message: Message, state: FSMContext):
    """Обработка количества кредитов"""
    try:
        amount = int(message.text.strip())
        
        if amount == 0:
            await message.answer("❌ Количество должно быть не равно 0")
            return
        
        data = await state.get_data()
        target_user_id = data.get("target_user_id")
        
        success = await process_credits_change(
            target_user_id,
            amount,
            message.from_user.id,
            message.bot
        )
        
        if success:
            await message.answer(
                f"✅ Успешно! Баланс пользователя изменен на {amount} кредитов",
                reply_markup=InlineKeyboardBuilder()
                    .button(text="◀️ Назад", callback_data="admin_menu")
                    .as_markup()
            )
        else:
            await message.answer("❌ Ошибка при изменении баланса")
        
    except ValueError:
        await message.answer("❌ Введите корректное число")
        return
    finally:
        await state.clear()

@router.callback_query(F.data == "admin_api_balance")
@admin_only
async def check_api_balance(callback: CallbackQuery, **kwargs):
    """Проверить баланс API"""
    try:
        await callback.answer("Проверяю баланс API...")
        
        balance_check = await api_monitor.check_and_notify(callback.bot)
        
        text = format_api_balance_message(balance_check)
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔄 Обновить", callback_data="admin_api_balance")
        builder.button(text="◀️ Назад", callback_data="admin_menu")
        builder.adjust(2)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
        
        
    except Exception as e:
        logger.error(f"Error checking API balance: {e}")
        await callback.answer("❌ Ошибка при проверке баланса", show_alert=True)

# Вспомогательные функции

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

async def find_user_by_input(user_input: str) -> Optional[User]:
    """Найти пользователя по ID или username"""
    user_input = user_input.strip()
    
    if user_input.isdigit():
        return await db.get_user(int(user_input))
    elif user_input.startswith('@'):
        return await db.get_user_by_username(user_input[1:])
    return None

async def broadcast_to_users(bot, admin_id: int, message_id: int) -> int:
    """Выполнить рассылку сообщения (оптимизированная версия)"""
    success_count = 0
    failed_count = 0
    batch_size = 100  # Обрабатываем по 100 пользователей за раз
    
    # Получаем общее количество пользователей
    async with db.async_session() as session:
        total_result = await session.execute(select(func.count(User.id)))
        total_users = total_result.scalar()
    
    logger.info(f"Starting broadcast to {total_users} users")
    
    # Обрабатываем пользователей батчами
    for offset in range(0, total_users, batch_size):
        users = await db.get_all_users(limit=batch_size, offset=offset)
        
        for user in users:
            try:
                await bot.copy_message(
                    chat_id=user.telegram_id,
                    from_chat_id=admin_id,
                    message_id=message_id
                )
                success_count += 1
                await asyncio.sleep(0.05)  # Антифлуд
            except Exception as e:
                failed_count += 1
                logger.error(f"Broadcast error for user {user.telegram_id}: {e}")
        
        # Даем серверу отдохнуть между батчами
        await asyncio.sleep(1)
        logger.info(f"Broadcast progress: {offset + len(users)}/{total_users}")
    
    logger.info(f"Broadcast completed: {success_count} success, {failed_count} failed")
    return success_count

async def process_credits_change(
    user_id: int,
    amount: int,
    admin_id: int,
    bot
) -> bool:
    """Обработать изменение баланса пользователя"""
    try:
        async with db.async_session() as session:
            user = await session.get(User, user_id)
            if not user:
                return False
            
            old_balance = user.balance
            user.balance = max(0, user.balance + amount)
            
            if amount > 0:
                user.total_bought += amount
            else:
                user.total_spent += abs(amount)
            
            await session.commit()
            
            # Логируем действие
            await db.log_admin_action(
                admin_id=admin_id,
                action="give_credits",
                target_user_id=user.telegram_id,
                details=f"Amount: {amount}, Balance: {old_balance} -> {user.balance}"
            )
            
            # Уведомляем пользователя
            try:
                text = f"💰 Ваш баланс изменен на {amount:+d} кредитов\n"
                text += f"Новый баланс: {user.balance} кредитов"
                await bot.send_message(user.telegram_id, text)
            except:
                pass
            
            return True
            
    except Exception as e:
        logger.error(f"Error changing user balance: {e}")
        return False

def format_stats_message(stats: dict) -> str:
    """Форматировать сообщение со статистикой"""
    return f"""
📊 <b>Статистика бота</b>

👥 <b>Пользователи:</b>
├ Всего: {stats['users']['total']}
├ Активных сегодня: {stats['users']['active_today']}
└ Новых сегодня: {stats['users']['new_today']}

🎬 <b>Генерации:</b>
├ Всего: {stats['generations']['total']}
├ Сегодня: {stats['generations']['today']}
└ В обработке: {stats['generations']['pending']}

💰 <b>Финансы:</b>
├ Доходы сегодня: {stats['finance']['revenue_today']} Stars
└ Общие доходы: {stats['finance']['total_revenue']} Stars
"""

def format_api_balance_message(balance_check: dict) -> str:
    """Форматировать сообщение о балансе API"""
    balance = balance_check.get('balance')
    status = balance_check.get('status')
    
    if balance is None:
        return "❌ <b>Ошибка проверки баланса API</b>\n\nНе удалось получить информацию."
    
    status_info = {
        'critical': ('🚨', 'КРИТИЧНО', 'Требуется немедленное пополнение!'),
        'low': ('⚠️', 'НИЗКИЙ', 'Рекомендуется пополнить баланс.'),
        'normal': ('✅', 'НОРМА', 'Всё в порядке.')
    }
    
    emoji, status_text, advice = status_info.get(status, ('❓', 'НЕИЗВЕСТНО', ''))
    
    return f"""
{emoji} <b>Баланс API: {status_text}</b>

💰 <b>Текущий баланс:</b> ${balance}
📅 <b>Время проверки:</b> {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}

🎯 <b>Пороговые значения:</b>
├ Критичный: ${api_monitor.critical_balance_threshold}
└ Низкий: ${api_monitor.low_balance_threshold}

{advice}
"""

# === BACKUP HANDLERS ===

@router.callback_query(F.data == "admin_backup")
@admin_only
@ensure_user
async def backup_menu(callback: CallbackQuery, user: User, **kwargs):
    """Меню управления бэкапами"""
    stats = await backup_service.get_backup_stats()
    
    text = f"""
💾 <b>Управление бэкапами базы данных</b>

📊 <b>Статистика:</b>
├ Количество бэкапов: {stats['total_count']}
├ Общий размер: {stats['total_size_mb']:.1f} MB
└ Папка: <code>{stats['backup_dir']}</code>
"""
    
    if stats['latest_backup']:
        latest = stats['latest_backup']
        text += f"\n🕐 <b>Последний бэкап:</b> {latest['created_at'].strftime('%d.%m.%Y %H:%M:%S')}"
    
    await callback.message.edit_text(
        text=text,
        reply_markup=get_backup_keyboard(user.language_code or 'ru')
    )

@router.callback_query(F.data == "backup_create")
@admin_only
@ensure_user
async def backup_create(callback: CallbackQuery, state: FSMContext, user: User, **kwargs):
    """Создать бэкап"""
    await callback.message.edit_text(
        text="📝 <b>Создание бэкапа</b>\n\nВведите описание для бэкапа (или отправьте /skip для пропуска):",
        reply_markup=get_cancel_keyboard(user.language_code or 'ru')
    )
    
    await state.set_state(AdminStates.backup_description)

@router.message(AdminStates.backup_description)
@admin_only
@ensure_user
async def backup_create_with_description(message: Message, state: FSMContext, user: User):
    """Создать бэкап с описанием"""
    await state.clear()
    
    description = None if message.text == "/skip" else message.text
    
    # Отправляем сообщение о начале создания бэкапа
    status_msg = await message.answer("⏳ Создание бэкапа... Пожалуйста, подождите.")
    
    try:
        success, result_msg, file_path = await backup_service.create_backup(description)
        
        if success:
            await status_msg.edit_text(
                text=result_msg,
                reply_markup=get_backup_keyboard(user.language_code or 'ru')
            )
            
            # Логируем создание бэкапа
            await BaseHandler.log_admin_action(
                user.id,
                "backup_create",
                {"description": description, "file_path": file_path}
            )
        else:
            await status_msg.edit_text(
                text=f"❌ <b>Ошибка создания бэкапа</b>\n\n{result_msg}",
                reply_markup=get_backup_keyboard(user.language_code or 'ru')
            )
            
    except Exception as e:
        logger.error(f"Ошибка создания бэкапа: {e}", exc_info=True)
        await status_msg.edit_text(
            text=f"❌ <b>Критическая ошибка</b>\n\n{str(e)}",
            reply_markup=get_backup_keyboard(user.language_code or 'ru')
        )

@router.callback_query(F.data == "backup_list")
@admin_only
@ensure_user
async def backup_list(callback: CallbackQuery, user: User, **kwargs):
    """Список бэкапов"""
    await callback.answer("🔄 Загрузка списка бэкапов...")
    
    try:
        backups = await backup_service.list_backups()
        
        if not backups:
            await callback.message.edit_text(
                text="📁 <b>Список бэкапов пуст</b>\n\nБэкапы еще не созданы.",
                reply_markup=get_backup_keyboard(user.language_code or 'ru')
            )
            return
        
        text = f"📁 <b>Список бэкапов</b> (показаны последние 10)\n\n"
        
        for i, backup in enumerate(backups[:10], 1):
            created_at = backup['created_at'].strftime('%d.%m.%Y %H:%M')
            size_mb = backup['size_mb']
            description = backup.get('description', 'Без описания')[:30]
            
            text += f"{i}. <b>{backup['filename']}</b>\n"
            text += f"   📅 {created_at} | 💾 {size_mb:.1f} MB\n"
            text += f"   📝 {description}\n\n"
        
        await callback.message.edit_text(
            text=text,
            reply_markup=get_backup_list_keyboard(backups, user.language_code or 'ru')
        )
        
    except Exception as e:
        logger.error(f"Ошибка получения списка бэкапов: {e}")
        await callback.message.edit_text(
            text=f"❌ <b>Ошибка получения списка</b>\n\n{str(e)}",
            reply_markup=get_backup_keyboard(user.language_code or 'ru')
        )

@router.callback_query(F.data.startswith("backup_info_"))
@admin_only
@ensure_user
async def backup_info(callback: CallbackQuery, user: User, **kwargs):
    """Информация о конкретном бэкапе"""
    filename = callback.data.replace("backup_info_", "")
    
    try:
        backups = await backup_service.list_backups()
        backup = next((b for b in backups if b['filename'] == filename), None)
        
        if not backup:
            await callback.answer("❌ Бэкап не найден", show_alert=True)
            return
        
        text = f"""
📄 <b>Информация о бэкапе</b>

📁 <b>Файл:</b> <code>{backup['filename']}</code>
📅 <b>Создан:</b> {backup['created_at'].strftime('%d.%m.%Y %H:%M:%S')}
💾 <b>Размер:</b> {backup['size_mb']:.1f} MB
📝 <b>Описание:</b> {backup.get('description', 'Без описания')}

⚠️ <b>Внимание:</b> Восстановление заменит всю текущую базу данных!
"""
        
        await callback.message.edit_text(
            text=text,
            reply_markup=get_backup_info_keyboard(filename, user.language_code or 'ru')
        )
        
    except Exception as e:
        logger.error(f"Ошибка получения информации о бэкапе: {e}")
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)

@router.callback_query(F.data.startswith("backup_delete_"))
@admin_only
@ensure_user
async def backup_delete(callback: CallbackQuery, user: User, **kwargs):
    """Удалить бэкап"""
    filename = callback.data.replace("backup_delete_", "")
    
    try:
        success, message = await backup_service.delete_backup(filename)
        
        if success:
            await callback.answer("✅ Бэкап удален")
            
            # Логируем удаление
            await BaseHandler.log_admin_action(
                user.id,
                "backup_delete", 
                {"filename": filename}
            )
            
            # Возвращаемся к списку
            await backup_list(callback)
        else:
            await callback.answer(f"❌ {message}", show_alert=True)
            
    except Exception as e:
        logger.error(f"Ошибка удаления бэкапа: {e}")
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)

@router.callback_query(F.data.startswith("backup_restore_"))
@admin_only
async def backup_restore(callback: CallbackQuery, state: FSMContext):
    """Восстановить из бэкапа"""
    user, _ = await BaseHandler.get_user_and_translator(callback)
    if not user:
        return
    
    filename = callback.data.replace("backup_restore_", "")
    
    # Сохраняем имя файла в состоянии
    await state.update_data(restore_filename=filename)
    
    # Получаем информацию о бэкапе
    try:
        backups = await backup_service.list_backups()
        backup = next((b for b in backups if b['filename'] == filename), None)
        
        if not backup:
            await callback.answer("❌ Бэкап не найден", show_alert=True)
            return
        
        # Подтверждение опасной операции
        await callback.message.edit_text(
            text=f"""
⚠️ <b>ВНИМАНИЕ! КРИТИЧЕСКИ ОПАСНАЯ ОПЕРАЦИЯ!</b>

Вы собираетесь ПОЛНОСТЬЮ ЗАМЕНИТЬ базу данных:

📁 <b>Файл бэкапа:</b> <code>{filename}</code>
📅 <b>Дата создания:</b> {backup['created_at'].strftime('%d.%m.%Y %H:%M:%S')}
💾 <b>Размер:</b> {backup['size_mb']:.1f} MB
📝 <b>Описание:</b> {backup.get('description', 'Без описания')}

🚨 <b>ЭТО НЕОБРАТИМО ПРИВЕДЕТ К:</b>
• Полной замене текущей базы данных
• Потере ВСЕХ пользователей и данных
• Потере всех генераций после {backup['created_at'].strftime('%d.%m.%Y %H:%M')}
• Невозможности отмены операции

⚠️ <b>ПЕРЕД ВОССТАНОВЛЕНИЕМ:</b>
• Создайте резервную копию текущей БД!
• Убедитесь, что это именно тот бэкап!
• Предупредите всех пользователей!

Для подтверждения введите точно: <code>ВОССТАНОВИТЬ {filename}</code>

❌ Или нажмите "Отмена" для безопасного возврата.
""",
            reply_markup=InlineKeyboardBuilder().button(
                text="❌ Отмена",
                callback_data="backup_list"
            ).as_markup()
        )
        
        # Переводим в состояние ожидания подтверждения
        await state.set_state(AdminStates.backup_restore_confirm)
        
    except Exception as e:
        logger.error(f"Error preparing backup restore: {e}")
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)

@router.message(AdminStates.backup_restore_confirm)
@admin_only
@ensure_user
async def backup_restore_confirm(message: Message, state: FSMContext, user: User):
    """Подтверждение восстановления через точный текст"""
    # Получаем данные из состояния
    data = await state.get_data()
    filename = data.get('restore_filename')
    
    if not filename:
        await message.answer("❌ Ошибка: имя файла не найдено. Начните сначала.")
        await state.clear()
        return
    
    # Проверяем точное соответствие текста
    expected_text = f"ВОССТАНОВИТЬ {filename}"
    if message.text.strip() != expected_text:
        await message.answer(
            f"❌ <b>Неверный текст подтверждения!</b>\n\n"
            f"Ожидается: <code>{expected_text}</code>\n"
            f"Получено: <code>{message.text}</code>\n\n"
            f"Введите точно или нажмите /cancel для отмены.",
            parse_mode="HTML"
        )
        return
    
    # Очищаем состояние
    await state.clear()
    
    # Создаем автоматический бэкап перед восстановлением
    await message.answer("🔄 Создание защитного бэкапа перед восстановлением...")
    
    try:
        success, backup_msg, backup_path = await backup_service.create_backup(
            f"Автобэкап перед восстановлением {filename}"
        )
        
        if not success:
            await message.answer(
                f"❌ <b>КРИТИЧЕСКАЯ ОШИБКА!</b>\n\n"
                f"Не удалось создать защитный бэкап: {backup_msg}\n\n"
                f"🚫 Восстановление ОТМЕНЕНО для безопасности данных!"
            )
            return
        
        await message.answer(f"✅ Защитный бэкап создан: <code>{backup_path}</code>")
        
    except Exception as e:
        await message.answer(
            f"❌ <b>КРИТИЧЕСКАЯ ОШИБКА!</b>\n\n"
            f"Ошибка создания защитного бэкапа: {str(e)}\n\n"
            f"🚫 Восстановление ОТМЕНЕНО!"
        )
        return
    
    # Начинаем процесс восстановления
    status_msg = await message.answer("⏳ <b>ВОССТАНОВЛЕНИЕ БАЗЫ ДАННЫХ...</b>\n\n⚠️ НЕ ПЕРЕЗАГРУЖАЙТЕ БОТА!")
    
    try:
        success, result_msg = await backup_service.restore_backup(filename)
        
        if success:
            # Логируем критическую операцию
            await BaseHandler.log_admin_action(
                user.id,
                "backup_restore",
                {
                    "filename": filename,
                    "admin_id": user.id,
                    "admin_username": message.from_user.username,
                    "timestamp": datetime.now().isoformat()
                }
            )
            
            await status_msg.edit_text(
                f"✅ <b>ВОССТАНОВЛЕНИЕ ЗАВЕРШЕНО!</b>\n\n"
                f"{result_msg}\n\n"
                f"📄 <b>Восстановлен файл:</b> {filename}\n"
                f"👤 <b>Администратор:</b> @{message.from_user.username or 'Unknown'}\n"
                f"🕐 <b>Время:</b> {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n\n"
                f"🔄 <b>Рекомендуется перезапустить бота для обновления соединений с БД.</b>",
                reply_markup=get_backup_keyboard(user.language_code or 'ru')
            )
            
        else:
            await status_msg.edit_text(
                f"❌ <b>ОШИБКА ВОССТАНОВЛЕНИЯ!</b>\n\n"
                f"{result_msg}\n\n"
                f"💾 База данных НЕ была изменена.\n"
                f"✅ Защитный бэкап сохранен: <code>{backup_path}</code>",
                reply_markup=get_backup_keyboard(user.language_code or 'ru')
            )
            
    except Exception as e:
        logger.error(f"Critical error during backup restore: {e}", exc_info=True)
        await status_msg.edit_text(
            f"❌ <b>КРИТИЧЕСКАЯ ОШИБКА ВОССТАНОВЛЕНИЯ!</b>\n\n"
            f"Ошибка: {str(e)}\n\n"
            f"💾 Статус БД неизвестен!\n"
            f"✅ Защитный бэкап: <code>{backup_path}</code>\n\n"
            f"🚨 СРОЧНО проверьте состояние базы данных!",
            reply_markup=get_backup_keyboard(user.language_code or 'ru')
        )

@router.callback_query(F.data == "backup_stats")
@admin_only
@ensure_user
async def backup_stats(callback: CallbackQuery, user: User, **kwargs):
    """Статистика бэкапов"""
    try:
        stats = await backup_service.get_backup_stats()
        
        text = f"""
📊 <b>Статистика бэкапов</b>

📁 <b>Общая информация:</b>
├ Количество бэкапов: {stats['total_count']}
├ Общий размер: {stats['total_size_mb']:.1f} MB
└ Папка: <code>{stats['backup_dir']}</code>

"""
        
        if stats['latest_backup']:
            latest = stats['latest_backup']
            text += f"""🕐 <b>Последний бэкап:</b>
├ Файл: {latest['filename'][:30]}...
├ Размер: {latest['size_mb']:.1f} MB
├ Создан: {latest['created_at'].strftime('%d.%m.%Y %H:%M:%S')}
└ Описание: {latest.get('description', 'Без описания')[:50]}

"""
        
        if stats['oldest_backup']:
            oldest = stats['oldest_backup']
            text += f"""📅 <b>Самый старый:</b>
├ Файл: {oldest['filename'][:30]}...
└ Создан: {oldest['created_at'].strftime('%d.%m.%Y %H:%M:%S')}
"""
        
        await callback.message.edit_text(
            text=text,
            reply_markup=get_backup_keyboard(user.language_code or 'ru')
        )
        
    except Exception as e:
        logger.error(f"Ошибка получения статистики: {e}")
        await callback.message.edit_text(
            text=f"❌ <b>Ошибка получения статистики</b>\n\n{str(e)}",
            reply_markup=get_backup_keyboard(user.language_code or 'ru')
        )

@router.callback_query(F.data == "backup_cleanup")
@admin_only
@ensure_user
async def backup_cleanup(callback: CallbackQuery, user: User, **kwargs):
    """Очистка старых бэкапов"""
    await callback.answer("🧹 Очистка старых бэкапов...")
    
    try:
        deleted_count, message = await backup_service.cleanup_old_backups(days=7)
        
        await callback.message.edit_text(
            text=message,
            reply_markup=get_backup_keyboard(user.language_code or 'ru')
        )
        
        # Логируем очистку
        await BaseHandler.log_admin_action(
            user.id,
            "backup_cleanup",
            {"deleted_count": deleted_count}
        )
        
    except Exception as e:
        logger.error(f"Ошибка очистки бэкапов: {e}")
        await callback.message.edit_text(
            text=f"❌ <b>Ошибка очистки</b>\n\n{str(e)}",
            reply_markup=get_backup_keyboard(user.language_code or 'ru')
        )

@router.message(AdminStates.backup_restore_confirm, F.text.in_(["/cancel", "отмена", "Отмена", "ОТМЕНА"]))
@admin_only
@ensure_user
async def cancel_backup_restore(message: Message, state: FSMContext, user: User):
    """Отмена восстановления бэкапа"""
    await state.clear()
    
    await message.answer(
        "✅ <b>Восстановление отменено</b>\n\nВозвращаю в меню бэкапов.",
        reply_markup=get_backup_keyboard(user.language_code or 'ru')
    )

# ===============================
# УПРАВЛЕНИЕ ЦЕНАМИ
# ===============================

@router.callback_query(F.data == "admin_prices")
@admin_only
@ensure_user
async def show_price_management(callback: CallbackQuery, user: User, **kwargs):
    """Показать меню управления ценами"""
    text = """
💰 <b>Управление ценами пакетов</b>

Здесь вы можете:
• Просматривать текущие цены
• Изменять цены для Stars и ЮКассы
• Просматривать историю изменений
• Настраивать интеграцию с ЮКассой

Выберите действие:
"""
    
    from bot.keyboard.inline import get_price_management_keyboard
    
    await callback.message.edit_text(
        text,
        reply_markup=get_price_management_keyboard(user.language_code or 'ru')
    )
    await callback.answer()

@router.callback_query(F.data == "price_view")
@admin_only
async def show_current_prices(callback: CallbackQuery, **kwargs):
    """Показать текущие цены"""
    try:
        from services.price_service import price_service
        from core.constants import CREDIT_PACKAGES
        
        # Получаем все цены из БД
        prices = await price_service.get_package_prices()
        
        text = "💰 <b>Текущие цены пакетов</b>\n\n"
        
        for package in CREDIT_PACKAGES:
            package_data = prices.get(package.id, {})
            
            # Цена в Stars
            stars_price = package_data.get("stars_price", package.stars)
            stars_status = "💡 кастомная" if package_data.get("id") else "📋 дефолтная"
            
            # Цена в рублях
            rub_price = package_data.get("rub_price")
            rub_text = f"{rub_price:.2f} ₽" if rub_price else "не установлена"
            
            text += f"{package.emoji} <b>{package.name}</b>\n"
            text += f"   🎬 {package.credits} кредитов\n"
            text += f"   ⭐ {stars_price} Stars ({stars_status})\n"
            text += f"   💳 {rub_text}\n\n"
        
        # Статус ЮКассы
        from services.yookassa_service import yookassa_service
        yookassa_status = "✅ настроена" if yookassa_service.is_available() else "❌ не настроена"
        text += f"🏪 <b>ЮКасса:</b> {yookassa_status}\n"
        
        from bot.keyboard.inline import get_price_management_keyboard
        user, _ = await BaseHandler.get_user_and_translator(callback)
        
        await callback.message.edit_text(
            text,
            reply_markup=get_price_management_keyboard(user.language_code or 'ru')
        )
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error showing prices: {e}")
        await callback.answer("❌ Ошибка загрузки цен", show_alert=True)

@router.callback_query(F.data == "price_edit")
@admin_only
@ensure_user
async def show_package_selection(callback: CallbackQuery, user: User, **kwargs):
    """Показать выбор пакета для редактирования"""
    text = """
✏️ <b>Редактирование цен</b>

Выберите пакет для изменения цен:
"""
    
    from bot.keyboard.inline import get_package_edit_keyboard
    
    await callback.message.edit_text(
        text,
        reply_markup=get_package_edit_keyboard(user.language_code or 'ru')
    )
    await callback.answer()

@router.callback_query(F.data.startswith("price_edit_"))
@admin_only
async def show_package_edit_options(callback: CallbackQuery, **kwargs):
    """Показать опции редактирования пакета"""
    package_id = callback.data.split("_", 2)[2]
    
    try:
        from services.price_service import price_service
        from core.constants import CREDIT_PACKAGES
        
        # Находим пакет
        package = next((p for p in CREDIT_PACKAGES if p.id == package_id), None)
        if not package:
            await callback.answer("❌ Пакет не найден", show_alert=True)
            return
        
        # Получаем текущие цены
        prices = await price_service.get_package_prices(package_id)
        price_data = prices.get(package_id, {})
        
        # Цены
        stars_price = price_data.get("stars_price", package.stars)
        rub_price = price_data.get("rub_price")
        notes = price_data.get("notes", "")
        is_custom = price_data.get("id") is not None
        
        text = f"""
✏️ <b>Редактирование пакета</b>

{package.emoji} <b>{package.name}</b>
🎬 {package.credits} кредитов

<b>Текущие цены:</b>
⭐ Stars: {stars_price} {"(кастомная)" if is_custom else "(дефолтная)"}
💳 Рубли: {f"{rub_price:.2f} ₽" if rub_price else "не установлена"}

<b>Заметки:</b> {notes or "отсутствуют"}

Выберите что изменить:
"""
        
        from bot.keyboard.inline import get_price_edit_options_keyboard
        user, _ = await BaseHandler.get_user_and_translator(callback)
        
        await callback.message.edit_text(
            text,
            reply_markup=get_price_edit_options_keyboard(package_id, user.language_code or 'ru')
        )
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error showing package edit options: {e}")
        await callback.answer("❌ Ошибка загрузки данных", show_alert=True)

@router.callback_query(F.data.startswith("price_stars_"))
@admin_only
async def start_edit_stars_price(callback: CallbackQuery, state: FSMContext):
    """Начать редактирование цены в Stars"""
    package_id = callback.data.split("_", 2)[2]
    
    from core.constants import CREDIT_PACKAGES
    package = next((p for p in CREDIT_PACKAGES if p.id == package_id), None)
    if not package:
        await callback.answer("❌ Пакет не найден", show_alert=True)
        return
    
    # Сохраняем package_id в состоянии
    await state.update_data(package_id=package_id)
    await state.set_state(AdminStates.price_edit_stars)
    
    text = f"""
⭐ <b>Изменение цены в Telegram Stars</b>

{package.emoji} <b>{package.name}</b> ({package.credits} кредитов)

Введите новую цену в Stars:
(текущая цена: {package.stars} Stars)

Отправьте /cancel для отмены.
"""
    
    await callback.message.edit_text(text)
    await callback.answer()

@router.message(AdminStates.price_edit_stars)
@admin_only
async def process_stars_price_edit(message: Message, state: FSMContext):
    """Обработка изменения цены в Stars"""
    try:
        # Получаем цену
        stars_price = int(message.text.strip())
        
        if stars_price <= 0:
            await message.answer("❌ Цена должна быть положительным числом")
            return
        
        if stars_price > 10000:
            await message.answer("❌ Слишком большая цена (максимум 10000 Stars)")
            return
        
        # Получаем данные из состояния
        data = await state.get_data()
        package_id = data.get("package_id")
        
        # Обновляем цену
        from services.price_service import price_service
        success, message_text = await price_service.update_package_price(
            package_id=package_id,
            stars_price=stars_price,
            admin_id=message.from_user.id
        )
        
        if success:
            await message.answer(f"✅ {message_text}")
            # Возвращаем к опциям редактирования
            from bot.keyboard.inline import get_price_edit_options_keyboard
            user, _ = await BaseHandler.get_user_and_translator(message)
            
            await message.answer(
                "Цена обновлена. Выберите следующее действие:",
                reply_markup=get_price_edit_options_keyboard(package_id, user.language_code or 'ru')
            )
        else:
            await message.answer(f"❌ Ошибка: {message_text}")
        
        await state.clear()
        
    except ValueError:
        await message.answer("❌ Введите корректное число")
    except Exception as e:
        logger.error(f"Error processing stars price edit: {e}")
        await message.answer("❌ Ошибка обработки")
        await state.clear()

@router.callback_query(F.data.startswith("price_rub_"))
@admin_only
async def start_edit_rub_price(callback: CallbackQuery, state: FSMContext):
    """Начать редактирование цены в рублях"""
    package_id = callback.data.split("_", 2)[2]
    
    from core.constants import CREDIT_PACKAGES
    package = next((p for p in CREDIT_PACKAGES if p.id == package_id), None)
    if not package:
        await callback.answer("❌ Пакет не найден", show_alert=True)
        return
    
    # Сохраняем package_id в состоянии
    await state.update_data(package_id=package_id)
    await state.set_state(AdminStates.price_edit_rub)
    
    text = f"""
💳 <b>Изменение цены в рублях (ЮКасса)</b>

{package.emoji} <b>{package.name}</b> ({package.credits} кредитов)

Введите новую цену в рублях:
Например: 150.50

Отправьте /cancel для отмены.
"""
    
    await callback.message.edit_text(text)
    await callback.answer()

@router.message(AdminStates.price_edit_rub)
@admin_only
async def process_rub_price_edit(message: Message, state: FSMContext):
    """Обработка изменения цены в рублях"""
    try:
        from decimal import Decimal
        
        # Получаем цену
        rub_price = Decimal(message.text.strip().replace(",", "."))
        
        if rub_price <= 0:
            await message.answer("❌ Цена должна быть положительным числом")
            return
        
        if rub_price > 100000:
            await message.answer("❌ Слишком большая цена (максимум 100000 ₽)")
            return
        
        # Получаем данные из состояния
        data = await state.get_data()
        package_id = data.get("package_id")
        
        # Обновляем цену
        from services.price_service import price_service
        success, message_text = await price_service.update_package_price(
            package_id=package_id,
            rub_price=rub_price,
            admin_id=message.from_user.id
        )
        
        if success:
            await message.answer(f"✅ {message_text}")
            # Возвращаем к опциям редактирования
            from bot.keyboard.inline import get_price_edit_options_keyboard
            user, _ = await BaseHandler.get_user_and_translator(message)
            
            await message.answer(
                "Цена обновлена. Выберите следующее действие:",
                reply_markup=get_price_edit_options_keyboard(package_id, user.language_code or 'ru')
            )
        else:
            await message.answer(f"❌ Ошибка: {message_text}")
        
        await state.clear()
        
    except (ValueError, Exception) as e:
        if isinstance(e, ValueError):
            await message.answer("❌ Введите корректную цену в формате 150.50")
        else:
            logger.error(f"Error processing rub price edit: {e}")
            await message.answer("❌ Ошибка обработки")
        await state.clear()

@router.callback_query(F.data.startswith("price_delete_"))
@admin_only
async def delete_custom_price(callback: CallbackQuery, **kwargs):
    """Удалить кастомную цену пакета"""
    package_id = callback.data.split("_", 2)[2]
    
    try:
        from services.price_service import price_service
        
        success, message_text = await price_service.delete_package_price(
            package_id=package_id,
            admin_id=callback.from_user.id
        )
        
        if success:
            await callback.answer(f"✅ {message_text}", show_alert=True)
            # Обновляем опции редактирования
            from bot.keyboard.inline import get_price_edit_options_keyboard
            user, _ = await BaseHandler.get_user_and_translator(callback)
            
            # Получаем обновленные данные пакета
            from core.constants import CREDIT_PACKAGES
            package = next((p for p in CREDIT_PACKAGES if p.id == package_id), None)
            
            text = f"""
✏️ <b>Редактирование пакета</b>

{package.emoji} <b>{package.name}</b>
🎬 {package.credits} кредитов

<b>Текущие цены:</b>
⭐ Stars: {package.stars} (дефолтная)
💳 Рубли: не установлена

<b>Заметки:</b> отсутствуют

Выберите что изменить:
"""
            
            await callback.message.edit_text(
                text,
                reply_markup=get_price_edit_options_keyboard(package_id, user.language_code or 'ru')
            )
        else:
            await callback.answer(f"❌ {message_text}", show_alert=True)
        
    except Exception as e:
        logger.error(f"Error deleting custom price: {e}")
        await callback.answer("❌ Ошибка удаления", show_alert=True)

@router.callback_query(F.data == "price_yookassa")
@admin_only
@ensure_user
async def show_yookassa_settings(callback: CallbackQuery, user: User, **kwargs):
    """Показать настройки ЮКассы"""
    try:
        from services.yookassa_service import yookassa_service
        from core.config import settings
        
        # Проверяем статус ЮКассы
        is_configured = yookassa_service.is_available()
        
        shop_id_status = "✅ настроен" if settings.YOOKASSA_SHOP_ID else "❌ не настроен"
        secret_status = "✅ настроен" if settings.YOOKASSA_SECRET_KEY else "❌ не настроен"
        enabled_status = "✅ включена" if settings.ENABLE_YOOKASSA else "❌ отключена"
        
        text = f"""
💳 <b>Настройки ЮКассы</b>

<b>Статус интеграции:</b> {"✅ работает" if is_configured else "❌ не работает"}

<b>Конфигурация:</b>
• Shop ID: {shop_id_status}
• Secret Key: {secret_status}  
• Включена: {enabled_status}

<b>Настройка:</b>
Для работы ЮКассы добавьте в .env.client:

<code>YOOKASSA_SHOP_ID=ваш_shop_id
YOOKASSA_SECRET_KEY=ваш_secret_key
ENABLE_YOOKASSA=true</code>

<b>Webhook URL:</b>
{settings.YOOKASSA_WEBHOOK_ENDPOINT or "не настроен"}

Настройте этот URL в личном кабинете ЮКассы для получения уведомлений о платежах.
"""
        
        from bot.keyboard.inline import get_price_management_keyboard
        
        await callback.message.edit_text(
            text,
            reply_markup=get_price_management_keyboard(user.language_code or 'ru')
        )
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error showing YooKassa settings: {e}")
        await callback.answer("❌ Ошибка загрузки настроек", show_alert=True)

@router.callback_query(F.data == "price_history")
@admin_only
@ensure_user
async def show_price_history(callback: CallbackQuery, user: User, **kwargs):
    """Показать историю изменения цен"""
    try:
        from services.price_service import price_service
        
        history = await price_service.get_price_history()
        
        if not history:
            text = "📈 <b>История изменения цен</b>\n\nИстория пуста. Цены еще не изменялись."
        else:
            text = "📈 <b>История изменения цен</b>\n\n"
            
            for record in history[:10]:  # Показываем последние 10 записей
                status = "✅ активна" if record["is_active"] else "❌ удалена"
                stars_price = record.get("stars_price", "—")
                rub_price = f"{record['rub_price']:.2f} ₽" if record.get("rub_price") else "—"
                date = record["updated_at"].strftime("%d.%m.%Y %H:%M") if record.get("updated_at") else "—"
                
                text += f"📦 <b>{record['package_id']}</b> ({status})\n"
                text += f"   ⭐ {stars_price} Stars | 💳 {rub_price}\n"
                text += f"   📅 {date}\n"
                if record.get("notes"):
                    text += f"   📝 {record['notes'][:50]}{'...' if len(record['notes']) > 50 else ''}\n"
                text += "\n"
        
        from bot.keyboard.inline import get_price_management_keyboard
        
        await callback.message.edit_text(
            text,
            reply_markup=get_price_management_keyboard(user.language_code or 'ru')
        )
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error showing price history: {e}")
        await callback.answer("❌ Ошибка загрузки истории", show_alert=True)

@router.callback_query(F.data == "price_history")
@admin_only
@ensure_user
async def show_price_history(callback: CallbackQuery, user: User, **kwargs):
    """Показать историю изменения цен"""
    try:
        from services.price_service import price_service
        
        history = await price_service.get_price_history()
        
        if not history:
            text = "📈 <b>История изменения цен</b>\n\nИстория пуста. Цены еще не изменялись."
        else:
            text = "📈 <b>История изменения цен</b>\n\n"
            
            for record in history[:10]:  # Показываем последние 10 записей
                status = "✅ активна" if record["is_active"] else "❌ удалена"
                stars_price = record.get("stars_price", "—")
                rub_price = f"{record['rub_price']:.2f} ₽" if record.get("rub_price") else "—"
                date = record["updated_at"].strftime("%d.%m.%Y %H:%M") if record.get("updated_at") else "—"
                
                text += f"📦 <b>{record['package_id']}</b> ({status})\n"
                text += f"   ⭐ {stars_price} Stars | 💳 {rub_price}\n"
                text += f"   📅 {date}\n"
                if record.get("notes"):
                    text += f"   📝 {record['notes'][:50]}{'...' if len(record['notes']) > 50 else ''}\n"
                text += "\n"
        
        from bot.keyboard.inline import get_price_management_keyboard
        
        await callback.message.edit_text(
            text,
            reply_markup=get_price_management_keyboard(user.language_code or 'ru')
        )
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error showing price history: {e}")
        await callback.answer("❌ Ошибка загрузки истории", show_alert=True)

@router.callback_query(F.data == "price_reset")
@admin_only
@ensure_user
async def reset_all_prices_confirm(callback: CallbackQuery, user: User, **kwargs):
    """Подтверждение сброса всех цен"""
    try:
        text = """
⚠️ <b>Сброс всех цен</b>

Вы действительно хотите сбросить все кастомные цены к дефолтным значениям?

Это действие:
• Удалит все измененные цены в Stars
• Удалит все установленные цены в рублях
• Вернет цены из constants.py

<b>Это действие нельзя отменить!</b>
"""
        
        builder = InlineKeyboardBuilder()
        builder.button(text="✅ Да, сбросить все цены", callback_data="price_reset_execute")
        builder.button(text="❌ Отмена", callback_data="admin_prices")
        builder.adjust(1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error in reset_all_prices_confirm: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)

@router.callback_query(F.data == "price_reset_execute")
@admin_only
async def reset_all_prices_execute(callback: CallbackQuery, **kwargs):
    """Выполнить сброс всех цен"""
    try:
        await callback.answer("🔄 Сбрасываю все цены...")
        
        from services.price_service import price_service
        
        success, message = await price_service.reset_all_prices(admin_id=callback.from_user.id)
        
        if success:
            # Логируем действие
            await BaseHandler.log_admin_action(
                callback.from_user.id,
                "price_reset_all",
                {"message": message}
            )
            
            text = f"""
✅ <b>Цены успешно сброшены</b>

{message}

Все пакеты теперь используют дефолтные цены из constants.py
"""
        else:
            text = f"❌ <b>Ошибка сброса цен</b>\n\n{message}"
        
        from bot.keyboard.inline import get_price_management_keyboard
        user, _ = await BaseHandler.get_user_and_translator(callback)
        
        await callback.message.edit_text(
            text,
            reply_markup=get_price_management_keyboard(user.language_code or 'ru')
        )
        
    except Exception as e:
        logger.error(f"Error executing price reset: {e}")
        await callback.answer("❌ Критическая ошибка при сбросе цен", show_alert=True)

@router.callback_query(F.data == "admin_panel")
@admin_only
@ensure_user
async def back_to_admin_panel(callback: CallbackQuery, user: User, **kwargs):
    """Возврат в админ панель"""
    await callback.message.edit_text(
        f"👑 \u003cb\u003eПанель администратора\u003c/b\u003e\n\nВыберите действие:",
        reply_markup=get_admin_keyboard(user.language_code or 'ru')
    )
    await BaseHandler.answer_callback(callback)

# Управление пользователями
@router.callback_query(F.data == "admin_users")
@admin_only
async def admin_users_menu(callback: CallbackQuery, **kwargs):
    """Меню управления пользователями"""
    try:
        await callback.answer()
        
        # Получаем пользователя для локализации
        user = await db.get_user(callback.from_user.id)
        _ = lambda key, **kwargs: i18n.get(key, user.language_code or 'ru', **kwargs)
        
        async with db.async_session() as session:
            # Получаем статистику пользователей
            total_users_result = await session.execute(select(func.count(User.id)))
            total_users = total_users_result.scalar()
            
            active_users_result = await session.execute(
                select(func.count(User.id)).where(User.last_active >= datetime.now() - timedelta(days=30))
            )
            active_users = active_users_result.scalar()
            
            banned_users_result = await session.execute(
                select(func.count(User.id)).where(User.is_banned == True)
            )
            banned_users = banned_users_result.scalar()
            
            admin_users_result = await session.execute(
                select(func.count(User.id)).where(User.is_admin == True)
            )
            admin_users = admin_users_result.scalar()
            
            premium_users_result = await session.execute(
                select(func.count(User.id)).where(User.is_premium == True)
            )
            premium_users = premium_users_result.scalar()
        
        text = _(
            "admin.users.menu",
            total=total_users,
            active=active_users,
            banned=banned_users,
            admins=admin_users,
            premium=premium_users,
            default=f"""📊 Статистика пользователей

👥 Всего пользователей: {total_users}
🟢 Активных (30 дней): {active_users}
🚫 Заблокированных: {banned_users}
⭐ Администраторов: {admin_users}
💎 Premium пользователей: {premium_users}

Выберите действие:"""
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔍 Поиск пользователя", callback_data="user_search")
        builder.button(text="📋 Список активных", callback_data="users_list_active")
        builder.button(text="🚫 Заблокированные", callback_data="users_list_banned")
        builder.button(text="⭐ Администраторы", callback_data="users_list_admins")
        builder.button(text="💎 Premium", callback_data="users_list_premium")
        builder.adjust(2, 2, 1, 1)
        builder.button(text="◀️ Назад к админке", callback_data="admin_menu")
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
        
        
    except Exception as e:
        logging.error(f"Ошибка в admin_users_menu: {e}")
        await callback.answer("Произошла ошибка, попробуйте снова", show_alert=True)


@router.callback_query(F.data.startswith("users_list_"))
@admin_only
async def users_list(callback: CallbackQuery, **kwargs):
    """Показать список пользователей по категориям"""
    try:
        await callback.answer()
        
        # Получаем пользователя для локализации
        user = await db.get_user(callback.from_user.id)
        _ = lambda key, **kwargs: i18n.get(key, user.language_code or 'ru', **kwargs)
        
        list_type = callback.data.split("_")[-1]  # active, banned, admins, premium
        page = 1  # TODO: добавить пагинацию
        limit = 10
        
        async with db.async_session() as session:
            # Фильтрация по типу списка
            if list_type == "active":
                query = select(User).where(User.last_active >= datetime.now() - timedelta(days=30))
                count_query = select(func.count(User.id)).where(User.last_active >= datetime.now() - timedelta(days=30))
                title = "🟢 Активные пользователи (30 дней)"
            elif list_type == "banned":
                query = select(User).where(User.is_banned == True)
                count_query = select(func.count(User.id)).where(User.is_banned == True)
                title = "🚫 Заблокированные пользователи"
            elif list_type == "admins":
                query = select(User).where(User.is_admin == True)
                count_query = select(func.count(User.id)).where(User.is_admin == True)
                title = "⭐ Администраторы"
            elif list_type == "premium":
                query = select(User).where(User.is_premium == True)
                count_query = select(func.count(User.id)).where(User.is_premium == True)
                title = "💎 Premium пользователи"
            else:
                query = select(User)
                count_query = select(func.count(User.id))
                title = "👥 Все пользователи"
            
            # Получаем пользователей
            query = query.order_by(User.created_at.desc()).limit(limit)
            result = await session.execute(query)
            users_list = result.scalars().all()
            
            count_result = await session.execute(count_query)
            total = count_result.scalar()
        
        if not users_list:
            text = f"{title}\n\n❌ Пользователей не найдено"
        else:
            text = f"{title}\n\nВсего: {total}\n\n"
            
            for u in users_list:
                username_str = f"@{u.username}" if u.username else "Без username"
                name = u.first_name or "Без имени"
                
                status_icons = []
                if u.is_admin:
                    status_icons.append("⭐")
                if u.is_premium:
                    status_icons.append("💎")
                if u.is_banned:
                    status_icons.append("🚫")
                
                text += f"{''.join(status_icons)} {name} ({username_str})\n"
                text += f"   ID: {u.telegram_id} | Баланс: {u.balance or 0}\n"
                text += f"   Регистрация: {u.created_at.strftime('%d.%m.%Y') if u.created_at else 'Неизвестно'}\n\n"
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔍 Поиск пользователя", callback_data="user_search")
        builder.button(text="◀️ К управлению пользователями", callback_data="admin_users")
        
        await callback.message.edit_text(text[:4096], reply_markup=builder.as_markup())  # Telegram limit
        
    except Exception as e:
        logging.error(f"Ошибка в users_list: {e}")
        await callback.answer("Произошла ошибка, попробуйте снова", show_alert=True)


@router.callback_query(F.data == "user_search")
@admin_only
async def user_search_start(callback: CallbackQuery, state: FSMContext, **kwargs):
    """Начать поиск пользователя"""
    try:
        await callback.answer()
        
        # Получаем пользователя для локализации
        user = await db.get_user(callback.from_user.id)
        _ = lambda key, **kwargs: i18n.get(key, user.language_code or 'ru', **kwargs)
        
        text = "🔍 Поиск пользователя\n\nВведите один из параметров для поиска:\n• Telegram ID\n• Username (без @)\n• Имя пользователя\n\nОтправьте сообщение с параметром поиска:"
        
        builder = InlineKeyboardBuilder()
        builder.button(text="◀️ К управлению пользователями", callback_data="admin_users")
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
        
        
        # TODO: добавить FSM для управления состояниями
        
    except Exception as e:
        logging.error(f"Ошибка в user_search_start: {e}")
        await callback.answer("Произошла ошибка, попробуйте снова", show_alert=True)


# Управление банами
@router.callback_query(F.data == "admin_bans")
@admin_only
async def admin_bans_menu(callback: CallbackQuery, **kwargs):
    """Меню управления банами"""
    try:
        await callback.answer()
        
        # Получаем пользователя для локализации
        user = await db.get_user(callback.from_user.id)
        _ = lambda key, **kwargs: i18n.get(key, user.language_code or 'ru', **kwargs)
        
        async with db.async_session() as session:
            # Получаем статистику банов
            total_banned_result = await session.execute(
                select(func.count(User.id)).where(User.is_banned == True)
            )
            total_banned = total_banned_result.scalar()
            
            # Последние заблокированные пользователи
            recent_bans_result = await session.execute(
                select(User).where(User.is_banned == True)
                .order_by(User.banned_at.desc())
                .limit(5)
            )
            recent_bans = recent_bans_result.scalars().all()
        
        text = f"""🚫 Управление банами

📊 Статистика:
• Заблокированных пользователей: {total_banned}

"""
        
        if recent_bans:
            text += "🕐 Последние заблокированные:\n"
            for banned_user in recent_bans:
                username = f"@{banned_user.username}" if banned_user.username else "Без username"
                name = banned_user.first_name or "Без имени"
                ban_date = banned_user.banned_at.strftime('%d.%m.%Y') if banned_user.banned_at else "Неизвестно"
                text += f"• {name} ({username}) - {ban_date}\n"
        
        text += "\nВыберите действие:"
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔍 Поиск пользователя", callback_data="ban_search_user")
        builder.button(text="📋 Список заблокированных", callback_data="ban_list_banned")
        builder.button(text="🔓 Массовая разблокировка", callback_data="ban_mass_unban")
        builder.adjust(2, 2, 1, 1)
        builder.button(text="◀️ Назад к админке", callback_data="admin_menu")
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
        
        
    except Exception as e:
        logging.error(f"Ошибка в admin_bans_menu: {e}")
        await callback.answer("Произошла ошибка, попробуйте снова", show_alert=True)


@router.callback_query(F.data == "ban_list_banned")
@admin_only
async def ban_list_banned_users(callback: CallbackQuery, **kwargs):
    """Показать список заблокированных пользователей"""
    try:
        await callback.answer()
        
        # Получаем пользователя для локализации
        user = await db.get_user(callback.from_user.id)
        _ = lambda key, **kwargs: i18n.get(key, user.language_code or 'ru', **kwargs)
        
        banned_users = await db.get_all_users(limit=20, only_banned=True)
        
        if not banned_users:
            text = "🚫 Заблокированные пользователи\n\n✅ Нет заблокированных пользователей"
        else:
            text = f"🚫 Заблокированные пользователи ({len(banned_users)}):\n\n"
            
            for banned_user in banned_users:
                username = f"@{banned_user.username}" if banned_user.username else "Без username"
                name = banned_user.first_name or "Без имени"
                ban_date = banned_user.banned_at.strftime('%d.%m.%Y %H:%M') if banned_user.banned_at else "Неизвестно"
                reason = banned_user.ban_reason or "Причина не указана"
                
                text += f"👤 {name} ({username})\n"
                text += f"   ID: {banned_user.telegram_id}\n"
                text += f"   Заблокирован: {ban_date}\n"
                text += f"   Причина: {reason}\n"
                text += f"   /unban_{banned_user.id}\n\n"
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔍 Поиск пользователя", callback_data="ban_search_user")
        builder.button(text="◀️ К управлению банами", callback_data="admin_bans")
        
        await callback.message.edit_text(text[:4096], reply_markup=builder.as_markup())
        
    except Exception as e:
        logging.error(f"Ошибка в ban_list_banned_users: {e}")
        await callback.answer("Произошла ошибка, попробуйте снова", show_alert=True)


@router.callback_query(F.data == "ban_search_user")
@admin_only
async def ban_search_user_start(callback: CallbackQuery, state: FSMContext, **kwargs):
    """Начать поиск пользователя для бана/разбана"""
    try:
        await callback.answer()
        
        text = """🔍 Поиск пользователя для бана/разбана

Введите один из параметров:
• Telegram ID
• Username (без @)
• Имя пользователя

Отправьте сообщение с параметром поиска:"""
        
        builder = InlineKeyboardBuilder()
        builder.button(text="◀️ К управлению банами", callback_data="admin_bans")
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
        
        
    except Exception as e:
        logging.error(f"Ошибка в ban_search_user_start: {e}")
        await callback.answer("Произошла ошибка, попробуйте снова", show_alert=True)


@router.callback_query(F.data == "ban_mass_unban")
@admin_only
async def ban_mass_unban_confirm(callback: CallbackQuery, **kwargs):
    """Подтверждение массовой разблокировки"""
    try:
        await callback.answer()
        
        async with db.async_session() as session:
            banned_count_result = await session.execute(
                select(func.count(User.id)).where(User.is_banned == True)
            )
            banned_count = banned_count_result.scalar()
        
        if banned_count == 0:
            await callback.answer("Нет заблокированных пользователей", show_alert=True)
            return
        
        text = f"""⚠️ Массовая разблокировка

Вы действительно хотите разблокировать всех пользователей?

Количество заблокированных: {banned_count}

Это действие нельзя отменить!"""
        
        builder = InlineKeyboardBuilder()
        builder.button(text="✅ Да, разблокировать всех", callback_data="ban_mass_unban_execute")
        builder.button(text="❌ Отмена", callback_data="admin_bans")
        builder.adjust(1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
        
        
    except Exception as e:
        logging.error(f"Ошибка в ban_mass_unban_confirm: {e}")
        await callback.answer("Произошла ошибка, попробуйте снова", show_alert=True)


@router.callback_query(F.data == "ban_mass_unban_execute")
@admin_only
async def ban_mass_unban_execute(callback: CallbackQuery, **kwargs):
    """Выполнить массовую разблокировку"""
    try:
        await callback.answer()
        await callback.message.edit_text("🔄 Выполняется массовая разблокировка...")
        
        # Получаем всех заблокированных пользователей
        banned_users = await db.get_all_users(limit=10000, only_banned=True)
        unban_count = 0
        
        for banned_user in banned_users:
            try:
                if await db.unban_user(banned_user.id):
                    unban_count += 1
            except Exception as e:
                logging.error(f"Ошибка разблокировки пользователя {banned_user.id}: {e}")
        
        text = f"""✅ Массовая разблокировка завершена

Разблокировано пользователей: {unban_count}
Всего было заблокированных: {len(banned_users)}"""
        
        builder = InlineKeyboardBuilder()
        builder.button(text="◀️ К управлению банами", callback_data="admin_bans")
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
        
        
        # Логируем действие администратора
        await db.log_admin_action(
            admin_id=callback.from_user.id,
            action="mass_unban",
            details=f"Unban count: {unban_count}"
        )
        
    except Exception as e:
        logging.error(f"Ошибка в ban_mass_unban_execute: {e}")
        await callback.answer("Произошла ошибка, попробуйте снова", show_alert=True)


# Обработчик команд разбана
@router.message(F.text.startswith("/unban_"))
@admin_only
async def handle_unban_command(message: Message, **kwargs):
    """Обработка команды разбана пользователя"""
    try:
        # Извлекаем ID пользователя из команды
        command_parts = message.text.split("_")
        if len(command_parts) != 2:
            await message.answer("❌ Неверный формат команды")
            return
        
        try:
            user_id = int(command_parts[1])
        except ValueError:
            await message.answer("❌ Неверный ID пользователя")
            return
        
        # Получаем информацию о пользователе
        async with db.async_session() as session:
            user_result = await session.execute(
                select(User).where(User.id == user_id)
            )
            target_user = user_result.scalars().first()
        
        if not target_user:
            await message.answer("❌ Пользователь не найден")
            return
        
        if not target_user.is_banned:
            await message.answer("❌ Пользователь не заблокирован")
            return
        
        # Разблокируем пользователя
        if await db.unban_user(user_id):
            username = f"@{target_user.username}" if target_user.username else "Без username"
            name = target_user.first_name or "Без имени"
            
            await message.answer(
                f"✅ Пользователь разблокирован\n\n"
                f"👤 {name} ({username})\n"
                f"ID: {target_user.telegram_id}"
            )
            
            # Логируем действие
            await db.log_admin_action(
                admin_id=message.from_user.id,
                action="unban_user",
                target_user_id=target_user.telegram_id,
                details=f"User ID: {user_id}, Telegram ID: {target_user.telegram_id}"
            )
        else:
            await message.answer("❌ Ошибка при разблокировке пользователя")
    
    except Exception as e:
        logging.error(f"Ошибка в handle_unban_command: {e}")
        await message.answer("❌ Произошла ошибка при разблокировке")


# Обработчики состояний поиска пользователей
@router.message(AdminStates.user_search)
@admin_only
async def handle_user_search_input(message: Message, state: FSMContext, **kwargs):
    """Обработка ввода для поиска пользователя"""
    try:
        search_query = message.text.strip()
        
        # Поиск пользователя
        found_users = await db.search_users(search_query, limit=10)
        
        if not found_users:
            await message.answer(
                "❌ Пользователи не найдены\n\n"
                "Попробуйте другой запрос или проверьте правильность ввода.",
                reply_markup=InlineKeyboardBuilder()
                .button(text="🔍 Новый поиск", callback_data="user_search")
                .button(text="◀️ К управлению пользователями", callback_data="admin_users")
                .adjust(1)
                .as_markup()
            )
            await state.clear()
            return
        
        # Показываем найденных пользователей
        text = f"🔍 Результаты поиска по запросу: {search_query}\n\nНайдено пользователей: {len(found_users)}\n\n"
        
        builder = InlineKeyboardBuilder()
        
        for user in found_users:
            username = f"@{user.username}" if user.username else "Без username"
            name = user.first_name or "Без имени"
            
            status_icons = []
            if user.is_admin:
                status_icons.append("⭐")
            if user.is_premium:
                status_icons.append("💎")
            if user.is_banned:
                status_icons.append("🚫")
            
            status_str = "".join(status_icons)
            
            text += f"{status_str} {name} ({username})\n"
            text += f"   ID: {user.telegram_id} | Баланс: {user.balance or 0}\n"
            text += f"   Регистрация: {user.created_at.strftime('%d.%m.%Y') if user.created_at else 'Неизвестно'}\n"
            
            # Кнопки действий для каждого пользователя
            builder.button(
                text=f"👤 {name[:15]}..." if len(name) > 15 else f"👤 {name}",
                callback_data=f"user_details_{user.id}"
            )
        
        builder.button(text="🔍 Новый поиск", callback_data="user_search")
        builder.button(text="◀️ К управлению пользователями", callback_data="admin_users")
        builder.adjust(2, 2, 1)
        
        await message.answer(text[:4096], reply_markup=builder.as_markup())
        await state.clear()
        
    except Exception as e:
        logging.error(f"Ошибка в handle_user_search_input: {e}")
        await message.answer("❌ Произошла ошибка при поиске")
        await state.clear()


@router.message(AdminStates.ban_search)
@admin_only
async def handle_ban_search_input(message: Message, state: FSMContext, **kwargs):
    """Обработка ввода для поиска пользователя для бана"""
    try:
        search_query = message.text.strip()
        
        # Поиск пользователя
        found_users = await db.search_users(search_query, limit=5)
        
        if not found_users:
            await message.answer(
                "❌ Пользователи не найдены\n\n"
                "Попробуйте другой запрос или проверьте правильность ввода.",
                reply_markup=InlineKeyboardBuilder()
                .button(text="🔍 Новый поиск", callback_data="ban_search_user")
                .button(text="◀️ К управлению банами", callback_data="admin_bans")
                .adjust(1)
                .as_markup()
            )
            await state.clear()
            return
        
        # Показываем найденных пользователей с кнопками бана/разбана
        text = f"🔍 Результаты поиска для бан/разбан: {search_query}\n\nНайдено: {len(found_users)}\n\n"
        
        builder = InlineKeyboardBuilder()
        
        for user in found_users:
            username = f"@{user.username}" if user.username else "Без username"
            name = user.first_name or "Без имени"
            
            ban_status = "🚫 ЗАБЛОКИРОВАН" if user.is_banned else "✅ Активен"
            
            text += f"👤 {name} ({username})\n"
            text += f"   ID: {user.telegram_id} | Статус: {ban_status}\n"
            text += f"   Регистрация: {user.created_at.strftime('%d.%m.%Y') if user.created_at else 'Неизвестно'}\n\n"
            
            # Кнопки бана/разбана
            if user.is_banned:
                builder.button(
                    text=f"✅ Разбанить {name[:10]}...",
                    callback_data=f"unban_user_{user.id}"
                )
            else:
                builder.button(
                    text=f"🚫 Забанить {name[:10]}...",
                    callback_data=f"ban_user_{user.id}"
                )
        
        builder.button(text="🔍 Новый поиск", callback_data="ban_search_user")
        builder.button(text="◀️ К управлению банами", callback_data="admin_bans")
        builder.adjust(1, 1, 2)
        
        await message.answer(text[:4096], reply_markup=builder.as_markup())
        await state.clear()
        
    except Exception as e:
        logging.error(f"Ошибка в handle_ban_search_input: {e}")
        await message.answer("❌ Произошла ошибка при поиске")
        await state.clear()


# Обработчики действий с пользователями
@router.callback_query(F.data.startswith("user_details_"))
@admin_only
async def show_user_details(callback: CallbackQuery, **kwargs):
    """Показать детальную информацию о пользователе"""
    try:
        await callback.answer()
        
        user_id = int(callback.data.split("_")[2])
        
        async with db.async_session() as session:
            user_result = await session.execute(
                select(User).where(User.id == user_id)
            )
            user = user_result.scalars().first()
        
        if not user:
            await callback.answer("❌ Пользователь не найден", show_alert=True)
            return
        
        username = f"@{user.username}" if user.username else "Без username"
        name = user.first_name or "Без имени"
        last_name = f" {user.last_name}" if user.last_name else ""
        
        # Статус пользователя
        status_parts = []
        if user.is_admin:
            status_parts.append("⭐ Администратор")
        if user.is_premium:
            status_parts.append("💎 Premium")
        if user.is_banned:
            status_parts.append("🚫 Заблокирован")
        
        status = ", ".join(status_parts) if status_parts else "👤 Обычный пользователь"
        
        text = f"""👤 Информация о пользователе

📝 Имя: {name}{last_name}
🆔 Username: {username}
🔢 Telegram ID: {user.telegram_id}
🔢 Внутренний ID: {user.id}

📊 Статус: {status}
💰 Баланс: {user.balance or 0}
💸 Потрачено: {user.total_spent or 0}
💳 Куплено: {user.total_bought or 0}
🎁 Бонусов: {user.total_bonuses or 0}

📅 Регистрация: {user.created_at.strftime('%d.%m.%Y %H:%M') if user.created_at else 'Неизвестно'}
🕐 Последняя активность: {user.last_active.strftime('%d.%m.%Y %H:%M') if user.last_active else 'Неизвестно'}
"""
        
        if user.is_banned and user.ban_reason:
            text += f"\n🚫 Причина бана: {user.ban_reason}"
        if user.is_banned and user.banned_at:
            text += f"\n📅 Дата бана: {user.banned_at.strftime('%d.%m.%Y %H:%M')}"
        
        builder = InlineKeyboardBuilder()
        
        # Кнопки действий
        if user.is_banned:
            builder.button(text="✅ Разбанить", callback_data=f"unban_user_{user.id}")
        else:
            builder.button(text="🚫 Забанить", callback_data=f"ban_user_{user.id}")
        
        builder.button(text="💰 Изменить баланс", callback_data=f"edit_balance_{user.id}")
        builder.button(text="◀️ К управлению пользователями", callback_data="admin_users")
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
        
    except Exception as e:
        logging.error(f"Ошибка в show_user_details: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@router.callback_query(F.data.startswith("ban_user_"))
@admin_only
async def ban_user_action(callback: CallbackQuery, **kwargs):
    """Забанить пользователя"""
    try:
        await callback.answer()
        
        user_id = int(callback.data.split("_")[2])
        
        if await db.ban_user_by_id(user_id, reason="Заблокирован администратором"):
            await callback.answer("✅ Пользователь заблокирован", show_alert=True)
            
            # Логируем действие
            await db.log_admin_action(
                admin_id=callback.from_user.id,
                action="ban_user",
                details=f"Banned user ID: {user_id}"
            )
        else:
            await callback.answer("❌ Ошибка при блокировке", show_alert=True)
        
        # Обновляем информацию
        await show_user_details(callback)
        
    except Exception as e:
        logging.error(f"Ошибка в ban_user_action: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@router.callback_query(F.data.startswith("unban_user_"))
@admin_only
async def unban_user_action(callback: CallbackQuery, **kwargs):
    """Разбанить пользователя"""
    try:
        await callback.answer()
        
        user_id = int(callback.data.split("_")[2])
        
        if await db.unban_user(user_id):
            await callback.answer("✅ Пользователь разблокирован", show_alert=True)
            
            # Логируем действие
            await db.log_admin_action(
                admin_id=callback.from_user.id,
                action="unban_user",
                details=f"Unbanned user ID: {user_id}"
            )
        else:
            await callback.answer("❌ Ошибка при разблокировке", show_alert=True)
        
        # Обновляем информацию
        await show_user_details(callback)
        
    except Exception as e:
        logging.error(f"Ошибка в unban_user_action: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Union
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
from core.config import settings
from models.models import User, AdminLog, Generation, Transaction, SupportTicket
from core.constants import GenerationStatus

logger = logging.getLogger(__name__)

class AdminStates(StatesGroup):
    broadcast_message = State()
    give_credits_user = State()
    give_credits_amount = State()
    user_search = State()
    backup_description = State()
    backup_restore_confirm = State()

router = Router(name="admin")

# Декоратор для проверки админских прав
def admin_only(func):
    """Декоратор для ограничения доступа только админам"""
    async def wrapper(update: Union[Message, CallbackQuery], *args, **kwargs):
        if update.from_user.id not in settings.ADMIN_IDS:
            if isinstance(update, CallbackQuery):
                await update.answer("❌ Доступ запрещен", show_alert=True)
            else:
                await update.answer("❌ У вас нет прав администратора")
            return
        return await func(update, *args, **kwargs)
    return wrapper

@router.message(F.text == "/admin")
@admin_only
async def admin_panel(message: Message):
    """Админ панель"""
    user, _ = await BaseHandler.get_user_and_translator(message)
    if not user:
        return
    
    await message.answer(
        f"👑 <b>Панель администратора</b>\n\nВыберите действие:",
        reply_markup=get_admin_keyboard(user.language_code or 'ru')
    )

@router.callback_query(F.data == "admin_stats")
@admin_only
async def show_admin_stats(callback: CallbackQuery):
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

@router.callback_query(F.data == "admin_menu")
@admin_only
async def show_admin_menu(callback: CallbackQuery):
    """Показать админ меню"""
    user, _ = await BaseHandler.get_user_and_translator(callback)
    if not user:
        return
    
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
    
    users_count = await db.get_users_count()
    
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
async def check_api_balance(callback: CallbackQuery):
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
async def find_user_by_input(user_input: str) -> Optional[User]:
    """Найти пользователя по ID или username"""
    if user_input.isdigit():
        return await db.get_user_by_telegram_id(int(user_input))
    elif user_input.startswith('@'):
        return await db.get_user_by_username(user_input[1:])
    return None

async def broadcast_to_users(bot, admin_id: int, message_id: int) -> int:
    """Выполнить рассылку сообщения"""
    users = await db.get_all_users()
    success_count = 0
    
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
            logger.error(f"Broadcast error for user {user.telegram_id}: {e}")
    
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
async def backup_menu(callback: CallbackQuery):
    """Меню управления бэкапами"""
    user, _ = await BaseHandler.get_user_and_translator(callback)
    if not user:
        return
    
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
async def backup_create(callback: CallbackQuery, state: FSMContext):
    """Создать бэкап"""
    user, _ = await BaseHandler.get_user_and_translator(callback)
    if not user:
        return
    
    await callback.message.edit_text(
        text="📝 <b>Создание бэкапа</b>\n\nВведите описание для бэкапа (или отправьте /skip для пропуска):",
        reply_markup=get_cancel_keyboard(user.language_code or 'ru')
    )
    
    await state.set_state(AdminStates.backup_description)

@router.message(AdminStates.backup_description)
@admin_only
async def backup_create_with_description(message: Message, state: FSMContext):
    """Создать бэкап с описанием"""
    user, _ = await BaseHandler.get_user_and_translator(message)
    if not user:
        return
    
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
                user.user_id,
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
async def backup_list(callback: CallbackQuery):
    """Список бэкапов"""
    user, _ = await BaseHandler.get_user_and_translator(callback)
    if not user:
        return
    
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
async def backup_info(callback: CallbackQuery):
    """Информация о конкретном бэкапе"""
    user, _ = await BaseHandler.get_user_and_translator(callback)
    if not user:
        return
    
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
async def backup_delete(callback: CallbackQuery):
    """Удалить бэкап"""
    user, _ = await BaseHandler.get_user_and_translator(callback)
    if not user:
        return
    
    filename = callback.data.replace("backup_delete_", "")
    
    try:
        success, message = await backup_service.delete_backup(filename)
        
        if success:
            await callback.answer("✅ Бэкап удален")
            
            # Логируем удаление
            await BaseHandler.log_admin_action(
                user.user_id,
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
async def backup_restore_confirm(message: Message, state: FSMContext):
    """Подтверждение восстановления через точный текст"""
    user, _ = await BaseHandler.get_user_and_translator(message)
    if not user:
        return
    
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
                user.user_id,
                "backup_restore",
                {
                    "filename": filename,
                    "admin_id": user.user_id,
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
async def backup_stats(callback: CallbackQuery):
    """Статистика бэкапов"""
    user, _ = await BaseHandler.get_user_and_translator(callback)
    if not user:
        return
    
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
async def backup_cleanup(callback: CallbackQuery):
    """Очистка старых бэкапов"""
    user, _ = await BaseHandler.get_user_and_translator(callback)
    if not user:
        return
    
    await callback.answer("🧹 Очистка старых бэкапов...")
    
    try:
        deleted_count, message = await backup_service.cleanup_old_backups(days=30)
        
        await callback.message.edit_text(
            text=message,
            reply_markup=get_backup_keyboard(user.language_code or 'ru')
        )
        
        # Логируем очистку
        await BaseHandler.log_admin_action(
            user.user_id,
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
async def cancel_backup_restore(message: Message, state: FSMContext):
    """Отмена восстановления бэкапа"""
    await state.clear()
    user, _ = await BaseHandler.get_user_and_translator(message)
    
    await message.answer(
        "✅ <b>Восстановление отменено</b>\n\nВозвращаю в меню бэкапов.",
        reply_markup=get_backup_keyboard(user.language_code or 'ru')
    )

@router.callback_query(F.data == "admin_panel")
@admin_only  
async def back_to_admin_panel(callback: CallbackQuery):
    """Возврат в админ панель"""
    user, _ = await BaseHandler.get_user_and_translator(callback)
    if not user:
        return
    
    await admin_panel(callback.message)
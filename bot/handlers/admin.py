import logging
import asyncio
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import StateFilter, Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, func, delete
import re

from bot.keyboard.inline import get_admin_keyboard, get_cancel_keyboard
from bot.utils.messages import MessageTemplates
from bot.middlewares.i18n import I18n
from services.database import db
from services.api_monitor import api_monitor
from core.config import settings
from models.models import User, AdminLog, Generation, Transaction, PromoCodeUsage, SupportTicket
from core.constants import GenerationStatus

logger = logging.getLogger(__name__)

# Глобальная функция локализации для админки
i18n = I18n()
_ = lambda key, **kwargs: i18n.get(key, lang='ru', **kwargs)

class AdminStates(StatesGroup):
    broadcast_message = State()
    broadcast_confirm = State()
    give_credits_user = State()
    give_credits_amount = State()
    user_search = State()
    banning_user = State()
    unbanning_user = State()

router = Router(name="admin")

# Фильтр для админов с кешированием
_admin_cache = {}
def admin_filter(update: Message | CallbackQuery) -> bool:
    """Проверка прав администратора с кешированием"""
    user_id = update.from_user.id
    
    # Проверяем кеш (обновляется каждые 5 минут)
    cache_key = f"admin_{user_id}"
    cached_result = _admin_cache.get(cache_key)
    if cached_result and cached_result['expires'] > datetime.now():
        return cached_result['is_admin']
    
    # Проверяем права
    is_admin_user = user_id in settings.ADMIN_IDS
    
    # Кешируем результат
    _admin_cache[cache_key] = {
        'is_admin': is_admin_user,
        'expires': datetime.now() + timedelta(minutes=5)
    }
    
    return is_admin_user

async def is_admin(user_id: int) -> bool:
    """Проверка прав администратора"""
    return user_id in settings.ADMIN_IDS

@router.message(F.text == "/admin")
async def admin_panel(message: Message):
    """Админ панель"""
    if not await is_admin(message.from_user.id):
        return
    
    text = f"👑 <b>{_('admin.panel')}</b>\n\n"
    text += _('admin.choose_action')
    
    await message.answer(text, reply_markup=get_admin_keyboard('ru'))

@router.callback_query(F.data == "admin_stats")
async def show_admin_stats(callback: CallbackQuery):
    """Показать статистику бота"""
    if callback.from_user.id not in settings.ADMIN_IDS:
        await callback.answer(_('admin.access_denied'), show_alert=True)
        return
    
    try:
        stats = await db.get_bot_statistics()
        
        text = "📊 <b>Статистика бота</b>\n\n"
        
        text += "👥 <b>Пользователи:</b>\n"
        text += f"├ Всего: {stats['users']['total']}\n"
        text += f"├ Активных сегодня: {stats['users']['active_today']}\n"
        text += f"└ Новых сегодня: {stats['users']['new_today']}\n\n"
        
        text += "🎬 <b>Генерации:</b>\n"
        text += f"├ Всего: {stats['generations']['total']}\n"
        text += f"├ Сегодня: {stats['generations']['today']}\n"
        text += f"└ В обработке: {stats['generations']['pending']}\n\n"
        
        text += "💰 <b>Финансы:</b>\n"
        text += f"├ Доходы сегодня: {stats['finance']['revenue_today']} Stars\n"
        text += f"└ Общие доходы: {stats['finance']['total_revenue']} Stars"
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔄 Обновить", callback_data="admin_stats")
        builder.button(text="📊 Детальная статистика", callback_data="admin_detailed_stats")
        builder.button(text="◀️ Назад", callback_data="admin_menu")
        builder.adjust(2, 1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error loading admin stats: {e}")
        await callback.answer(_('admin.error_stats'), show_alert=True)

@router.callback_query(F.data == "admin_menu")
async def show_admin_menu(callback: CallbackQuery):
    """Показать админ меню"""
    if callback.from_user.id not in settings.ADMIN_IDS:
        await callback.answer(_('admin.access_denied'), show_alert=True)
        return
    
    text = f"👑 <b>{_('admin.panel')}</b>\n\n"
    text += _('admin.choose_action')
    
    await callback.message.edit_text(text, reply_markup=get_admin_keyboard('ru'))
    await callback.answer()

@router.callback_query(F.data == "admin_users")
async def show_admin_users(callback: CallbackQuery):
    """Показать пользователей"""
    if callback.from_user.id not in settings.ADMIN_IDS:
        await callback.answer(_('admin.access_denied'), show_alert=True)
        return
    
    try:
        # Первые 50 пользователей
        users = await db.get_all_users(limit=50)
        total_users = len(await db.get_all_users(limit=1000))  # Приблизительный подсчет
        
        if not users:
            await callback.answer(_('admin.users.not_found', default="Пользователей не найдено"), show_alert=True)
            return
        
        text = f"👥 <b>{_('admin.users.title')}</b>\n\n"
        text += f"{_('admin.users.total', count=total_users)}\n\n"
        
        for user in users[:10]:  # Показываем первых 10
            status = "🚫" if user.is_banned else "✅"
            name = user.first_name or user.username or f"ID{user.telegram_id}"
            text += f"{status} {name} (ID: {user.telegram_id})\n"
        
        if len(users) > 10:
            text += f"\n... и еще {len(users) - 10} пользователей"
        
        # Пагинация
        builder = InlineKeyboardBuilder()
        
        page = 1
        total_pages = (total_users + 49) // 50  # По 50 на страницу
        
        # Навигация
        if page > 1:
            builder.button(text="◀️", callback_data=f"admin_users_page_{page-1}")
        if page < total_pages:
            text_btn = f"{page}/{total_pages}"
            data = "noop"
            if page < total_pages:
                builder.button(text="▶️", callback_data=f"admin_users_page_{page+1}")
        
        builder.button(text=f"🔍 {_('admin.users.search')}", callback_data="admin_user_search")
        builder.button(text="◀️ Назад", callback_data="admin_menu")
        builder.adjust(2, 1, 1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error loading users: {e}")
        await callback.answer(_('admin.loading_error'), show_alert=True)

@router.callback_query(F.data.startswith("admin_users_page_"))
async def admin_users_pagination(callback: CallbackQuery):
    """Пагинация пользователей"""
    if callback.from_user.id not in settings.ADMIN_IDS:
        await callback.answer(_('admin.access_denied'), show_alert=True)
        return
    
    try:
        page = int(callback.data.split("_")[-1])
        if page < 1:
            await callback.answer(_('admin.invalid_page'), show_alert=True)
            return
    except (ValueError, IndexError):
        await callback.answer(_('admin.invalid_page'), show_alert=True)
        return

@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(callback: CallbackQuery, state: FSMContext):
    """Начать рассылку"""
    if callback.from_user.id not in settings.ADMIN_IDS:
        await callback.answer(_('admin.access_denied'), show_alert=True)
        return
    
    await callback.message.edit_text(
        _('admin.broadcast.instruction'),
        reply_markup=InlineKeyboardBuilder().button(
            text="❌ Отмена",
            callback_data="admin_menu"
        ).as_markup()
    )
    
    await state.set_state(AdminStates.broadcast_message)
    await callback.answer()

@router.message(AdminStates.broadcast_message)
async def handle_broadcast_message(message: Message, state: FSMContext):
    """Обработка сообщения для рассылки"""
    if message.from_user.id not in settings.ADMIN_IDS:
        return
    
    # Сохраняем сообщение
    await state.update_data(broadcast_message=message.message_id)
    
    # Получаем количество пользователей для рассылки
    users_count = await db.get_users_count()
    
    # Показываем подтверждение
    confirm_text = f"📢 <b>{_('admin.broadcast.confirm')}</b>\n\n"
    confirm_text += f"{_('admin.broadcast.recipients', count=users_count)}\n\n"
    
    # Показываем превью сообщения
    if message.text:
        preview = message.text[:100]
        if len(message.text) > 100:
            preview += "..."
        confirm_text += f"📝 <b>Текст:</b> {preview}\n\n"
    elif message.photo:
        confirm_text += f"📸 <b>Фото</b>"
        if message.caption:
            preview = message.caption[:100]
            if len(message.caption) > 100:
                preview += "..."
            confirm_text += f" с подписью: {preview}"
        confirm_text += "\n\n"
    
    confirm_text += f"⚠️ <b>Внимание:</b> Сообщение будет отправлено {users_count} пользователям!"
    
    builder = InlineKeyboardBuilder()
    builder.button(text=f"✅ {_('admin.broadcast.start')}", callback_data="broadcast_confirm")
    builder.button(text="❌ Отмена", callback_data="admin_menu")
    builder.adjust(1)
    
    await message.answer(confirm_text, reply_markup=builder.as_markup())

@router.callback_query(F.data == "broadcast_confirm")
async def confirm_broadcast(callback: CallbackQuery, state: FSMContext):
    """Подтверждение и запуск рассылки"""
    if callback.from_user.id not in settings.ADMIN_IDS:
        await callback.answer(_('admin.access_denied'), show_alert=True)
        return
    
    data = await state.get_data()
    broadcast_message_id = data.get("broadcast_message")
    
    if not broadcast_message_id:
        await callback.answer(_('admin.broadcast.no_message'), show_alert=True)
        return
    
    # Получаем пользователей для рассылки
    users = await db.get_all_users()
    
    # Обновляем сообщение
    await callback.message.edit_text(
        f"📢 <b>{_('admin.broadcast.started')}</b>\n\n"
        f"{_('admin.broadcast.progress', sent=0, total=len(users))}"
    )
    
    # Запускаем рассылку в фоне
    success_count = 0
    error_count = 0
    
    for i, user in enumerate(users):
        try:
            # Копируем сообщение пользователю
            await callback.bot.copy_message(
                chat_id=user.telegram_id,
                from_chat_id=callback.from_user.id,
                message_id=broadcast_message_id
            )
            success_count += 1
            
            # Обновляем прогресс каждые 10 пользователей
            if (i + 1) % 10 == 0:
                progress_text = f"📢 <b>{_('admin.broadcast.started')}</b>\n\n"
                progress_text += f"{_('admin.broadcast.progress', sent=i+1, total=len(users))}"
                
                try:
                    await callback.message.edit_text(progress_text)
                except:
                    pass  # Игнорируем ошибки редактирования
                    
        except Exception as e:
            error_count += 1
            logger.error(f"Broadcast error for user {user.telegram_id}: {e}")
            
        # Небольшая задержка между отправками
        await asyncio.sleep(0.1)
    
    # Финальный отчет
    final_text = f"✅ <b>{_('admin.broadcast.completed')}</b>\n\n"
    final_text += f"{_('admin.broadcast.stats', success=success_count, errors=error_count)}"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="◀️ Назад", callback_data="admin_menu")
    
    await callback.message.edit_text(final_text, reply_markup=builder.as_markup())
    await state.clear()

@router.callback_query(F.data == "admin_give_credits")
async def give_credits(callback: CallbackQuery, state: FSMContext):
    """Начать выдачу кредитов"""
    if callback.from_user.id not in settings.ADMIN_IDS:
        await callback.answer(_('admin.access_denied'), show_alert=True)
        return
    
    await callback.message.edit_text(
        _('admin.credits.enter_user'),
        reply_markup=InlineKeyboardBuilder().button(
            text="❌ Отмена",
            callback_data="admin_menu"
        ).as_markup()
    )
    
    await state.set_state(AdminStates.give_credits_user)
    await callback.answer()

@router.message(AdminStates.give_credits_user)
async def handle_give_credits_user(message: Message, state: FSMContext):
    """Обработка пользователя для выдачи кредитов"""
    if message.from_user.id not in settings.ADMIN_IDS:
        return
    
    try:
        # Определяем пользователя
        user_input = message.text.strip()
        
        user = None
        
        # Попробуем найти по ID
        if user_input.isdigit():
            user_id = int(user_input)
            user = await db.get_user_by_telegram_id(user_id)
        
        # Попробуем найти по username
        if not user and user_input.startswith('@'):
            username = user_input[1:]  # Убираем @
            user = await db.get_user_by_username(username)
        
        if not user:
            await message.answer(
                _('admin.credits.user_not_found'),
                reply_markup=InlineKeyboardBuilder().button(
                    text="❌ Отмена",
                    callback_data="admin_menu"
                ).as_markup()
            )
            return
        
        # Сохраняем найденного пользователя
        await state.update_data(target_user=user.id)
        
        # Показываем информацию о пользователе
        user_info = _('admin.credits.user_info',
                     name=user.first_name or _('admin.users.never'),
                     balance=user.balance,
                     bought=user.total_bought,
                     spent=user.total_spent)
        
        await message.answer(
            user_info,
            reply_markup=InlineKeyboardBuilder().button(
                text="❌ Отмена",
                callback_data="admin_menu"
            ).as_markup()
        )
        
        await state.set_state(AdminStates.give_credits_amount)
        
    except Exception as e:
        logger.error(f"Error finding user for credits: {e}")
        await message.answer(
            _('admin.credits.user_not_found'),
            reply_markup=InlineKeyboardBuilder().button(
                text="❌ Отмена",
                callback_data="admin_menu"
            ).as_markup()
        )

@router.message(AdminStates.give_credits_amount)
async def handle_give_credits_amount(message: Message, state: FSMContext):
    """Обработка количества кредитов"""
    if message.from_user.id not in settings.ADMIN_IDS:
        return
    
    try:
        amount = int(message.text.strip())
        
        if amount == 0:
            await message.answer(_('admin.credits.invalid_amount'))
            return
        
        # Получаем данные состояния
        data = await state.get_data()
        target_user_id = data.get("target_user")
        
        if not target_user_id:
            await message.answer(_('admin.users.not_found_error', default="Ошибка: пользователь не найден"))
            await state.clear()
            return
        
        # Получаем пользователя
        async with db.async_session() as session:
            user = await session.get(User, target_user_id)
            
            if not user:
                await message.answer(_('admin.user_not_found'))
                await state.clear()
                return
            
            # Изменяем баланс
            old_balance = user.balance
            user.balance = max(0, user.balance + amount)
            
            # Обновляем статистику
            if amount > 0:
                user.total_bought += amount
            else:
                user.total_spent += abs(amount)
            
            await session.commit()
            
            # Логируем действие
            await db.log_admin_action(
                admin_id=message.from_user.id,
                action="give_credits",
                target_user_id=user.telegram_id,
                details=f"Amount: {amount}, Balance: {old_balance} -> {user.balance}"
            )
            
            # Уведомляем пользователя
            try:
                if amount > 0:
                    notify_text = _('admin.credits.success_user',
                                   amount=amount,
                                   balance=user.balance)
                else:
                    notify_text = _('admin.credits.success_negative',
                                   amount=abs(amount),
                                   balance=user.balance)
                
                await message.bot.send_message(
                    chat_id=user.telegram_id,
                    text=notify_text
                )
            except Exception as e:
                logger.error(f"Error notifying user {user.telegram_id}: {e}")
            
            # Отчет админу
            action_text = _('admin.credits.action_added') if amount > 0 else _('admin.credits.action_removed')
            admin_text = _('admin.credits.success_admin',
                          user_id=user.telegram_id,
                          action=action_text,
                          amount=abs(amount),
                          balance=user.balance)
            
            await message.answer(
                admin_text,
                reply_markup=InlineKeyboardBuilder().button(
                    text="◀️ Назад", 
                    callback_data="admin_menu"
                ).as_markup()
            )
            
    except ValueError:
        await message.answer(_('admin.credits.invalid_amount'))
        return
    except Exception as e:
        logger.error(f"Error giving credits: {e}")
        await message.answer(
            _('admin.credits.error'),
            reply_markup=InlineKeyboardBuilder().button(
                text="◀️ Назад", 
                callback_data="admin_menu"
            ).as_markup()
        )
    finally:
        await state.clear()

@router.callback_query(F.data == "admin_bans")
async def show_bans_menu(callback: CallbackQuery):
    """Меню управления банами"""
    if not admin_filter(callback):
        await callback.answer("Доступ запрещен", show_alert=True)
        return
    
    try:
        # Получаем количество забаненных
        async with db.async_session() as session:
            banned_count = await session.execute(
                select(func.count(User.id)).where(User.is_banned == True)
            )
            banned = banned_count.scalar() or 0
        
        builder = InlineKeyboardBuilder()
        builder.button(text=f"🚫 Забаненные ({banned})", callback_data="show_banned_users")
        builder.button(text="➕ Забанить", callback_data="ban_user_start")
        builder.button(text="➖ Разбанить", callback_data="unban_user_start")
        builder.button(text="◀️ Назад", callback_data="admin_menu")
        builder.adjust(1)
        
        await callback.message.edit_text(
            "🚫 <b>Управление банами</b>\n\n"
                    f"{_('admin.bans.total_banned', banned=banned)}\n\n"
        f"{_('admin.choose_action')}",
            reply_markup=builder.as_markup()
        )
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error showing bans menu: {e}")
        await callback.answer("Ошибка загрузки", show_alert=True)

@router.callback_query(F.data == "show_banned_users")
async def show_banned_users(callback: CallbackQuery):
    """Показать забаненных пользователей"""
    if not admin_filter(callback):
        await callback.answer("Доступ запрещен", show_alert=True)
        return
    
    try:
        async with db.async_session() as session:
            banned_users = await session.execute(
                select(User).where(User.is_banned == True).limit(20)
            )
            users = banned_users.scalars().all()
        
        if not users:
            await callback.answer(_('admin.bans.no_banned'), show_alert=True)
            return
        
        text = "🚫 <b>Забаненные пользователи:</b>\n\n"
        
        for user in users:
            text += f"• {user.telegram_id} - @{user.username or 'нет'}\n"
            if user.ban_reason:
                text += f"  Причина: {user.ban_reason}\n"
        
        builder = InlineKeyboardBuilder()
        builder.button(text="◀️ Назад", callback_data="admin_bans")
        
        await callback.message.edit_text(text)
        await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error showing banned users: {e}")
        await callback.answer("Ошибка загрузки", show_alert=True)

@router.callback_query(F.data == "admin_logs")
async def show_admin_logs(callback: CallbackQuery, page: int = 1):
    """Показать логи админских действий"""
    if not admin_filter(callback):
        await callback.answer("Доступ запрещен", show_alert=True)
        return
    
    try:
        limit = 20
        offset = (page - 1) * limit
        
        async with db.async_session() as session:
            # Получаем логи
            logs_query = await session.execute(
                select(AdminLog)
                .order_by(AdminLog.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            logs = logs_query.scalars().all()
            
            # Получаем общее количество
            total_count = await session.execute(
                select(func.count(AdminLog.id))
            )
            total_logs = total_count.scalar() or 0
        
        total_pages = (total_logs + limit - 1) // limit
        
        text = f"📋 <b>Логи админских действий</b> (стр. {page}/{total_pages}):\n\n"
        
        for log in logs:
            date = log.created_at.strftime("%d.%m %H:%M")
            text += f"• {date} - Admin {log.admin_id}: {log.action}\n"
            if log.target_user_id:
                text += f"  Пользователь: {log.target_user_id}\n"
            if log.details:
                text += f"  Детали: {str(log.details)[:50]}...\n"
        
        # Кнопки навигации
        builder = InlineKeyboardBuilder()
        
        if page > 1:
            builder.button(text="◀️", callback_data=f"admin_logs_page_{page-1}")
        builder.button(text=f"{page}/{total_pages}", callback_data="noop")
        if page < total_pages:
            builder.button(text="▶️", callback_data=f"admin_logs_page_{page+1}")
        
        builder.row()
        builder.button(text="◀️ Назад", callback_data="admin_menu")
        
        await callback.message.edit_text(text)
        await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error showing admin logs: {e}")
        await callback.answer("Ошибка загрузки логов", show_alert=True)

@router.callback_query(F.data.startswith("admin_logs_page_"))
async def admin_logs_pagination(callback: CallbackQuery):
    """Пагинация логов"""
    if not admin_filter(callback):
        await callback.answer("Доступ запрещен", show_alert=True)
        return
    
    try:
        page = int(callback.data.split("_")[3])
        await show_admin_logs(callback, page=page)
    except ValueError:
        await callback.answer("Неверный номер страницы", show_alert=True)

@router.callback_query(F.data == "admin_detailed_stats")
async def show_detailed_stats(callback: CallbackQuery):
    """Показать детальную статистику"""
    if not admin_filter(callback):
        await callback.answer("Доступ запрещен", show_alert=True)
        return
    
    try:
        # Получаем детальную статистику
        async with db.async_session() as session:
            # Статистика по моделям
            model_stats = await session.execute(
                select(
                    Generation.model,
                    func.count(Generation.id).label('count')
                ).group_by(Generation.model)
            )
            
            # Статистика по дням
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            week_ago = today - timedelta(days=7)
            
            daily_stats = await session.execute(
                select(
                    func.date(Generation.created_at).label('date'),
                    func.count(Generation.id).label('count')
                ).where(
                    Generation.created_at >= week_ago
                ).group_by('date')
            )
            
            # Топ пользователей
            top_users = await session.execute(
                select(
                    User.telegram_id,
                    User.username,
                    func.count(Generation.id).label('gen_count')
                ).join(
                    Generation, User.id == Generation.user_id
                ).group_by(
                    User.id
                ).order_by(
                    func.count(Generation.id).desc()
                ).limit(5)
            )
        
        text = "📊 <b>Детальная статистика</b>\n\n"
        
        text += "<b>Популярность моделей:</b>\n"
        for model, count in model_stats:
            model_name = model.split('-')[2].upper() if len(model.split('-')) > 2 else model
            text += f"• {model_name}: {count} генераций\n"
        
        text += "\n<b>Генерации за последние 7 дней:</b>\n"
        for date, count in daily_stats:
            text += f"• {date}: {count} генераций\n"
        
        text += "\n<b>Топ-5 пользователей:</b>\n"
        for i, (user_id, username, count) in enumerate(top_users, 1):
            text += f"{i}. @{username or 'user'} ({user_id}): {count} генераций\n"
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📈 Экспорт статистики", callback_data="export_stats")
        builder.button(text="◀️ Назад", callback_data="admin_stats")
        builder.adjust(1)
        
        await callback.message.edit_text(text)
        await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error showing detailed stats: {e}")
        await callback.answer("Ошибка загрузки статистики", show_alert=True)

@router.message(Command("ban"))
async def ban_user_command(message: Message):
    """Команда бана пользователя: /ban user_id [reason]"""
    if not admin_filter(message):
        return
    
    parts = message.text.split(maxsplit=2)
    if len(parts) < 2:
        await message.answer(_('admin.ban.usage', default="Использование: /ban user_id [причина]"))
        return
    
    try:
        user_id = int(parts[1])
        reason = parts[2] if len(parts) > 2 else _('admin.bans.default_reason', default="Нарушение правил")
        
        # Проверяем, что не баним админа
        if user_id in settings.ADMIN_IDS:
            await message.answer(_('admin.bans.cannot_ban_admin'))
            return
        
        success = await db.ban_user(user_id, banned=True, reason=reason)
        
        if success:
            # Логируем
            async with db.async_session() as session:
                log = AdminLog(
                    admin_id=message.from_user.id,
                    action="ban_user",
                    target_user_id=user_id,
                    details={"reason": reason}
                )
                session.add(log)
                await session.commit()
            
            await message.answer(f"✅ Пользователь {user_id} забанен\nПричина: {reason}")
        else:
            await message.answer(_('admin.users.not_found'))
            
    except ValueError:
        await message.answer("❌ Неверный ID пользователя")
    except Exception as e:
        logger.error(f"Error banning user: {e}")
        await message.answer(f"❌ Ошибка: {str(e)}")

@router.message(Command("unban"))
async def unban_user_command(message: Message):
    """Команда разбана пользователя: /unban user_id"""
    if not admin_filter(message):
        return
    
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Использование: /unban user_id")
        return
    
    try:
        user_id = int(parts[1])
        success = await db.ban_user(user_id, banned=False)
        
        if success:
            # Логируем
            async with db.async_session() as session:
                log = AdminLog(
                    admin_id=message.from_user.id,
                    action="unban_user",
                    target_user_id=user_id
                )
                session.add(log)
                await session.commit()
            
            await message.answer(f"✅ Пользователь {user_id} разбанен")
        else:
            await message.answer("❌ Пользователь не найден")
            
    except ValueError:
        await message.answer("❌ Неверный ID пользователя")
    except Exception as e:
        logger.error(f"Error unbanning user: {e}")
        await message.answer(f"❌ Ошибка: {str(e)}")

@router.callback_query(F.data == "admin_user_search")
async def start_user_search(callback: CallbackQuery, state: FSMContext):
    """Начать поиск пользователя"""
    if not admin_filter(callback):
        await callback.answer("Доступ запрещен", show_alert=True)
        return
    
    await callback.message.edit_text(
        "🔍 <b>Поиск пользователя</b>\n\n"
        "Введите ID, username или имя пользователя:\n\n"
        "💡 Примеры:\n"
        "• 123456789 (ID)\n"
        "• @username\n"
        "• Иван (имя)",
        reply_markup=get_cancel_keyboard()
    )
    
    await state.set_state(AdminStates.user_search)
    await callback.answer()

@router.message(AdminStates.user_search)
async def process_user_search(message: Message, state: FSMContext):
    """Обработка поиска пользователя"""
    if not admin_filter(message):
        return
    
    search_query = message.text.strip()
    
    # Валидация поискового запроса (защита от SQL injection)
    if len(search_query) < 2:
        await message.answer(
            "❌ Слишком короткий запрос (минимум 2 символа)",
            reply_markup=get_cancel_keyboard()
        )
        return
    
    if len(search_query) > 50:
        await message.answer(
            "❌ Слишком длинный запрос (максимум 50 символов)",
            reply_markup=get_cancel_keyboard()
        )
        return
    
    try:
        # Поиск пользователей
        users = await db.search_users(search_query, limit=10)
        
        if not users:
            await message.answer(
                "❌ Пользователи не найдены\n"
                "Попробуйте другой запрос:",
                reply_markup=get_cancel_keyboard()
            )
            return
        
        text = f"🔍 <b>Результаты поиска:</b> {search_query[:30]}...\n\n"
        
        builder = InlineKeyboardBuilder()
        
        for user in users:
            text += f"• {user.telegram_id} - @{user.username or 'нет'}\n"
            text += f"  {user.first_name or ''} {user.last_name or ''}\n"
            text += f"  💰 {user.balance} | 📅 {user.created_at.strftime('%d.%m.%Y')}\n"
            
            # Кнопка для каждого пользователя
            builder.button(
                text=f"👤 {user.telegram_id}",
                callback_data=f"admin_user_{user.telegram_id}"
            )
        
        builder.adjust(2)
        builder.row()
        builder.button(text="🔍 Новый поиск", callback_data="admin_user_search")
        builder.button(text="◀️ Назад", callback_data="admin_users")
        
        await message.answer(text, reply_markup=builder.as_markup())
        
    except Exception as e:
        logger.error(f"Error searching users: {e}")
        await message.answer(
            "❌ Ошибка поиска. Попробуйте позже.",
            reply_markup=get_cancel_keyboard()
        )
    finally:
        await state.clear()

@router.callback_query(F.data.startswith("admin_user_"))
async def show_user_details(callback: CallbackQuery):
    """Показать детали пользователя"""
    if not admin_filter(callback):
        await callback.answer("Доступ запрещен", show_alert=True)
        return
    
    try:
        user_id = int(callback.data.split("_")[2])
        user = await db.get_user(user_id)
        
        if not user:
            await callback.answer("Пользователь не найден", show_alert=True)
            return
        
        # Получаем статистику
        stats = await db.get_user_statistics(user_id)
        
        # Форматируем последнюю активность
        last_active = user.last_active.strftime('%d.%m.%Y %H:%M') if user.last_active else _('admin.users.never')
        
        text = f"""
👤 <b>Информация о пользователе</b>

🆔 <b>ID:</b> <code>{user.telegram_id}</code>
👤 <b>Имя:</b> {user.first_name or "—"} {user.last_name or ""}
🏷 <b>Username:</b> @{user.username or "—"}
🌐 <b>Язык:</b> {user.language_code or "ru"}

💰 <b>Финансы:</b>
├ Баланс: {user.balance} кредитов
├ Куплено: {user.total_bought} кредитов
└ Потрачено: {user.total_spent} кредитов

🎬 <b>Генерации:</b>
├ Всего: {stats.get('total_generations', 0)}
├ Успешных: {stats.get('successful_generations', 0)}
└ Средняя оценка: {stats.get('average_rating', 0):.1f}/5

📅 <b>Даты:</b>
├ Регистрация: {user.created_at.strftime('%d.%m.%Y %H:%M')}
└ Активность: {last_active}

🔐 <b>Статус:</b> {"🚫 Забанен" if user.is_banned else "✅ Активен"}
⭐ <b>Premium:</b> {"✅ Да" if user.is_premium else "❌ Нет"}
"""
        
        if user.is_banned and hasattr(user, 'ban_reason'):
            text += f"\n🚫 <b>Причина бана:</b> {user.ban_reason}"
        
        # Кнопки действий
        builder = InlineKeyboardBuilder()
        
        if user.is_banned:
            builder.button(text="✅ Разбанить", callback_data=f"quick_unban_{user.telegram_id}")
        else:
            builder.button(text="🚫 Забанить", callback_data=f"quick_ban_{user.telegram_id}")
        
        builder.button(text="💰 Выдать кредиты", callback_data=f"quick_credits_{user.telegram_id}")
        builder.button(text="📨 Написать", url=f"tg://user?id={user.telegram_id}")
        builder.button(text="📊 История генераций", callback_data=f"user_generations_{user.telegram_id}")
        builder.button(text="◀️ Назад", callback_data="admin_users")
        
        builder.adjust(2, 2, 1)
        
        await callback.message.edit_text(text)
        await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
        await callback.answer()
        
    except ValueError:
        await callback.answer("Неверный ID пользователя", show_alert=True)
    except Exception as e:
        logger.error(f"Error showing user details: {e}")
        await callback.answer("Ошибка загрузки данных", show_alert=True)

@router.callback_query(F.data.startswith("quick_ban_"))
async def quick_ban(callback: CallbackQuery):
    """Быстрый бан пользователя"""
    if not admin_filter(callback):
        await callback.answer("Доступ запрещен", show_alert=True)
        return
    
    try:
        user_id = int(callback.data.split("_")[2])
        
        # Проверяем, что не баним админа
        if user_id in settings.ADMIN_IDS:
            await callback.answer("❌ Нельзя забанить администратора", show_alert=True)
            return
        
        success = await db.ban_user(user_id, banned=True, reason="Quick ban by admin")
        
        if success:
            # Логируем
            async with db.async_session() as session:
                log = AdminLog(
                    admin_id=callback.from_user.id,
                    action="ban_user",
                    target_user_id=user_id,
                    details={"method": "quick_ban"}
                )
                session.add(log)
                await session.commit()
            
            await callback.answer("✅ Пользователь забанен")
            # Обновляем информацию
            callback.data = f"admin_user_{user_id}"
            await show_user_details(callback)
        else:
            await callback.answer("❌ Ошибка при бане", show_alert=True)
            
    except Exception as e:
        logger.error(f"Error quick banning user: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)

@router.callback_query(F.data.startswith("quick_unban_"))
async def quick_unban(callback: CallbackQuery):
    """Быстрый разбан пользователя"""
    if not admin_filter(callback):
        await callback.answer("Доступ запрещен", show_alert=True)
        return
    
    try:
        user_id = int(callback.data.split("_")[2])
        success = await db.ban_user(user_id, banned=False)
        
        if success:
            # Логируем
            async with db.async_session() as session:
                log = AdminLog(
                    admin_id=callback.from_user.id,
                    action="unban_user",
                    target_user_id=user_id,
                    details={"method": "quick_unban"}
                )
                session.add(log)
                await session.commit()
            
            await callback.answer("✅ Пользователь разбанен")
            # Обновляем информацию
            callback.data = f"admin_user_{user_id}"
            await show_user_details(callback)
        else:
            await callback.answer("❌ Ошибка при разбане", show_alert=True)
            
    except Exception as e:
        logger.error(f"Error quick unbanning user: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)

@router.callback_query(F.data.startswith("quick_credits_"))
async def quick_credits(callback: CallbackQuery, state: FSMContext):
    """Быстрая выдача кредитов"""
    if not admin_filter(callback):
        await callback.answer("Доступ запрещен", show_alert=True)
        return
    
    try:
        user_id = int(callback.data.split("_")[2])
        await state.update_data(target_user_id=user_id)
        
        # Показываем быстрые варианты
        builder = InlineKeyboardBuilder()
        
        quick_amounts = [10, 50, 100, 500, 1000, -50, -100]
        for amount in quick_amounts:
            emoji = "➕" if amount > 0 else "➖"
            builder.button(
                text=f"{emoji} {abs(amount)}",
                callback_data=f"instant_credits_{user_id}_{amount}"
            )
        
        builder.button(text="✏️ Другая сумма", callback_data="admin_give_credits")
        builder.button(text="❌ Отмена", callback_data=f"admin_user_{user_id}")
        builder.adjust(4, 3, 1, 1)
        
        await callback.message.edit_text(
            "💰 <b>Быстрая выдача кредитов</b>\n\n"
            "Выберите сумму или введите свою:",
            reply_markup=builder.as_markup()
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error in quick credits: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)

@router.callback_query(F.data.startswith("instant_credits_"))
async def instant_credits(callback: CallbackQuery, bot):
    """Мгновенная выдача кредитов"""
    if not admin_filter(callback):
        await callback.answer("Доступ запрещен", show_alert=True)
        return
    
    try:
        parts = callback.data.split("_")
        user_id = int(parts[2])
        amount = int(parts[3])
        
        # Выдаем кредиты
        success = await db.add_credits_to_user(
            user_id, 
            amount,
            admin_id=callback.from_user.id,
            reason="Quick grant by admin"
        )
        
        if success:
            # Уведомляем пользователя
            try:
                if amount > 0:
                    await bot.send_message(
                        user_id,
                        f"🎁 <b>Вам начислено {amount} кредитов!</b>\n\n"
                        f"Администратор пополнил ваш баланс."
                    )
                else:
                    await bot.send_message(
                        user_id,
                        f"💰 <b>С вашего баланса списано {abs(amount)} кредитов</b>\n\n"
                        f"Обратитесь в поддержку за разъяснениями."
                    )
            except:
                pass
            
            # Логируем
            async with db.async_session() as session:
                log = AdminLog(
                    admin_id=callback.from_user.id,
                    action="give_credits",
                    target_user_id=user_id,
                    details={
                        "amount": amount,
                        "method": "instant"
                    }
                )
                session.add(log)
                await session.commit()
            
            await callback.answer(
                f"✅ {'Начислено' if amount > 0 else 'Списано'} {abs(amount)} кредитов"
            )
            
            # Возвращаемся к деталям пользователя
            callback.data = f"admin_user_{user_id}"
            await show_user_details(callback)
        else:
            await callback.answer("❌ Ошибка выдачи кредитов", show_alert=True)
            
    except Exception as e:
        logger.error(f"Error instant credits: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)

@router.callback_query(F.data == "export_stats")
async def export_stats(callback: CallbackQuery):
    """Экспорт статистики (заглушка)"""
    if not admin_filter(callback):
        await callback.answer("Доступ запрещен", show_alert=True)
        return
    
    await callback.answer(
        "📊 Функция экспорта статистики в разработке.\n"
        "Скоро вы сможете скачать детальный отчет в формате Excel.",
        show_alert=True
    )

@router.callback_query(F.data == "noop")
async def noop_handler(callback: CallbackQuery):
    """Обработчик для неактивных кнопок"""
    await callback.answer()

# Обработчик отмены для админских состояний
@router.callback_query(F.data == "cancel", StateFilter(AdminStates))
async def cancel_admin_action(callback: CallbackQuery, state: FSMContext):
    """Отмена админского действия"""
    await state.clear()
    await callback.message.edit_text(
        "❌ Действие отменено",
        reply_markup=InlineKeyboardBuilder().button(
            text="🏠 Админ меню",
            callback_data="admin_menu"
        ).as_markup()
    )
    await callback.answer()

@router.callback_query(F.data == "ban_user_start")
async def ban_user_start(callback: CallbackQuery, state: FSMContext):
    """Начать процедуру бана пользователя"""
    if callback.from_user.id not in settings.ADMIN_IDS:
        await callback.answer("Доступ запрещен", show_alert=True)
        return
    
    await callback.message.edit_text(
        "🚫 <b>Забанить пользователя</b>\n\n"
        "Отправьте ID пользователя или перешлите его сообщение:",
        reply_markup=InlineKeyboardBuilder().button(
            text="❌ Отмена",
            callback_data="admin_bans"
        ).as_markup()
    )
    await state.set_state(AdminStates.banning_user)
    await callback.answer()

@router.callback_query(F.data == "unban_user_start")
async def unban_user_start(callback: CallbackQuery, state: FSMContext):
    """Начать процедуру разбана пользователя"""
    if callback.from_user.id not in settings.ADMIN_IDS:
        await callback.answer("Доступ запрещен", show_alert=True)
        return
    
    await callback.message.edit_text(
        "✅ <b>Разбанить пользователя</b>\n\n"
        "Отправьте ID пользователя или перешлите его сообщение:",
        reply_markup=InlineKeyboardBuilder().button(
            text="❌ Отмена",
            callback_data="admin_bans"
        ).as_markup()
    )
    await state.set_state(AdminStates.unbanning_user)
    await callback.answer()

@router.message(AdminStates.banning_user)
async def process_ban_user(message: Message, state: FSMContext):
    """Обработка бана пользователя"""
    try:
        # Пытаемся извлечь ID пользователя
        user_id = None
        if message.text and message.text.isdigit():
            user_id = int(message.text)
        elif message.forward_from:
            user_id = message.forward_from.id
        elif message.reply_to_message and message.reply_to_message.from_user:
            user_id = message.reply_to_message.from_user.id
        
        if not user_id:
            await message.answer("❌ Не удалось определить ID пользователя")
            return
        
        # Проверяем, существует ли пользователь
        user = await db.get_user_by_telegram_id(user_id)
        if not user:
            await message.answer("❌ Пользователь не найден в базе данных")
            return
        
        # Проверяем, не админ ли это
        if user_id in settings.ADMIN_IDS:
            await message.answer("❌ Нельзя забанить администратора")
            return
        
        # Баним пользователя
        await db.ban_user_by_id(user.id)
        
        await message.answer(
            f"✅ <b>Пользователь забанен</b>\n\n"
            f"🆔 ID: <code>{user_id}</code>\n"
            f"👤 Имя: {user.first_name}\n"
            f"📅 Дата бана: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
            reply_markup=InlineKeyboardBuilder().button(
                text="🏠 Админ меню",
                callback_data="admin_menu"
            ).as_markup()
        )
        
        # Пытаемся уведомить пользователя
        try:
            await message.bot.send_message(
                user_id,
                "🚫 <b>Ваш аккаунт заблокирован</b>\n\n"
                "Если вы считаете, что это ошибка, обратитесь в поддержку."
            )
        except Exception:
            pass  # Игнорируем ошибки отправки
        
    except ValueError:
        await message.answer("❌ Неверный формат ID пользователя")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")
    finally:
        await state.clear()

@router.message(AdminStates.unbanning_user)
async def process_unban_user(message: Message, state: FSMContext):
    """Обработка разбана пользователя"""
    try:
        # Пытаемся извлечь ID пользователя
        user_id = None
        if message.text and message.text.isdigit():
            user_id = int(message.text)
        elif message.forward_from:
            user_id = message.forward_from.id
        elif message.reply_to_message and message.reply_to_message.from_user:
            user_id = message.reply_to_message.from_user.id
        
        if not user_id:
            await message.answer("❌ Не удалось определить ID пользователя")
            return
        
        # Проверяем, существует ли пользователь
        user = await db.get_user_by_telegram_id(user_id)
        if not user:
            await message.answer("❌ Пользователь не найден в базе данных")
            return
        
        # Проверяем, забанен ли пользователь
        if not user.is_banned:
            await message.answer("❌ Пользователь не забанен")
            return
        
        # Разбаниваем пользователя
        await db.unban_user(user.id)
        
        await message.answer(
            f"✅ <b>Пользователь разбанен</b>\n\n"
            f"🆔 ID: <code>{user_id}</code>\n"
            f"👤 Имя: {user.first_name}\n"
            f"📅 Дата разбана: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
            reply_markup=InlineKeyboardBuilder().button(
                text="🏠 Админ меню",
                callback_data="admin_menu"
            ).as_markup()
        )
        
        # Пытаемся уведомить пользователя
        try:
            await message.bot.send_message(
                user_id,
                "✅ <b>Ваш аккаунт разблокирован</b>\n\n"
                "Добро пожаловать обратно! Теперь вы можете пользоваться ботом."
            )
        except Exception:
            pass  # Игнорируем ошибки отправки
        
    except ValueError:
        await message.answer("❌ Неверный формат ID пользователя")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")
    finally:
        await state.clear()

@router.callback_query(F.data.startswith("user_generations_"))
async def show_user_generations(callback: CallbackQuery):
    """Показать историю генераций пользователя"""
    if callback.from_user.id not in settings.ADMIN_IDS:
        await callback.answer("Доступ запрещен", show_alert=True)
        return
    
    user_id = int(callback.data.split("_")[2])
    
    # Получаем пользователя
    user = await db.get_user_by_telegram_id(user_id)
    if not user:
        await callback.answer("❌ Пользователь не найден", show_alert=True)
        return
    
    # Получаем генерации
    async with db.async_session() as session:
        result = await session.execute(
            select(Generation)
            .where(Generation.user_id == user.id)
            .order_by(Generation.created_at.desc())
            .limit(20)
        )
        generations = result.scalars().all()
    
    if not generations:
        await callback.answer("❌ У пользователя нет генераций", show_alert=True)
        return
    
    # Формируем текст
    text = f"📊 <b>История генераций</b>\n\n"
    text += f"👤 <b>Пользователь:</b> {user.first_name} (ID: {user_id})\n"
    text += f"📊 <b>Всего генераций:</b> {len(generations)}\n\n"
    
    from core.constants import STATUS_EMOJIS
    for gen in generations[:10]:  # Показываем только первые 10
        status_emoji = STATUS_EMOJIS.get(gen.status, "❓")
        date = gen.created_at.strftime('%d.%m %H:%M')
        text += f"{status_emoji} {date} - {gen.resolution} - {gen.model_type}\n"
    
    if len(generations) > 10:
        text += f"\n... и еще {len(generations) - 10} генераций"
    
    # Статистика
    successful = sum(1 for gen in generations if gen.status == 'completed')
    failed = len(generations) - successful
    
    text += f"\n\n📈 <b>Статистика:</b>\n"
    text += f"✅ Успешных: {successful}\n"
    text += f"❌ Неудачных: {failed}\n"
    text += f"💰 Потрачено кредитов: {user.total_spent}\n"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="◀️ Назад", callback_data=f"admin_user_{user_id}")
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()

@router.callback_query(F.data == "admin_api_balance")
async def check_api_balance(callback: CallbackQuery):
    """Проверить баланс API"""
    if callback.from_user.id not in settings.ADMIN_IDS:
        await callback.answer(_('admin.access_denied'), show_alert=True)
        return
    
    try:
        await callback.answer("Проверяю баланс API...")
        
        # Проверяем баланс
        balance_check = await api_monitor.check_and_notify(callback.bot)
        
        balance = balance_check.get('balance')
        status = balance_check.get('status')
        
        if balance is None:
            text = "❌ <b>Ошибка проверки баланса API</b>\n\n"
            text += "Не удалось получить информацию о балансе.\n"
            text += "Проверьте подключение к API и токен."
        else:
            # Определяем эмодзи статуса
            if status == 'critical':
                status_emoji = "🚨"
                status_text = "КРИТИЧНО"
            elif status == 'low':
                status_emoji = "⚠️"
                status_text = "НИЗКИЙ"
            else:
                status_emoji = "✅"
                status_text = "НОРМА"
            
            text = f"{status_emoji} <b>Баланс API: {status_text}</b>\n\n"
            text += f"💰 <b>Текущий баланс:</b> ${balance}\n"
            text += f"📅 <b>Время проверки:</b> {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n\n"
            
            text += "🎯 <b>Пороговые значения:</b>\n"
            text += f"├ Критичный: ${api_monitor.critical_balance_threshold}\n"
            text += f"└ Низкий: ${api_monitor.low_balance_threshold}\n\n"
            
            if status == 'critical':
                text += "🚨 <b>ТРЕБУЕТСЯ НЕМЕДЛЕННОЕ ДЕЙСТВИЕ!</b>\n"
                text += "Генерация видео временно недоступна.\n"
                text += "Пополните баланс API как можно скорее."
            elif status == 'low':
                text += "⚠️ <b>Рекомендуется пополнить баланс</b>\n"
                text += "Баланс API становится критически низким."
            else:
                text += "✅ <b>Всё в порядке</b>\n"
                text += "Баланс API находится в пределах нормы."
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔄 Обновить", callback_data="admin_api_balance")
        builder.button(text="◀️ Назад", callback_data="admin_menu")
        builder.adjust(2)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"Error checking API balance: {e}")
        await callback.answer("Ошибка при проверке баланса API", show_alert=True)

@router.message(Command("test_api_balance"))
async def test_api_balance(message: Message):
    """Тестирование проверки баланса API (только для админов)"""
    if message.from_user.id not in settings.ADMIN_IDS:
        return
    
    await message.answer("🔍 Тестирую систему мониторинга баланса API...")
    
    try:
        # Проверяем баланс
        balance_check = await api_monitor.check_and_notify(message.bot)
        
        balance = balance_check.get('balance')
        status = balance_check.get('status')
        
        if balance is None:
            text = "❌ <b>Тест не пройден</b>\n\n"
            text += "Не удалось получить баланс API.\n"
            text += "Проверьте API токен и подключение."
        else:
            text = f"✅ <b>Тест пройден успешно</b>\n\n"
            text += f"💰 Баланс API: ${balance}\n"
            text += f"📊 Статус: {status}\n"
            text += f"🎯 Сервис {'доступен' if api_monitor.is_service_available(balance) else 'недоступен'}\n\n"
            
            # Информация о настройках
            text += "⚙️ <b>Настройки мониторинга:</b>\n"
            text += f"└ Низкий баланс: ${api_monitor.low_balance_threshold}\n"
            text += f"└ Критический: ${api_monitor.critical_balance_threshold}\n"
            text += f"└ Уведомления: {'включены' if balance <= api_monitor.low_balance_threshold else 'не требуются'}"
        
        await message.answer(text, parse_mode='HTML')
        
    except Exception as e:
        await message.answer(f"❌ <b>Ошибка тестирования:</b>\n\n{str(e)}", parse_mode='HTML')
        logger.error(f"API balance test failed: {e}")

@router.message(Command("recover_videos"))
async def recover_lost_videos_command(message: Message):
    """Восстановить потерянные видео (админская команда)"""
    user = await db.get_user(message.from_user.id)
    
    if not user or not user.is_admin:
        await message.answer("Доступ запрещен")
        return
    
    try:
        # Отправляем сообщение о начале процесса
        status_msg = await message.answer("🔄 Начинаю восстановление потерянных видео...")
        
        # Получаем неудачные генерации
        failed_generations = await db.get_failed_generations_with_task_id(hours_back=24)
        
        if not failed_generations:
            await status_msg.edit_text("✅ Неудачных генераций для восстановления не найдено")
            return
        
        await status_msg.edit_text(f"🔍 Найдено {len(failed_generations)} неудачных генераций. Проверяю статус...")
        
        # Восстанавливаем видео
        from services.wavespeed_api import get_wavespeed_api
        api = get_wavespeed_api()
        recovered = await api.recover_lost_videos(failed_generations)
        
        # Отправляем уведомления пользователям
        notifications_sent = 0
        for recovery in recovered:
            try:
                from bot.tasks import send_generation_notification
                await send_generation_notification(
                    recovery['generation_id'],
                    'recovered',
                    video_url=recovery['video_url']
                )
                notifications_sent += 1
            except Exception as e:
                logger.error(f"Error sending recovery notification: {e}")
        
        # Формируем отчет
        report = f"""
✅ <b>Восстановление завершено!</b>

📊 <b>Статистика:</b>
• Проверено генераций: {len(failed_generations)}
• Восстановлено видео: {len(recovered)}
• Отправлено уведомлений: {notifications_sent}

🆔 <b>Восстановленные ID:</b>
"""
        
        if recovered:
            for recovery in recovered[:10]:  # Показываем первые 10
                report += f"• <code>{recovery['generation_id']}</code>\n"
            
            if len(recovered) > 10:
                report += f"• ... и еще {len(recovered) - 10}\n"
        else:
            report += "• Нет восстановленных видео\n"
        
        await status_msg.edit_text(report, parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"Error in recover_videos command: {e}")
        await status_msg.edit_text(f"❌ Ошибка при восстановлении: {str(e)}")
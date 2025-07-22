import logging
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import StateFilter
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, func

from bot.middlewares.i18n import I18n
from services.database import db
from core.config import settings
from models.models import SupportTicket, User

logger = logging.getLogger(__name__)

# Глобальная функция локализации для поддержки
i18n = I18n()
_ = lambda key, **kwargs: i18n.get(key, lang='ru', **kwargs)

class SupportStates(StatesGroup):
    choosing_category = State()
    writing_message = State()
    confirming_ticket = State()
    admin_replying = State()

router = Router(name="support")

# Исправлено: раздельные обработчики для Message и CallbackQuery
@router.message(F.text == "/support")
async def support_menu_message(message: Message):
    """Показать меню поддержки через команду"""
    try:
        await message.answer(
            _('support.menu.choose_option'),
            reply_markup=InlineKeyboardBuilder()
            .button(text=_('support.menu.faq_button'), callback_data="support_faq")
            .button(text=_('support.menu.new_ticket_button'), callback_data="support_new_ticket")
            .button(text=_('support.my_tickets'), callback_data="my_tickets")
            .button(text=f"◀️ {_('common.back')}", callback_data="back_to_menu")
            .adjust(1)
            .as_markup()
        )
    except Exception as e:
        logger.error(f"Error in support_menu_message: {e}")
        await message.answer(_('errors.error'))

@router.callback_query(F.data == "support")
async def support_menu_callback(callback: CallbackQuery):
    """Показать меню поддержки через callback"""
    try:
        await callback.message.edit_text(
            _('support.menu.choose_option'),
            reply_markup=InlineKeyboardBuilder()
            .button(text=_('support.menu.faq_button'), callback_data="support_faq")
            .button(text=_('support.menu.new_ticket_button'), callback_data="support_new_ticket")
            .button(text=_('support.my_tickets'), callback_data="my_tickets")
            .button(text=f"◀️ {_('common.back')}", callback_data="back_to_menu")
            .adjust(1)
            .as_markup()
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Error in support_menu_callback: {e}")
        await callback.answer(_('errors.error'), show_alert=True)

@router.callback_query(F.data == "support_faq")
async def support_faq(callback: CallbackQuery):
    """Показать частые вопросы"""
    try:
        await callback.message.edit_text(
            _('support.faq.content'),
            reply_markup=InlineKeyboardBuilder()
            .button(text=_('support.menu.new_ticket_button'), callback_data="support_new_ticket")
            .button(text=f"◀️ {_('common.back')}", callback_data="support")
            .adjust(1)
            .as_markup()
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Error in support_faq: {e}")
        await callback.answer(_('errors.error'), show_alert=True)

@router.callback_query(F.data == "support_new_ticket")
async def support_new_ticket(callback: CallbackQuery, state: FSMContext):
    """Начать создание тикета"""
    try:
        user = await db.get_user(callback.from_user.id)
        if not user:
            await callback.answer(_('errors.user_not_found'), show_alert=True)
            return
        
        # Проверяем, есть ли уже открытый тикет
        async with db.async_session() as session:
            existing_ticket = await session.execute(
                select(SupportTicket).where(
                    SupportTicket.user_id == user.id,
                    SupportTicket.status.in_(['open', 'in_progress'])
                )
            )
            existing_ticket = existing_ticket.scalar_one_or_none()
        
        if existing_ticket:
            await callback.answer(_('support.ticket.existing'), show_alert=True)
            return
        
        # Показываем категории
        builder = InlineKeyboardBuilder()
        categories = {
            'technical': _('support.ticket.category.technical'),
            'payment': _('support.ticket.category.payment'),
            'quality': _('support.ticket.category.quality'),
            'account': _('support.ticket.category.account'),
            'other': _('support.ticket.category.other')
        }
        
        for category_id, category_name in categories.items():
            builder.button(text=category_name, callback_data=f"ticket_cat_{category_id}")
        
        builder.button(text=f"◀️ {_('common.back')}", callback_data="support")
        builder.adjust(1)
        
        await callback.message.edit_text(
            _('support.ticket.start'),
            reply_markup=builder.as_markup()
        )
        await callback.answer()
        await state.set_state(SupportStates.choosing_category)
    except Exception as e:
        logger.error(f"Error in support_new_ticket: {e}")
        await callback.answer(_('errors.error'), show_alert=True)

@router.callback_query(F.data.startswith("ticket_cat_"))
async def ticket_category(callback: CallbackQuery, state: FSMContext):
    """Выбор категории тикета"""
    try:
        category = callback.data.split("_")[2]
        await state.update_data(category=category)
        
        await callback.message.edit_text(
            _('support.ticket.message_instruction'),
            reply_markup=InlineKeyboardBuilder()
            .button(text=f"◀️ {_('common.back')}", callback_data="support_new_ticket")
            .as_markup()
        )
        
        await state.set_state(SupportStates.writing_message)
        await callback.answer()
    except Exception as e:
        logger.error(f"Error in ticket_category: {e}")
        await callback.answer(_('errors.error'), show_alert=True)

@router.message(SupportStates.writing_message)
async def ticket_message(message: Message, state: FSMContext):
    """Обработка сообщения тикета"""
    try:
        if len(message.text) < 10:
            await message.answer(_('errors.prompt_too_short'))
            return
        
        if len(message.text) > 1000:
            await message.answer(_('errors.prompt_too_long'))
            return
        
        await state.update_data(message_text=message.text)
        
        # Получаем данные для подтверждения
        data = await state.get_data()
        category = data.get('category')
        
        # Переводим категорию для отображения
        category_names = {
            'technical': _('support.ticket.category.technical'),
            'payment': _('support.ticket.category.payment'),
            'quality': _('support.ticket.category.quality'),
            'account': _('support.ticket.category.account'),
            'other': _('support.ticket.category.other')
        }
        
        category_display = category_names.get(category, category)
        
        confirm_text = _('support.ticket.confirm',
                        category=category_display,
                        message=message.text)
        
        builder = InlineKeyboardBuilder()
        builder.button(text=_('support.ticket.send'), callback_data="confirm_ticket")
        builder.button(text=_('support.ticket.edit'), callback_data="support_new_ticket")
        builder.button(text=f"◀️ {_('common.back')}", callback_data="support")
        builder.adjust(1)
        
        await message.answer(confirm_text, reply_markup=builder.as_markup())
        await state.set_state(SupportStates.confirming_ticket)
        
    except Exception as e:
        logger.error(f"Error in ticket_message: {e}")
        await message.answer(_('errors.error'))

@router.callback_query(F.data == "confirm_ticket")
async def confirm_ticket(callback: CallbackQuery, state: FSMContext):
    """Подтверждение и создание тикета"""
    try:
        user = await db.get_user(callback.from_user.id)
        if not user:
            await callback.answer(_('errors.user_not_found'), show_alert=True)
            return
        
        data = await state.get_data()
        category = data.get('category')
        message_text = data.get('message_text')
        
        # Создаем тикет
        async with db.async_session() as session:
            ticket = SupportTicket(
                user_id=user.id,
                category=category,
                message=message_text,
                subject=_('support.admin.new_ticket', id='{id}'),
                status='open',
                created_at=datetime.utcnow()
            )
            session.add(ticket)
            await session.commit()
            await session.refresh(ticket)
            
            # Обновляем subject с правильным ID
            ticket.subject = _('support.admin.new_ticket', id=ticket.id)
            await session.commit()
            
            # Уведомляем пользователя
            success_text = _('support.ticket.created', id=ticket.id)
            
            await callback.message.edit_text(
                success_text,
                reply_markup=InlineKeyboardBuilder()
                .button(text=_('support.my_tickets'), callback_data="my_tickets")
                .button(text=f"◀️ {_('common.back')}", callback_data="support")
                .adjust(1)
                .as_markup()
            )
            
            # Уведомляем админов
            admin_text = _('support.admin.new_ticket', id=ticket.id) + "\n"
            admin_text += _('support.admin.from', 
                          username=callback.from_user.username or 'без username',
                          user_id=callback.from_user.id) + "\n"
            admin_text += _('support.admin.category', 
                          category=category) + "\n\n"
            admin_text += _('support.admin.message') + "\n"
            admin_text += message_text
            
            admin_builder = InlineKeyboardBuilder()
            admin_builder.button(
                text=_('support.admin.take_ticket'),
                callback_data=f"take_ticket_{ticket.id}"
            )
            admin_builder.button(
                text=_('support.admin.reply_ticket'),
                callback_data=f"reply_ticket_{ticket.id}"
            )
            admin_builder.button(
                text=_('support.admin.close_ticket'),
                callback_data=f"close_ticket_{ticket.id}"
            )
            admin_builder.adjust(1)
            
            for admin_id in settings.ADMIN_IDS:
                try:
                    await callback.bot.send_message(
                        admin_id,
                        admin_text,
                        reply_markup=admin_builder.as_markup()
                    )
                except Exception as e:
                    logger.error(f"Failed to notify admin {admin_id}: {e}")
            
            await state.clear()
            await callback.answer()
            
    except Exception as e:
        logger.error(f"Error creating ticket: {e}")
        await callback.answer(_('errors.error'), show_alert=True)

@router.message(F.text.regexp(r"^/ticket_(\d+)$"))
async def show_ticket(message: Message):
    """Показать тикет (для админов)"""
    if message.from_user.id not in settings.ADMIN_IDS:
        return
    
    ticket_id = int(message.text.split("_")[1])
    
    async with db.async_session() as session:
        ticket = await session.get(SupportTicket, ticket_id)
        
        if not ticket:
            await message.answer("❌ Тикет не найден")
            return
        
        # Получаем информацию о пользователе
        user = await session.get(User, ticket.user_id)
        
        status_emoji = {
            'open': '🔴',
            'in_progress': '🟡',
            'resolved': '🟢',
            'closed': '⚫'
        }
        
        text = f"""
📋 <b>Тикет #{ticket.id}</b>

👤 <b>Пользователь:</b> @{user.username or 'user'} (ID: {user.telegram_id})
📅 <b>Создан:</b> {ticket.created_at.strftime('%d.%m.%Y %H:%M')}
📋 <b>Категория:</b> {ticket.category}
{status_emoji.get(ticket.status, '❓')} <b>Статус:</b> {ticket.status}

📝 <b>Сообщение:</b>
{ticket.message}
"""
        
        if ticket.admin_response:
            text += f"\n\n💬 <b>Ответ поддержки:</b>\n{ticket.admin_response}"
            text += f"\n👤 <b>Ответил:</b> Admin ID {ticket.admin_id}"
        
        # Кнопки для админа
        builder = InlineKeyboardBuilder()
        
        if ticket.status == 'open':
            builder.button(text="📝 Взять в работу", callback_data=f"take_ticket_{ticket.id}")
        elif ticket.status == 'in_progress' and ticket.admin_id == message.from_user.id:
            builder.button(text="💬 Ответить", callback_data=f"reply_ticket_{ticket.id}")
            builder.button(text="✅ Закрыть", callback_data=f"close_ticket_{ticket.id}")
        
        builder.adjust(1)
        
        await message.answer(text, reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("take_ticket_"))
async def take_ticket(callback: CallbackQuery):
    """Взять тикет в работу (для админов)"""
    if callback.from_user.id not in settings.ADMIN_IDS:
        await callback.answer(_('admin.access_denied'), show_alert=True)
        return
    
    ticket_id = int(callback.data.split("_")[2])
    
    async with db.async_session() as session:
        ticket = await session.get(SupportTicket, ticket_id)
        
        if ticket and ticket.status == 'open':
            ticket.status = 'in_progress'
            ticket.admin_id = callback.from_user.id
            ticket.updated_at = datetime.utcnow()
            
            await session.commit()
            
            await callback.answer(_('support.admin.ticket_taken'))
            
            # Обновляем кнопки
            builder = InlineKeyboardBuilder()
            builder.button(
                text=_('support.admin.reply_ticket'),
                callback_data=f"reply_ticket_{ticket_id}"
            )
            builder.button(
                text=_('support.admin.close_ticket'),
                callback_data=f"close_ticket_{ticket_id}"
            )
            builder.adjust(1)
            
            await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
        else:
            await callback.answer(_('support.admin.ticket_in_progress'), show_alert=True)

@router.callback_query(F.data.startswith("reply_ticket_"))
async def reply_ticket(callback: CallbackQuery, state: FSMContext):
    """Ответить на тикет (для админов)"""
    if callback.from_user.id not in settings.ADMIN_IDS:
        await callback.answer(_('admin.access_denied'), show_alert=True)
        return
    
    ticket_id = int(callback.data.split("_")[2])
    await state.update_data(ticket_id=ticket_id)
    
    await callback.message.edit_text(
        _('support.admin.reply_instruction'),
        reply_markup=InlineKeyboardBuilder()
        .button(text=_('common.cancel'), callback_data="cancel_reply")
        .as_markup()
    )
    
    await state.set_state(SupportStates.admin_replying)
    await callback.answer()

@router.callback_query(F.data.startswith("close_ticket_"))
async def close_ticket(callback: CallbackQuery):
    """Закрыть тикет (для админов)"""
    if callback.from_user.id not in settings.ADMIN_IDS:
        await callback.answer(_('admin.access_denied'), show_alert=True)
        return
    
    ticket_id = int(callback.data.split("_")[2])
    
    async with db.async_session() as session:
        ticket = await session.get(SupportTicket, ticket_id)
        
        if ticket and ticket.status != 'closed':
            ticket.status = 'closed'
            ticket.admin_id = callback.from_user.id
            ticket.updated_at = datetime.utcnow()
            
            await session.commit()
            
            # Получаем пользователя
            user = await session.get(User, ticket.user_id)
            
            if user:
                try:
                    # Уведомляем пользователя
                    await callback.bot.send_message(
                        user.telegram_id,
                        _('support.admin.ticket_closed_notify', id=ticket_id)
                    )
                except Exception as e:
                    logger.error(f"Error notifying user {user.telegram_id}: {e}")
            
            await callback.answer(_('support.admin.ticket_closed'))
            
            # Обновляем сообщение
            await callback.message.edit_text(
                callback.message.text + f"\n\n✅ {_('support.admin.ticket_closed')}"
            )
        else:
            await callback.answer(_('support.admin.ticket_already_closed'), show_alert=True)

@router.message(SupportStates.admin_replying, F.text)
async def process_reply(message: Message, state: FSMContext):
    """Обработка ответа на тикет"""
    if message.from_user.id not in settings.ADMIN_IDS:
        return
    
    data = await state.get_data()
    ticket_id = data.get('ticket_id')
    
    if not ticket_id:
        await message.answer(_('support.admin.ticket_error'))
        await state.clear()
        return
    
    async with db.async_session() as session:
        ticket = await session.get(SupportTicket, ticket_id)
        
        if not ticket:
            await message.answer(_('support.admin.ticket_not_found'))
            await state.clear()
            return
        
        # Закрываем тикет и сохраняем ответ
        ticket.status = 'resolved'
        ticket.admin_id = message.from_user.id
        ticket.admin_response = message.text
        ticket.updated_at = datetime.utcnow()
        
        await session.commit()
        
        # Получаем пользователя
        user = await session.get(User, ticket.user_id)
        
        if user:
            try:
                # Отправляем ответ пользователю
                await message.bot.send_message(
                    user.telegram_id,
                    _('support.admin.reply_notify', 
                      id=ticket_id, 
                      message=message.text)
                )
            except Exception as e:
                logger.error(f"Error sending reply to user {user.telegram_id}: {e}")
        
        await message.answer(_('support.admin.reply_sent', id=ticket_id))
        await state.clear()

@router.callback_query(F.data == "cancel_reply")
async def cancel_reply(callback: CallbackQuery, state: FSMContext):
    """Отмена ответа на тикет"""
    await state.clear()
    await callback.message.edit_text(_('support.admin.cancel_reply'))
    await callback.answer()

@router.callback_query(F.data == "my_tickets")
async def my_tickets(callback: CallbackQuery):
    """Показать мои тикеты"""
    try:
        user = await db.get_user(callback.from_user.id)
        if not user:
            await callback.answer(_('errors.user_not_found'), show_alert=True)
            return
        
        async with db.async_session() as session:
            tickets = await session.execute(
                select(SupportTicket)
                .where(SupportTicket.user_id == user.id)
                .order_by(SupportTicket.created_at.desc())
            )
            tickets = tickets.scalars().all()
        
        if not tickets:
            await callback.message.edit_text(
                _('support.ticket.my_tickets_empty'),
                reply_markup=InlineKeyboardBuilder()
                .button(text=_('support.menu.new_ticket_button'), callback_data="support_new_ticket")
                .button(text=f"◀️ {_('common.back')}", callback_data="support")
                .adjust(1)
                .as_markup()
            )
            await callback.answer()
            return
        
        text = _('support.ticket.my_tickets_list') + "\n\n"
        
        for ticket in tickets:
            status_emoji = {
                'open': '🔴',
                'in_progress': '🟡',
                'resolved': '🟢',
                'closed': '⚫'
            }.get(ticket.status, '⚪')
            
            status_text = _('support.ticket.status.' + ticket.status)
            
            text += f"{status_emoji} #{ticket.id} - {status_text}\n"
            text += f"📅 {ticket.created_at.strftime('%d.%m.%Y %H:%M')}\n"
            text += f"📝 {ticket.message[:50]}{'...' if len(ticket.message) > 50 else ''}\n\n"
        
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardBuilder()
            .button(text=_('support.menu.new_ticket_button'), callback_data="support_new_ticket")
            .button(text=f"◀️ {_('common.back')}", callback_data="support")
            .adjust(1)
            .as_markup()
        )
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error in my_tickets: {e}")
        await callback.answer(_('errors.error'), show_alert=True)
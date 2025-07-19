import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.keyboard.inline import get_history_keyboard, get_back_keyboard
from bot.utils.messages import MessageTemplates
from services.database import db
from core.constants import STATUS_EMOJIS, GenerationStatus
from bot.middlewares.i18n import i18n
from core.config import settings

logger = logging.getLogger(__name__)

router = Router(name="balance")

@router.message(F.text == "/history")
@router.callback_query(F.data == "history")
async def show_history(update: Message | CallbackQuery, page: int = 1):
    """Показать историю генераций"""
    user_id = update.from_user.id
    user = await db.get_user(user_id)
    
    if not user:
        if isinstance(update, CallbackQuery):
            await update.answer(_('errors.use_start'), show_alert=True)
        else:
            await update.answer(_('errors.use_start'))
        return
    
    # Получаем функцию перевода
    _ = lambda key, **kwargs: i18n.get(key, user.language_code or 'ru', **kwargs)
    
    # Получаем генерации
    limit = 10
    offset = (page - 1) * limit
    generations = await db.get_user_generations(user.id, limit=limit, offset=offset)
    
    # Получаем общее количество
    stats = await db.get_user_statistics(user_id)
    total_generations = stats.get('total_generations', 0)
    total_pages = max(1, (total_generations + limit - 1) // limit)
    
    if not generations:
        text = _('history.empty')
        keyboard = InlineKeyboardBuilder()
        keyboard.button(text=_("menu.generate"), callback_data="generate")
        keyboard.button(text=_("menu.main_menu"), callback_data="back_to_menu")
        keyboard.adjust(1)
        
        if isinstance(update, CallbackQuery):
            await update.message.edit_text(text, reply_markup=keyboard.as_markup())
            await update.answer()
        else:
            await update.answer(text, reply_markup=keyboard.as_markup())
        return
    
    # Формируем текст
    text = f"{_('history.title')} ({_('common.page', page=page, total=total_pages)})\n\n"
    
    for gen in generations:
        status_emoji = STATUS_EMOJIS.get(gen.status, "❓")
        date = MessageTemplates.format_date(gen.created_at)
        mode_text = "T2V" if gen.mode == "t2v" else "I2V"
        
        text += f"{status_emoji} <b>{date}</b> - {mode_text} {gen.resolution}\n"
        if gen.status == GenerationStatus.COMPLETED and gen.rating:
            text += f"   ⭐ {_('history.rating', rating=gen.rating)}\n"
        text += "\n"
    
    # Показываем историю
    keyboard = get_history_keyboard(generations, page, total_pages, user.language_code)
    
    if isinstance(update, CallbackQuery):
        await update.message.edit_text(text, reply_markup=keyboard)
        await update.answer()
    else:
        await update.answer(text, reply_markup=keyboard)

@router.callback_query(F.data.startswith("history_page_"))
async def history_pagination(callback: CallbackQuery):
    """Переход по страницам истории"""
    try:
        page = int(callback.data.split("_")[2])
        await show_history(callback, page=page)
    except ValueError:
        await callback.answer(_('errors.navigation'), show_alert=True)

@router.callback_query(F.data.startswith("gen_details_"))
async def show_generation_details(callback: CallbackQuery):
    """Показать детали генерации"""
    try:
        generation_id = int(callback.data.split("_")[2])
    except ValueError:
        await callback.answer(_('errors.invalid_generation_id'), show_alert=True)
        return
    
    # Получаем генерацию
    generation = await db.get_generation(generation_id)
    if not generation:
        await callback.answer(_('errors.generation_not_found'), show_alert=True)
        return
    
    # Проверяем владельца
    user = await db.get_user(callback.from_user.id)
    if not user or generation.user_id != user.id:
        await callback.answer("Доступ запрещен", show_alert=True)
        return
    
    # Получаем функцию перевода
    _ = lambda key, **kwargs: i18n.get(key, user.language_code or 'ru', **kwargs)
    
    # Формируем текст
    mode_text = MessageTemplates.get_mode_text(generation.mode)
    status_text = MessageTemplates.get_status_text(generation.status)
    
    additional_info = ""
    if generation.status == GenerationStatus.COMPLETED:
        if generation.generation_time:
            additional_info += f"\n⏱ <b>{_('generation.generation_time')}:</b> {int(generation.generation_time)} {_('generation.seconds', default='сек')}"
        if generation.video_url or generation.video_file_id:
            additional_info += f"\n🔗 <b>{_('generation.video_available', default='Видео доступно')}</b>"
    elif generation.status == GenerationStatus.FAILED:
        if generation.error_message:
            additional_info += f"\n❌ <b>{_('errors.error')}:</b> {generation.error_message[:200]}"
    
    text = f"{_('history.details')}\n\n"
    text += f"🆔 <b>ID:</b> <code>{generation.id}</code>\n"
    text += f"{_('history.date', date=generation.created_at.strftime('%d.%m.%Y %H:%M'))}\n"
    text += f"{_('history.status', status=status_text)}\n\n"
    text += f"{_('history.parameters')}\n"
    text += f"{_('history.mode', mode=mode_text)}\n"
    text += f"{_('history.model', model=generation.model)}\n"
    text += f"{_('history.resolution', resolution=generation.resolution.upper())}\n"
    text += f"{_('history.duration', duration=generation.duration)}\n"
    text += f"{_('history.cost', cost=generation.cost)}\n\n"
    text += f"{_('history.prompt')}\n"
    prompt_text = generation.prompt[:500] + "..." if len(generation.prompt) > 500 else generation.prompt
    text += f"<i>{prompt_text}</i>"
    text += additional_info
    
    # Кнопки
    builder = InlineKeyboardBuilder()
    
    if generation.status == GenerationStatus.COMPLETED and (generation.video_url or generation.video_file_id):
        builder.button(
            text=f"🎬 {_('generation.view_video', default='Посмотреть видео')}", 
            callback_data=f"view_video_{generation.id}"
        )
    
    if generation.status == GenerationStatus.COMPLETED and not generation.rating:
        builder.button(
            text=f"⭐ {_('generation.rate_video')}", 
            callback_data=f"rate_gen_{generation.id}"
        )
    
    # Кнопка повтора для неудачных генераций
    if generation.status == GenerationStatus.FAILED:
        builder.button(
            text=f"🔄 {_('generation.retry', default='Повторить')}", 
            callback_data="generate"
        )
    
    builder.button(
        text=f"◀️ {_('history.back_to_history', default='К истории')}", 
        callback_data="history"
    )
    builder.adjust(1)
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()

@router.callback_query(F.data.startswith("view_video_"))
async def view_video(callback: CallbackQuery):
    """Показать видео из истории"""
    try:
        generation_id = int(callback.data.split("_")[2])
    except ValueError:
        await callback.answer("Неверный ID", show_alert=True)
        return
    
    # Получаем генерацию
    generation = await db.get_generation(generation_id)
    if not generation:
        await callback.answer("Видео не найдено", show_alert=True)
        return
    
    # Проверяем владельца
    user = await db.get_user(callback.from_user.id)
    if not user or generation.user_id != user.id:
        await callback.answer("Доступ запрещен", show_alert=True)
        return
    
    # Получаем функцию перевода
    _ = lambda key, **kwargs: i18n.get(key, user.language_code or 'ru', **kwargs)
    
    # Отправляем видео
    try:
        caption = (
            f"🎬 {_('video.title', id=generation.id)}\n"
            f"📅 {generation.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
            f"📝 {generation.prompt[:200]}..."
        )
        
        # Если есть file_id телеграма (предпочтительно)
        if generation.video_file_id and generation.video_file_id.startswith(('BAA', 'CAA', 'DAA')):
            await callback.message.answer_video(
                generation.video_file_id,
                caption=caption
            )
            await callback.answer(f"📤 {_('video.sending', default='Отправляю видео...')}")
        # Если есть внешний URL
        elif generation.video_url:
            # Пробуем скачать и отправить
            try:
                from services.wavespeed_api import get_wavespeed_api
                api = get_wavespeed_api()
                video_data = await api.download_video(generation.video_url)
                
                # Если видео создано на бонусные кредиты, добавляем QR-код
                if generation.used_bonus_credits:
                    try:
                        from services.video_processor import add_qr_code_to_video
                        logger.info(f"Adding QR code to video {generation.id} (created with bonus credits)")
                        video_data = await add_qr_code_to_video(video_data)
                    except Exception as e:
                        logger.error(f"Error adding QR code to video {generation.id}: {e}")
                        # Продолжаем без QR-кода в случае ошибки
                
                from aiogram.types import BufferedInputFile
                video_file = BufferedInputFile(
                    video_data,
                    filename=f"seedance_{generation.id}.mp4"
                )
                
                sent_msg = await callback.message.answer_video(
                    video_file,
                    caption=caption
                )
                
                # Сохраняем file_id для будущего использования
                if sent_msg.video:
                    await db.update_generation_video_file_id(generation.id, sent_msg.video.file_id)
                
                await callback.answer(f"📤 {_('video.sending', default='Отправляю видео...')}")
            except Exception as e:
                logger.error(f"Error downloading video: {e}")
                # Если не удалось скачать, отправляем ссылку
                await callback.message.answer(
                    f"🎬 {_('video.link_available', default='Ваше видео доступно по ссылке')}:\n{generation.video_url}"
                )
                await callback.answer()
        else:
            await callback.answer(
                _('video.not_found', default='Видео не найдено'), 
                show_alert=True
            )
        
    except Exception as e:
        logger.error(f"Error sending video: {e}")
        await callback.answer(
            _('video.send_error', default='Ошибка при отправке видео'), 
            show_alert=True
        )

@router.callback_query(F.data.startswith("rate_gen_"))
async def rate_generation_from_history(callback: CallbackQuery):
    """Оценить генерацию из истории"""
    try:
        generation_id = int(callback.data.split("_")[2])
    except ValueError:
        await callback.answer("Неверный ID", show_alert=True)
        return
    
    # Получаем генерацию
    generation = await db.get_generation(generation_id)
    if not generation:
        await callback.answer("Генерация не найдена", show_alert=True)
        return
    
    # Проверяем владельца
    user = await db.get_user(callback.from_user.id)
    if not user or generation.user_id != user.id:
        await callback.answer("Доступ запрещен", show_alert=True)
        return
    
    # Получаем функцию перевода
    _ = lambda key, **kwargs: i18n.get(key, user.language_code or 'ru', **kwargs)
    
    # Показываем клавиатуру оценки
    builder = InlineKeyboardBuilder()
    for i in range(1, 6):
        builder.button(text="⭐" * i, callback_data=f"history_rate_{generation_id}_{i}")
    builder.button(text=f"◀️ {_('common.back')}", callback_data="history")
    builder.adjust(5, 1)
    
    await callback.message.edit_text(
        f"⭐ <b>{_('generation.rate_generation', id=generation_id)}</b>\n\n"
        f"{_('generation.choose_rating', default='Выберите оценку от 1 до 5 звезд')}:"
    )
    await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
    await callback.answer()

@router.callback_query(F.data.startswith("history_rate_"))
async def save_rating_from_history(callback: CallbackQuery):
    """Сохранить оценку из истории"""
    try:
        parts = callback.data.split("_")
        generation_id = int(parts[2])
        rating = int(parts[3])
        
        if rating < 1 or rating > 5:
            raise ValueError("Invalid rating")
        
        # Проверяем владельца
        generation = await db.get_generation(generation_id)
        user = await db.get_user(callback.from_user.id)
        
        if not generation or not user or generation.user_id != user.id:
            await callback.answer("Доступ запрещен", show_alert=True)
            return
        
        # Сохраняем оценку
        await db.rate_generation(generation_id, rating)
        
        # Получаем функцию перевода
        _ = lambda key, **kwargs: i18n.get(key, user.language_code or 'ru', **kwargs)
        
        # Возвращаемся к деталям
        await callback.answer(f"✅ {_('generation.rating_saved', default='Спасибо за оценку!')}")
        
        # Обновляем callback data для показа деталей
        callback.data = f"gen_details_{generation_id}"
        await show_generation_details(callback)
        
    except (ValueError, IndexError):
        await callback.answer("Ошибка сохранения оценки", show_alert=True)

@router.callback_query(F.data == "statistics")
async def show_statistics(callback: CallbackQuery):
    """Показать статистику пользователя"""
    user_id = callback.from_user.id
    user = await db.get_user(user_id)
    
    if not user:
        await callback.answer("Используйте /start", show_alert=True)
        return
    
    stats = await db.get_user_statistics(user_id)
    
    # Получаем функцию перевода
    _ = lambda key, **kwargs: i18n.get(key, user.language_code or 'ru', **kwargs)
    
    # Форматируем язык
    from core.constants import LANGUAGES
    language_name = LANGUAGES.get(user.language_code or 'ru', {}).get('name', 'Русский')
    
    # Форматируем даты
    reg_date = user.created_at.strftime("%d.%m.%Y") if user.created_at else "—"
    last_gen = MessageTemplates.format_date(stats.get('last_generation')) if stats.get('last_generation') else _('history.no_generations', default="Нет генераций")
    
    # Вычисляем средние показатели
    avg_gen_per_day = 0
    if user.created_at:
        from datetime import datetime
        days_since_reg = (datetime.utcnow() - user.created_at).days or 1
        avg_gen_per_day = stats.get('total_generations', 0) / days_since_reg
    
    text = f"📊 <b>{_('statistics.title', default='Статистика')}</b>\n\n"
    text += f"👤 <b>{_('statistics.profile', default='Профиль')}:</b>\n"
    text += f"├ 🆔 ID: <code>{user.telegram_id}</code>\n"
    text += f"├ 📅 {_('statistics.registration', default='Регистрация')}: {reg_date}\n"
    text += f"└ 🌐 {_('statistics.language', default='Язык')}: {language_name}\n\n"
    
    text += f"💰 <b>{_('statistics.balance', default='Баланс')}:</b>\n"
    text += f"├ 💳 {_('statistics.current', default='Текущий')}: {user.balance} {_('common.credits')}\n"
    text += f"├ 📥 {_('statistics.total_bought', default='Куплено')}: {user.total_bought} {_('common.credits')}\n"
    text += f"├ 🎁 {_('statistics.bonuses_received', default='Получено бонусов')}: {stats.get('total_bonuses', 0)} {_('common.credits')}\n"
    text += f"└ 📤 {_('statistics.total_spent', default='Потрачено')}: {user.total_spent} {_('common.credits')}\n\n"
    
    text += f"🎬 <b>{_('statistics.generations', default='Генерации')}:</b>\n"
    text += f"├ 📊 {_('statistics.total', default='Всего')}: {stats.get('total_generations', 0)}\n"
    text += f"├ ✅ {_('statistics.successful', default='Успешных')}: {stats.get('successful_generations', 0)}\n"
    text += f"├ ❌ {_('statistics.failed', default='Неудачных')}: {stats.get('total_generations', 0) - stats.get('successful_generations', 0)}\n"
    text += f"├ ⭐ {_('statistics.avg_rating', default='Средняя оценка')}: {stats.get('average_rating', 0):.1f}/5\n"
    text += f"└ 📈 {_('statistics.avg_per_day', default='В среднем в день')}: {avg_gen_per_day:.1f}\n\n"
    
    text += f"📈 <b>{_('statistics.activity', default='Активность')}:</b>\n"
    text += f"├ 📅 {_('statistics.last_generation', default='Последняя генерация')}: {last_gen}\n"
    text += f"├ 🔥 {_('statistics.current_streak', default='Текущая серия')}: {stats.get('current_streak', 0)} {_('common.days', default='дней')}\n"
    text += f"└ 🏆 {_('statistics.max_streak', default='Максимальная серия')}: {stats.get('max_streak', 0)} {_('common.days', default='дней')}"
    
    # Кнопки
    builder = InlineKeyboardBuilder()
    builder.button(text=_("menu.history"), callback_data="history")
    builder.button(text=_("menu.main_menu"), callback_data="back_to_menu")
    builder.adjust(2, 1)
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()
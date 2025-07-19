import logging
import asyncio
from io import BytesIO
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.keyboard.inline import (
    get_generation_mode_keyboard, get_model_selection_keyboard,
    get_resolution_keyboard, get_duration_keyboard,
    get_aspect_ratio_keyboard, get_generation_confirm_keyboard,
    get_generation_rating_keyboard, get_cancel_keyboard
)
from bot.utils.messages import MessageTemplates
from services.database import db
from services.wavespeed_api import get_wavespeed_api, GenerationRequest, calculate_generation_cost
from services.api_monitor import api_monitor
from core.constants import GENERATION_COSTS, GenerationStatus, ModelType, MODEL_INFO
from bot.middlewares.throttling import rate_limit, GenerationThrottling
from bot.middlewares.i18n import i18n

logger = logging.getLogger(__name__)

class GenerationStates(StatesGroup):
    choosing_mode = State()
    choosing_model = State()
    choosing_resolution = State()
    choosing_duration = State()
    choosing_aspect_ratio = State()
    choosing_audio = State()  # Новое состояние для выбора аудио (Google Veo3)
    entering_prompt = State()
    uploading_image = State()
    confirming = State()
    processing = State()

router = Router(name="generation")

@router.message(F.text == "/generate")
@router.callback_query(F.data == "generate")
async def start_generation(update: Message | CallbackQuery, state: FSMContext):
    """Начало генерации видео"""
    # Очищаем предыдущее состояние
    await state.clear()
    
    # Получаем пользователя
    user_id = update.from_user.id
    user = await db.get_user(user_id)
    
    if not user:
        error_msg = _('errors.please_use_start')
        if isinstance(update, CallbackQuery):
            await update.answer(error_msg, show_alert=True)
        else:
            await update.answer(error_msg)
        return
    
    # Проверяем бан
    if user.is_banned:
        ban_msg = _('errors.user_banned_msg', default="Ваш аккаунт заблокирован. Обратитесь в поддержку: /support")
        if isinstance(update, CallbackQuery):
            await update.answer(ban_msg, show_alert=True)
        else:
            await update.answer(ban_msg)
        return
    
    # Получаем функцию перевода
    _ = lambda key, **kwargs: i18n.get(key, user.language_code or 'ru', **kwargs)
    
    # Проверяем баланс
    if user.balance < 3:  # Минимальная стоимость генерации
        text = f"❌ <b>{_('errors.insufficient_balance')}</b>\n\n"
        text += f"💰 {_('menu.balance', balance=user.balance)}\n"
        text += f"💎 {_('generation.min_cost', default='Минимальная стоимость генерации')}: 3 {_('common.credits')}\n\n"
        text += _('generation.need_more_credits', default='Пополните баланс для продолжения.')
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=_("menu.buy_credits"), callback_data="shop"),
            InlineKeyboardButton(text=_("common.back"), callback_data="back_to_menu")
        ]])
        
        if isinstance(update, CallbackQuery):
            await update.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
            await update.answer()
        else:
            await update.answer(text, reply_markup=keyboard, parse_mode="HTML")
        return
    
    # Создаем красивое сообщение выбора режима
    text = f"""
{_("generation.beautiful.divider")}
{_("generation.beautiful.create_title")}
{_("generation.beautiful.ai_magic")}
{_("generation.beautiful.divider")}

{_("generation.beautiful.mode_selection")}
{_("generation.beautiful.mode_description")}

{_("generation.beautiful.t2v_title")}
{_("generation.beautiful.t2v_desc")}
{_("generation.beautiful.t2v_features")}

{_("generation.beautiful.i2v_title")}
{_("generation.beautiful.i2v_desc")}
{_("generation.beautiful.i2v_features")}

{_("generation.beautiful.divider")}
"""
    
    if isinstance(update, CallbackQuery):
        await update.message.edit_text(text, reply_markup=get_generation_mode_keyboard(user.language_code), parse_mode="HTML")
        await update.answer()
    else:
        await update.answer(text, reply_markup=get_generation_mode_keyboard(user.language_code), parse_mode="HTML")
    
    await state.set_state(GenerationStates.choosing_mode)

@router.callback_query(GenerationStates.choosing_mode, F.data.in_(["mode_t2v", "mode_i2v"]))
async def choose_mode(callback: CallbackQuery, state: FSMContext):
    """Выбор режима генерации"""
    mode = callback.data.split("_")[1]
    await state.update_data(mode=mode)
    
    # Получаем пользователя и функцию перевода
    user = await db.get_user(callback.from_user.id)
    _ = lambda key, **kwargs: i18n.get(key, user.language_code or 'ru', **kwargs)
    
    # Определяем название выбранного режима
    mode_text = _('generation.text_to_video') if mode == "t2v" else _('generation.image_to_video')
    
    # Создаем красивое сообщение выбора модели
    text = f"""
{_("generation.beautiful.divider")}
{_("generation.beautiful.create_title")}
{_("generation.beautiful.ai_magic")}
{_("generation.beautiful.divider")}

{_("generation.beautiful.model_selection")}
{_("generation.beautiful.model_subtitle")}

📌 <b>Выбранный режим:</b> {mode_text}

{_("generation.beautiful.lite_title")}
{_("generation.beautiful.lite_desc")}
{_("generation.beautiful.lite_features")}

{_("generation.beautiful.pro_title")}
{_("generation.beautiful.pro_desc")}
{_("generation.beautiful.pro_features")}

{_("generation.beautiful.divider")}
"""
    
    await callback.message.edit_text(text, reply_markup=get_model_selection_keyboard(mode, user.language_code), parse_mode="HTML")
    await state.set_state(GenerationStates.choosing_model)
    await callback.answer()

@router.callback_query(GenerationStates.choosing_model, F.data.startswith("model_"))
async def choose_model(callback: CallbackQuery, state: FSMContext):
    """Выбор модели"""
    parts = callback.data.split("_")
    
    # Обработка Google Veo3 моделей
    if len(parts) >= 4 and parts[1] == "veo3":
        if parts[2] == "fast":
            model_type = "veo3_fast"
            mode = parts[3]
        else:
            model_type = "veo3"
            mode = parts[2]
    else:
        model_type = parts[1]  # lite или pro
        mode = parts[2]  # t2v или i2v
    
    await state.update_data(model_type=model_type)
    
    # Получаем пользователя и функцию перевода
    user = await db.get_user(callback.from_user.id)
    _ = lambda key, **kwargs: i18n.get(key, user.language_code or 'ru', **kwargs)
    
    # Определяем названия
    mode_text = _('generation.text_to_video') if mode == "t2v" else _('generation.image_to_video')
    
    # Google Veo3 модели имеют фиксированные настройки
    if model_type in ["veo3", "veo3_fast"]:
        model_info = MODEL_INFO[model_type]
        model_text = model_info["name"]
        
        # Для Google Veo3 переходим сразу к настройкам аудио
        text = f"""
{_("generation.beautiful.divider")}
{_("generation.beautiful.create_title")} - {model_text}
{_("generation.beautiful.ai_magic")}
{_("generation.beautiful.divider")}

📌 <b>Выбрано:</b>
├ 🎯 Режим: {mode_text}
├ 🤖 Модель: {model_text}
├ 📐 Разрешение: 1080p (фиксированно)
├ ⏱️ Длительность: 8 секунд (фиксированно)
└ 📱 Соотношение: 16:9 (по умолчанию)

🎵 <b>Генерация аудио:</b>
Включить синхронизированное аудио для видео?
• Диалоги с синхронизацией губ
• Фоновые звуки и музыка
• Естественные звуковые эффекты

💡 <b>Совет:</b> Аудио делает видео более реалистичным, но увеличивает время генерации.

{_("generation.beautiful.divider")}
"""
        
        # Создаем клавиатуру для выбора аудио
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        builder = InlineKeyboardBuilder()
        builder.button(text="🎵 Включить аудио", callback_data="audio_on")
        builder.button(text="🔇 Без аудио", callback_data="audio_off")
        builder.button(text=f"◀️ {_('common.back')}", callback_data="back_to_model")
        builder.adjust(1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await state.set_state(GenerationStates.choosing_audio)
        await callback.answer()
        return
    
    # Для обычных моделей (Seedance)
    model_text = "Pro" if model_type == "pro" else "Lite"
    
    # Создаем красивое сообщение настроек
    text = f"""
{_("generation.beautiful.divider")}
{_("generation.beautiful.create_title")}
{_("generation.beautiful.ai_magic")}
{_("generation.beautiful.divider")}

{_("generation.beautiful.settings_title")}
{_("generation.beautiful.quality_resolution")}

📌 <b>Выбрано:</b>
├ 🎯 Режим: {mode_text}
└ 🤖 Модель: Seedance V1 {model_text}

{_("generation.beautiful.resolution_desc")}

💡 <b>Совет:</b> {_('generation.beautiful.resolution_tip')}

{_("generation.beautiful.divider")}
"""
    
    await callback.message.edit_text(text, reply_markup=get_resolution_keyboard(model_type, user.language_code), parse_mode="HTML")
    await state.set_state(GenerationStates.choosing_resolution)
    await callback.answer()

@router.callback_query(GenerationStates.choosing_audio, F.data.in_(["audio_on", "audio_off"]))
async def choose_audio(callback: CallbackQuery, state: FSMContext):
    """Выбор настроек аудио для Google Veo3"""
    generate_audio = callback.data == "audio_on"
    await state.update_data(generate_audio=generate_audio)
    
    # Получаем пользователя и функцию перевода
    user = await db.get_user(callback.from_user.id)
    _ = lambda key, **kwargs: i18n.get(key, user.language_code or 'ru', **kwargs)
    
    # Получаем данные состояния
    data = await state.get_data()
    model_type = data['model_type']
    mode = data['mode']
    
    mode_text = _('generation.text_to_video') if mode == "t2v" else _('generation.image_to_video')
    model_info = MODEL_INFO[model_type]
    
    audio_text = "🎵 Включено" if generate_audio else "🔇 Отключено"
    
    # Переходим к вводу промпта
    text = f"""
{_("generation.beautiful.divider")}
{_("generation.beautiful.create_title")} - {model_info["name"]}
{_("generation.beautiful.ai_magic")}
{_("generation.beautiful.divider")}

📌 <b>Итоговые настройки:</b>
├ 🎯 Режим: {mode_text}
├ 🤖 Модель: {model_info["name"]}
├ 📐 Разрешение: 1080p
├ ⏱️ Длительность: 8 секунд
├ 📱 Соотношение: 16:9
└ 🎵 Аудио: {audio_text}

📝 <b>Опишите желаемое видео:</b>
Напишите детальное описание того, что вы хотите видеть в кадре.

💡 <b>Советы для лучшего результата:</b>
• Опишите композицию кадра (крупный план, общий план)
• Укажите стиль (реалистичный, анимационный, кинематографичный)
• Добавьте детали освещения и атмосферы
• Опишите движения камеры (приближение, панорама)

{_("generation.beautiful.divider")}
"""
    
    # Создаем клавиатуру для отмены
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text=f"◀️ {_('common.back')}", callback_data="back_to_audio")
    builder.button(text=f"❌ {_('common.cancel')}", callback_data="cancel_generation")
    builder.adjust(1)
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await state.set_state(GenerationStates.entering_prompt)
    await callback.answer()

@router.callback_query(GenerationStates.choosing_resolution, F.data.startswith("res_"))
async def choose_resolution(callback: CallbackQuery, state: FSMContext):
    """Выбор разрешения"""
    resolution = callback.data.split("_")[1]
    await state.update_data(resolution=resolution)
    
    # Получаем данные состояния
    data = await state.get_data()
    
    # Получаем пользователя и функцию перевода
    user = await db.get_user(callback.from_user.id)
    _ = lambda key, **kwargs: i18n.get(key, user.language_code or 'ru', **kwargs)
    
    # Определяем названия
    mode_text = _('generation.text_to_video') if data['mode'] == "t2v" else _('generation.image_to_video')
    model_text = "Pro" if data['model_type'] == "pro" else "Lite"
    
    # Создаем красивое сообщение для выбора длительности
    text = f"""
{_("generation.beautiful.divider")}
{_("generation.beautiful.create_title")}
{_("generation.beautiful.ai_magic")}
{_("generation.beautiful.divider")}

{_("generation.beautiful.settings_title")}
{_("generation.beautiful.duration_time")}

📌 <b>Выбрано:</b>
├ 🎯 Режим: {mode_text}
├ 🤖 Модель: Seedance V1 {model_text}
└ 📐 Разрешение: {resolution}

{_("generation.beautiful.duration_desc")}

💡 <b>Совет:</b> {_('generation.beautiful.duration_tip')}

{_("generation.beautiful.divider")}
"""
    
    await callback.message.edit_text(text, reply_markup=get_duration_keyboard(user.language_code), parse_mode="HTML")
    await state.set_state(GenerationStates.choosing_duration)
    await callback.answer()

@router.callback_query(GenerationStates.choosing_duration, F.data.startswith("dur_"))
async def choose_duration(callback: CallbackQuery, state: FSMContext):
    """Выбор длительности"""
    duration = int(callback.data.split("_")[1])  # Конвертируем в число
    await state.update_data(duration=duration)
    
    # Получаем данные состояния
    data = await state.get_data()
    
    # Получаем пользователя и функцию перевода
    user = await db.get_user(callback.from_user.id)
    _ = lambda key, **kwargs: i18n.get(key, user.language_code or 'ru', **kwargs)
    
    # Определяем названия
    mode_text = _('generation.text_to_video') if data['mode'] == "t2v" else _('generation.image_to_video')
    model_text = "Pro" if data['model_type'] == "pro" else "Lite"
    
    # Создаем красивое сообщение для выбора соотношения сторон
    text = f"""
{_("generation.beautiful.divider")}
{_("generation.beautiful.create_title")}
{_("generation.beautiful.ai_magic")}
{_("generation.beautiful.divider")}

{_("generation.beautiful.settings_title")}
{_("generation.beautiful.aspect_ratio")}

📌 <b>Выбрано:</b>
├ 🎯 Режим: {mode_text}
├ 🤖 Модель: Seedance V1 {model_text}
├ 📐 Разрешение: {data['resolution']}
└ ⏱ Длительность: {duration}с

{_("generation.beautiful.aspect_desc")}

💡 <b>Совет:</b> {_('generation.beautiful.aspect_tip')}

{_("generation.beautiful.divider")}
"""
    
    await callback.message.edit_text(text, reply_markup=get_aspect_ratio_keyboard(user.language_code), parse_mode="HTML")
    await state.set_state(GenerationStates.choosing_aspect_ratio)
    await callback.answer()

@router.callback_query(GenerationStates.choosing_aspect_ratio, F.data.startswith("ratio_"))
async def choose_aspect_ratio(callback: CallbackQuery, state: FSMContext):
    """Выбор соотношения сторон"""
    ratio = callback.data.split("_", 1)[1].replace("_", ":")
    await state.update_data(aspect_ratio=ratio)
    
    # Получаем данные состояния
    data = await state.get_data()
    
    # Получаем пользователя и функцию перевода
    user = await db.get_user(callback.from_user.id)
    _ = lambda key, **kwargs: i18n.get(key, user.language_code or 'ru', **kwargs)
    
    # Определяем названия
    mode_text = _('generation.text_to_video') if data['mode'] == "t2v" else _('generation.image_to_video')
    model_text = "Pro" if data['model_type'] == "pro" else "Lite"
    
    # Переходим к следующему шагу в зависимости от режима
    if data['mode'] == "t2v":
        # Для text-to-video переходим к вводу промта
        text = f"""
{_("generation.beautiful.divider")}
{_("generation.beautiful.create_title")}
{_("generation.beautiful.ai_magic")}
{_("generation.beautiful.divider")}

{_("generation.beautiful.prompt_title")}
{_("generation.beautiful.prompt_subtitle")}

📌 <b>Выбранные настройки:</b>
├ 🎯 Режим: {mode_text}
├ 🤖 Модель: Seedance V1 {model_text}
├ 📐 Разрешение: {data['resolution']}
├ ⏱ Длительность: {data['duration']}с
└ 📏 Соотношение: {ratio}

{_("generation.beautiful.prompt_desc")}

💡 <b>Примеры промтов:</b>
• {_('generation.example_1', default='"Красивый закат над океаном с волнами"')}
• {_('generation.example_2', default='"Котенок играет в саду среди цветов"')}
• {_('generation.example_3', default='"Городская улица в дождь с неоновыми огнями"')}

{_("generation.beautiful.divider")}
"""
        
        await callback.message.edit_text(text, reply_markup=get_cancel_keyboard(user.language_code), parse_mode="HTML")
        await state.set_state(GenerationStates.entering_prompt)
        await callback.answer()
    else:
        # Для image-to-video переходим к запросу изображения
        await request_image_upload(callback, state)

async def request_image_upload(callback: CallbackQuery, state: FSMContext):
    """Запрос загрузки изображения для I2V"""
    # Получаем данные состояния
    data = await state.get_data()
    
    # Получаем пользователя и функцию перевода
    user = await db.get_user(callback.from_user.id)
    _ = lambda key, **kwargs: i18n.get(key, user.language_code or 'ru', **kwargs)
    
    # Определяем названия
    mode_text = _('generation.text_to_video') if data['mode'] == "t2v" else _('generation.image_to_video')
    model_text = "Pro" if data['model_type'] == "pro" else "Lite"
    
    text = f"""
{_("generation.beautiful.divider")}
{_("generation.beautiful.create_title")}
{_("generation.beautiful.ai_magic")}
{_("generation.beautiful.divider")}

{_("generation.beautiful.image_upload")}
{_("generation.beautiful.image_subtitle")}

📌 <b>Выбрано:</b>
├ 🎯 Режим: {mode_text}
├ 🤖 Модель: Seedance V1 {model_text}
├ 📐 Разрешение: {data['resolution'].upper()}
└ ⏱️ Длительность: {data['duration']} сек

📋 <b>Требования к изображению:</b>
{_('generation.image_requirements.format')}
{_('generation.image_requirements.size', max_size=10)}
{_('generation.image_requirements.resolution', min_res=300)}

{_("generation.beautiful.image_quality")}

{_("generation.beautiful.divider")}
"""
    
    await callback.message.edit_text(text, reply_markup=get_cancel_keyboard(user.language_code), parse_mode="HTML")
    await state.set_state(GenerationStates.uploading_image)

@router.message(GenerationStates.entering_prompt, F.text)
async def process_prompt(message: Message, state: FSMContext):
    """Обработка промпта"""
    prompt = message.text.strip()
    
    # Получаем пользователя и функцию перевода
    user = await db.get_user(message.from_user.id)
    _ = lambda key, **kwargs: i18n.get(key, user.language_code or 'ru', **kwargs)
    
    # Валидация длины
    if len(prompt) > 2000:
        await message.answer(
            f"❌ {_('errors.prompt_too_long')} ({len(prompt)} {_('generation.characters', default='символов')})\n"
            f"{_('generation.max_chars', max=2000)}\n\n"
            f"{_('generation.please_shorten', default='Пожалуйста, сократите текст.')}",
            reply_markup=get_cancel_keyboard(user.language_code)
        )
        return
    
    if len(prompt) < 10:
        await message.answer(
            f"❌ {_('errors.prompt_too_short')}\n"
            f"{_('generation.please_elaborate', default='Пожалуйста, опишите подробнее, что вы хотите увидеть.')}",
            reply_markup=get_cancel_keyboard(user.language_code)
        )
        return
    
    await state.update_data(prompt=prompt)
    
    # Показываем подтверждение
    await show_generation_confirmation(message, state)

@router.message(GenerationStates.uploading_image, F.photo)
async def process_image(message: Message, state: FSMContext):
    """Обработка загруженного изображения"""
    # Получаем пользователя и функцию перевода
    user = await db.get_user(message.from_user.id)
    _ = lambda key, **kwargs: i18n.get(key, user.language_code or 'ru', **kwargs)
    
    # Получаем файл наибольшего размера
    photo = message.photo[-1]
    
    # Проверяем размер (10 MB)
    if photo.file_size > 10 * 1024 * 1024:
        await message.answer(
            f"❌ {_('errors.image_too_large')}\n"
            f"{_('generation.max_size', default='Максимальный размер')}: 10 {_('generation.mb', default='МБ')}",
            reply_markup=get_cancel_keyboard(user.language_code)
        )
        return
    
    # Проверяем file_id
    if not photo.file_id or not photo.file_id.startswith(('AgAC', 'AQAD')):
        logger.warning(f"Invalid file_id format: {photo.file_id}")
    
    try:
        # Скачиваем файл
        file = await message.bot.get_file(photo.file_id)
        file_data = BytesIO()
        await message.bot.download_file(file.file_path, file_data)
        
        # Проверяем размер скачанного файла
        file_data.seek(0, 2)  # Переходим в конец
        file_size = file_data.tell()
        file_data.seek(0)  # Возвращаемся в начало
        
        if file_size == 0:
            raise ValueError("Downloaded file is empty")
        
        # Конвертируем в base64
        api = get_wavespeed_api()
        image_base64 = await api.convert_image_to_base64(file_data.getvalue())
        
        # Сохраняем в состоянии
        await state.update_data(
            image_base64=image_base64,
            image_file_id=photo.file_id
        )
        
        # Запрашиваем промпт
        text = f"""
{_("generation.beautiful.divider")}
{_("generation.beautiful.create_title")}
{_("generation.beautiful.ai_magic")}
{_("generation.beautiful.divider")}

{_("generation.beautiful.animation_prompt")}
{_("generation.beautiful.animation_subtitle")}

✅ <b>{_('generation.image_uploaded')}!</b>

{_("generation.beautiful.prompt_creativity")}

{_("generation.beautiful.prompt_examples")}
{_("generation.beautiful.example_1")}
{_("generation.beautiful.example_2")}
{_("generation.beautiful.example_3")}

📝 <b>Примеры анимации:</b>
{_('generation.animation_examples.camera')}
{_('generation.animation_examples.character')}
{_('generation.animation_examples.nature')}

📌 <i>{_('generation.max_chars', max=2000)}</i>

{_("generation.beautiful.divider")}
"""
        
        await message.answer(text, reply_markup=get_cancel_keyboard(user.language_code), parse_mode="HTML")
        await state.set_state(GenerationStates.entering_prompt)
        
    except Exception as e:
        logger.error(f"Error processing image: {e}")
        await message.answer(
            f"❌ {_('generation.image_error', default='Ошибка при обработке изображения')}\n"
            f"{_('generation.try_another_image', default='Пожалуйста, попробуйте другое изображение.')}",
            reply_markup=get_cancel_keyboard(user.language_code)
        )
        # Не сбрасываем состояние, позволяем попробовать еще раз

@router.message(GenerationStates.uploading_image)
async def handle_non_photo_upload(message: Message, state: FSMContext):
    """Обработка неправильного типа файла"""
    user = await db.get_user(message.from_user.id)
    _ = lambda key, **kwargs: i18n.get(key, user.language_code or 'ru', **kwargs)
    
    await message.answer(
        f"❌ {_('errors.invalid_file_type', default='Неверный тип файла')}\n"
        f"{_('generation.photo_only', default='Пожалуйста, отправьте фото (не документ).')}",
        reply_markup=get_cancel_keyboard(user.language_code)
    )

async def show_generation_confirmation(message: Message, state: FSMContext):
    """Показать подтверждение генерации"""
    data = await state.get_data()
    
    # Получаем пользователя и функцию перевода
    user = await db.get_user(message.from_user.id)
    _ = lambda key, **kwargs: i18n.get(key, user.language_code or 'ru', **kwargs)
    
    # Формируем название модели
    if data['model_type'] in ["veo3", "veo3_fast"]:
        # Google Veo3 models
        model_name = "veo3" if data['model_type'] == "veo3" else "veo3-fast"
        duration = 8  # Фиксированная длительность для Veo3
    else:
        # Seedance models
        model_name = f"seedance-v1-{data['model_type']}-{data['mode']}-{data['resolution']}"
        duration = data['duration']
    
    # Рассчитываем стоимость
    cost = await calculate_generation_cost(model_name, duration)
    
    # Получаем баланс пользователя
    balance = user.balance
    
    # Проверяем достаточно ли средств
    balance_status = ""
    if balance < cost:
        balance_status = f"\n❌ <b>{_('generation.insufficient_balance', missing=cost - balance)}</b>"
    else:
        balance_status = f"\n✅ {_('generation.balance_after', balance=balance - cost)}"
    
    # Форматируем сообщение
    mode_text = _('generation.text_to_video') if data['mode'] == 't2v' else _('generation.image_to_video')
    
    if data['model_type'] in ["veo3", "veo3_fast"]:
        # Google Veo3 models
        model_info = MODEL_INFO[data['model_type']]
        model_text = model_info["name"]
        resolution_text = "1080p (фиксированно)"
        duration_text = "8 секунд (фиксированно)"
        aspect_ratio = "16:9 (фиксированно)"
        audio_text = "🎵 Включено" if data.get('generate_audio', False) else "🔇 Отключено"
    else:
        # Seedance models
        model_text = "Pro" if data['model_type'] == 'pro' else "Lite"
        resolution_text = data['resolution'].upper()
        duration_text = f"{data['duration']} сек"
        aspect_ratio = data.get('aspect_ratio', '16:9')
        audio_text = None
    
    # Создаем красивое сообщение подтверждения
    text = f"""
{_("generation.beautiful.divider")}
{_("generation.beautiful.create_title")}
{_("generation.beautiful.ai_magic")}
{_("generation.beautiful.divider")}

{_("generation.beautiful.confirmation")}
{_("generation.beautiful.generation_summary")}

📋 <b>Параметры генерации:</b>
├ 🎯 Режим: {mode_text}
├ 🤖 Модель: {model_text}
├ 📐 Разрешение: {resolution_text}
├ ⏱️ Длительность: {duration_text}"""
    
    if data['model_type'] not in ["veo3", "veo3_fast"] and data['mode'] == 't2v':
        text += f"\n├ 🖼️ Формат: {aspect_ratio}"
    elif data['model_type'] in ["veo3", "veo3_fast"]:
        text += f"\n├ 🖼️ Формат: {aspect_ratio}"
        text += f"\n├ 🎵 Аудио: {audio_text}"
    
    text += f"\n└ 💰 Стоимость: {cost} кредитов"
    
    text += f"""

📝 <b>Ваш промпт:</b>
<i>"{data['prompt'][:300]}{'...' if len(data['prompt']) > 300 else ''}"</i>

💰 <b>Баланс:</b> {balance} кредитов{balance_status}

{_("generation.beautiful.all_set")}

{_("generation.beautiful.divider")}
"""
    
    # Сохраняем стоимость
    await state.update_data(cost=cost, model=model_name)
    
    # Показываем подтверждение
    keyboard = get_generation_confirm_keyboard(cost, user.language_code) if balance >= cost else get_cancel_keyboard(user.language_code)
    
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    await state.set_state(GenerationStates.confirming)

@router.callback_query(GenerationStates.confirming, F.data == "confirm_generation")
async def confirm_generation(callback: CallbackQuery, state: FSMContext):
    """Подтверждение и запуск генерации"""
    data = await state.get_data()
    user_id = callback.from_user.id
    
    # Получаем пользователя и функцию перевода
    user = await db.get_user(user_id)
    _ = lambda key, **kwargs: i18n.get(key, user.language_code or 'ru', **kwargs)
    
    # Проверяем баланс API перед началом генерации
    api_balance_check = await api_monitor.check_and_notify(callback.bot)
    
    if not api_monitor.is_service_available(api_balance_check.get('balance')):
        # Сервис недоступен из-за нулевого баланса API
        maintenance_message = api_monitor.get_maintenance_message()
        await callback.message.edit_text(
            maintenance_message,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text=_("common.back"), callback_data="back_to_menu")
            ]]),
            parse_mode="HTML"
        )
        await callback.answer()
        return
    
    # Проверяем лимиты генерации
    allowed, error_message = await GenerationThrottling.check_generation_limit(user_id)
    if not allowed:
        await callback.answer(f"⏱ {error_message}", show_alert=True)
        return
    
    # Еще раз проверяем баланс пользователя
    if user.balance < data['cost']:
        await callback.answer("❌ Недостаточно кредитов!", show_alert=True)
        return
    
    try:
        # Списываем кредиты
        await db.update_user_balance(user.id, -data['cost'])
        
        # Создаем запись о генерации
        generation = await db.create_generation(
            user_id=user.id,
            mode=data['mode'],
            model=data['model'],
            prompt=data['prompt'],
            cost=data['cost'],
            resolution=data['resolution'],
            duration=data['duration'],
            aspect_ratio=data.get('aspect_ratio', '16:9'),
            image_url=data.get('image_file_id')
        )
        
        # Обновляем сообщение с красивым прогресс-баром
        text = f"""
{_("generation.beautiful.divider")}
{_("generation.beautiful.processing_title")}
{_("generation.beautiful.ai_working")}
{_("generation.beautiful.divider")}

🆔 <b>ID генерации:</b> <code>{generation.id}</code>
💰 <b>Списано кредитов:</b> {data['cost']}

{_("generation.beautiful.progress_processing")}
{_("generation.beautiful.progress_bar")}

{_("generation.beautiful.please_wait")}
{_("generation.beautiful.eta")}

{_("generation.beautiful.divider")}
"""
        
        await callback.message.edit_text(text, parse_mode="HTML")
        
        await state.set_state(GenerationStates.processing)
        await callback.answer()
        
        # Запускаем генерацию
        asyncio.create_task(process_generation(
            callback.message,
            generation,
            data,
            state
        ))
        
    except Exception as e:
        logger.error(f"Error confirming generation: {e}")
        
        # Отменяем лимит генерации при ошибке
        GenerationThrottling.cancel_generation_limit(user_id)
        
        await callback.answer("❌ Ошибка создания генерации", show_alert=True)
        # Возвращаем состояние для повторной попытки
        await state.set_state(GenerationStates.confirming)

async def process_generation(message: Message, generation, data: dict, state: FSMContext):
    """Обработка генерации видео"""
    try:
        # Получаем пользователя и функцию перевода в начале
        user = await db.get_user_by_id(generation.user_id)
        _ = lambda key, **kwargs: i18n.get(key, user.language_code or 'ru', **kwargs)
        
        api = get_wavespeed_api()
        
        # Подготавливаем запрос
        if data['model'] in ["veo3", "veo3-fast"]:
            # Google Veo3 request
            request = GenerationRequest(
                model=data['model'],
                prompt=data['prompt'],
                duration=8,  # Фиксированная длительность
                aspect_ratio=data.get('aspect_ratio', '16:9'),
                generate_audio=data.get('generate_audio', False),
                enable_prompt_expansion=True
            )
        else:
            # Seedance request
            request = GenerationRequest(
                model=data['model'],
                prompt=data['prompt'],
                duration=data['duration'],
                aspect_ratio=data.get('aspect_ratio', '16:9'),
                image=f"data:image/jpeg;base64,{data['image_base64']}" if data.get('image_base64') else None
            )
        
        # Обновляем статус
        await db.update_generation_status(generation.id, GenerationStatus.PROCESSING)
        
        # Показываем начальное сообщение о прогрессе
        initial_text = f"""
{_("generation.beautiful.divider")}
{_("generation.beautiful.processing_title")}
{_("generation.beautiful.ai_working")}
{_("generation.beautiful.divider")}

🆔 <b>ID генерации:</b> <code>{generation.id}</code>
💰 <b>Списано кредитов:</b> {data['cost']}

⏳ <b>{_("generation.beautiful.progress_processing")}</b>
░░░░░░░░░░ 0%

⏱ <b>Прошло времени:</b> 0 сек

{_("generation.beautiful.divider")}
"""
        await message.edit_text(initial_text, parse_mode="HTML")
        
        # Небольшая задержка чтобы пользователь увидел начальный прогресс
        await asyncio.sleep(1)
        
        # Callback для обновления прогресса
        last_progress = -1  # Начинаем с -1 чтобы первое обновление точно прошло
        last_update_time = asyncio.get_event_loop().time()
        
        async def progress_callback(progress: int, status: str):
            nonlocal last_progress, last_update_time
            current_time = asyncio.get_event_loop().time()
            
            # Обновляем прогресс только если он увеличился или прошло достаточно времени
            should_update = (
                progress > last_progress or 
                progress == 100 or
                current_time - last_update_time >= 3 or  # Обновляем каждые 3 секунды
                (progress == 0 and last_progress == -1)  # Первое обновление
            )
            
            if should_update:
                last_progress = progress
                last_update_time = current_time
                
                logger.debug(f"Updating progress UI: {progress}% (status: {status})")
                
                try:
                    # Создаем красивый прогресс-бар
                    progress_blocks = int(progress / 10)
                    progress_bar = "█" * progress_blocks + "░" * (10 - progress_blocks)
                    
                    # Определяем статус и эмодзи на основе прогресса и статуса API
                    if progress == 0:
                        status_emoji = "⏳"
                        status_text = _("generation.beautiful.progress_processing")
                    elif progress < 20:
                        status_emoji = "🔄"
                        status_text = _("generation.beautiful.progress_processing")
                    elif progress < 50:
                        status_emoji = "🔍"
                        status_text = _("generation.beautiful.progress_analyzing")
                    elif progress < 80:
                        status_emoji = "🎨"
                        status_text = _("generation.beautiful.progress_rendering")
                    elif progress < 100:
                        status_emoji = "✨"
                        status_text = _("generation.beautiful.progress_finalizing")
                    else:
                        status_emoji = "✅"
                        status_text = _("generation.beautiful.progress_complete")
                    
                    # Формируем красивое сообщение
                    text = f"""
{_("generation.beautiful.divider")}
{_("generation.beautiful.processing_title")}
{_("generation.beautiful.ai_working")}
{_("generation.beautiful.divider")}

🆔 <b>ID генерации:</b> <code>{generation.id}</code>
💰 <b>Списано кредитов:</b> {data['cost']}

{status_emoji} <b>{status_text}</b>
{progress_bar} {progress}%

⏱ <b>Прошло времени:</b> {MessageTemplates.format_time(int((progress / 100) * 60))}

{_("generation.beautiful.divider")}
"""
                    
                    await message.edit_text(text, parse_mode="HTML")
                except Exception as e:
                    logger.debug(f"Progress update skipped: {e}")
        
        # Генерируем видео
        result = await api.generate_video(request, progress_callback)
        
        # Обновляем запись в БД
        await db.update_generation_status(
            generation.id,
            GenerationStatus.COMPLETED,
            video_url=result.video_url,
            generation_time=result.generation_time
        )
        
        # Скачиваем видео
        video_data = await api.download_video(result.video_url)
        
        # Если видео создано на бонусные кредиты, добавляем QR-код
        if generation.used_bonus_credits:
            try:
                from services.video_processor import add_qr_code_to_video
                logger.info(f"Adding QR code to video {generation.id} (created with bonus credits)")
                video_data = await add_qr_code_to_video(video_data)
            except Exception as e:
                logger.error(f"Error adding QR code to video {generation.id}: {e}")
                # Продолжаем без QR-кода в случае ошибки
        
        # Отправляем видео пользователю
        video_file = BufferedInputFile(
            video_data,
            filename=f"seedance_{generation.id}.mp4"
        )
        
        # Получаем язык пользователя для сообщения (уже получен в начале функции)
        
        bonus_info = ""
        if generation.used_bonus_credits:
            bonus_info = f"\n{_('generation.bonus_credits_info')}\n"
        
        caption = (
            f"{_('generation.beautiful.success_title')}\n"
            f"{_('generation.beautiful.success_subtitle')}\n\n"
            f"{_('generation.beautiful.download_ready')}\n{bonus_info}\n"
            f"{_('generation.beautiful.generation_stats')}\n"
            f"🆔 <b>ID:</b> <code>{generation.id}</code>\n"
            f"{_('generation.beautiful.time_spent', time=int(result.generation_time))}\n"
            f"{_('generation.beautiful.model_used', model=data['model'])}\n"
            f"📐 <b>Разрешение:</b> {data['resolution'].upper()}\n"
            f"⏱ <b>Длительность:</b> {data['duration']} сек\n\n"
            f"{_('generation.beautiful.rate_prompt')}:"
        )
        
        sent_message = await message.answer_video(
            video_file,
            caption=caption,
            reply_markup=get_generation_rating_keyboard(generation.id)
        )
        
        # Сохраняем file_id видео для быстрой отправки в будущем
        if sent_message.video:
            await db.update_generation_video_file_id(generation.id, sent_message.video.file_id)
        
        # Проверяем баланс API после завершения генерации
        try:
            await api_monitor.check_and_notify(message.bot)
        except Exception as e:
            logger.error(f"Error checking API balance after generation: {e}")
        
        # Удаляем сообщение о прогрессе
        try:
            await message.delete()
        except:
            pass
        
    except asyncio.CancelledError:
        logger.info(f"Generation {generation.id} was cancelled")
        
        # Отменяем лимит генерации при отмене через asyncio
        user = await db.get_user_by_id(generation.user_id)
        if user:
            GenerationThrottling.cancel_generation_limit(user.telegram_id)
        
        raise
    except Exception as e:
        logger.error(f"Generation {generation.id} failed: {e}")
        
        # Обновляем статус
        await db.update_generation_status(
            generation.id,
            GenerationStatus.FAILED,
            error_message=str(e)
        )
        
        # Возвращаем кредиты
        await db.update_user_balance(generation.user_id, generation.cost)
        
        # Отменяем лимит генерации при неудачной генерации
        user = await db.get_user_by_id(generation.user_id)
        if user:
            GenerationThrottling.cancel_generation_limit(user.telegram_id)
        
        # Получаем язык пользователя (уже получен в начале функции)
        
        # Определяем тип ошибки и показываем соответствующее сообщение
        error_message = str(e)
        
        # Ошибки модерации контента
        if any(word in error_message.lower() for word in ['flagged', 'sensitive', 'content', 'moderation', 'inappropriate']):
            error_text = (
                f"🚫 <b>ОШИБКА ГЕНЕРАЦИИ</b>\n"
                f"К сожалению, что-то пошло не так\n\n"
                f"💰 <b>Кредиты возвращены на баланс</b>\n\n"
                f"🖼️ <b>Причина:</b> Generation failed: Content flagged as potentially sensitive. Please try different prompts or images\n\n"
                f"💡 <b>Рекомендации:</b>\n"
                f"• Измените описание (промпт) на более нейтральное\n"
                f"• Используйте другое изображение (если загружали)\n"
                f"• Избегайте слов, которые могут быть восприняты как неподходящие\n"
                f"• Попробуйте описать сцену более общими словами\n\n"
                f"Пожалуйста, попробуйте еще раз или обратитесь в поддержку."
            )
        elif "download" in error_message.lower() or "cloudfront" in error_message.lower():
            # Ошибка скачивания видео
            error_text = (
                f"{_('generation.beautiful.error_title')}\n"
                f"{_('generation.beautiful.error_subtitle')}\n\n"
                f"{_('generation.beautiful.credits_refunded')}\n\n"
                f"📝 <b>Причина:</b> Проблема с сетью при получении видео\n\n"
                f"💡 <b>Что делать:</b>\n"
                f"• Попробуйте создать видео еще раз\n"
                f"• Если проблема повторяется, обратитесь в поддержку\n"
                f"• Видео может быть доступно позже\n\n"
                f"{_('generation.try_again_or_support', default='Пожалуйста, попробуйте еще раз или обратитесь в поддержку.')}"
            )
        elif "timeout" in error_message.lower():
            # Ошибка таймаута
            error_text = (
                f"{_('generation.beautiful.error_title')}\n"
                f"{_('generation.beautiful.error_subtitle')}\n\n"
                f"{_('generation.beautiful.credits_refunded')}\n\n"
                f"📝 <b>Причина:</b> Сервер не ответил вовремя\n\n"
                f"💡 <b>Что делать:</b>\n"
                f"• Попробуйте создать видео еще раз\n"
                f"• Сервер может быть перегружен\n"
                f"• Видео может быть доступно позже\n\n"
                f"{_('generation.try_again_or_support', default='Пожалуйста, попробуйте еще раз или обратитесь в поддержку.')}"
            )
        elif "network" in error_message.lower() or "connection" in error_message.lower():
            # Сетевая ошибка
            error_text = (
                f"{_('generation.beautiful.error_title')}\n"
                f"{_('generation.beautiful.error_subtitle')}\n\n"
                f"{_('generation.beautiful.credits_refunded')}\n\n"
                f"📝 <b>Причина:</b> Проблема с интернет-соединением\n\n"
                f"💡 <b>Что делать:</b>\n"
                f"• Проверьте интернет-соединение\n"
                f"• Попробуйте создать видео еще раз\n"
                f"• Если проблема повторяется, обратитесь в поддержку\n\n"
                f"{_('generation.try_again_or_support', default='Пожалуйста, попробуйте еще раз или обратитесь в поддержку.')}"
            )
        else:
            # Общая ошибка
            error_text = (
                f"{_('generation.beautiful.error_title')}\n"
                f"{_('generation.beautiful.error_subtitle')}\n\n"
                f"{_('generation.beautiful.credits_refunded')}\n\n"
                f"📝 <b>Причина:</b> {error_message}\n\n"
                f"{_('generation.try_again_or_support', default='Пожалуйста, попробуйте еще раз или обратитесь в поддержку.')}"
            )
        
        builder = InlineKeyboardBuilder()
        builder.button(text=f"{_('generation.beautiful.error_retry')}", callback_data="generate")
        builder.button(text=f"{_('generation.beautiful.error_support')}", callback_data="support")
        builder.adjust(2)
        
        try:
            await message.edit_text(error_text, reply_markup=builder.as_markup())
        except:
            await message.answer(error_text, reply_markup=builder.as_markup())
    
    finally:
        # Очищаем состояние
        await state.clear()

# =================== ОБРАБОТЧИКИ НАВИГАЦИИ ===================

@router.callback_query(F.data == "back")
async def handle_back(callback: CallbackQuery, state: FSMContext):
    """Универсальный обработчик для кнопки Назад"""
    current_state = await state.get_state()
    
    if current_state == GenerationStates.choosing_model:
        # Возвращаемся к выбору режима
        await start_generation(callback, state)
    elif current_state == GenerationStates.choosing_audio:
        # Возвращаемся к выбору модели
        await back_to_model(callback, state)
    elif current_state == GenerationStates.choosing_resolution:
        # Возвращаемся к выбору модели
        await back_to_model(callback, state)
    elif current_state == GenerationStates.choosing_duration:
        # Возвращаемся к выбору разрешения
        await back_to_resolution(callback, state)
    elif current_state == GenerationStates.choosing_aspect_ratio:
        # Возвращаемся к выбору длительности
        await back_to_duration(callback, state)
    else:
        # По умолчанию возвращаемся в главное меню
        await handle_back_to_menu(callback, state)

@router.callback_query(F.data == "back_to_menu")
async def handle_back_to_menu(callback: CallbackQuery, state: FSMContext):
    """Возврат в главное меню"""
    await state.clear()
    
    user = await db.get_user(callback.from_user.id)
    if not user:
        await callback.answer("Ошибка: пользователь не найден", show_alert=True)
        return
    
    from bot.handlers.start import show_main_menu
    await show_main_menu(callback.message, user)
    await callback.answer()

@router.callback_query(F.data == "cancel")
async def handle_cancel(callback: CallbackQuery, state: FSMContext):
    """Обработчик для общей кнопки отмены"""
    current_state = await state.get_state()
    
    # Если в процессе выбора параметров - возвращаемся в меню
    if current_state in [
        GenerationStates.entering_prompt,
        GenerationStates.uploading_image
    ]:
        await cancel_generation(callback, state)
    else:
        # Для остальных состояний возвращаемся в главное меню
        await handle_back_to_menu(callback, state)

@router.callback_query(F.data == "cancel_generation")
async def cancel_generation(callback: CallbackQuery, state: FSMContext):
    """Отмена генерации"""
    current_state = await state.get_state()
    
    # Если генерация уже запущена, не позволяем отменить
    if current_state == GenerationStates.processing:
        user = await db.get_user(callback.from_user.id)
        _ = lambda key, **kwargs: i18n.get(key, user.language_code or 'ru', **kwargs)
        await callback.answer(_('generation.cannot_cancel_processing', default="Генерация уже запущена, дождитесь завершения"), show_alert=True)
        return
    
    # Если генерация была подтверждена но еще не запущена, отменяем лимит
    if current_state == GenerationStates.confirming:
        GenerationThrottling.cancel_generation_limit(callback.from_user.id)
    
    await state.clear()
    
    user = await db.get_user(callback.from_user.id)
    _ = lambda key, **kwargs: i18n.get(key, user.language_code or 'ru', **kwargs)
    
    try:
        await callback.message.delete()
    except:
        pass
    
    # Отправляем красивое сообщение об отмене
    text = f"""
{_("generation.beautiful.divider")}
{_("generation.beautiful.cancelled_title")}
{_("generation.beautiful.cancelled_subtitle")}
{_("generation.beautiful.divider")}

{_("generation.beautiful.credits_refunded")}

{_("generation.beautiful.back_to_menu")}

{_("generation.beautiful.divider")}
"""
    
    # Отправляем сообщение об отмене и возвращаемся в главное меню
    from bot.handlers.start import show_main_menu
    await show_main_menu(callback.message, user)
    
    await callback.answer(_('generation.cancelled', default='Генерация отменена'))

# Обработчики для возврата к предыдущим шагам
@router.callback_query(GenerationStates.choosing_resolution, F.data == "back_to_model")
async def back_to_model(callback: CallbackQuery, state: FSMContext):
    """Возврат к выбору модели"""
    data = await state.get_data()
    mode = data.get('mode', 't2v')
    
    # Получаем пользователя и функцию перевода
    user = await db.get_user(callback.from_user.id)
    _ = lambda key, **kwargs: i18n.get(key, user.language_code or 'ru', **kwargs)
    
    # Определяем название выбранного режима
    mode_text = _('generation.text_to_video') if mode == "t2v" else _('generation.image_to_video')
    
    # Создаем красивое сообщение выбора модели
    text = f"""
{_("generation.beautiful.divider")}
{_("generation.beautiful.create_title")}
{_("generation.beautiful.ai_magic")}
{_("generation.beautiful.divider")}

{_("generation.beautiful.model_selection")}
{_("generation.beautiful.model_subtitle")}

📌 <b>Выбранный режим:</b> {mode_text}

{_("generation.beautiful.lite_title")}
{_("generation.beautiful.lite_desc")}
{_("generation.beautiful.lite_features")}

{_("generation.beautiful.pro_title")}
{_("generation.beautiful.pro_desc")}
{_("generation.beautiful.pro_features")}

{_("generation.beautiful.divider")}
"""
    
    await callback.message.edit_text(text, reply_markup=get_model_selection_keyboard(mode, user.language_code), parse_mode="HTML")
    await state.set_state(GenerationStates.choosing_model)
    await callback.answer()

@router.callback_query(GenerationStates.choosing_duration, F.data == "back_to_resolution")
async def back_to_resolution(callback: CallbackQuery, state: FSMContext):
    """Возврат к выбору разрешения"""
    data = await state.get_data()
    model_type = data.get('model_type', 'lite')
    mode = data.get('mode', 't2v')
    
    # Получаем пользователя и функцию перевода
    user = await db.get_user(callback.from_user.id)
    _ = lambda key, **kwargs: i18n.get(key, user.language_code or 'ru', **kwargs)
    
    # Определяем названия
    mode_text = _('generation.text_to_video') if mode == "t2v" else _('generation.image_to_video')
    model_text = "Pro" if model_type == "pro" else "Lite"
    
    # Создаем красивое сообщение настроек
    text = f"""
{_("generation.beautiful.divider")}
{_("generation.beautiful.create_title")}
{_("generation.beautiful.ai_magic")}
{_("generation.beautiful.divider")}

{_("generation.beautiful.settings_title")}
{_("generation.beautiful.quality_resolution")}

📌 <b>Выбрано:</b>
├ 🎯 Режим: {mode_text}
└ 🤖 Модель: Seedance V1 {model_text}

{_("generation.beautiful.resolution_desc")}

💡 <b>Совет:</b> {_('generation.beautiful.resolution_tip')}

{_("generation.beautiful.divider")}
"""
    
    await callback.message.edit_text(text, reply_markup=get_resolution_keyboard(model_type, user.language_code), parse_mode="HTML")
    await state.set_state(GenerationStates.choosing_resolution)
    await callback.answer()

@router.callback_query(GenerationStates.entering_prompt, F.data == "back_to_audio")
async def back_to_audio(callback: CallbackQuery, state: FSMContext):
    """Возврат к выбору аудио для Google Veo3"""
    data = await state.get_data()
    model_type = data.get('model_type')
    mode = data.get('mode', 't2v')
    
    # Получаем пользователя и функцию перевода
    user = await db.get_user(callback.from_user.id)
    _ = lambda key, **kwargs: i18n.get(key, user.language_code or 'ru', **kwargs)
    
    mode_text = _('generation.text_to_video') if mode == "t2v" else _('generation.image_to_video')
    model_info = MODEL_INFO[model_type]
    model_text = model_info["name"]
    
    # Возвращаемся к выбору аудио
    text = f"""
{_("generation.beautiful.divider")}
{_("generation.beautiful.create_title")} - {model_text}
{_("generation.beautiful.ai_magic")}
{_("generation.beautiful.divider")}

📌 <b>Выбрано:</b>
├ 🎯 Режим: {mode_text}
├ 🤖 Модель: {model_text}
├ 📐 Разрешение: 1080p (фиксированно)
├ ⏱️ Длительность: 8 секунд (фиксированно)
└ 📱 Соотношение: 16:9 (по умолчанию)

🎵 <b>Генерация аудио:</b>
Включить синхронизированное аудио для видео?
• Диалоги с синхронизацией губ
• Фоновые звуки и музыка
• Естественные звуковые эффекты

💡 <b>Совет:</b> Аудио делает видео более реалистичным, но увеличивает время генерации.

{_("generation.beautiful.divider")}
"""
    
    # Создаем клавиатуру для выбора аудио
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="🎵 Включить аудио", callback_data="audio_on")
    builder.button(text="🔇 Без аудио", callback_data="audio_off")
    builder.button(text=f"◀️ {_('common.back')}", callback_data="back_to_model")
    builder.adjust(1)
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await state.set_state(GenerationStates.choosing_audio)
    await callback.answer()

@router.callback_query(GenerationStates.choosing_aspect_ratio, F.data == "back_to_duration")
async def back_to_duration(callback: CallbackQuery, state: FSMContext):
    """Возврат к выбору длительности"""
    data = await state.get_data()
    mode = data.get('mode', 't2v')
    model_type = data.get('model_type', 'lite')
    
    # Получаем пользователя и функцию перевода
    user = await db.get_user(callback.from_user.id)
    _ = lambda key, **kwargs: i18n.get(key, user.language_code or 'ru', **kwargs)
    
    # Определяем названия
    mode_text = _('generation.text_to_video') if mode == "t2v" else _('generation.image_to_video')
    model_text = "Pro" if model_type == "pro" else "Lite"
    
    # Создаем красивое сообщение для выбора длительности
    text = f"""
{_("generation.beautiful.divider")}
{_("generation.beautiful.create_title")}
{_("generation.beautiful.ai_magic")}
{_("generation.beautiful.divider")}

{_("generation.beautiful.settings_title")}
{_("generation.beautiful.duration_time")}

📌 <b>Выбрано:</b>
├ 🎯 Режим: {mode_text}
├ 🤖 Модель: Seedance V1 {model_text}
└ 📐 Разрешение: {data['resolution']}

{_("generation.beautiful.duration_desc")}

💡 <b>Совет:</b> {_('generation.beautiful.duration_tip')}

{_("generation.beautiful.divider")}
"""
    
    await callback.message.edit_text(text, reply_markup=get_duration_keyboard(user.language_code), parse_mode="HTML")
    await state.set_state(GenerationStates.choosing_duration)
    await callback.answer()

# =================== ДОПОЛНИТЕЛЬНЫЕ ОБРАБОТЧИКИ ===================

@router.callback_query(F.data.startswith("rate_"))
async def rate_generation(callback: CallbackQuery):
    """Оценка генерации"""
    try:
        parts = callback.data.split("_")
        generation_id = int(parts[1])
        rating = int(parts[2])
        
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
        
        await callback.answer(f"✅ {_('generation.rating_saved', default='Спасибо за оценку!')}")
        
        # Убираем клавиатуру оценки
        await callback.message.edit_reply_markup(reply_markup=None)
        
    except (ValueError, IndexError):
        await callback.answer("Ошибка сохранения оценки", show_alert=True)

@router.callback_query(F.data == "skip_rating")
async def skip_rating(callback: CallbackQuery):
    """Пропустить оценку генерации"""
    user = await db.get_user(callback.from_user.id)
    if not user:
        await callback.answer("Ошибка", show_alert=True)
        return
    
    # Получаем функцию перевода
    _ = lambda key, **kwargs: i18n.get(key, user.language_code or 'ru', **kwargs)
    
    await callback.answer(_('generation.rating_skipped', default='Оценка пропущена'))
    
    # Убираем клавиатуру оценки
    await callback.message.edit_reply_markup(reply_markup=None)

@router.callback_query(F.data == "compare_models")
async def compare_models(callback: CallbackQuery):
    """Сравнение моделей"""
    # Получаем пользователя и функцию перевода
    user = await db.get_user(callback.from_user.id)
    _ = lambda key, **kwargs: i18n.get(key, user.language_code or 'ru', **kwargs)
    
    text = f"🤖 <b>{_('models.comparison_title', default='Сравнение всех моделей')}</b>\n\n"
    
    # Google Veo3 Fast
    veo3_fast_info = MODEL_INFO["veo3_fast"]
    text += f"<b>⚡ {veo3_fast_info['name']}</b>\n"
    for feature in veo3_fast_info['features']:
        text += f"• {feature}\n"
    text += f"• 🎯 Идеально для соцсетей и быстрого контента\n"
    text += f"• 💰 Стоимость: 20 кредитов за 8 секунд\n\n"
    
    # Google Veo3
    veo3_info = MODEL_INFO["veo3"]
    text += f"<b>🚀 {veo3_info['name']}</b>\n"
    for feature in veo3_info['features']:
        text += f"• {feature}\n"
    text += f"• 🎯 Максимальное качество от Google DeepMind\n"
    text += f"• 💰 Стоимость: 100 кредитов за 8 секунд\n\n"
    
    # Lite модель
    lite_info = MODEL_INFO["lite"]
    text += f"<b>🥈 {lite_info['name']}</b>\n"
    for feature in lite_info['features']:
        text += f"• {feature}\n"
    text += f"• {_('models.lite.use_case', default='🎯 Подходит для простых сцен')}\n"
    text += f"• {_('models.lite.perfect_for', default='💡 Идеальна для тестов и прототипов')}\n\n"
    
    # Pro модель  
    pro_info = MODEL_INFO["pro"]
    text += f"<b>🥇 {pro_info['name']}</b>\n"
    for feature in pro_info['features']:
        text += f"• {feature}\n"
    text += f"• {_('models.pro.use_case', default='🎯 Сложные сцены и движения')}\n"
    text += f"• {_('models.pro.perfect_for', default='🎨 Профессиональный результат')}\n\n"
    
    # Рекомендации
    text += f"<b>{_('models.recommendations', default='Рекомендации')}:</b>\n"
    text += f"• 🚀 Попробуйте Veo3 Fast для высокого качества по доступной цене\n"
    text += f"• 🎭 Используйте Veo3 для видео с диалогами и аудио\n"
    text += f"• {_('models.rec1', default='Начните с Lite для тестирования идей')}\n"
    text += f"• {_('models.rec2', default='Используйте Pro для финальных видео')}"
    
    await callback.answer(text, show_alert=True)

# Обработчик для неподдерживаемых типов файлов в любом состоянии
@router.message(F.document)
async def handle_document_in_generation(message: Message, state: FSMContext):
    """Обработка документов вместо фото"""
    current_state = await state.get_state()
    
    if current_state == GenerationStates.uploading_image:
        user = await db.get_user(message.from_user.id)
        _ = lambda key, **kwargs: i18n.get(key, user.language_code or 'ru', **kwargs)
        
        await message.answer(
            f"❌ {_('generation.send_as_photo', default='Пожалуйста, отправьте изображение как фото, а не как документ.')}\n\n"
            f"💡 {_('generation.photo_hint', default='Используйте кнопку 📎 и выберите «Фото или видео»')}",
            reply_markup=get_cancel_keyboard(user.language_code or 'ru')
        )
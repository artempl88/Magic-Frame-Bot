import logging
from datetime import datetime
from typing import Optional, Union
from aiogram import Router, F, Bot
from aiogram.types import (
    Message, CallbackQuery, LabeledPrice,
    PreCheckoutQuery, ContentType, InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select  # Добавлен импорт

from bot.keyboard.inline import (
    get_shop_keyboard, get_package_details_keyboard,
    get_back_keyboard
)
from bot.utils.messages import MessageTemplates
from services.database import db
from services.utm_analytics import utm_service
from core.constants import CREDIT_PACKAGES, SPECIAL_OFFERS
from core.config import settings
from bot.middlewares.i18n import I18n
from models.models import TransactionTypeEnum, TransactionStatusEnum, Transaction, User

logger = logging.getLogger(__name__)

# Глобальная функция локализации
i18n = I18n()

router = Router(name="payment")

# Добавляем декоратор для проверки пользователя
def ensure_user(func):
    """Декоратор для проверки существования пользователя"""
    from functools import wraps
    
    @wraps(func)
    async def wrapper(update: Union[Message, CallbackQuery], *args, **kwargs):
        user_id = update.from_user.id
        user = await db.get_user(user_id)
        
        if not user:
            text = i18n.get('errors.use_start', 'ru')
            if isinstance(update, CallbackQuery):
                await update.answer(text, show_alert=True)
            else:
                await update.answer(text)
            return
        
        kwargs['user'] = user
        kwargs['_'] = lambda key, **kw: i18n.get(key, user.language_code or 'ru', **kw)
        return await func(update, *args, **kwargs)
    return wrapper

@router.message(F.text == "/buy")
@router.callback_query(F.data == "shop")
@ensure_user
async def show_shop(update: Message | CallbackQuery, user: User, _, **kwargs):
    """Показать магазин кредитов"""
    # Проверяем специальные предложения
    has_new_user_offer = False
    if user.total_bought == 0:
        # Проверяем, использовал ли уже новичковое предложение
        transactions = await db.get_user_transactions(user.telegram_id, limit=100)
        new_user_used = any(
            t.meta_data and t.meta_data.get('offer_id') == 'new_user'
            for t in transactions if t.meta_data
        )
        has_new_user_offer = not new_user_used
    
    # Форматируем текст
    text = MessageTemplates.SHOP_MENU.format(balance=user.balance)
    
    if has_new_user_offer:
        text += f"\n\n🎁 <b>{_('shop.special_offer_available', default='Специальное предложение для новых пользователей доступно!')}</b>"
    
    # Показываем магазин
    if isinstance(update, CallbackQuery):
        await update.message.edit_text(text, reply_markup=get_shop_keyboard(user.language_code))
        await update.answer()
    else:
        await update.answer(text, reply_markup=get_shop_keyboard(user.language_code))

@router.callback_query(F.data.startswith("buy_"))
@ensure_user
async def show_package_details(callback: CallbackQuery, user: User, _, **kwargs):
    """Показать детали пакета"""
    package_id = callback.data.split("_", 1)[1]
    
    # Находим пакет
    package = next((p for p in CREDIT_PACKAGES if p.id == package_id), None)
    if not package:
        await callback.answer(_("shop.package_not_found"), show_alert=True)
        return
    
    # Форматируем текст
    discount_text = ""
    if package.discount > 0:
        discount_text = f"\n🎯 <b>{_('shop.discount', default='Скидка')}:</b> {package.discount}%"
    
    text = MessageTemplates.PACKAGE_DETAILS.format(
        emoji=package.emoji,
        name=package.name,
        badge=package.badge or "",
        credits=package.credits,
        stars=package.stars,
        discount_text=discount_text,
        description=package.description
    )
    
    await callback.message.edit_text(text)
    await callback.message.edit_reply_markup(
        reply_markup=get_package_details_keyboard(package_id, user.language_code)
    )
    await callback.answer()

@router.callback_query(F.data == "special_offers")
@ensure_user
async def show_special_offers(callback: CallbackQuery, user: User, _, **kwargs):
    """Показать специальные предложения"""
    text = f"🎁 <b>{_('shop.special_offers')}</b>\n\n"
    
    builder = InlineKeyboardBuilder()
    available_offers = []
    
    # Проверяем доступные предложения
    for offer in SPECIAL_OFFERS:
        if offer['condition'] == 'one_time' and user.total_bought == 0:
            # Проверяем, не использовал ли уже
            transactions = await db.get_user_transactions(user.telegram_id, limit=100)
            used = any(
                t.meta_data and t.meta_data.get('offer_id') == offer['id']
                for t in transactions if t.meta_data
            )
            
            if not used:
                available_offers.append(offer)
                offer_name = _(f"offers.{offer['id']}.name", default=offer['name'])
                offer_desc = _(f"offers.{offer['id']}.description", default=offer['description'])
                
                text += f"{offer_name}\n"
                text += f"💰 {offer['credits']} {_('common.credits')} {_('shop.for', default='за')} {offer['stars']} Stars\n"
                text += f"📝 {offer_desc}\n\n"
                
                builder.button(
                    text=f"{offer_name} - {offer['stars']} ⭐",
                    callback_data=f"special_{offer['id']}"
                )
    
    if not available_offers:
        text += f"😔 <i>{_('shop.no_offers', default='Сейчас нет доступных специальных предложений')}</i>\n\n"
        text += _('shop.check_later', default='Следите за обновлениями!')
    
    builder.button(text=_("common.back"), callback_data="shop")
    builder.adjust(1)
    
    await callback.message.edit_text(text)
    await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
    await callback.answer()

@router.callback_query(F.data.startswith("pay_"))
@ensure_user
async def process_payment(callback: CallbackQuery, bot: Bot, user: User, _, **kwargs):
    """Обработка оплаты пакета - показать выбор способа оплаты"""
    package_id = callback.data.split("_", 1)[1]
    
    # Находим пакет
    package = next((p for p in CREDIT_PACKAGES if p.id == package_id), None)
    if not package:
        await callback.answer(_('shop.package_not_found'), show_alert=True)
        return
    
    # Проверяем есть ли выбор способов оплаты
    from services.yookassa_service import yookassa_service
    from services.price_service import price_service
    
    # Получаем доступные способы оплаты
    stars_price = await price_service.get_effective_price(package_id, "telegram_stars")
    rub_price = await price_service.get_effective_price(package_id, "yookassa")
    yookassa_available = yookassa_service.is_available() and rub_price is not None
    
    # Формируем текст с доступными способами оплаты
    text = f"""
💳 <b>{_('payment.choose_method', default='Выберите способ оплаты')}</b>

{package.emoji} <b>{package.name}</b>
🎬 {package.credits} {_('common.credits')}

<b>{_('payment.available_methods', default='Доступные способы:')}:</b>
"""
    
    builder = InlineKeyboardBuilder()
    has_payment_methods = False
    
    # Telegram Stars (всегда доступен если есть цена)
    if stars_price:
        text += f"\n⭐ <b>Telegram Stars:</b> {stars_price} Stars"
        builder.button(
            text=f"⭐ {stars_price} Stars",
            callback_data=f"pay_stars_{package_id}"
        )
        has_payment_methods = True
    
    # ЮКасса (если настроена и есть цена)
    if yookassa_available:
        text += f"\n💳 <b>ЮКасса (банковская карта):</b> {rub_price:.2f} ₽"
        builder.button(
            text=f"💳 {rub_price:.2f} ₽",
            callback_data=f"pay_yookassa_{package_id}"
        )
        has_payment_methods = True
    
    if not has_payment_methods:
        await callback.answer("❌ Способы оплаты не настроены", show_alert=True)
        return
    
    builder.button(text=f"◀️ {_('common.back')}", callback_data="shop")
    builder.adjust(1)
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()

@router.callback_query(F.data.startswith("special_"))
async def process_special_offer(callback: CallbackQuery, bot: Bot):
    """Обработка специального предложения"""
    offer_id = callback.data.split("_", 1)[1]
    
    # Находим предложение
    offer = next((o for o in SPECIAL_OFFERS if o['id'] == offer_id), None)
    if not offer:
        await callback.answer(i18n.get('shop.offer_not_found', 'ru'), show_alert=True)
        return
    
    # Проверяем доступность
    user = await db.get_user(callback.from_user.id)
    if offer['condition'] == 'one_time' and user.total_bought > 0:
        user_lang = user.language_code or 'ru'
        translate = lambda key, **kwargs: i18n.get(key, user_lang, **kwargs)
        await callback.answer(
            translate("shop.offer_expired"),
            show_alert=True
        )
        return
    
    await create_stars_invoice(
        callback, bot,
        offer['credits'],
        offer['stars'],
        offer['name'],
        offer_id,
        is_special=True
    )

@router.callback_query(F.data.startswith("pay_stars_"))
@ensure_user
async def pay_with_stars(callback: CallbackQuery, bot: Bot):
    """Оплата через Telegram Stars"""
    package_id = callback.data.split("_", 2)[2]
    
    # Находим пакет
    package = next((p for p in CREDIT_PACKAGES if p.id == package_id), None)
    if not package:
        await callback.answer(i18n.get('shop.package_not_found', 'ru'), show_alert=True)
        return
    
    # Получаем актуальную цену в Stars
    from services.price_service import price_service
    stars_price = await price_service.get_effective_price(package_id, "telegram_stars")
    
    if not stars_price:
        await callback.answer("❌ Цена в Stars не установлена", show_alert=True)
        return
    
    await create_stars_invoice(callback, bot, package.credits, stars_price, package.name, package_id)

@router.callback_query(F.data.startswith("pay_yookassa_"))
@ensure_user
async def pay_with_yookassa(callback: CallbackQuery, bot: Bot):
    """Оплата через ЮКассу"""
    package_id = callback.data.split("_", 2)[2]
    
    # Проверяем что ЮКасса настроена
    from services.yookassa_service import yookassa_service
    if not yookassa_service.is_available():
        await callback.answer("❌ ЮКасса не настроена", show_alert=True)
        return
    
    # Находим пакет
    package = next((p for p in CREDIT_PACKAGES if p.id == package_id), None)
    if not package:
        await callback.answer(i18n.get('shop.package_not_found', 'ru'), show_alert=True)
        return
    
    # Получаем актуальную цену в рублях
    from services.price_service import price_service
    rub_price = await price_service.get_effective_price(package_id, "yookassa")
    
    if not rub_price:
        await callback.answer("❌ Цена в рублях не установлена", show_alert=True)
        return
    
    await create_yookassa_payment(callback, bot, package.credits, rub_price, package.name, package_id)

async def create_stars_invoice(
    callback: CallbackQuery,
    bot: Bot,
    credits: int,
    stars: int,
    title: str,
    package_id: str,
    is_special: bool = False
):
    """Создать инвойс для оплаты Telegram Stars"""
    # Валидация параметров
    if credits <= 0 or credits > 100000:
        await callback.answer("❌ Некорректное количество кредитов", show_alert=True)
        return
        
    if stars <= 0 or stars > 10000:
        await callback.answer("❌ Некорректная цена", show_alert=True)
        return
    
    user_id = callback.from_user.id
    user = await db.get_user(user_id)
    
    if not user:
        await callback.answer(i18n.get('errors.user_not_found', 'ru'), show_alert=True)
        return
    
    # Функция перевода для языка пользователя
    user_lang = user.language_code or 'ru'
    translate = lambda key, **kwargs: i18n.get(key, user_lang, **kwargs)
    
    try:
        # Создаем транзакцию в базе данных
        transaction = await db.create_transaction(
            user_id=user.id,
            type='purchase',
            amount=credits,
            stars_paid=stars,
            package_id=package_id
        )
        
        # Создаем инвойс
        prices = [LabeledPrice(label=title, amount=stars)]
        
        # Создаем описание
        description = translate('shop.invoice.description', default='Покупка кредитов для генерации видео')
        
        # Отправляем инвойс с правильным payload
        await bot.send_invoice(
            chat_id=callback.from_user.id,
            title=title[:32],  # Telegram ограничение на длину
            description=description[:255],  # Telegram ограничение на длину
            provider_token="",  # Telegram Stars не требует токен
            currency="XTR",  # Telegram Stars
            prices=prices,
            payload=f"stars_transaction_{transaction.id}_{package_id}"[:64],  # Ограничение 64 байта
            start_parameter=f"pay_{package_id}",
            need_name=False,
            need_phone_number=False,
            need_email=False,
            need_shipping_address=False,
            is_flexible=False,
            reply_markup=None
        )
        
        await callback.answer(translate('shop.invoice.sent', default='Инвойс отправлен'))
        
        # Логируем создание инвойса
        logger.info(
            f"Stars invoice created: user={user_id}, credits={credits}, "
            f"stars={stars}, transaction_id={transaction.id}"
        )
        
    except Exception as e:
        logger.error(f"Error creating invoice: {e}")
        
        # Проверяем конкретные ошибки
        error_text = str(e).lower()
        if 'not enough' in error_text or 'insufficient' in error_text:
            await callback.answer(
                translate('shop.insufficient_stars', default='Недостаточно Telegram Stars'),
                show_alert=True
            )
        elif 'form expired' in error_text:
            await callback.answer(
                translate('shop.form_expired', default='Форма истекла. Попробуйте снова.'),
                show_alert=True
            )
        elif 'invoice already paid' in error_text:
            await callback.answer(
                translate('shop.invoice_already_paid', default='Инвойс уже оплачен.'),
                show_alert=True
            )
        else:
            await callback.answer(
                translate('shop.payment_error', default='Ошибка платежа'),
                show_alert=True
            )

@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery, bot: Bot):
    """Подтверждение платежа Telegram Stars перед оплатой"""
    # Извлекаем ID транзакции из payload
    payload = pre_checkout_query.invoice_payload
    
    if not payload or not payload.startswith("stars_transaction_"):
        await bot.answer_pre_checkout_query(
            pre_checkout_query.id,
            ok=False,
            error_message="Invalid payment data format"
        )
        return
    
    try:
        # Парсим payload: stars_transaction_{transaction_id}_{package_id}
        parts = payload.split("_")
        if len(parts) < 3:
            raise ValueError("Invalid payload format")
            
        transaction_id = int(parts[2])
        package_id = parts[3] if len(parts) > 3 else None
        
        # Проверяем транзакцию
        transaction = await db.get_transaction(transaction_id)
        
        if not transaction:
            await bot.answer_pre_checkout_query(
                pre_checkout_query.id,
                ok=False,
                error_message="Transaction not found"
            )
            return
        
        if transaction.status != 'pending':
            await bot.answer_pre_checkout_query(
                pre_checkout_query.id,
                ok=False,
                error_message="Transaction already processed"
            )
            return
            
        # Проверяем валидность суммы Stars
        if pre_checkout_query.total_amount != transaction.stars_paid:
            logger.warning(
                f"Stars amount mismatch: expected {transaction.stars_paid}, "
                f"got {pre_checkout_query.total_amount}"
            )
            await bot.answer_pre_checkout_query(
                pre_checkout_query.id,
                ok=False,
                error_message="Invalid payment amount"
            )
            return
        
        # Проверяем валюту
        if pre_checkout_query.currency != "XTR":
            await bot.answer_pre_checkout_query(
                pre_checkout_query.id,
                ok=False,
                error_message="Invalid currency"
            )
            return
        
        # Подтверждаем платеж
        await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)
        
        # Логируем подтверждение
        logger.info(
            f"Stars pre-checkout approved: user={pre_checkout_query.from_user.id}, "
            f"transaction_id={transaction_id}, stars={pre_checkout_query.total_amount}"
        )
        
    except (ValueError, IndexError) as e:
        logger.error(f"Error parsing pre-checkout payload: {e}, payload: {payload}")
        await bot.answer_pre_checkout_query(
            pre_checkout_query.id,
            ok=False,
            error_message="Payment data processing error"
        )
    except Exception as e:
        logger.error(f"Unexpected error in pre-checkout: {e}")
        await bot.answer_pre_checkout_query(
            pre_checkout_query.id,
            ok=False,
            error_message="Internal error"
        )

@router.message(F.content_type == ContentType.SUCCESSFUL_PAYMENT)
async def process_successful_payment(message: Message):
    """Обработка успешного платежа Telegram Stars"""
    payment = message.successful_payment
    payload = payment.invoice_payload
    
    # Извлекаем ID транзакции из payload
    if not payload or not payload.startswith("stars_transaction_"):
        logger.error(f"Invalid Stars payment payload: {payload}")
        return
    
    try:
        # Парсим payload: stars_transaction_{transaction_id}_{package_id}
        parts = payload.split("_")
        transaction_id = int(parts[2])
        package_id = parts[3] if len(parts) > 3 else None
        
        # Завершаем транзакцию с сохранением telegram_charge_id
        await db.complete_transaction(
            transaction_id,
            telegram_charge_id=payment.telegram_payment_charge_id
        )
        
        # Получаем обновленного пользователя и транзакцию
        user = await db.get_user(message.from_user.id)
        transaction = await db.get_transaction(transaction_id)
        
        if not user or not transaction:
            logger.error(f"User or transaction not found after payment: user_id={message.from_user.id}, transaction_id={transaction_id}")
            return
        
        # Функция перевода для языка пользователя
        user_lang = user.language_code or 'ru'
        translate = lambda key, **kwargs: i18n.get(key, user_lang, **kwargs)
        
        # Форматируем сообщение об успехе
        stars_word = "Stars" if payment.total_amount > 1 else "Star"
        text = (
            f"✅ <b>{translate('payment.success', default='Платеж успешно завершен!')}</b>\n\n"
            f"🎬 <b>{translate('payment.credits_received', default='Получено кредитов')}:</b> {transaction.amount}\n"
            f"⭐ <b>{translate('payment.paid', default='Оплачено')}:</b> {payment.total_amount} Telegram {stars_word}\n"
            f"💰 <b>{translate('payment.your_balance', default='Ваш баланс')}:</b> {user.balance} {translate('common.credits')}\n\n"
            f"🧾 <b>{translate('payment.transaction_id', default='ID транзакции')}:</b> #{transaction.id}\n"
            f"📅 <b>{translate('payment.date', default='Дата')}:</b> {transaction.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
            f"🚀 <b>{translate('payment.ready_to_create', default='Готовы создавать невероятные видео!')}</b>"
        )
        
        # Добавляем кнопки действий
        builder = InlineKeyboardBuilder()
        builder.button(text=f"🎬 {translate('menu.generate')}", callback_data="generate")
        builder.button(text=f"💰 {translate('shop.buy_more', default='Купить еще')}", callback_data="shop")
        builder.button(text=f"📊 {translate('menu.balance', balance='')}", callback_data="balance")
        builder.button(text=f"◀️ {translate('menu.main_menu')}", callback_data="back_to_menu")
        builder.adjust(2, 2)
        
        await message.answer(text, reply_markup=builder.as_markup())
        
        # Отслеживаем событие покупки для UTM аналитики
        try:
            await utm_service.track_utm_event(
                user_id=user.id,
                event_type='purchase',
                event_data={
                    'transaction_id': transaction_id,
                    'package_id': package_id,
                    'telegram_charge_id': payment.telegram_payment_charge_id
                },
                revenue=float(payment.total_amount),  # В Telegram Stars
                credits_purchased=transaction.amount
            )
        except Exception as e:
            logger.error(f"Error tracking UTM purchase event: {e}")
        
        # Логируем успешный платеж Stars
        logger.info(
            f"Successful Telegram Stars payment: user={message.from_user.id}, "
            f"credits={transaction.amount}, stars={payment.total_amount}, "
            f"charge_id={payment.telegram_payment_charge_id}, "
            f"transaction_id={transaction_id}"
        )
        
        # Отправляем уведомление в админ-канал (если настроен)
        if hasattr(settings, 'ADMIN_CHANNEL_ID') and settings.ADMIN_CHANNEL_ID:
            admin_text = (
                f"💰 <b>Новый платеж Telegram Stars</b>\n\n"
                f"👤 <b>Пользователь:</b> {message.from_user.full_name} "
                f"(@{message.from_user.username or 'no_username'})\n"
                f"🆔 <b>ID:</b> {message.from_user.id}\n"
                f"🎬 <b>Кредиты:</b> {transaction.amount}\n"
                f"⭐ <b>Stars:</b> {payment.total_amount}\n"
                f"🧾 <b>Транзакция:</b> #{transaction_id}\n"
                f"📦 <b>Пакет:</b> {package_id or 'unknown'}"
            )
            try:
                await message.bot.send_message(
                    chat_id=settings.ADMIN_CHANNEL_ID,
                    text=admin_text,
                    parse_mode='HTML'
                )
            except Exception as e:
                logger.error(f"Failed to send admin notification: {e}")
        
    except (ValueError, IndexError) as e:
        logger.error(f"Error processing Stars payment: {e}, payload: {payload}")
        
        # Функция перевода для ошибки
        user = await db.get_user(message.from_user.id)
        _ = lambda key, **kwargs: i18n.get(key, user.language_code or 'ru' if user else 'ru', **kwargs)
        
        await message.answer(
            f"❌ {_('payment.processing_error', default='Ошибка обработки платежа. Обратитесь в поддержку.')}",
            reply_markup=InlineKeyboardBuilder().button(
                text=f"🆘 {_('menu.support')}", callback_data="support"
            ).as_markup()
        )
    except Exception as e:
        logger.error(f"Unexpected error processing payment: {e}")
        
        # Функция перевода для ошибки
        user = await db.get_user(message.from_user.id)
        _ = lambda key, **kwargs: i18n.get(key, user.language_code or 'ru' if user else 'ru', **kwargs)
        
        # Отправляем сообщение об ошибке пользователю
        error_text = (
            f"❌ {_('payment.processing_error', default='Ошибка обработки платежа.')}\n\n"
            f"🔧 {_('payment.contact_support', default='Пожалуйста, обратитесь в поддержку и укажите:')}\n"
            f"• ID транзакции: {transaction_id if 'transaction_id' in locals() else 'неизвестен'}\n"
            f"• Время: {datetime.utcnow().strftime('%d.%m.%Y %H:%M:%S')}\n"
            f"• Ошибка: {str(e)[:100]}..."
        )
        
        await message.answer(
            error_text,
            reply_markup=InlineKeyboardBuilder().button(
                text=f"🆘 {_('menu.support')}", callback_data="support"
            ).as_markup()
        )

async def create_yookassa_payment(
    callback: CallbackQuery,
    bot: Bot,
    credits: int,
    rub_amount: float,
    title: str,
    package_id: str,
    is_special: bool = False
):
    """Создать платеж в ЮКассе"""
    user_id = callback.from_user.id
    user = await db.get_user(user_id)
    
    if not user:
        await callback.answer(i18n.get('errors.user_not_found', 'ru'), show_alert=True)
        return
    
    # Функция перевода для языка пользователя
    user_lang = user.language_code or 'ru'
    translate = lambda key, **kwargs: i18n.get(key, user_lang, **kwargs)
    
    try:
        from decimal import Decimal
        from services.yookassa_service import yookassa_service
        
        # Создаем транзакцию в базе данных
        transaction = await db.create_transaction(
            user_id=user.id,
            type='purchase',
            amount=credits,
            rub_paid=Decimal(str(rub_amount)),
            package_id=package_id,
            payment_method='yookassa'
        )
        
        # Создаем платеж в ЮКассе
        description = f"{title} - {credits} кредитов для {user.username or user.first_name}"
        return_url = f"{settings.WEBHOOK_HOST}/payment/success" if settings.WEBHOOK_HOST else "https://t.me/seedance_bot"
        
        success, payment_data, error = await yookassa_service.create_payment(
            amount=Decimal(str(rub_amount)),
            description=description,
            return_url=return_url,
            user_id=user_id,
            package_id=package_id,
            transaction_id=transaction.id
        )
        
        if success:
            # Сохраняем ID платежа в транзакции
            async with db.async_session() as session:
                transaction_obj = await session.get(Transaction, transaction.id)
                if transaction_obj:
                    transaction_obj.yookassa_payment_id = payment_data["payment_id"]
                    transaction_obj.yookassa_status = payment_data["status"]
                    await session.commit()
            
            # Отправляем ссылку на оплату
            confirmation_url = payment_data.get("confirmation_url")
            if confirmation_url:
                text = f"""
💳 <b>{translate('payment.yookassa.created', default='Платеж создан')}</b>

{title}
🎬 {credits} {translate('common.credits')}
💰 {rub_amount:.2f} ₽

Нажмите на кнопку ниже для оплаты банковской картой:
"""
                
                builder = InlineKeyboardBuilder()
                builder.button(
                    text=f"💳 {translate('payment.pay_now', default='Оплатить')} {rub_amount:.2f} ₽",
                    url=confirmation_url
                )
                builder.button(
                    text=f"◀️ {translate('common.back')}",
                    callback_data="shop"
                )
                builder.adjust(1)
                
                await callback.message.edit_text(text, reply_markup=builder.as_markup())
                await callback.answer(translate('payment.yookassa.redirect', default='Переходите к оплате'))
                
                # Логируем создание платежа
                logger.info(
                    f"YooKassa payment created: user={user_id}, credits={credits}, "
                    f"rub={rub_amount}, payment_id={payment_data['payment_id']}, "
                    f"transaction_id={transaction.id}"
                )
            else:
                await callback.answer(
                    translate('payment.yookassa.no_url', default='Ошибка получения ссылки на оплату'),
                    show_alert=True
                )
        else:
            await callback.answer(f"❌ {error}", show_alert=True)
            
            # Отмечаем транзакцию как неудачную
            async with db.async_session() as session:
                transaction_obj = await session.get(Transaction, transaction.id)
                if transaction_obj:
                    transaction_obj.status = 'failed'
                    await session.commit()
        
    except Exception as e:
        logger.error(f"Error creating YooKassa payment: {e}")
        await callback.answer(
            translate('payment.creation_error', default='Ошибка создания платежа'),
            show_alert=True
        )

@router.message(F.text == "/balance")
@router.callback_query(F.data == "balance")
@ensure_user
async def show_balance(update: Message | CallbackQuery, user: User, _, **kwargs):
    """Показать баланс пользователя"""
    # Получаем статистику
    stats = await db.get_user_statistics(user.telegram_id)
    
    # Считаем бонусы
    bonuses = settings.WELCOME_BONUS_CREDITS  # Бонус новичка
    
    text = MessageTemplates.BALANCE_INFO.format(
        balance=user.balance,
        total_bought=user.total_bought,
        total_spent=user.total_spent,
        bonuses=bonuses
    )
    
    # Добавляем последние транзакции
    transactions = await db.get_user_transactions(user.telegram_id, limit=5)
    if transactions:
        text += f"\n\n📋 <b>{_('balance.recent_transactions', default='Последние операции')}:</b>\n"
        for t in transactions:
            emoji = "📥" if t.amount > 0 else "📤"
            date = MessageTemplates.format_date(t.created_at)
            
            # Описание транзакции
            if t.type == TransactionTypeEnum.PURCHASE:
                desc = _('transaction.purchase', default='Покупка')
            elif t.type == TransactionTypeEnum.GENERATION:
                desc = _('transaction.generation', default='Генерация')
            elif t.type == TransactionTypeEnum.REFUND:
                desc = _('transaction.refund', default='Возврат')
            elif t.type == TransactionTypeEnum.BONUS:
                desc = _('transaction.bonus', default='Бонус')
            else:
                desc = t.description or _('transaction.other', default='Другое')
            
            text += f"{emoji} {t.amount:+d} - {desc} - {date}\n"
    
    # Кнопки
    builder = InlineKeyboardBuilder()
    builder.button(text=_("menu.buy_credits"), callback_data="shop")
    builder.button(text=_("menu.history"), callback_data="history")
    builder.button(text=f"◀️ {_('menu.main_menu')}", callback_data="back_to_menu")
    builder.adjust(2, 1)
    
    if isinstance(update, CallbackQuery):
        await update.message.edit_text(text, reply_markup=builder.as_markup())
        await update.answer()
    else:
        await update.answer(text, reply_markup=builder.as_markup())

# Функции для работы с возвратами Telegram Stars
async def refund_stars_payment(
    bot: Bot,
    user_id: int,
    telegram_charge_id: str,
    reason: str = "Refund requested"
) -> bool:
    """Возврат платежа Telegram Stars"""
    try:
        # Выполняем возврат через Bot API
        await bot.refund_star_payment(
            user_id=user_id,
            telegram_payment_charge_id=telegram_charge_id
        )
        
        logger.info(
            f"Stars refund successful: user={user_id}, "
            f"charge_id={telegram_charge_id}, reason={reason}"
        )
        return True
        
    except Exception as e:
        logger.error(f"Stars refund failed: {e}")
        return False

@router.callback_query(F.data.startswith("refund_"))
async def handle_refund_request(callback: CallbackQuery, bot: Bot):
    """Обработка запроса на возврат (только для админов)"""
    # Проверяем, является ли пользователь админом
    if callback.from_user.id not in settings.ADMIN_IDS:
        await callback.answer("❌ Доступ запрещен", show_alert=True)
        return
    
    try:
        transaction_id = int(callback.data.split("_")[1])
        transaction = await db.get_transaction(transaction_id)
        
        if not transaction:
            await callback.answer("❌ Транзакция не найдена", show_alert=True)
            return
        
        if transaction.status != 'completed':
            await callback.answer("❌ Транзакция не завершена", show_alert=True)
            return
        
        if not transaction.telegram_charge_id:
            await callback.answer("❌ Отсутствует ID платежа", show_alert=True)
            return
        
        # Проверяем, что транзакция не старше 30 дней
        from datetime import datetime, timedelta
        if datetime.utcnow() - transaction.created_at > timedelta(days=30):
            await callback.answer(
                "❌ Невозможно вернуть платеж старше 30 дней",
                show_alert=True
            )
            return
        
        # Получаем пользователя по ID из транзакции
        user_obj = await db.get_user_by_id(transaction.user_id)
        if not user_obj:
            await callback.answer("❌ Пользователь не найден", show_alert=True)
            return
        
        # Проверяем баланс пользователя
        if user_obj.balance < transaction.amount:
            await callback.answer(
                f"❌ Недостаточно средств на балансе пользователя\n"
                f"Необходимо: {transaction.amount}, доступно: {user_obj.balance}",
                show_alert=True
            )
            return
        
        # Выполняем возврат
        success = await refund_stars_payment(
            bot=bot,
            user_id=user_obj.telegram_id,
            telegram_charge_id=transaction.telegram_charge_id,
            reason="Admin refund"
        )
        
        if success:
            # Обновляем статус транзакции и баланс
            await db.process_refund(transaction_id)
            
            # Функция перевода для уведомления
            _ = lambda key, **kwargs: i18n.get(key, user_obj.language_code or 'ru', **kwargs)
            
            # Уведомляем пользователя
            try:
                await bot.send_message(
                    chat_id=user_obj.telegram_id,
                    text=(
                        f"✅ <b>{_('refund.completed', default='Возврат выполнен')}</b>\n\n"
                        f"⭐ <b>{_('refund.returned', default='Возвращено')}:</b> {transaction.stars_paid} Telegram Stars\n"
                        f"💰 <b>{_('refund.credits_deducted', default='Списано кредитов')}:</b> {transaction.amount}\n"
                        f"🧾 <b>{_('refund.transaction', default='Транзакция')}:</b> #{transaction.id}\n"
                        f"📅 <b>{_('refund.date', default='Дата')}:</b> {transaction.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
                        f"💫 {_('refund.info', default='Средства будут зачислены на ваш баланс Telegram Stars в течение нескольких минут.')}"
                    ),
                    parse_mode='HTML'
                )
            except Exception as e:
                logger.error(f"Failed to notify user about refund: {e}")
            
            await callback.answer("✅ Возврат выполнен", show_alert=True)
            
            # Логируем в админ-канал
            if hasattr(settings, 'ADMIN_CHANNEL_ID') and settings.ADMIN_CHANNEL_ID:
                admin_text = (
                    f"💸 <b>Выполнен возврат</b>\n\n"
                    f"👤 <b>Админ:</b> @{callback.from_user.username or 'admin'} ({callback.from_user.id})\n"
                    f"👤 <b>Пользователь:</b> @{user_obj.username or 'user'} ({user_obj.telegram_id})\n"
                    f"⭐ <b>Возвращено Stars:</b> {transaction.stars_paid}\n"
                    f"💰 <b>Списано кредитов:</b> {transaction.amount}\n"
                    f"🧾 <b>Транзакция:</b> #{transaction.id}"
                )
                try:
                    await bot.send_message(
                        chat_id=settings.ADMIN_CHANNEL_ID,
                        text=admin_text,
                        parse_mode='HTML'
                    )
                except:
                    pass
        else:
            await callback.answer("❌ Ошибка возврата", show_alert=True)
            
    except ValueError:
        await callback.answer("❌ Неверный ID транзакции", show_alert=True)
    except Exception as e:
        logger.error(f"Error processing refund: {e}")
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)

@router.message(F.text == "/transactions")
@ensure_user
async def show_transactions(message: Message, user: User, _, **kwargs):
    """Показать историю транзакций (расширенная)"""
    # Получаем транзакции (только завершенные и возвращенные)
    transactions = await db.get_user_transactions(user.telegram_id, limit=20)
    
    if not transactions:
        await message.answer(
            f"{_('transactions.empty', default='У вас пока нет транзакций')}\n\n"
            f"{_('transactions.buy_credits_hint', default='Купите кредиты, чтобы начать создавать видео!')}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text=_("menu.buy_credits"), callback_data="shop")
            ]])
        )
        return
    
    text = f"📋 <b>{_('transactions.history', default='История транзакций')}</b>\n\n"
    
    for t in transactions:
        # Эмодзи по типу
        if t.type == TransactionTypeEnum.PURCHASE:
            emoji = "💳"
            type_text = _('transaction.purchase', default='Покупка')
        elif t.type == TransactionTypeEnum.GENERATION:
            emoji = "🎬"
            type_text = _('transaction.generation', default='Генерация')
        elif t.type == TransactionTypeEnum.REFUND:
            emoji = "💸"
            type_text = _('transaction.refund', default='Возврат')
        elif t.type == TransactionTypeEnum.BONUS:
            emoji = "🎁"
            type_text = _('transaction.bonus', default='Бонус')
        else:
            emoji = "💰"
            type_text = _('transaction.other', default='Другое')
        
        # Форматируем сумму
        amount_str = f"{t.amount:+d}" if t.amount != 0 else "0"
        
        # Дата
        date = t.created_at.strftime("%d.%m.%Y %H:%M")
        
        # Статус транзакции
        status_suffix = ""
        if t.status == 'refunded':
            status_suffix = f" | ❌ {_('transaction.refunded', default='Возвращено')}"
        elif t.status == 'failed':
            status_suffix = f" | ❌ {_('transaction.failed', default='Неудачно')}"
        elif t.status == 'cancelled':
            status_suffix = f" | ❌ {_('transaction.cancelled', default='Отменено')}"
        elif t.status == 'pending':
            status_suffix = f" | ⏳ {_('transaction.pending', default='Ожидание')}"
        elif t.status == 'completed':
            status_suffix = f" | ✅ {_('transaction.completed', default='Завершено')}"
        
        text += f"{emoji} <b>#{t.id}</b> | {date}\n"
        text += f"   {type_text} | {amount_str} {_('common.credits')}{status_suffix}\n"
        
        if t.description:
            text += f"   📝 {t.description}\n"
        
        text += "\n"
    
    # Кнопки
    builder = InlineKeyboardBuilder()
    builder.button(text=f"📊 {_('menu.balance', balance='')}", callback_data="balance")
    builder.button(text=f"💰 {_('menu.buy_credits')}", callback_data="shop")
    builder.button(text=f"◀️ {_('menu.main_menu')}", callback_data="back_to_menu")
    builder.adjust(2, 1)
    
    await message.answer(text, reply_markup=builder.as_markup())

@router.message(F.text == "/all_transactions")
@ensure_user
async def show_all_transactions(message: Message, user: User, _, **kwargs):
    """Показать ВСЕ транзакции включая отмененные (для админов)"""
    # Получаем все транзакции (включая отмененные)
    transactions = await db.get_user_transactions(user.telegram_id, limit=50, include_all_statuses=True)
    
    if not transactions:
        await message.answer(_('transactions.empty'))
        return
    
    text = f"📋 <b>{_('transactions.all_history', default='Полная история транзакций')}</b>\n\n"
    
    for t in transactions:
        # Эмодзи по типу
        if t.type == TransactionTypeEnum.PURCHASE:
            emoji = "💳"
            type_text = _('balance.purchase')
        elif t.type == TransactionTypeEnum.GENERATION:
            emoji = "🎬"
            type_text = _('balance.generation')
        elif t.type == TransactionTypeEnum.REFUND:
            emoji = "💸"
            type_text = _('balance.refund')
        elif t.type == TransactionTypeEnum.BONUS:
            emoji = "🎁"
            type_text = _('balance.bonus')
        else:
            emoji = "💰"
            type_text = _('balance.other')
        
        # Форматируем сумму
        amount_str = f"{t.amount:+d}"
        
        # Дата
        date = t.created_at.strftime('%d.%m %H:%M')
        
        # Статус
        status_emoji = ""
        if t.status == 'refunded':
            status_emoji = _('balance.status.refunded')
        elif t.status == 'failed':
            status_emoji = _('balance.status.failed')
        elif t.status == 'cancelled':
            status_emoji = _('balance.status.cancelled')
        elif t.status == 'pending':
            status_emoji = _('balance.status.pending')
        elif t.status == 'completed':
            status_emoji = _('balance.status.completed')
        
        text += f"{emoji} <b>#{t.id}</b> | {date}\n"
        text += f"   {type_text} | {amount_str} {_('common.credits')}{status_emoji}\n"
        
        if t.description:
            desc = t.description if len(t.description) <= 50 else f"{t.description[:50]}..."
            text += f"   💬 {desc}\n"
        
        text += "\n"
    
    # Кнопки
    builder = InlineKeyboardBuilder()
    builder.button(text=f"📊 {_('menu.balance', balance='')}", callback_data="balance")
    builder.button(text=f"💰 {_('menu.buy_credits')}", callback_data="shop")
    builder.button(text=f"◀️ {_('menu.main_menu')}", callback_data="back_to_menu")
    builder.adjust(2, 1)
    
    await message.answer(text, reply_markup=builder.as_markup())

# ===============================
# ОБРАБОТКА WEBHOOK ЮКАССЫ
# ===============================

async def process_yookassa_webhook(event_data: dict, bot):
    """Обработать webhook от ЮКассы"""
    try:
        from services.yookassa_service import yookassa_service
        from models.models import Transaction
        
        event_type = event_data.get("event_type")
        payment_id = event_data.get("payment_id")
        status = event_data.get("status")
        metadata = event_data.get("metadata", {})
        
        if not payment_id:
            logger.error("YooKassa webhook: payment_id not found")
            return False
        
        # Находим транзакцию по payment_id
        async with db.async_session() as session:
            result = await session.execute(
                select(Transaction).where(Transaction.yookassa_payment_id == payment_id)
            )
            transaction = result.scalar_one_or_none()
            
            if not transaction:
                logger.error(f"YooKassa webhook: transaction not found for payment {payment_id}")
                return False
        
        user_id = int(metadata.get("user_id", 0))
        transaction_id = int(metadata.get("transaction_id", 0))
        package_id = metadata.get("package_id")
        
        if transaction.id != transaction_id:
            logger.error(f"YooKassa webhook: transaction ID mismatch")
            return False
        
        # Обрабатываем разные типы событий
        if event_type == "payment.succeeded" and status == "succeeded":
            await process_successful_yookassa_payment(
                transaction, event_data, bot
            )
        elif event_type == "payment.canceled" or status in ["canceled", "failed"]:
            await process_failed_yookassa_payment(
                transaction, event_data, bot
            )
        else:
            # Обновляем статус транзакции
            async with db.async_session() as session:
                transaction_obj = await session.get(Transaction, transaction.id)
                if transaction_obj:
                    transaction_obj.yookassa_status = status
                    await session.commit()
            
            logger.info(f"YooKassa webhook: status updated to {status} for payment {payment_id}")
        
        return True
        
    except Exception as e:
        logger.error(f"Error processing YooKassa webhook: {e}")
        return False

async def process_successful_yookassa_payment(transaction, event_data: dict, bot):
    """Обработать успешный платеж ЮКассы"""
    try:
        payment_id = event_data.get("payment_id")
        amount = event_data.get("amount", 0)
        
        # Завершаем транзакцию
        async with db.async_session() as session:
            transaction_obj = await session.get(Transaction, transaction.id)
            if not transaction_obj or transaction_obj.status == 'completed':
                logger.warning(f"YooKassa: transaction {transaction.id} already completed or not found")
                return
            
            # Обновляем транзакцию
            transaction_obj.status = 'completed'
            transaction_obj.yookassa_status = 'succeeded'
            transaction_obj.completed_at = datetime.utcnow()
            
            # Начисляем кредиты пользователю
            user = await session.get(User, transaction_obj.user_id)
            if user:
                old_balance = user.balance
                user.balance += transaction_obj.amount
                user.total_bought += transaction_obj.amount
                transaction_obj.balance_before = old_balance
                transaction_obj.balance_after = user.balance
            
            await session.commit()
        
        # Получаем обновленные данные
        user = await db.get_user_by_id(transaction.user_id)
        if not user:
            logger.error(f"YooKassa: user not found for transaction {transaction.id}")
            return
        
        # Функция перевода для языка пользователя
        user_lang = user.language_code or 'ru'
        translate = lambda key, **kwargs: i18n.get(key, user_lang, **kwargs)
        
        # Отправляем уведомление пользователю
        text = f"""
✅ <b>{translate('payment.yookassa.success', default='Оплата ЮКассой успешна!')}</b>

🎬 <b>{translate('payment.credits_received', default='Получено кредитов')}:</b> {transaction.amount}
💳 <b>{translate('payment.paid', default='Оплачено')}:</b> {amount:.2f} ₽
💰 <b>{translate('payment.your_balance', default='Ваш баланс')}:</b> {user.balance} {translate('common.credits')}

🧾 <b>{translate('payment.transaction_id', default='ID транзакции')}:</b> #{transaction.id}
📅 <b>{translate('payment.date', default='Дата')}:</b> {transaction.created_at.strftime('%d.%m.%Y %H:%M')}

🚀 <b>{translate('payment.ready_to_create', default='Готовы создавать невероятные видео!')}</b>
"""
        
        # Добавляем кнопки действий
        builder = InlineKeyboardBuilder()
        builder.button(text=f"🎬 {translate('menu.generate')}", callback_data="generate")
        builder.button(text=f"💰 {translate('shop.buy_more', default='Купить еще')}", callback_data="shop")
        builder.button(text=f"📊 {translate('menu.balance', balance='')}", callback_data="balance")
        builder.button(text=f"◀️ {translate('menu.main_menu')}", callback_data="back_to_menu")
        builder.adjust(2, 2)
        
        await bot.send_message(
            chat_id=user.telegram_id,
            text=text,
            reply_markup=builder.as_markup(),
            parse_mode='HTML'
        )
        
        # Отслеживаем событие покупки для UTM аналитики
        try:
            await utm_service.track_utm_event(
                user_id=user.id,
                event_type='purchase',
                event_data={
                    'transaction_id': transaction.id,
                    'package_id': transaction.package_id,
                    'yookassa_payment_id': payment_id
                },
                revenue=float(amount),  # В рублях
                credits_purchased=transaction.amount
            )
        except Exception as e:
            logger.error(f"Error tracking UTM purchase event: {e}")
        
        # Логируем успешный платеж
        logger.info(
            f"Successful YooKassa payment: user={user.telegram_id}, "
            f"credits={transaction.amount}, rub={amount}, "
            f"payment_id={payment_id}, transaction_id={transaction.id}"
        )
        
        # Отправляем уведомление в админ-канал
        if hasattr(settings, 'ADMIN_CHANNEL_ID') and settings.ADMIN_CHANNEL_ID:
            admin_text = f"""
💳 <b>Новый платеж ЮКасса</b>

👤 <b>Пользователь:</b> {user.first_name} (@{user.username or 'no_username'})
🆔 <b>ID:</b> {user.telegram_id}
🎬 <b>Кредиты:</b> {transaction.amount}
💳 <b>Рубли:</b> {amount:.2f} ₽
🧾 <b>Транзакция:</b> #{transaction.id}
📦 <b>Пакет:</b> {transaction.package_id or 'unknown'}
💰 <b>Payment ID:</b> {payment_id}
"""
            try:
                await bot.send_message(
                    chat_id=settings.ADMIN_CHANNEL_ID,
                    text=admin_text,
                    parse_mode='HTML'
                )
            except Exception as e:
                logger.error(f"Failed to send admin notification: {e}")
        
    except Exception as e:
        logger.error(f"Error processing successful YooKassa payment: {e}")

async def process_failed_yookassa_payment(transaction, event_data: dict, bot):
    """Обработать неудачный платеж ЮКассы"""
    try:
        payment_id = event_data.get("payment_id")
        status = event_data.get("status")
        
        # Обновляем статус транзакции
        async with db.async_session() as session:
            transaction_obj = await session.get(Transaction, transaction.id)
            if transaction_obj:
                transaction_obj.status = 'failed' if status == 'failed' else 'cancelled'
                transaction_obj.yookassa_status = status
                await session.commit()
        
        # Получаем пользователя
        user = await db.get_user_by_id(transaction.user_id)
        if not user:
            return
        
        # Функция перевода
        user_lang = user.language_code or 'ru'
        translate = lambda key, **kwargs: i18n.get(key, user_lang, **kwargs)
        
        # Отправляем уведомление пользователю
        if status == 'canceled':
            text = f"""
❌ <b>{translate('payment.yookassa.canceled', default='Платеж отменен')}</b>

Оплата была отменена пользователем или истекло время ожидания.

Попробуйте оформить заказ заново или обратитесь в поддержку.
"""
        else:
            text = f"""
❌ <b>{translate('payment.yookassa.failed', default='Ошибка оплаты')}</b>

Произошла ошибка при обработке платежа.

Попробуйте оформить заказ заново или обратитесь в поддержку.
"""
        
        builder = InlineKeyboardBuilder()
        builder.button(text=f"💰 {translate('shop.try_again', default='Попробовать снова')}", callback_data="shop")
        builder.button(text=f"🆘 {translate('menu.support')}", callback_data="support")
        builder.adjust(1)
        
        await bot.send_message(
            chat_id=user.telegram_id,
            text=text,
            reply_markup=builder.as_markup(),
            parse_mode='HTML'
        )
        
        logger.info(f"YooKassa payment {status}: payment_id={payment_id}, transaction_id={transaction.id}")
        
    except Exception as e:
        logger.error(f"Error processing failed YooKassa payment: {e}")
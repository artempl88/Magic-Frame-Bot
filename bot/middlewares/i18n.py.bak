import json
import os
import logging
from typing import Callable, Dict, Any, Awaitable, Optional
from pathlib import Path
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

logger = logging.getLogger(__name__)

class I18n:
    """Класс для работы с переводами"""
    
    def __init__(self, default_lang: str = 'ru', locales_dir: str = 'locales'):
        self.default_lang = default_lang
        self.locales_dir = Path(locales_dir)
        self.translations: Dict[str, Dict] = {}
        self._load_fallback_translations()
        self.load_translations()
    
    def _load_fallback_translations(self):
        """Загрузка резервных переводов"""
        self.translations['ru'] = {
            'language_info': {
                'name': 'Русский',
                'native_name': 'Русский',
                'emoji': '🇷🇺'
            },
            'common': {
                'back': 'Назад',
                'cancel': 'Отмена',
                'credits': 'кредитов',
                'page': 'стр. {page}/{total}',
                'days': 'дней'
            },
            'menu': {
                'main': 'Главное меню',
                'main_menu': 'Главное меню',
                'generate': 'Создать видео',
                'buy_credits': 'Купить кредиты',
                'balance': 'Баланс: {balance}',
                'history': 'История',
                'referral': 'Реферальная программа',
                'settings': 'Настройки',
                'help': 'Помощь',
                'support': 'Поддержка',
                'videos_created': 'Создано видео: {count}',
                'choose_action': 'Выберите действие:'
            },
            'errors': {
                'insufficient_balance': 'Недостаточно кредитов',
                'error': 'Ошибка',
                'prompt_too_long': 'Слишком длинный промпт',
                'prompt_too_short': 'Слишком короткий промпт',
                'image_too_large': 'Изображение слишком большое',
                'invalid_file_type': 'Неверный тип файла'
            }
        }
    
    def load_translations(self):
        """Загрузка всех файлов переводов"""
        if not self.locales_dir.exists():
            logger.warning(f"Locales directory {self.locales_dir} does not exist, using fallback translations")
            return
        
        for locale_file in self.locales_dir.glob('*.json'):
            lang_code = locale_file.stem
            try:
                with open(locale_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if content:  # Проверяем, что файл не пустой
                        self.translations[lang_code] = json.loads(content)
                        logger.info(f"Loaded locale: {lang_code}")
                    else:
                        logger.warning(f"Empty locale file: {lang_code}")
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in locale {lang_code}: {e}")
            except Exception as e:
                logger.error(f"Failed to load locale {lang_code}: {e}")
    
    def get(
        self,
        key: str,
        lang: Optional[str] = None,
        default: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        Получить перевод по ключу
        
        Args:
            key: Ключ перевода (например, "menu.generate")
            lang: Код языка
            default: Значение по умолчанию
            **kwargs: Параметры для форматирования
        """
        lang = lang or self.default_lang
        
        # Получаем переводы для языка
        translations = self.translations.get(lang)
        if not translations:
            translations = self.translations.get(self.default_lang, {})
        
        # Навигация по ключу
        keys = key.split('.')
        value = translations
        
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                value = None
                break
        
        # Если перевод не найден
        if value is None:
            # Пробуем найти в языке по умолчанию
            if lang != self.default_lang:
                default_translations = self.translations.get(self.default_lang, {})
                default_value = default_translations
                for k in keys:
                    if isinstance(default_value, dict):
                        default_value = default_value.get(k)
                    else:
                        default_value = None
                        break
                if default_value is not None:
                    value = default_value
            
            # Если все еще не найден, используем default или возвращаем ключ
            if value is None:
                if default is not None:
                    return default
                logger.debug(f"Translation not found: {key} for lang {lang}")
                return key
        
        # Форматируем строку если есть параметры
        if isinstance(value, str) and kwargs:
            try:
                return value.format(**kwargs)
            except KeyError as e:
                logger.error(f"Format error in translation {key}: {e}")
                return value
        
        return value
    
    def get_available_languages(self) -> Dict[str, Dict[str, str]]:
        """Получить список доступных языков"""
        languages = {}
        for lang_code in self.translations.keys():
            lang_info = self.translations[lang_code].get('language_info', {})
            languages[lang_code] = {
                'name': lang_info.get('name', lang_code),
                'native_name': lang_info.get('native_name', lang_code),
                'emoji': lang_info.get('emoji', '🌐')
            }
        return languages

class I18nMiddleware(BaseMiddleware):
    """Middleware для мультиязычности"""
    
    def __init__(self, i18n: Optional[I18n] = None):
        self.i18n = i18n or I18n()
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        """Добавление i18n в контекст"""
        user = data.get("event_from_user")
        
        # Определяем язык пользователя
        user_lang = self.i18n.default_lang
        
        if user:
            # Пробуем получить из БД
            db_user = data.get('db_user')
            if db_user and db_user.language_code:
                user_lang = db_user.language_code
            else:
                # Используем язык из Telegram
                user_lang = self.determine_user_language(user)
        
        # Создаем функцию перевода для текущего пользователя
        def _(key: str, default: Optional[str] = None, **kwargs) -> str:
            return self.i18n.get(key, lang=user_lang, default=default, **kwargs)
        
        # Добавляем в контекст
        data['i18n'] = self.i18n
        data['_'] = _
        data['user_lang'] = user_lang
        
        # Продолжаем обработку
        return await handler(event, data)
    
    def determine_user_language(self, telegram_user) -> str:
        """Определяет язык пользователя на основе языка Telegram"""
        if not hasattr(telegram_user, 'language_code') or not telegram_user.language_code:
            return self.i18n.default_lang
        
        lang_code = telegram_user.language_code.lower()
        
        # Прямое соответствие
        if lang_code in self.i18n.translations:
            return lang_code
        
        # Обработка языков с региональными кодами
        base_lang = lang_code.split('-')[0].split('_')[0]
        if base_lang in self.i18n.translations:
            return base_lang
        
        # Специальная обработка для региональных кодов (только ru и en)
        lang_mapping = {
            'en': ['en-us', 'en_us', 'en-gb', 'en_gb'],
            'ru': ['ru-ru', 'ru_ru']
        }
        
        for supported_lang, variants in lang_mapping.items():
            if lang_code in variants:
                return supported_lang
        
        # По умолчанию
        return self.i18n.default_lang

# Глобальный экземпляр i18n
i18n = I18n()

def get_text(key: str, lang: str = 'ru', default: Optional[str] = None, **kwargs) -> str:
    """Быстрый доступ к переводам"""
    return i18n.get(key, lang, default, **kwargs)

# Декоратор для локализованных хендлеров
def localized(key_prefix: str = None):
    """
    Декоратор для автоматической локализации ответов
    
    Usage:
        @localized("menu")
        async def menu_handler(message: Message, _: Callable):
            await message.answer(_("main"))  # Будет искать "menu.main"
    """
    def decorator(func):
        async def wrapper(event, *args, **kwargs):
            # Получаем функцию перевода из контекста
            _ = kwargs.get('_')
            if _ and key_prefix:
                # Создаем функцию с префиксом
                def prefixed_translate(key: str, default: Optional[str] = None, **format_kwargs):
                    full_key = f"{key_prefix}.{key}" if not key.startswith('.') else key[1:]
                    return _(full_key, default=default, **format_kwargs)
                kwargs['_'] = prefixed_translate
            
            return await func(event, *args, **kwargs)
        
        return wrapper
    return decorator

# Хелперы для работы с языками
class LanguageManager:
    """Менеджер для управления языками пользователей"""
    
    @staticmethod
    async def set_user_language(user_id: int, language: str) -> bool:
        """Установить язык пользователя"""
        from services.database import db
        
        try:
            user = await db.get_user(user_id)
            if user:
                user.language_code = language
                if user.settings is None:
                    user.settings = {}
                user.settings['language'] = language
                
                async with db.async_session() as session:
                    session.add(user)
                    await session.commit()
                
                return True
            return False
        except Exception as e:
            logger.error(f"Error setting user language: {e}")
            return False
    
    @staticmethod
    async def get_user_language(user_id: int) -> str:
        """Получить язык пользователя"""
        from services.database import db
        
        try:
            user = await db.get_user(user_id)
            if user and user.language_code:
                return user.language_code
            return i18n.default_lang
        except Exception as e:
            logger.error(f"Error getting user language: {e}")
            return i18n.default_lang
    
    @staticmethod
    def get_language_keyboard():
        """Получить клавиатуру выбора языка"""
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        
        builder = InlineKeyboardBuilder()
        languages = i18n.get_available_languages()
        
        for lang_code, lang_info in languages.items():
            builder.button(
                text=f"{lang_info['emoji']} {lang_info['native_name']}",
                callback_data=f"set_language_{lang_code}"
            )
        
        # Размещаем по 2 кнопки в ряд
        builder.adjust(2)
        return builder.as_markup()
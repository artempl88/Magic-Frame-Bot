#!/usr/bin/env python3

import re

# Читаем файл
with open('./bot/handlers/admin.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Исправляем декоратор admin_only
old_decorator = '''# Декоратор для проверки админских прав
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
    return wrapper'''

new_decorator = '''# Декоратор для проверки админских прав
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
    return wrapper'''

# Заменяем декоратор
content = content.replace(old_decorator, new_decorator)

# Записываем обратно
with open('./bot/handlers/admin.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Декоратор admin_only исправлен")

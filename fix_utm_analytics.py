import re

# Читаем файл
with open('services/utm_analytics.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Исправляем проблемную строку
# Заменяем func.cast(UTMClick.is_first_visit, func.INTEGER) на более простую конструкцию
content = content.replace(
    'func.sum(func.cast(UTMClick.is_first_visit, func.INTEGER)).label(\'first_visits\')',
    'func.sum(UTMClick.is_first_visit.cast(func.Integer)).label(\'first_visits\')'
)

# Также добавим импорт Integer
if 'from sqlalchemy import' in content:
    content = content.replace(
        'from sqlalchemy import and_, func, desc, or_, select, text',
        'from sqlalchemy import and_, func, desc, or_, select, text, Integer'
    )

# Записываем исправленный файл
with open('services/utm_analytics.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Файл utm_analytics.py исправлен")

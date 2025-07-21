# Читаем файл
with open('services/utm_analytics.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Заменим проблемную строку на более простую
old_pattern = r'func\.sum\(UTMClick\.is_first_visit\.cast\(func\.Integer\)\)\.label\(\'first_visits\'\)'
new_pattern = 'func.count(UTMClick.id.distinct().filter(UTMClick.is_first_visit == True)).label(\'first_visits\')'

if 'func.sum(UTMClick.is_first_visit.cast(func.Integer)).label(\'first_visits\')' in content:
    content = content.replace(
        'func.sum(UTMClick.is_first_visit.cast(func.Integer)).label(\'first_visits\')',
        'func.sum(func.case((UTMClick.is_first_visit == True, 1), else_=0)).label(\'first_visits\')'
    )
else:
    print("Строка не найдена, попробуем другой вариант")
    # Возможно строка все еще в старом формате
    if 'func.sum(func.cast(UTMClick.is_first_visit, func.INTEGER)).label(\'first_visits\')' in content:
        content = content.replace(
            'func.sum(func.cast(UTMClick.is_first_visit, func.INTEGER)).label(\'first_visits\')',
            'func.sum(func.case((UTMClick.is_first_visit == True, 1), else_=0)).label(\'first_visits\')'
        )

# Добавим импорт case если его нет
if 'from sqlalchemy import' in content and 'case' not in content:
    content = content.replace(
        'from sqlalchemy import and_, func, desc, or_, select, text',
        'from sqlalchemy import and_, func, desc, or_, select, text, case'
    )

# Записываем исправленный файл
with open('services/utm_analytics.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Файл utm_analytics.py исправлен (версия 2)")

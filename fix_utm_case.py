# Читаем файл
with open('services/utm_analytics.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Исправляем синтаксис func.case
# Неправильно: func.case((UTMClick.is_first_visit == True, 1), else_=0)
# Правильно: func.case([(UTMClick.is_first_visit == True, 1)], else_=0)
content = content.replace(
    'func.sum(func.case((UTMClick.is_first_visit == True, 1), else_=0)).label(\'first_visits\')',
    'func.sum(func.case([(UTMClick.is_first_visit == True, 1)], else_=0)).label(\'first_visits\')'
)

# Записываем исправленный файл
with open('services/utm_analytics.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Исправлен синтаксис func.case в utm_analytics.py")

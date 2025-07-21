# Читаем файл
with open('services/utm_analytics.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Найдем место перед "# Глобальный экземпляр сервиса"
insert_point = content.rfind("# Глобальный экземпляр сервиса")
if insert_point == -1:
    insert_point = len(content)

# Простая функция аналитики кредитов
credit_method = '''
    async def get_campaign_credit_analytics(self, campaign_id: int) -> Dict:
        """Простая аналитика по кредитам для кампании"""
        try:
            async with db.async_session() as session:
                # Получаем статистику пользователей кампании
                result = await session.execute(
                    select(
                        func.count(User.id).label('total_users'),
                        func.sum(User.balance).label('total_balance'),
                        func.sum(User.total_spent).label('total_spent'),
                        func.sum(User.total_bought).label('total_bought'),
                        func.sum(User.total_bonuses).label('total_bonuses')
                    ).select_from(User)
                    .join(UTMClick, User.id == UTMClick.user_id)
                    .where(UTMClick.campaign_id == campaign_id)
                )
                
                row = result.first()
                
                return {
                    'summary': {
                        'total_users': row.total_users or 0,
                        'total_credits_balance': row.total_balance or 0,
                        'total_credits_spent': row.total_spent or 0,
                        'total_credits_bought': row.total_bought or 0,
                        'total_bonus_credits': row.total_bonuses or 0,
                        'avg_balance_per_user': round((row.total_balance or 0) / max(row.total_users or 1, 1), 2),
                        'avg_spent_per_user': round((row.total_spent or 0) / max(row.total_users or 1, 1), 2)
                    },
                    'total_revenue': {'stars': 0, 'rub': 0}
                }
        except Exception as e:
            logger.error(f"Error in credit analytics: {e}")
            return {
                'summary': {
                    'total_users': 0,
                    'total_credits_balance': 0,
                    'total_credits_spent': 0,
                    'total_credits_bought': 0,
                    'total_bonus_credits': 0,
                    'avg_balance_per_user': 0,
                    'avg_spent_per_user': 0
                },
                'total_revenue': {'stars': 0, 'rub': 0}
            }

'''

# Вставляем метод
new_content = content[:insert_point] + credit_method + content[insert_point:]

# Записываем файл
with open('services/utm_analytics.py', 'w', encoding='utf-8') as f:
    f.write(new_content)

print("Добавлена простая аналитика кредитов")

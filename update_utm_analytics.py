# Читаем файл
with open('services/utm_analytics.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Найдем определение оригинальной версии get_campaign_analytics
method_start = content.find('async def get_campaign_analytics(')
method_end = content.find('\n    async def', method_start + 1)
if method_end == -1:
    method_end = content.find('\n    def', method_start + 1)
if method_end == -1:
    method_end = content.find('\n# Глобальный экземпляр сервиса', method_start)

# Улучшенная версия аналитики
enhanced_method = '''    async def get_campaign_analytics(
        self,
        campaign_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict:
        """Получает полную и расширенную аналитику по конкретной кампании"""

        async with db.async_session() as session:
            # Получаем кампанию
            result = await session.execute(
                select(UTMCampaign).where(UTMCampaign.id == campaign_id)
            )
            campaign = result.scalar()

            if not campaign:
                return {}

            # Базовые фильтры
            click_filters = [UTMClick.campaign_id == campaign_id]
            event_filters = [UTMEvent.campaign_id == campaign_id]

            if start_date:
                click_filters.append(UTMClick.clicked_at >= start_date)
                event_filters.append(UTMEvent.event_at >= start_date)

            if end_date:
                click_filters.append(UTMClick.clicked_at <= end_date)
                event_filters.append(UTMEvent.event_at <= end_date)

            # Статистика по кликам и покупкам
            clicks_and_payments = await session.execute(
                select(
                    func.count(UTMClick.id).label('total_clicks'),
                    func.count(func.distinct(UTMClick.telegram_id)).label('unique_users'),
                    func.sum(UTMClick.is_first_visit.cast(Integer)).label('first_visits'),
                    func.sum(UTMEvent.credits_purchased).label('total_credits_purchased'),
                    func.sum(UTMEvent.credits_spent).label('total_credits_spent')
                ).where(and_(*click_filters))
            )
            click_stats = clicks_and_payments.first()

            # Статистика по кредитам и покупкам
            credit_stats_result = await session.execute(
                select(
                    func.sum(User.balance).label('total_user_balance'),
                    func.sum(User.total_bonuses).label('total_bonus_credits'),
                    func.sum(User.total_bought).label('total_credits_bought')
                ).where(User.id == UTMClick.user_id)
            )
            credit_stats = credit_stats_result.first()

            # Анализ событий
            events_result = await session.execute(
                select(
                    UTMEvent.event_type,
                    func.count(UTMEvent.id).label('count'),
                    func.sum(UTMEvent.revenue).label('total_revenue')
                ).where(and_(*event_filters))
                .group_by(UTMEvent.event_type)
            )

            events_stats = {}
            for row in events_result:
                events_stats[row.event_type] = {
                    'count': row.count,
                    'total_revenue': float(row.total_revenue) if row.total_revenue else 0.0
                }

            # Конверсии
            total_clicks = click_stats.total_clicks or 0            
            total_users = click_stats.unique_users or 0
            registration_count = events_stats.get('registration', {}).get('count', 0)
            purchase_count = events_stats.get('purchase', {}).get('count', 0)

            conversion_registration = (registration_count / total_clicks * 100) if total_clicks > 0 else 0
            conversion_purchase = (purchase_count / registration_count * 100) if registration_count > 0 else 0

            # Пакеты покупок самые популярные
            popular_packages_result = await session.execute(
                select(
                    UTMEvent.campaign_id,
                    User.total_spent,
                    User.balance,
                    func.count(User.id).label('user_count')
                ).where(User.id == UTMClick.user_id)
                .group_by(UTMEvent.campaign_id, User.total_spent, User.balance)
                .order_by(desc('user_count'))
                .limit(5)
            )

            popular_packages = popular_packages_result.fetchall()

            return {
                'campaign': {
                    'id': campaign.id,
                    'name': campaign.name,
                    'utm_source': campaign.utm_source,
                    'utm_medium': campaign.utm_medium,
                    'utm_campaign': campaign.utm_campaign,
                    'utm_content': campaign.utm_content,
                    'action_type': campaign.action_type,
                    'created_at': campaign.created_at.isoformat(),
                    'is_active': campaign.is_active
                },
                'clicks': {
                    'total_clicks': total_clicks,
                    'unique_users': total_users,
                    'first_visits': click_stats.first_visits or 0
                },
                'events': events_stats,
                'conversions': {
                    'registration_rate': round(conversion_registration, 2),
                    'purchase_rate': round(conversion_purchase, 2)
                },
                'credits': {
                    'total_user_balance': credit_stats.total_user_balance or 0,
                    'total_bonus_credits': credit_stats.total_bonus_credits or 0,
                    'total_credits_bought': credit_stats.total_credits_bought or 0
                },
                'popular_packages': [
                    {
                        'campaign_id': pkg.campaign_id,
                        'total_spent': pkg.total_spent,
                        'balance': pkg.balance,
                        'user_count': pkg.user_count
                    }
                    for pkg in popular_packages
                ]
            }
'''

# Заменяем метод на улучшенную версию
if method_end != -1:
    content = content[:method_start] + enhanced_method + content[method_end:]
else:
    content = content[:method_start] + enhanced_method + '\n\n'

# Записываем обновленный файл
with open('services/utm_analytics.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Аналитика UTM обновлена для отслеживания кредитов и покупок")

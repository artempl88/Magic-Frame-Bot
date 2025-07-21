# Читаем файл
with open('services/utm_analytics.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Найдем функцию export_campaign_data и заменим её
export_start = content.find('async def export_campaign_data(')
export_end = content.find('\n    async def', export_start + 1)
if export_end == -1:
    export_end = content.find('\n# Глобальный экземпляр сервиса', export_start)

# Расширенная функция экспорта с кредитами
enhanced_export = '''    async def export_campaign_data(
        self,
        campaign_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        export_format: str = "detailed"
    ) -> List[Dict]:
        """Экспортирует расширенные данные кампании включая кредиты и покупки"""
        
        async with db.async_session() as session:
            # Получаем кампанию для метаданных
            campaign_result = await session.execute(
                select(UTMCampaign).where(UTMCampaign.id == campaign_id)
            )
            campaign = campaign_result.scalar()
            
            if not campaign:
                return []
            
            if export_format == "summary":
                # Краткий экспорт с базовой аналитикой
                analytics = await self.get_campaign_analytics(campaign_id, start_date, end_date)
                credit_analytics = await self.get_campaign_credit_analytics(campaign_id, start_date, end_date)
                
                summary_data = [{
                    'campaign_id': campaign_id,
                    'campaign_name': analytics['campaign']['name'],
                    'utm_source': analytics['campaign']['utm_source'],
                    'utm_medium': analytics['campaign']['utm_medium'],
                    'utm_campaign': analytics['campaign']['utm_campaign'],
                    'utm_content': analytics['campaign']['utm_content'] or '',
                    'total_clicks': analytics['clicks']['total_clicks'],
                    'unique_users': analytics['clicks']['unique_users'],
                    'first_visits': analytics['clicks']['first_visits'],
                    'registrations': analytics['events'].get('registration', {}).get('count', 0),
                    'purchases': analytics['events'].get('purchase', {}).get('count', 0),
                    'total_revenue': analytics['events'].get('purchase', {}).get('total_revenue', 0),
                    'registration_rate': analytics['conversions']['registration_rate'],
                    'purchase_rate': analytics['conversions']['purchase_rate'],
                    'total_credits_bought': credit_analytics['summary']['total_credits_bought'],
                    'total_credits_spent': credit_analytics['summary']['total_credits_spent'],
                    'total_purchases_count': credit_analytics['summary']['total_purchases'],
                    'avg_purchase_amount': credit_analytics['summary']['avg_purchase_amount'],
                    'most_popular_package': credit_analytics['summary']['most_popular_package'] or '',
                    'total_revenue_stars': credit_analytics['total_revenue']['stars'],
                    'total_revenue_rub': credit_analytics['total_revenue']['rub'],
                    'bonus_events_count': len(credit_analytics['bonus_events']),
                    'created_at': analytics['campaign']['created_at'],
                    'is_active': analytics['campaign']['is_active'],
                    'export_date': datetime.utcnow().isoformat()
                }]
                
                return summary_data
            
            # Детальный экспорт со всеми данными
            query = """
            SELECT 
                c.id as click_id,
                c.clicked_at,
                c.telegram_id,
                c.is_first_visit,
                c.is_registered_user,
                c.user_agent,
                c.ip_address,
                u.username,
                u.first_name,
                u.balance as user_current_balance,
                u.total_spent as user_total_spent,
                u.total_bought as user_total_bought,
                u.total_bonuses as user_total_bonuses,
                u.created_at as user_registration_date,
                e.id as event_id,
                e.event_type,
                e.event_at,
                e.revenue,
                e.credits_spent,
                e.credits_purchased,
                e.time_from_click,
                e.event_data,
                t.type as transaction_type,
                t.amount as transaction_amount,
                t.package_id as purchased_package,
                t.stars_paid,
                t.rub_paid,
                t.payment_method,
                t.created_at as transaction_date,
                pc.code as promo_code_used,
                pcu.used_at as promo_used_at,
                pcu.credits_bonus as promo_credits_bonus
            FROM utm_clicks c
            LEFT JOIN users u ON c.user_id = u.id
            LEFT JOIN utm_events e ON c.id = e.click_id
            LEFT JOIN transactions t ON u.id = t.user_id
            LEFT JOIN promo_code_usages pcu ON u.id = pcu.user_id
            LEFT JOIN promo_codes pc ON pcu.promo_code_id = pc.id
            WHERE c.campaign_id = :campaign_id
            """
            
            params = {'campaign_id': campaign_id}
            
            if start_date:
                query += " AND c.clicked_at >= :start_date"
                params['start_date'] = start_date
            
            if end_date:
                query += " AND c.clicked_at <= :end_date"
                params['end_date'] = end_date
            
            query += " ORDER BY c.clicked_at DESC, e.event_at ASC, t.created_at ASC"
            
            result = await session.execute(text(query), params)
            
            data = []
            for row in result:
                data.append({
                    'campaign_id': campaign_id,
                    'campaign_name': campaign.name,
                    'utm_source': campaign.utm_source,
                    'utm_medium': campaign.utm_medium,
                    'utm_campaign': campaign.utm_campaign,
                    'utm_content': campaign.utm_content or '',
                    'click_id': row.click_id,
                    'clicked_at': row.clicked_at.isoformat() if row.clicked_at else '',
                    'telegram_id': row.telegram_id,
                    'username': row.username or '',
                    'first_name': row.first_name or '',
                    'is_first_visit': row.is_first_visit,
                    'is_registered_user': row.is_registered_user,
                    'user_agent': row.user_agent or '',
                    'ip_address': row.ip_address or '',
                    'user_current_balance': row.user_current_balance or 0,
                    'user_total_spent': row.user_total_spent or 0,
                    'user_total_bought': row.user_total_bought or 0,
                    'user_total_bonuses': row.user_total_bonuses or 0,
                    'user_registration_date': row.user_registration_date.isoformat() if row.user_registration_date else '',
                    'event_id': row.event_id or '',
                    'event_type': row.event_type or '',
                    'event_at': row.event_at.isoformat() if row.event_at else '',
                    'revenue': float(row.revenue) if row.revenue else 0.0,
                    'credits_spent': row.credits_spent or 0,
                    'credits_purchased': row.credits_purchased or 0,
                    'time_from_click_seconds': row.time_from_click or 0,
                    'time_from_click_minutes': round((row.time_from_click or 0) / 60, 2),
                    'event_data': str(row.event_data) if row.event_data else '',
                    'transaction_type': row.transaction_type or '',
                    'transaction_amount': row.transaction_amount or 0,
                    'purchased_package': row.purchased_package or '',
                    'stars_paid': row.stars_paid or 0,
                    'rub_paid': float(row.rub_paid) if row.rub_paid else 0.0,
                    'payment_method': row.payment_method or '',
                    'transaction_date': row.transaction_date.isoformat() if row.transaction_date else '',
                    'promo_code_used': row.promo_code_used or '',
                    'promo_used_at': row.promo_used_at.isoformat() if row.promo_used_at else '',
                    'promo_credits_bonus': row.promo_credits_bonus or 0,
                    'has_converted': 'Yes' if row.event_type else 'No',
                    'has_purchased': 'Yes' if row.transaction_type == 'purchase' else 'No',
                    'used_promo': 'Yes' if row.promo_code_used else 'No',
                    'export_timestamp': datetime.utcnow().isoformat()
                })
            
            return data'''

# Заменяем функцию экспорта
if export_end != -1:
    content = content[:export_start] + enhanced_export + content[export_end:]
else:
    content = content[:export_start] + enhanced_export + '\n\n'

# Записываем обновленный файл
with open('services/utm_analytics.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Функция экспорта обновлена для включения данных по кредитам и промо-кодам")

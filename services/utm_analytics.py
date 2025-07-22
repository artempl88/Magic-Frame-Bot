import hashlib
import secrets
import string
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlencode, urlparse, parse_qs
import json
import logging

from sqlalchemy import and_, func, desc, or_, select, text
from sqlalchemy.orm import sessionmaker

from models.models import UTMCampaign, UTMClick, UTMEvent, User
from services.database import db

logger = logging.getLogger(__name__)

class UTMAnalyticsService:
    """Сервис для работы с UTM-аналитикой"""
    
    def __init__(self):
        self.base_bot_url = "https://t.me/MagicFrameBot"  # URL бота
    
    def generate_short_code(self, length: int = 8) -> str:
        """Генерирует короткий код для UTM ссылки"""
        alphabet = string.ascii_letters + string.digits
        return ''.join(secrets.choice(alphabet) for _ in range(length))
    
    async def create_utm_campaign(
        self,
        admin_id: int,
        name: str,
        utm_source: str,
        utm_medium: str,
        utm_campaign: str,
        action_type: str = "registration",
        utm_content: Optional[str] = None,
        utm_term: Optional[str] = None,
        description: Optional[str] = None
    ) -> UTMCampaign:
        """Создает новую UTM кампанию"""
        
        # Генерируем уникальный короткий код
        short_code = self.generate_short_code()
        while await self._short_code_exists(short_code):
            short_code = self.generate_short_code()
        
        # Формируем UTM параметры
        utm_params = {
            'utm_source': utm_source,
            'utm_medium': utm_medium,
            'utm_campaign': utm_campaign,
            'start': f'utm_{short_code}'  # Специальный параметр для deeplink
        }
        
        if utm_content:
            utm_params['utm_content'] = utm_content
        if utm_term:
            utm_params['utm_term'] = utm_term
        
        # Генерируем финальную ссылку
        utm_link = f"{self.base_bot_url}?{urlencode(utm_params)}"
        
        # Создаем кампанию
        campaign = UTMCampaign(
            name=name,
            description=description,
            utm_source=utm_source,
            utm_medium=utm_medium,
            utm_campaign=utm_campaign,
            utm_content=utm_content,
            utm_term=utm_term,
            action_type=action_type,
            utm_link=utm_link,
            short_code=short_code,
            created_by_admin_id=admin_id
        )
        
        async with db.async_session() as session:
            session.add(campaign)
            await session.commit()
            await session.refresh(campaign)
        
        logger.info(f"Created UTM campaign {campaign.id} by admin {admin_id}")
        return campaign
    
    async def _short_code_exists(self, short_code: str) -> bool:
        """Проверяет существование короткого кода"""
        async with db.async_session() as session:
            result = await session.execute(
                select(UTMCampaign).where(UTMCampaign.short_code == short_code)
            )
            return result.scalar() is not None
    
    async def track_utm_click(
        self,
        short_code: str,
        telegram_id: Optional[int] = None,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
        referrer: Optional[str] = None,
        additional_params: Optional[Dict] = None
    ) -> Optional[UTMClick]:
        """Отслеживает клик по UTM ссылке"""
        
        async with db.async_session() as session:
            # Находим кампанию
            result = await session.execute(
                select(UTMCampaign).where(
                    and_(
                        UTMCampaign.short_code == short_code,
                        UTMCampaign.is_active == True
                    )
                )
            )
            campaign = result.scalar()
            
            if not campaign:
                logger.warning(f"UTM campaign not found for short_code: {short_code}")
                return None
            
            # Ищем пользователя если есть telegram_id
            user = None
            is_registered_user = False
            is_first_visit = True
            
            if telegram_id:
                result = await session.execute(
                    select(User).where(User.telegram_id == telegram_id)
                )
                user = result.scalar()
                is_registered_user = user is not None
                
                # Проверяем, был ли уже клик от этого пользователя по этой кампании
                if user:
                    result = await session.execute(
                        select(UTMClick).where(
                            and_(
                                UTMClick.campaign_id == campaign.id,
                                UTMClick.user_id == user.id
                            )
                        ).limit(1)
                    )
                    is_first_visit = result.scalar() is None
            
            # Создаем запись клика
            click = UTMClick(
                campaign_id=campaign.id,
                user_id=user.id if user else None,
                telegram_id=telegram_id,
                user_agent=user_agent,
                ip_address=ip_address,
                referrer=referrer,
                additional_params=additional_params,
                is_first_visit=is_first_visit,
                is_registered_user=is_registered_user
            )
            
            session.add(click)
            
            # Обновляем счетчик кликов в кампании
            campaign.total_clicks += 1
            
            await session.commit()
            await session.refresh(click)
            
            logger.info(f"Tracked UTM click for campaign {campaign.id}, user {telegram_id}")
            return click
    
    async def track_utm_event(
        self,
        user_id: int,
        event_type: str,
        event_data: Optional[Dict] = None,
        revenue: Optional[float] = None,
        credits_spent: Optional[int] = None,
        credits_purchased: Optional[int] = None,
        session_id: Optional[str] = None
    ) -> Optional[UTMEvent]:
        """Отслеживает событие пользователя и привязывает к UTM кампании"""
        
        async with db.async_session() as session:
            # Находим последний клик пользователя (в течение 30 дней)
            cutoff_date = datetime.utcnow() - timedelta(days=30)
            
            result = await session.execute(
                select(UTMClick).where(
                    and_(
                        UTMClick.user_id == user_id,
                        UTMClick.clicked_at > cutoff_date
                    )
                ).order_by(desc(UTMClick.clicked_at)).limit(1)
            )
            
            last_click = result.scalar()
            
            if not last_click:
                # Нет UTM клика, событие не привязываем
                return None
            
            # Вычисляем время от клика до события
            time_from_click = int((datetime.utcnow() - last_click.clicked_at).total_seconds())
            
            # Создаем событие
            event = UTMEvent(
                campaign_id=last_click.campaign_id,
                user_id=user_id,
                click_id=last_click.id,
                event_type=event_type,
                event_data=event_data,
                revenue=revenue,
                credits_spent=credits_spent,
                credits_purchased=credits_purchased,
                session_id=session_id,
                time_from_click=time_from_click
            )
            
            session.add(event)
            
            # Обновляем статистику кампании
            campaign_result = await session.execute(
                select(UTMCampaign).where(UTMCampaign.id == last_click.campaign_id)
            )
            campaign = campaign_result.scalar()
            
            if campaign:
                if event_type == 'registration':
                    campaign.total_registrations += 1
                elif event_type == 'purchase':
                    campaign.total_purchases += 1
                    if revenue:
                        campaign.total_revenue += revenue
            
            await session.commit()
            await session.refresh(event)
            
            logger.info(f"Tracked UTM event {event_type} for user {user_id}, campaign {last_click.campaign_id}")
            return event
    
    async def get_campaign_analytics(
        self,
        campaign_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict:
        """Получает аналитику по конкретной кампании"""
        
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
            
            # Статистика по кликам
            clicks_result = await session.execute(
                select(
                    func.count(UTMClick.id).label('total_clicks'),
                    func.count(func.distinct(UTMClick.telegram_id)).label('unique_users'),
                    func.count(UTMClick.id).filter(UTMClick.is_first_visit == True).label('first_visits')
                ).where(and_(*click_filters))
            )
            click_stats = clicks_result.first()
            
            # Статистика по событиям
            events_result = await session.execute(
                select(
                    UTMEvent.event_type,
                    func.count(UTMEvent.id).label('count'),
                    func.sum(UTMEvent.revenue).label('total_revenue'),
                    func.sum(UTMEvent.credits_spent).label('total_credits_spent'),
                    func.sum(UTMEvent.credits_purchased).label('total_credits_purchased'),
                    func.avg(UTMEvent.time_from_click).label('avg_time_to_convert_seconds'),
                    func.min(UTMEvent.time_from_click).label('min_time_to_convert_seconds'),
                    func.max(UTMEvent.time_from_click).label('max_time_to_convert_seconds')
                ).where(and_(*event_filters))
                .group_by(UTMEvent.event_type)
            )
            
            events_stats = {}
            for row in events_result:
                events_stats[row.event_type] = {
                    'count': row.count,
                    'total_revenue': float(row.total_revenue) if row.total_revenue else 0.0,
                    'total_credits_spent': row.total_credits_spent or 0,
                    'total_credits_purchased': row.total_credits_purchased or 0,
                    'avg_time_to_convert_minutes': round(row.avg_time_to_convert_seconds / 60, 1) if row.avg_time_to_convert_seconds else 0,
                    'min_time_to_convert_seconds': row.min_time_to_convert_seconds or 0,
                    'max_time_to_convert_seconds': row.max_time_to_convert_seconds or 0
                }
            
            # Конверсии
            total_clicks = click_stats.total_clicks or 0
            registrations = events_stats.get('registration', {}).get('count', 0)
            purchases = events_stats.get('purchase', {}).get('count', 0)
            
            conversion_registration = (registrations / total_clicks * 100) if total_clicks > 0 else 0
            conversion_purchase = (purchases / registrations * 100) if registrations > 0 else 0
            
            # Статистика по времени
            timeline_data = await self._get_timeline_analytics(campaign_id, start_date, end_date, session)
            
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
                    'unique_users': click_stats.unique_users or 0,
                    'first_visits': click_stats.first_visits or 0
                },
                'events': events_stats,
                'conversions': {
                    'registration_rate': round(conversion_registration, 2),
                    'purchase_rate': round(conversion_purchase, 2)
                },
                'revenue': {
                    'total': sum(stats.get('total_revenue', 0) for stats in events_stats.values()),
                    'per_click': 0  # Будет вычислено ниже
                },
                'timeline': timeline_data
            }
    
    async def _get_timeline_analytics(self, campaign_id: int, start_date: Optional[datetime], end_date: Optional[datetime], session) -> Dict:
        """Получает аналитику по времени для кампании"""
        filters = [UTMClick.campaign_id == campaign_id]
        if start_date:
            filters.append(UTMClick.clicked_at >= start_date)
        if end_date:
            filters.append(UTMClick.clicked_at <= end_date)
        
        # Статистика по дням (используем func.date для PostgreSQL)
        daily_result = await session.execute(
            select(
                func.date(UTMClick.clicked_at).label('date'),
                func.count(UTMClick.id).label('clicks'),
                func.count(func.distinct(UTMClick.telegram_id)).label('unique_users')
            ).where(and_(*filters))
            .group_by(func.date(UTMClick.clicked_at))
            .order_by(desc('date'))
            .limit(30)
        )
        
        daily_stats = []
        for row in daily_result:
            daily_stats.append({
                'date': row.date.isoformat(),
                'clicks': row.clicks,
                'unique_users': row.unique_users
            })
        
        # Топ часы активности - ИСПРАВЛЕННЫЙ ЗАПРОС
        # Создаем алиас для выражения to_char
        hour_expr = func.to_char(UTMClick.clicked_at, 'HH24:00')
        
        hour_result = await session.execute(
            select(
                hour_expr.label('hour'),
                func.count(UTMClick.id).label('clicks')
            ).where(and_(*filters))
            .group_by(hour_expr)  # Группируем по тому же выражению
            .order_by(desc('clicks'))
            .limit(5)
        )
        
        top_hours = []
        for row in hour_result:
            top_hours.append({
                'hour': row.hour,
                'clicks': row.clicks
            })
        
        return {
            'daily_stats': daily_stats,
            'top_hours': top_hours
        }
    
    async def get_campaigns_list(
        self,
        admin_id: Optional[int] = None,
        is_active: Optional[bool] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[UTMCampaign]:
        """Получает список UTM кампаний"""
        
        async with db.async_session() as session:
            query = select(UTMCampaign)
            
            filters = []
            if admin_id:
                filters.append(UTMCampaign.created_by_admin_id == admin_id)
            if is_active is not None:
                filters.append(UTMCampaign.is_active == is_active)
            
            if filters:
                query = query.where(and_(*filters))
            
            query = query.order_by(desc(UTMCampaign.created_at)).limit(limit).offset(offset)
            
            result = await session.execute(query)
            return result.scalars().all()
    
    async def toggle_campaign_status(self, campaign_id: int, admin_id: int) -> bool:
        """Переключает статус активности кампании"""
        
        async with db.async_session() as session:
            result = await session.execute(
                select(UTMCampaign).where(UTMCampaign.id == campaign_id)
            )
            campaign = result.scalar()
            
            if not campaign:
                return False
            
            campaign.is_active = not campaign.is_active
            campaign.updated_at = datetime.utcnow()
            
            await session.commit()
            
            logger.info(f"Admin {admin_id} toggled campaign {campaign_id} status to {campaign.is_active}")
            return True
    
    async def export_campaign_data(
        self,
        campaign_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Dict]:
        """Экспортирует данные кампании для CSV/Excel"""
        
        async with db.async_session() as session:
            # Получаем информацию о кампании
            campaign_result = await session.execute(
                select(UTMCampaign).where(UTMCampaign.id == campaign_id)
            )
            campaign = campaign_result.scalar()
            
            if not campaign:
                return []
            
            # Получаем детальные данные по кликам и событиям
            query = """
            SELECT 
                c.id as click_id,
                c.clicked_at,
                c.telegram_id,
                c.is_first_visit,
                c.is_registered_user,
                c.user_agent,
                c.ip_address,
                c.referrer,
                u.username,
                u.first_name,
                u.last_name,
                u.language_code,
                u.balance as user_credits_balance,
                u.is_premium,
                u.created_at as user_registration_date,
                e.event_type,
                e.event_at,
                e.revenue,
                e.credits_spent,
                e.credits_purchased,
                e.time_from_click
            FROM utm_clicks c
            LEFT JOIN users u ON c.user_id = u.id
            LEFT JOIN utm_events e ON c.id = e.click_id
            WHERE c.campaign_id = :campaign_id
            """
            
            params = {'campaign_id': campaign_id}
            
            if start_date:
                query += " AND c.clicked_at >= :start_date"
                params['start_date'] = start_date
            
            if end_date:
                query += " AND c.clicked_at <= :end_date"
                params['end_date'] = end_date
            
            query += " ORDER BY c.clicked_at DESC"
            
            result = await session.execute(text(query), params)
            
            data = []
            for row in result:
                # Вычисляем производные метрики
                clicked_at = row.clicked_at
                click_date = clicked_at.date()
                click_hour = clicked_at.hour
                click_day_of_week = clicked_at.strftime('%A')
                
                time_from_click_minutes = round((row.time_from_click or 0) / 60, 2) if row.time_from_click else None
                time_from_click_hours = round((row.time_from_click or 0) / 3600, 2) if row.time_from_click else None
                
                has_converted = bool(row.event_type)
                conversion_type = row.event_type if has_converted else None
                
                data.append({
                    f'Кампания_{campaign_id}': campaign.name,
                    'utm_source': campaign.utm_source,
                    'utm_medium': campaign.utm_medium,
                    'utm_campaign': campaign.utm_campaign,
                    'utm_content': campaign.utm_content or '',
                    'click_id': row.click_id,
                    'clicked_at': clicked_at.isoformat() if clicked_at else '',
                    'click_date': str(click_date),
                    'click_hour': click_hour,
                    'click_day_of_week': click_day_of_week,
                    'telegram_id': row.telegram_id or '',
                    'username': row.username or '',
                    'first_name': row.first_name or '',
                    'last_name': row.last_name or '',
                    'language_code': row.language_code or '',
                    'is_first_visit': row.is_first_visit,
                    'is_registered_user': row.is_registered_user,
                    'is_premium': row.is_premium if hasattr(row, 'is_premium') else False,
                    'user_credits_balance': row.user_credits_balance or 0,
                    'user_registration_date': row.user_registration_date.isoformat() if row.user_registration_date else '',
                    'user_agent': row.user_agent or '',
                    'ip_address': row.ip_address or '',
                    'referrer': row.referrer or '',
                    'event_type': row.event_type or '',
                    'event_at': row.event_at.isoformat() if row.event_at else '',
                    'revenue': float(row.revenue) if row.revenue else 0.0,
                    'credits_spent': row.credits_spent or 0,
                    'credits_purchased': row.credits_purchased or 0,
                    'time_from_click_seconds': row.time_from_click or '',
                    'time_from_click_minutes': time_from_click_minutes or '',
                    'time_from_click_hours': time_from_click_hours or '',
                    'has_converted': has_converted,
                    'conversion_type': conversion_type or '',
                    'export_timestamp': datetime.utcnow().isoformat()
                })
            
            return data
    
    async def get_top_sources_analytics(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 10
    ) -> List[Dict]:
        """Получает аналитику по топ источникам трафика"""
        
        async with db.async_session() as session:
            filters = []
            
            if start_date:
                filters.append(UTMClick.clicked_at >= start_date)
            if end_date:
                filters.append(UTMClick.clicked_at <= end_date)
            
            query = select(
                UTMCampaign.utm_source,
                UTMCampaign.utm_medium,
                func.count(UTMClick.id).label('total_clicks'),
                func.count(func.distinct(UTMClick.telegram_id)).label('unique_users'),
                func.count(UTMEvent.id).label('total_events'),
                func.sum(UTMEvent.revenue).label('total_revenue')
            ).select_from(
                UTMCampaign.__table__.join(UTMClick, UTMCampaign.id == UTMClick.campaign_id)
                .outerjoin(UTMEvent, UTMClick.id == UTMEvent.click_id)
            )
            
            if filters:
                query = query.where(and_(*filters))
            
            query = query.group_by(
                UTMCampaign.utm_source, UTMCampaign.utm_medium
            ).order_by(
                desc('total_clicks')
            ).limit(limit)
            
            result = await session.execute(query)
            
            analytics = []
            for row in result:
                analytics.append({
                    'source': row.utm_source,
                    'medium': row.utm_medium,
                    'clicks': row.total_clicks,
                    'unique_users': row.unique_users,
                    'events': row.total_events or 0,
                    'revenue': float(row.total_revenue) if row.total_revenue else 0.0,
                    'conversion_rate': round((row.total_events or 0) / row.total_clicks * 100, 2) if row.total_clicks > 0 else 0
                })
            
            return analytics

    async def delete_utm_campaign(self, campaign_id: int, admin_id: int) -> bool:
        """Удаляет UTM кампанию и все связанные данные"""
        
        async with db.async_session() as session:
            # Проверяем существование кампании
            result = await session.execute(
                select(UTMCampaign).where(UTMCampaign.id == campaign_id)
            )
            campaign = result.scalar()
            
            if not campaign:
                return False
            
            try:
                # Удаляем связанные события
                await session.execute(
                    text("DELETE FROM utm_events WHERE campaign_id = :campaign_id"),
                    {"campaign_id": campaign_id}
                )
                
                # Удаляем связанные клики
                await session.execute(
                    text("DELETE FROM utm_clicks WHERE campaign_id = :campaign_id"),
                    {"campaign_id": campaign_id}
                )
                
                # Удаляем саму кампанию
                await session.execute(
                    text("DELETE FROM utm_campaigns WHERE id = :campaign_id"),
                    {"campaign_id": campaign_id}
                )
                
                await session.commit()
                
                logger.info(f"Admin {admin_id} deleted UTM campaign {campaign_id} ({campaign.name})")
                return True
                
            except Exception as e:
                await session.rollback()
                logger.error(f"Error deleting UTM campaign {campaign_id}: {e}")
                return False
    
    async def get_campaign_credit_analytics(self, campaign_id: int) -> Dict:
        """Получает детальную аналитику по кредитам для кампании"""
        
        async with db.async_session() as session:
            # Получаем общую статистику по кредитам
            summary_result = await session.execute(
                select(
                    func.count(UTMEvent.id).filter(UTMEvent.event_type == 'purchase').label('total_purchases'),
                    func.sum(UTMEvent.credits_purchased).filter(UTMEvent.event_type == 'purchase').label('total_credits_bought'),
                    func.sum(UTMEvent.credits_spent).filter(UTMEvent.event_type == 'generation').label('total_credits_spent'),
                    func.avg(UTMEvent.credits_purchased).filter(UTMEvent.event_type == 'purchase').label('avg_purchase_amount')
                ).where(UTMEvent.campaign_id == campaign_id)
            )
            summary = summary_result.first()
            
            # Получаем выручку по методам оплаты
            revenue_result = await session.execute(
                text("""
                    SELECT 
                        SUM(CASE WHEN t.stars_paid IS NOT NULL THEN t.stars_paid ELSE 0 END) as total_stars,
                        SUM(CASE WHEN t.rub_paid IS NOT NULL THEN t.rub_paid ELSE 0 END) as total_rub
                    FROM utm_events e
                    JOIN transactions t ON e.event_data->>'transaction_id' = CAST(t.id AS TEXT)
                    WHERE e.campaign_id = :campaign_id AND e.event_type = 'purchase'
                """),
                {"campaign_id": campaign_id}
            )
            revenue = revenue_result.first()
            
            # Топ покупаемые пакеты
            packages_result = await session.execute(
                text("""
                    SELECT 
                        t.package_id,
                        t.amount,
                        COUNT(*) as transaction_count,
                        SUM(t.amount) as total_credits,
                        SUM(COALESCE(t.stars_paid, 0)) as total_stars_paid,
                        SUM(COALESCE(t.rub_paid, 0)) as total_rub_paid
                    FROM utm_events e
                    JOIN transactions t ON e.event_data->>'transaction_id' = CAST(t.id AS TEXT)
                    WHERE e.campaign_id = :campaign_id 
                        AND e.event_type = 'purchase'
                        AND t.status = 'completed'
                    GROUP BY t.package_id, t.amount
                    ORDER BY transaction_count DESC
                    LIMIT 10
                """),
                {"campaign_id": campaign_id}
            )
            
            packages = []
            for row in packages_result:
                packages.append({
                    'package_id': row.package_id,
                    'amount': row.amount,
                    'transaction_count': row.transaction_count,
                    'total_credits': row.total_credits,
                    'total_stars_paid': row.total_stars_paid or 0,
                    'total_rub_paid': float(row.total_rub_paid) if row.total_rub_paid else 0.0
                })
            
            # Бонусные события
            bonus_result = await session.execute(
                select(
                    UTMEvent.event_data,
                    func.count(UTMEvent.id).label('usage_count'),
                    func.sum(UTMEvent.credits_purchased).label('credits_amount')
                ).where(
                    and_(
                        UTMEvent.campaign_id == campaign_id,
                        UTMEvent.event_type == 'bonus'
                    )
                ).group_by(UTMEvent.event_data)
            )
            
            bonuses = []
            for row in bonus_result:
                bonuses.append({
                    'event_data': row.event_data,
                    'usage_count': row.usage_count,
                    'credits_amount': row.credits_amount or 0
                })
            
            # Паттерны трат
            spending_result = await session.execute(
                text("""
                    SELECT 
                        t.amount,
                        COUNT(*) as transaction_count
                    FROM utm_events e
                    JOIN transactions t ON e.user_id = t.user_id
                    WHERE e.campaign_id = :campaign_id 
                        AND t.type = 'generation'
                        AND t.created_at >= e.event_at
                    GROUP BY t.amount
                    ORDER BY transaction_count DESC
                    LIMIT 10
                """),
                {"campaign_id": campaign_id}
            )
            
            spending_patterns = []
            for row in spending_result:
                spending_patterns.append({
                    'amount': row.amount,
                    'transaction_count': row.transaction_count
                })
            
            return {
                'summary': {
                    'total_purchases': summary.total_purchases or 0,
                    'total_credits_bought': summary.total_credits_bought or 0,
                    'total_credits_spent': summary.total_credits_spent or 0,
                    'avg_purchase_amount': float(summary.avg_purchase_amount) if summary.avg_purchase_amount else 0.0
                },
                'total_revenue': {
                    'stars': revenue.total_stars or 0 if revenue else 0,
                    'rub': float(revenue.total_rub) if revenue and revenue.total_rub else 0.0
                },
                'purchase_packages': packages,
                'bonus_events': bonuses,
                'spending_patterns': spending_patterns
            }


# Глобальный экземпляр сервиса
utm_service = UTMAnalyticsService()
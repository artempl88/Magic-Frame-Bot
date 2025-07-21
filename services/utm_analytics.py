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
                    func.sum(func.cast(UTMClick.is_first_visit, func.INTEGER)).label('first_visits')
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
                    func.sum(UTMEvent.credits_purchased).label('total_credits_purchased')
                ).where(and_(*event_filters))
                .group_by(UTMEvent.event_type)
            )
            
            events_stats = {}
            for row in events_result:
                events_stats[row.event_type] = {
                    'count': row.count,
                    'total_revenue': float(row.total_revenue) if row.total_revenue else 0.0,
                    'total_credits_spent': row.total_credits_spent or 0,
                    'total_credits_purchased': row.total_credits_purchased or 0
                }
            
            # Конверсии
            registrations = events_stats.get('registration', {}).get('count', 0)
            purchases = events_stats.get('purchase', {}).get('count', 0)
            
            conversion_registration = (registrations / click_stats.total_clicks * 100) if click_stats.total_clicks > 0 else 0
            conversion_purchase = (purchases / registrations * 100) if registrations > 0 else 0
            
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
                    'total_clicks': click_stats.total_clicks or 0,
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
                }
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
            # Получаем детальные данные по кликам и событиям
            query = """
            SELECT 
                c.clicked_at,
                c.telegram_id,
                c.is_first_visit,
                c.is_registered_user,
                u.username,
                u.first_name,
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
                data.append({
                    'clicked_at': row.clicked_at.isoformat() if row.clicked_at else '',
                    'telegram_id': row.telegram_id,
                    'username': row.username or '',
                    'first_name': row.first_name or '',
                    'is_first_visit': row.is_first_visit,
                    'is_registered_user': row.is_registered_user,
                    'event_type': row.event_type or '',
                    'event_at': row.event_at.isoformat() if row.event_at else '',
                    'revenue': float(row.revenue) if row.revenue else 0.0,
                    'credits_spent': row.credits_spent or 0,
                    'credits_purchased': row.credits_purchased or 0,
                    'time_from_click_seconds': row.time_from_click or 0,
                    'time_from_click_minutes': round((row.time_from_click or 0) / 60, 2)
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

# Глобальный экземпляр сервиса
utm_service = UTMAnalyticsService() 
import logging
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from sqlalchemy import select, update, delete
from sqlalchemy.orm import selectinload

from services.database import db
from models.models import PackagePrice
from core.constants import CREDIT_PACKAGES

logger = logging.getLogger(__name__)

class PriceService:
    """Сервис для управления ценами пакетов кредитов"""
    
    async def get_package_prices(self, package_id: str = None) -> Dict[str, Dict]:
        """
        Получить цены пакетов
        
        Args:
            package_id: ID конкретного пакета или None для всех
            
        Returns:
            Словарь с ценами: {package_id: {stars_price, rub_price, ...}}
        """
        try:
            async with db.async_session() as session:
                query = select(PackagePrice).where(PackagePrice.is_active == True)
                
                if package_id:
                    query = query.where(PackagePrice.package_id == package_id)
                
                result = await session.execute(query)
                price_records = result.scalars().all()
                
                # Формируем словарь цен
                prices = {}
                for record in price_records:
                    prices[record.package_id] = {
                        "id": record.id,
                        "package_id": record.package_id,
                        "stars_price": record.stars_price,
                        "rub_price": float(record.rub_price) if record.rub_price else None,
                        "created_at": record.created_at,
                        "updated_at": record.updated_at,
                        "notes": record.notes
                    }
                
                # Если цены для пакета не найдены в БД, используем дефолтные из constants
                if not prices:
                    return self._get_default_prices(package_id)
                
                return prices
                
        except Exception as e:
            logger.error(f"Error getting package prices: {e}")
            # Возвращаем дефолтные цены в случае ошибки
            return self._get_default_prices(package_id)
    
    def _get_default_prices(self, package_id: str = None) -> Dict[str, Dict]:
        """Получить дефолтные цены из constants.py"""
        default_prices = {}
        
        packages = [p for p in CREDIT_PACKAGES if not package_id or p.id == package_id]
        
        for package in packages:
            default_prices[package.id] = {
                "id": None,
                "package_id": package.id,
                "stars_price": package.stars,
                "rub_price": None,  # Дефолтные цены в рублях не установлены
                "created_at": None,
                "updated_at": None,
                "notes": "Дефолтная цена из constants.py"
            }
        
        return default_prices
    
    async def update_package_price(
        self,
        package_id: str,
        stars_price: Optional[int] = None,
        rub_price: Optional[Decimal] = None,
        admin_id: Optional[int] = None,
        notes: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Обновить цену пакета
        
        Returns:
            Tuple[success, message]
        """
        try:
            # Проверяем что пакет существует
            package = next((p for p in CREDIT_PACKAGES if p.id == package_id), None)
            if not package:
                return False, f"Пакет {package_id} не найден"
            
            async with db.async_session() as session:
                # Ищем существующую запись
                result = await session.execute(
                    select(PackagePrice).where(
                        PackagePrice.package_id == package_id,
                        PackagePrice.is_active == True
                    )
                )
                existing_price = result.scalar_one_or_none()
                
                if existing_price:
                    # Обновляем существующую запись
                    if stars_price is not None:
                        existing_price.stars_price = stars_price
                    if rub_price is not None:
                        existing_price.rub_price = rub_price
                    if notes is not None:
                        existing_price.notes = notes
                    if admin_id is not None:
                        existing_price.updated_by = admin_id
                    
                    await session.commit()
                    message = f"Цена пакета {package_id} обновлена"
                else:
                    # Создаем новую запись
                    new_price = PackagePrice(
                        package_id=package_id,
                        stars_price=stars_price or package.stars,  # Используем дефолтную если не указана
                        rub_price=rub_price,
                        created_by=admin_id,
                        updated_by=admin_id,
                        notes=notes
                    )
                    session.add(new_price)
                    await session.commit()
                    message = f"Цена пакета {package_id} создана"
                
                logger.info(f"Package price updated: {package_id} by admin {admin_id}")
                return True, message
                
        except Exception as e:
            error_msg = f"Error updating package price: {e}"
            logger.error(error_msg)
            return False, error_msg
    
    async def delete_package_price(self, package_id: str, admin_id: Optional[int] = None) -> Tuple[bool, str]:
        """
        Удалить кастомную цену пакета (вернуться к дефолтной)
        
        Returns:
            Tuple[success, message]
        """
        try:
            async with db.async_session() as session:
                # Помечаем запись как неактивную вместо удаления
                result = await session.execute(
                    update(PackagePrice)
                    .where(
                        PackagePrice.package_id == package_id,
                        PackagePrice.is_active == True
                    )
                    .values(is_active=False, updated_by=admin_id)
                )
                
                if result.rowcount > 0:
                    await session.commit()
                    logger.info(f"Package price deleted: {package_id} by admin {admin_id}")
                    return True, f"Кастомная цена пакета {package_id} удалена, восстановлена дефолтная"
                else:
                    return False, f"Кастомная цена для пакета {package_id} не найдена"
                
        except Exception as e:
            error_msg = f"Error deleting package price: {e}"
            logger.error(error_msg)
            return False, error_msg
    
    async def get_effective_price(self, package_id: str, payment_method: str = "telegram_stars") -> Optional[int]:
        """
        Получить эффективную цену пакета для определенного способа оплаты
        
        Args:
            package_id: ID пакета
            payment_method: "telegram_stars" или "yookassa"
            
        Returns:
            Цена или None если не найдена
        """
        try:
            prices = await self.get_package_prices(package_id)
            
            if package_id not in prices:
                return None
            
            price_data = prices[package_id]
            
            if payment_method == "telegram_stars":
                return price_data.get("stars_price")
            elif payment_method == "yookassa":
                rub_price = price_data.get("rub_price")
                return float(rub_price) if rub_price else None
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting effective price: {e}")
            return None
    
    async def bulk_update_prices(
        self,
        price_updates: List[Dict],
        admin_id: Optional[int] = None
    ) -> Tuple[bool, str, List[str]]:
        """
        Массовое обновление цен
        
        Args:
            price_updates: Список обновлений [{"package_id": "pack_50", "stars_price": 200, "rub_price": 150}, ...]
            admin_id: ID админа
            
        Returns:
            Tuple[success, message, errors]
        """
        try:
            successes = []
            errors = []
            
            for update_data in price_updates:
                package_id = update_data.get("package_id")
                stars_price = update_data.get("stars_price")
                rub_price = update_data.get("rub_price")
                notes = update_data.get("notes")
                
                if not package_id:
                    errors.append("package_id не указан")
                    continue
                
                success, message = await self.update_package_price(
                    package_id=package_id,
                    stars_price=stars_price,
                    rub_price=Decimal(str(rub_price)) if rub_price else None,
                    admin_id=admin_id,
                    notes=notes
                )
                
                if success:
                    successes.append(f"{package_id}: {message}")
                else:
                    errors.append(f"{package_id}: {message}")
            
            overall_success = len(successes) > 0
            summary = f"Обновлено: {len(successes)}, ошибок: {len(errors)}"
            
            return overall_success, summary, errors
            
        except Exception as e:
            error_msg = f"Error in bulk update: {e}"
            logger.error(error_msg)
            return False, error_msg, []
    
    async def get_price_history(self, package_id: str = None) -> List[Dict]:
        """
        Получить историю изменения цен
        
        Returns:
            Список записей с историей
        """
        try:
            async with db.async_session() as session:
                query = select(PackagePrice).order_by(PackagePrice.updated_at.desc())
                
                if package_id:
                    query = query.where(PackagePrice.package_id == package_id)
                
                result = await session.execute(query)
                records = result.scalars().all()
                
                history = []
                for record in records:
                    history.append({
                        "id": record.id,
                        "package_id": record.package_id,
                        "stars_price": record.stars_price,
                        "rub_price": float(record.rub_price) if record.rub_price else None,
                        "is_active": record.is_active,
                        "created_by": record.created_by,
                        "updated_by": record.updated_by,
                        "created_at": record.created_at,
                        "updated_at": record.updated_at,
                        "notes": record.notes
                    })
                
                return history
                
        except Exception as e:
            logger.error(f"Error getting price history: {e}")
            return []
    
    async def calculate_package_discount(self, old_price: int, new_price: int) -> Dict[str, float]:
        """
        Рассчитать процент скидки/наценки
        
        Returns:
            {"discount_percent": float, "discount_amount": int}
        """
        if old_price <= 0:
            return {"discount_percent": 0.0, "discount_amount": 0}
        
        discount_amount = old_price - new_price
        discount_percent = (discount_amount / old_price) * 100
        
        return {
            "discount_percent": round(discount_percent, 1),
            "discount_amount": discount_amount
        }


# Глобальный экземпляр сервиса
price_service = PriceService() 
import os
import gzip
import asyncio
import aiohttp
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Tuple
import logging
import shutil

from core.config import settings

logger = logging.getLogger(__name__)

class BackupService:
    """Сервис для управления бэкапами базы данных"""
    
    def __init__(self):
        self.backup_dir = Path("/app/backups")
        self.backup_dir.mkdir(exist_ok=True)
        
    async def create_backup(self, description: str = None) -> Tuple[bool, str, Optional[str]]:
        """
        Создать резервную копию базы данных через webhook
        
        Returns:
            Tuple[bool, str, Optional[str]]: (success, message, file_path)
        """
        try:
            logger.info(f"Создание бэкапа через webhook сервер")
            
            # URL webhook сервера на хосте
            webhook_url = "http://172.22.0.1:8082/create_backup"
            payload = {"description": description or "Резервная копия из админки"}
            
            # Отправляем запрос к webhook серверу
            timeout = aiohttp.ClientTimeout(total=300)  # 5 минут
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(webhook_url, json=payload) as response:
                        if response.status == 200:
                            result = await response.json()
                            
                            if result.get("success"):
                                # Получаем информацию о созданном файле
                                created_filename = result.get("filename", "backup_unknown.sql.gz")
                                file_size = result.get("size", 0)
                                size_mb = result.get("size_mb", 0)
                                
                                # Создаем метаданные для совместимости
                                await self._create_metadata(created_filename, description, file_size)
                                
                                success_msg = f"✅ Бэкап создан успешно!\n" \
                                             f"📁 Файл: {created_filename}\n" \
                                             f"📊 Размер: {size_mb:.1f} MB\n" \
                                             f"🕐 Время: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
                                
                                if description:
                                    success_msg += f"\n📝 Описание: {description}"
                                
                                logger.info(f"Бэкап создан через webhook: {created_filename}")
                                return True, success_msg, str(self.backup_dir / created_filename)
                            else:
                                error_msg = result.get("message", "Неизвестная ошибка")
                                logger.error(f"Ошибка webhook: {error_msg}")
                                return False, f"Ошибка создания бэкапа: {error_msg}", None
                        else:
                            error_msg = f"HTTP {response.status}: {await response.text()}"
                            logger.error(f"Ошибка HTTP: {error_msg}")
                            return False, f"Ошибка соединения с сервисом бэкапа", None
            
            except asyncio.TimeoutError:
                logger.error("Timeout при создании бэкапа")
                return False, "Превышено время ожидания создания бэкапа (5 минут)", None
            except aiohttp.ClientError as e:
                logger.error(f"Ошибка HTTP клиента: {e}")
                return False, f"Ошибка соединения с сервисом бэкапа: {str(e)}", None
            
        except Exception as e:
            error_msg = f"Критическая ошибка при создании бэкапа: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return False, error_msg, None
    
    async def _create_metadata(self, filename: str, description: str, file_size: int):
        """Создать файл метаданных для бэкапа"""
        try:
            metadata_file = self.backup_dir / f"{filename}.meta"
            metadata = {
                "created_at": datetime.now().isoformat(),
                "description": description or "Резервная копия из админки",
                "size": file_size,
                "database": settings.DB_NAME,
                "user": settings.DB_USER
            }
            
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            logger.warning(f"Не удалось создать метаданные: {e}")
    
    async def list_backups(self) -> List[dict]:
        """Получить список всех бэкапов"""
        backups = []
        
        try:
            # Включаем файлы из всех форматов
            patterns = ["backup_*.sql.gz", "magic_frame_bot_*.sql.gz"]
            all_files = []
            
            for pattern in patterns:
                all_files.extend(self.backup_dir.glob(pattern))
            
            for backup_file in sorted(all_files, key=lambda x: x.stat().st_mtime, reverse=True):
                metadata_file = backup_file.with_suffix(backup_file.suffix + ".meta")
                
                # Основная информация о файле
                stat = backup_file.stat()
                backup_info = {
                    "filename": backup_file.name,
                    "path": str(backup_file),
                    "size": stat.st_size,
                    "size_mb": stat.st_size / 1024 / 1024,
                    "created_at": datetime.fromtimestamp(stat.st_mtime),
                    "description": "Автоматический бэкап" if "magic_frame_bot_" in backup_file.name else "Ручной бэкап"
                }
                
                # Дополнительная информация из метаданных
                if metadata_file.exists():
                    try:
                        with open(metadata_file, 'r', encoding='utf-8') as f:
                            metadata = json.load(f)
                            backup_info.update({
                                "description": metadata.get("description", backup_info["description"]),
                                "created_at": datetime.fromisoformat(metadata.get("created_at", backup_info["created_at"].isoformat()))
                            })
                    except Exception as e:
                        logger.warning(f"Ошибка чтения метаданных {metadata_file}: {e}")
                
                backups.append(backup_info)
                
        except Exception as e:
            logger.error(f"Ошибка получения списка бэкапов: {e}")
        
        return backups
    
    async def delete_backup(self, filename: str) -> Tuple[bool, str]:
        """Удалить бэкап"""
        try:
            backup_file = self.backup_dir / filename
            metadata_file = backup_file.with_suffix(backup_file.suffix + ".meta")
            
            if not backup_file.exists():
                return False, f"Файл {filename} не найден"
            
            # Удаляем файл бэкапа
            backup_file.unlink()
            
            # Удаляем метаданные если есть
            if metadata_file.exists():
                metadata_file.unlink()
            
            logger.info(f"Бэкап удален: {filename}")
            return True, f"✅ Бэкап {filename} удален"
            
        except Exception as e:
            error_msg = f"Ошибка удаления бэкапа: {str(e)}"
            logger.error(error_msg)
            return False, error_msg
    
    async def cleanup_old_backups(self, days: int = 30) -> Tuple[int, str]:
        """Удалить старые бэкапы"""
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            deleted_count = 0
            total_size = 0
            
            # Обрабатываем все типы файлов
            patterns = ["backup_*.sql.gz", "magic_frame_bot_*.sql.gz"]
            
            for pattern in patterns:
                for backup_file in self.backup_dir.glob(pattern):
                    file_time = datetime.fromtimestamp(backup_file.stat().st_mtime)
                    
                    if file_time < cutoff_date:
                        file_size = backup_file.stat().st_size
                        total_size += file_size
                        
                        # Удаляем файл и метаданные
                        backup_file.unlink()
                        metadata_file = backup_file.with_suffix(backup_file.suffix + ".meta")
                        if metadata_file.exists():
                            metadata_file.unlink()
                        
                        deleted_count += 1
                        logger.info(f"Удален старый бэкап: {backup_file.name}")
            
            size_mb = total_size / 1024 / 1024
            result_msg = f"🧹 Очистка завершена:\n" \
                        f"📁 Удалено файлов: {deleted_count}\n" \
                        f"💾 Освобождено места: {size_mb:.1f} MB"
            
            logger.info(f"Очистка бэкапов: удалено {deleted_count} файлов ({size_mb:.1f} MB)")
            return deleted_count, result_msg
            
        except Exception as e:
            error_msg = f"Ошибка очистки бэкапов: {str(e)}"
            logger.error(error_msg)
            return 0, error_msg
    
    async def get_backup_stats(self) -> dict:
        """Получить статистику бэкапов"""
        try:
            backups = await self.list_backups()
            total_size = sum(b["size"] for b in backups)
            
            if backups:
                latest_backup = max(backups, key=lambda x: x["created_at"])
                oldest_backup = min(backups, key=lambda x: x["created_at"])
            else:
                latest_backup = oldest_backup = None
            
            return {
                "total_count": len(backups),
                "total_size": total_size,
                "total_size_mb": total_size / 1024 / 1024,
                "latest_backup": latest_backup,
                "oldest_backup": oldest_backup,
                "backup_dir": str(self.backup_dir.absolute())
            }
            
        except Exception as e:
            logger.error(f"Ошибка получения статистики: {e}")
            return {
                "total_count": 0,
                "total_size": 0,
                "total_size_mb": 0,
                "latest_backup": None,
                "oldest_backup": None,
                "backup_dir": str(self.backup_dir.absolute())
            }
    
    async def restore_backup(self, filename: str) -> Tuple[bool, str]:
        """
        Восстановить базу данных из бэкапа
        ⚠️ ОПАСНАЯ ОПЕРАЦИЯ - заменяет всю базу данных!
        """
        try:
            backup_file = self.backup_dir / filename
            
            if not backup_file.exists():
                return False, f"Файл {filename} не найден"
            
            logger.warning(f"ВОССТАНОВЛЕНИЕ БД из {filename}")
            
            # Пока возвращаем сообщение о недоступности функции
            return False, "Функция восстановления временно недоступна"
            
        except Exception as e:
            error_msg = f"Критическая ошибка восстановления: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return False, error_msg

# Глобальный экземпляр сервиса
backup_service = BackupService()

import os
import gzip
import asyncio
import subprocess
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
        self.backup_dir = Path("./backups")
        self.backup_dir.mkdir(exist_ok=True)
        
    async def create_backup(self, description: str = None) -> Tuple[bool, str, Optional[str]]:
        """
        Создать резервную копию базы данных
        
        Returns:
            Tuple[bool, str, Optional[str]]: (success, message, file_path)
        """
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"backup_{timestamp}.sql.gz"
            file_path = self.backup_dir / filename
            
            # Команда для создания дампа PostgreSQL
            pg_dump_cmd = [
                "docker", "exec", "-i", "client_postgres",
                "pg_dump", 
                "-U", settings.DB_USER,
                "-d", settings.DB_NAME,
                "--verbose",
                "--no-password"
            ]
            
            logger.info(f"Создание бэкапа: {filename}")
            
            # Выполняем pg_dump и сжимаем результат
            process = await asyncio.create_subprocess_exec(
                *pg_dump_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, "PGPASSWORD": settings.DB_PASSWORD}
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Неизвестная ошибка"
                logger.error(f"Ошибка создания бэкапа: {error_msg}")
                return False, f"Ошибка создания бэкапа: {error_msg}", None
            
            # Сжимаем результат
            with gzip.open(file_path, 'wb') as f:
                f.write(stdout)
            
            # Получаем размер файла
            file_size = file_path.stat().st_size
            size_mb = file_size / 1024 / 1024
            
            # Создаем метаданные
            await self._create_metadata(filename, description, file_size)
            
            success_msg = f"✅ Бэкап создан успешно!\n" \
                         f"📁 Файл: {filename}\n" \
                         f"📊 Размер: {size_mb:.1f} MB\n" \
                         f"🕐 Время: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
            
            if description:
                success_msg += f"\n📝 Описание: {description}"
            
            logger.info(f"Бэкап создан: {filename} ({size_mb:.1f} MB)")
            return True, success_msg, str(file_path)
            
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
                "description": description or "Ручной бэкап",
                "size": file_size,
                "database": settings.DB_NAME,
                "user": settings.DB_USER
            }
            
            with open(metadata_file, 'w', encoding='utf-8') as f:
                import json
                json.dump(metadata, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            logger.warning(f"Не удалось создать метаданные: {e}")
    
    async def list_backups(self) -> List[dict]:
        """Получить список всех бэкапов"""
        backups = []
        
        try:
            for backup_file in sorted(self.backup_dir.glob("backup_*.sql.gz"), reverse=True):
                metadata_file = backup_file.with_suffix(backup_file.suffix + ".meta")
                
                # Основная информация о файле
                stat = backup_file.stat()
                backup_info = {
                    "filename": backup_file.name,
                    "path": str(backup_file),
                    "size": stat.st_size,
                    "size_mb": stat.st_size / 1024 / 1024,
                    "created_at": datetime.fromtimestamp(stat.st_mtime),
                    "description": "Автоматический бэкап"
                }
                
                # Дополнительная информация из метаданных
                if metadata_file.exists():
                    try:
                        import json
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
            
            for backup_file in self.backup_dir.glob("backup_*.sql.gz"):
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
            
            # Команды для восстановления
            drop_db_cmd = [
                "docker", "exec", "-i", "client_postgres",
                "dropdb", "-U", settings.DB_USER, settings.DB_NAME
            ]
            
            create_db_cmd = [
                "docker", "exec", "-i", "client_postgres", 
                "createdb", "-U", settings.DB_USER, settings.DB_NAME
            ]
            
            restore_cmd = [
                "docker", "exec", "-i", "client_postgres",
                "psql", "-U", settings.DB_USER, "-d", settings.DB_NAME
            ]
            
            # Удаляем существующую БД
            process = await asyncio.create_subprocess_exec(
                *drop_db_cmd,
                env={**os.environ, "PGPASSWORD": settings.DB_PASSWORD}
            )
            await process.communicate()
            
            # Создаем новую БД  
            process = await asyncio.create_subprocess_exec(
                *create_db_cmd,
                env={**os.environ, "PGPASSWORD": settings.DB_PASSWORD}
            )
            await process.communicate()
            
            # Восстанавливаем данные
            with gzip.open(backup_file, 'rb') as f:
                process = await asyncio.create_subprocess_exec(
                    *restore_cmd,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env={**os.environ, "PGPASSWORD": settings.DB_PASSWORD}
                )
                
                stdout, stderr = await process.communicate(input=f.read())
                
                if process.returncode != 0:
                    error_msg = stderr.decode() if stderr else "Неизвестная ошибка"
                    logger.error(f"Ошибка восстановления: {error_msg}")
                    return False, f"Ошибка восстановления: {error_msg}"
            
            success_msg = f"✅ База данных восстановлена из {filename}"
            logger.warning(f"БД восстановлена из {filename}")
            return True, success_msg
            
        except Exception as e:
            error_msg = f"Критическая ошибка восстановления: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return False, error_msg

# Глобальный экземпляр сервиса
backup_service = BackupService() 
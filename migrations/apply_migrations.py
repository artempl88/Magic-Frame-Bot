#!/usr/bin/env python3
"""
Скрипт для применения миграций базы данных
"""

import asyncio
import os
import sys
from pathlib import Path

# Добавляем корневую папку в путь для импорта
sys.path.append(str(Path(__file__).parent.parent))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from core.config import settings

async def apply_migrations():
    """Применить все миграции"""
    # Создаем подключение к базе данных
    # Для запуска с хоста используем порт 15432 (проброшен из Docker)
    database_url = f"postgresql+asyncpg://{settings.DB_USER}:{settings.DB_PASSWORD}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"


    print(f"🔗 Подключение к базе данных: {database_url.replace(settings.DB_PASSWORD, '***')}")
    
    engine = create_async_engine(database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    # Подключаемся к базе данных
    async with async_session() as session:
        print("🔧 Применение миграций базы данных...")
        
        # Создаем таблицу для отслеживания миграций, если её нет
        await session.execute(text("""
            CREATE TABLE IF NOT EXISTS migrations (
                id SERIAL PRIMARY KEY,
                filename VARCHAR(255) UNIQUE NOT NULL,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """))
        
        # Получаем список уже примененных миграций
        result = await session.execute(text("SELECT filename FROM migrations"))
        applied_migrations = {row[0] for row in result.fetchall()}
        
        # Получаем список файлов миграций
        migrations_dir = Path(__file__).parent
        migration_files = sorted([
            f for f in migrations_dir.glob("*.sql") 
            if f.name != "apply_migrations.py"
        ])
        
        applied_count = 0
        
        for migration_file in migration_files:
            if migration_file.name in applied_migrations:
                print(f"⏭️  Миграция {migration_file.name} уже применена")
                continue
                
            print(f"📝 Применение миграции: {migration_file.name}")
            
            try:
                # Читаем содержимое миграции
                with open(migration_file, 'r', encoding='utf-8') as f:
                    migration_sql = f.read()
                
                # Разбиваем миграцию на отдельные команды
                # Удаляем комментарии и пустые строки
                commands = []
                for line in migration_sql.split('\n'):
                    line = line.strip()
                    if line and not line.startswith('--'):
                        commands.append(line)
                
                # Объединяем строки в команды (разделенные точкой с запятой)
                full_sql = ' '.join(commands)
                sql_commands = [cmd.strip() for cmd in full_sql.split(';') if cmd.strip()]
                
                # Применяем каждую команду отдельно
                for sql_command in sql_commands:
                    if sql_command:
                        await session.execute(text(sql_command))
                
                # Отмечаем миграцию как примененную
                await session.execute(
                    text("INSERT INTO migrations (filename) VALUES (:filename)"),
                    {"filename": migration_file.name}
                )
                
                await session.commit()
                print(f"✅ Миграция {migration_file.name} успешно применена")
                applied_count += 1
                
            except Exception as e:
                await session.rollback()
                print(f"❌ Ошибка при применении миграции {migration_file.name}: {e}")
                return False
        
        if applied_count == 0:
            print("📋 Все миграции уже применены")
        else:
            print(f"�� Применено {applied_count} миграций")
        
        return True

async def main():
    """Главная функция"""
    try:
        success = await apply_migrations()
        if success:
            print("✅ Все миграции успешно применены")
            sys.exit(0)
        else:
            print("❌ Ошибка при применении миграций")
            sys.exit(1)
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main()) 
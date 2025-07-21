#!/usr/bin/env python3
"""
Скрипт для запуска тестов админских обработчиков
"""

import sys
import os
import subprocess
import asyncio
from pathlib import Path

def run_tests():
    """Запустить все тесты"""
    
    # Добавляем текущую директорию в PYTHONPATH
    current_dir = Path(__file__).parent
    sys.path.insert(0, str(current_dir))
    
    try:
        # Проверяем наличие pytest
        result = subprocess.run([sys.executable, "-m", "pytest", "--version"], 
                              capture_output=True, text=True)
        if result.returncode != 0:
            print("❌ pytest не установлен. Установите: pip install pytest pytest-asyncio")
            return False
        
        print("🧪 Запуск тестов админских обработчиков...")
        
        # Запуск тестов
        test_cmd = [
            sys.executable, "-m", "pytest", 
            "tests/test_admin_handlers.py",
            "-v", 
            "--tb=short",
            "--asyncio-mode=auto"
        ]
        
        result = subprocess.run(test_cmd, cwd=current_dir)
        
        if result.returncode == 0:
            print("✅ Все тесты пройдены успешно!")
            return True
        else:
            print("❌ Некоторые тесты не пройдены")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка при запуске тестов: {e}")
        return False

def run_quick_integration_test():
    """Быстрый интеграционный тест"""
    
    print("🔍 Запуск быстрого интеграционного теста...")
    
    try:
        # Проверяем импорты
        from bot.handlers.admin import (
            show_admin_stats, admin_broadcast, give_credits,
            show_detailed_admin_stats, export_admin_stats
        )
        
        print("✅ Импорты обработчиков успешны")
        
        # Проверяем наличие необходимых функций
        handlers = [
            show_admin_stats,
            admin_broadcast, 
            give_credits,
            show_detailed_admin_stats,
            export_admin_stats
        ]
        
        for handler in handlers:
            if not callable(handler):
                print(f"❌ {handler.__name__} не является функцией")
                return False
            print(f"✅ Обработчик {handler.__name__} доступен")
        
        print("✅ Быстрый интеграционный тест пройден!")
        return True
        
    except ImportError as e:
        print(f"❌ Ошибка импорта: {e}")
        return False
    except Exception as e:
        print(f"❌ Ошибка интеграционного теста: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Запуск тестирования админских обработчиков")
    print("=" * 50)
    
    # Сначала быстрый тест
    if not run_quick_integration_test():
        print("❌ Быстрый тест не пройден, прерываем выполнение")
        sys.exit(1)
    
    print("\n" + "=" * 50)
    
    # Затем полные тесты, если доступны
    if os.path.exists("tests/test_admin_handlers.py"):
        success = run_tests()
        sys.exit(0 if success else 1)
    else:
        print("ℹ️ Полные тесты недоступны, только интеграционный тест")
        sys.exit(0)

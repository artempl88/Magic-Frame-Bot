# Makefile для Seedance Bot

.PHONY: help install dev prod build up down logs shell test lint format clean backup restore migrate

# Переменные
PYTHON := python3
PIP := pip3
DOCKER_COMPOSE := docker-compose
PROJECT_NAME := seedance_bot

# Цвета для вывода
GREEN := \033[0;32m
YELLOW := \033[0;33m
RED := \033[0;31m
NC := \033[0m # No Color

help: ## Показать эту справку
	@echo "$(GREEN)Seedance Bot - Доступные команды:$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "$(YELLOW)%-20s$(NC) %s\n", $$1, $$2}'

# Установка и настройка
install: ## Установить зависимости для разработки
	@echo "$(GREEN)Установка зависимостей...$(NC)"
	$(PIP) install -r requirements.txt
	@echo "$(GREEN)Создание .env файла...$(NC)"
	@if [ ! -f .env ]; then cp .env.example .env && echo "$(YELLOW)Не забудьте настроить .env файл!$(NC)"; fi
	@echo "$(GREEN)Готово!$(NC)"

install-dev: install ## Установить зависимости для разработки
	$(PIP) install watchgod pytest-watch

# Docker команды
build: ## Собрать Docker образы
	@echo "$(GREEN)Сборка Docker образов...$(NC)"
	$(DOCKER_COMPOSE) build

up: ## Запустить все сервисы
	@echo "$(GREEN)Запуск сервисов...$(NC)"
	$(DOCKER_COMPOSE) up -d
	@echo "$(GREEN)Сервисы запущены!$(NC)"
	@echo "Bot logs: make logs"

up-dev: ## Запустить в режиме разработки
	@echo "$(GREEN)Запуск в режиме разработки...$(NC)"
	$(DOCKER_COMPOSE) up -d postgres redis
	$(PYTHON) main.py

down: ## Остановить все сервисы
	@echo "$(YELLOW)Остановка сервисов...$(NC)"
	$(DOCKER_COMPOSE) down

restart: down up ## Перезапустить все сервисы

logs: ## Показать логи бота
	$(DOCKER_COMPOSE) logs -f bot

logs-all: ## Показать логи всех сервисов
	$(DOCKER_COMPOSE) logs -f

shell: ## Открыть shell в контейнере бота
	$(DOCKER_COMPOSE) exec bot /bin/bash

shell-db: ## Открыть PostgreSQL shell
	$(DOCKER_COMPOSE) exec postgres psql -U seedance -d seedance_bot

# База данных
migrate: ## Применить миграции БД
	@echo "$(GREEN)Применение миграций...$(NC)"
	$(DOCKER_COMPOSE) exec bot alembic upgrade head

migrate-create: ## Создать новую миграцию
	@echo "$(GREEN)Создание миграции...$(NC)"
	@read -p "Название миграции: " name; \
	$(DOCKER_COMPOSE) exec bot alembic revision -m "$$name"

migrate-rollback: ## Откатить последнюю миграцию
	@echo "$(YELLOW)Откат миграции...$(NC)"
	$(DOCKER_COMPOSE) exec bot alembic downgrade -1

db-backup: ## Создать бэкап БД
	@echo "$(GREEN)Создание бэкапа БД...$(NC)"
	@mkdir -p backups
	$(DOCKER_COMPOSE) exec postgres pg_dump -U seedance seedance_bot | gzip > backups/backup_$(shell date +%Y%m%d_%H%M%S).sql.gz
	@echo "$(GREEN)Бэкап создан в backups/$(NC)"

db-restore: ## Восстановить БД из бэкапа
	@echo "$(YELLOW)Доступные бэкапы:$(NC)"
	@ls -la backups/*.sql.gz
	@read -p "Введите имя файла бэкапа: " backup; \
	gunzip -c backups/$$backup | $(DOCKER_COMPOSE) exec -T postgres psql -U seedance seedance_bot

# Тестирование
test: ## Запустить тесты
	@echo "$(GREEN)Запуск тестов...$(NC)"
	$(PYTHON) -m pytest tests/ -v

test-watch: ## Запустить тесты в режиме watch
	$(PYTHON) -m pytest-watch tests/

test-coverage: ## Запустить тесты с покрытием
	$(PYTHON) -m pytest tests/ --cov=bot --cov=services --cov-report=html
	@echo "$(GREEN)Отчет о покрытии: htmlcov/index.html$(NC)"

# Качество кода
lint: ## Проверить код линтером
	@echo "$(GREEN)Проверка кода...$(NC)"
	$(PYTHON) -m flake8 bot/ services/ models/ core/
	$(PYTHON) -m mypy bot/ services/ models/ core/

format: ## Отформатировать код
	@echo "$(GREEN)Форматирование кода...$(NC)"
	$(PYTHON) -m black bot/ services/ models/ core/ tests/
	$(PYTHON) -m isort bot/ services/ models/ core/ tests/

# Celery
celery-worker: ## Запустить Celery worker
	celery -A bot.tasks worker --loglevel=info

celery-beat: ## Запустить Celery beat
	celery -A bot.tasks beat --loglevel=info

celery-flower: ## Запустить Flower (мониторинг Celery)
	celery -A bot.tasks flower

# Утилиты
clean: ## Очистить временные файлы
	@echo "$(GREEN)Очистка временных файлов...$(NC)"
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name ".coverage" -delete
	rm -rf htmlcov/
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	@echo "$(GREEN)Готово!$(NC)"

stats: ## Показать статистику проекта
	@echo "$(GREEN)Статистика проекта:$(NC)"
	@echo "Файлов Python: $$(find . -name '*.py' -not -path './venv/*' | wc -l)"
	@echo "Строк кода: $$(find . -name '*.py' -not -path './venv/*' -exec wc -l {} + | tail -1 | awk '{print $$1}')"
	@echo "TODO: $$(grep -r 'TODO' --include='*.py' . | wc -l)"
	@echo "FIXME: $$(grep -r 'FIXME' --include='*.py' . | wc -l)"

env-check: ## Проверить настройки окружения
	@echo "$(GREEN)Проверка переменных окружения...$(NC)"
	@if [ -f .env ]; then \
		echo "BOT_TOKEN: $$(grep BOT_TOKEN .env | cut -d'=' -f2 | cut -c1-10)..."; \
		echo "WAVESPEED_API_KEY: $$(grep WAVESPEED_API_KEY .env | cut -d'=' -f2 | cut -c1-10)..."; \
		echo "DB_PASSWORD: ***"; \
		echo "REDIS_PASSWORD: ***"; \
	else \
		echo "$(RED).env файл не найден!$(NC)"; \
	fi

# Развертывание
deploy-dev: ## Развернуть на dev сервере
	@echo "$(GREEN)Развертывание на dev...$(NC)"
	git push dev main
	ssh dev "cd /opt/seedance-bot && docker-compose pull && docker-compose up -d"

deploy-prod: ## Развернуть на production сервере
	@echo "$(RED)Развертывание на production!$(NC)"
	@read -p "Вы уверены? (y/N): " confirm; \
	if [ "$$confirm" = "y" ]; then \
		git push production main; \
		ssh production "cd /opt/seedance-bot && docker-compose pull && docker-compose up -d"; \
	fi

# Мониторинг
monitor: ## Открыть панели мониторинга
	@echo "$(GREEN)Открытие панелей мониторинга...$(NC)"
	@echo "Grafana: http://localhost:3000"
	@echo "Prometheus: http://localhost:9090"
	@echo "Flower: http://localhost:5555"
	@echo "PgAdmin: http://localhost:5050"
	@echo "Redis Commander: http://localhost:8081"

# Быстрые команды
dev: install-dev migrate up-dev ## Быстрый запуск для разработки

prod: build migrate up ## Быстрый запуск production

stop: down ## Алиас для down

restart-bot: ## Перезапустить только бота
	$(DOCKER_COMPOSE) restart bot

update: ## Обновить зависимости
	@echo "$(GREEN)Обновление зависимостей...$(NC)"
	$(PIP) install --upgrade -r requirements.txt
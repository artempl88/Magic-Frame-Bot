# Makefile для клиентского бота (упрощенная версия)

.PHONY: help build up down restart logs shell-bot shell-db backup clean

# Переменные
COMPOSE_FILE = docker-compose.yml
SERVICE_NAME = bot

help: ## Показать справку
	@echo "Доступные команды для клиентского бота:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# === ОСНОВНЫЕ КОМАНДЫ ===

build: ## Собрать Docker образы
	docker-compose -f $(COMPOSE_FILE) --env-file .env.client build

up: ## Запустить бота на VPS
	@echo "🚀 Запуск Magic Frame Bot на VPS..."
	docker-compose -f $(COMPOSE_FILE) --env-file .env.client up -d
	@echo "✅ Бот запущен! Webhook: https://chatbotan.ru/magicframe"

up-backup: ## Запустить с автоматическими бэкапами
	@echo "🚀 Запуск с автоматическими бэкапами..."
	docker-compose -f $(COMPOSE_FILE) --env-file .env.client --profile backup up -d
	@echo "✅ Бот с бэкапами запущен!"

up-full: ## Запустить с Celery Worker
	docker-compose -f $(COMPOSE_FILE) --env-file .env.client --profile full up -d

# === ТЕСТОВЫЕ КОМАНДЫ (МИНИМАЛЬНЫЕ РЕСУРСЫ) ===

test-up: ## 🧪 Запустить в тестовом режиме (экономия ресурсов)
	@echo "🧪 Запуск Magic Frame Bot в ТЕСТОВОМ режиме..."
	@echo "📊 Ресурсы: PostgreSQL=1GB, Redis=128MB, без Celery/Backup"
	docker-compose -f docker-compose.test.yml --env-file .env.client up -d
	@echo "✅ Тестовый бот запущен! Webhook: https://chatbotan.ru/magicframe"
	@echo "💡 Для остановки: make test-down"

test-down: ## ⏹️ Остановить тестовый бот
	@echo "⏹️ Остановка тестового бота..."
	docker-compose -f docker-compose.test.yml down

test-logs: ## 📋 Логи тестового бота
	docker-compose -f docker-compose.test.yml logs -f --tail=100

test-restart: ## 🔄 Перезапустить тестовый бот
	@echo "🔄 Перезапуск тестового бота..."
	docker-compose -f docker-compose.test.yml restart

test-clean: ## 🧹 Очистить тестовые данные
	@echo "🧹 Очистка тестового окружения..."
	docker-compose -f docker-compose.test.yml down -v --remove-orphans
	docker system prune -f

test-status: ## 📊 Статус тестовых сервисов
	@echo "📊 Статус тестовых сервисов:"
	docker-compose -f docker-compose.test.yml ps

up-foreground: ## Запустить в foreground режиме
	docker-compose -f $(COMPOSE_FILE) --env-file .env.client up

down: ## Остановить все сервисы
	docker-compose -f $(COMPOSE_FILE) --env-file .env.client down

restart: ## Перезапустить все сервисы
	docker-compose -f $(COMPOSE_FILE) --env-file .env.client restart

# === ЛОГИ ===

logs: ## Показать все логи
	docker-compose -f $(COMPOSE_FILE) --env-file .env.client logs -f

logs-bot: ## Показать логи бота
	docker-compose -f $(COMPOSE_FILE) --env-file .env.client logs -f $(SERVICE_NAME)

logs-db: ## Показать логи PostgreSQL
	docker-compose -f $(COMPOSE_FILE) --env-file .env.client logs -f postgres

logs-redis: ## Показать логи Redis
	docker-compose -f $(COMPOSE_FILE) --env-file .env.client logs -f redis

# === ПОДКЛЮЧЕНИЕ К СЕРВИСАМ ===

shell-bot: ## Войти в контейнер бота
	docker-compose -f $(COMPOSE_FILE) --env-file .env.client exec $(SERVICE_NAME) /bin/bash

shell-db: ## Войти в PostgreSQL
	docker-compose -f $(COMPOSE_FILE) --env-file .env.client exec postgres psql -U magic_frame -d magic_frame_bot

shell-redis: ## Войти в Redis CLI
	docker-compose -f $(COMPOSE_FILE) --env-file .env.client exec redis redis-cli -a RagnarLothbrok2021!

# === МИГРАЦИИ И ОБСЛУЖИВАНИЕ ===

migrate: ## Применить миграции БД
	docker-compose -f $(COMPOSE_FILE) --env-file .env.client exec $(SERVICE_NAME) python migrations/apply_migrations.py

ps: ## Показать статус контейнеров
	docker-compose -f $(COMPOSE_FILE) --env-file .env.client ps

health: ## Проверить здоровье сервисов
	@echo "Проверка бота..."
	@curl -f https://chatbotan.ru/magicframe/health || echo "❌ Bot недоступен"
	@echo "Проверка PostgreSQL..."
	@docker-compose -f $(COMPOSE_FILE) --env-file .env.client exec postgres pg_isready -U magic_frame -d magic_frame_bot || echo "❌ PostgreSQL недоступен"
	@echo "Проверка Redis..."
	@docker-compose -f $(COMPOSE_FILE) --env-file .env.client exec redis redis-cli -a RagnarLothbrok2021! ping || echo "❌ Redis недоступен"

# === РЕЗЕРВНОЕ КОПИРОВАНИЕ ===

backup: ## Создать резервную копию БД
	@mkdir -p ./backups
	docker-compose -f $(COMPOSE_FILE) --env-file .env.client exec postgres pg_dump -U magic_frame magic_frame_bot | gzip > ./backups/backup_$(shell date +%Y%m%d_%H%M%S).sql.gz
	@echo "Резервная копия создана в ./backups/"

restore: ## Восстановить БД из последней резервной копии
	@echo "Доступные резервные копии:"
	@ls -la ./backups/*.sql.gz 2>/dev/null || echo "Резервные копии не найдены"
	@echo "Использование: make restore BACKUP_FILE=./backups/backup_YYYYMMDD_HHMMSS.sql.gz"

restore-file: ## Восстановить из конкретного файла (укажите BACKUP_FILE=path)
	@if [ -z "$(BACKUP_FILE)" ]; then echo "Укажите BACKUP_FILE=path"; exit 1; fi
	docker-compose -f $(COMPOSE_FILE) --env-file .env.client exec postgres dropdb -U magic_frame magic_frame_bot || true
	docker-compose -f $(COMPOSE_FILE) --env-file .env.client exec postgres createdb -U magic_frame magic_frame_bot
	gunzip -c $(BACKUP_FILE) | docker-compose -f $(COMPOSE_FILE) --env-file .env.client exec -T postgres psql -U magic_frame magic_frame_bot

backup-auto: ## Создать автоматический бэкап прямо сейчас
	@echo "Создание внепланового автоматического бэкапа..."
	docker-compose -f $(COMPOSE_FILE) --env-file .env.client exec postgres sh -c 'pg_dump -U magic_frame magic_frame_bot | gzip > /backups/manual_backup_$$(date +%Y%m%d_%H%M%S).sql.gz'
	@echo "✅ Автоматический бэкап создан"

backup-cleanup: ## Очистить старые бэкапы (старше 30 дней)
	@echo "Очистка старых бэкапов..."
	find ./backups -name "*.sql.gz" -mtime +30 -delete 2>/dev/null || true
	@echo "✅ Старые бэкапы очищены"

backup-list: ## Показать список всех бэкапов
	@echo "📁 Список бэкапов:"
	@ls -la ./backups/*.sql.gz 2>/dev/null | awk '{print $$9, $$5/1024/1024 "MB", $$6, $$7, $$8}' || echo "Бэкапы не найдены"

backup-cleanup: ## Удалить бэкапы старше 30 дней
	@echo "🧹 Очистка старых бэкапов..."
	@find ./backups -name "*.sql.gz" -mtime +30 -exec rm {} \; 2>/dev/null || true
	@find ./backups -name "*.meta" -mtime +30 -exec rm {} \; 2>/dev/null || true
	@echo "✅ Очистка завершена"

backup-size: ## Показать общий размер всех бэкапов
	@du -sh ./backups/ 2>/dev/null || echo "Папка с бэкапами не найдена"

# === ОЧИСТКА ===

clean: ## Остановить и удалить volumes
	docker-compose -f $(COMPOSE_FILE_LOCAL) down -v

clean-all: ## Полная очистка (контейнеры + образы + volumes)
	docker-compose -f $(COMPOSE_FILE_LOCAL) down -v --rmi all

# === VPS КОМАНДЫ ===

vps-up: ## Запустить на VPS (минимальная конфигурация)
	docker-compose -f $(COMPOSE_FILE_VPS) up -d

vps-up-full: ## Запустить на VPS с Celery
	docker-compose -f $(COMPOSE_FILE_VPS) --profile full up -d

vps-up-backup: ## Запустить на VPS с автоматическими бэкапами
	docker-compose -f $(COMPOSE_FILE_VPS) --profile backup up -d

up-backup: ## Запустить локально с автоматическими бэкапами
	docker-compose -f $(COMPOSE_FILE_LOCAL) --profile backup up -d

vps-down: ## Остановить на VPS
	docker-compose -f $(COMPOSE_FILE_VPS) down

vps-logs: ## Логи на VPS
	docker-compose -f $(COMPOSE_FILE_VPS) logs -f

vps-status: ## Статус на VPS
	docker-compose -f $(COMPOSE_FILE_VPS) ps

vps-build: ## Собрать образы для VPS
	docker-compose -f $(COMPOSE_FILE_VPS) build

# === БЫСТРЫЕ КОМАНДЫ ===

quick-start: build up ## Быстрый старт (сборка + запуск)

quick-restart: down up ## Быстрый перезапуск

start-minimal: ## Запустить только бот + БД + Redis
	docker-compose -f $(COMPOSE_FILE) --env-file .env.client up -d bot postgres redis

# === ОТЛАДКА ===

debug: ## Запустить бота в debug режиме
	docker-compose -f $(COMPOSE_FILE) --env-file .env.client run --rm $(SERVICE_NAME) python main.py

debug-shell: ## Запустить интерактивную оболочку Python
	docker-compose -f $(COMPOSE_FILE) --env-file .env.client run --rm $(SERVICE_NAME) python -i

# === ИНФОРМАЦИЯ ===

info: ## Показать информацию о сервисах VPS
	@echo "=== Информация о VPS боте ==="
	@echo "Bot webhook: https://chatbotan.ru/magicframe"
@echo "YooKassa webhook: https://chatbotan.ru/yookassa/webhook"
@echo "Health check: https://chatbotan.ru/magicframe/health"
	@echo ""
	@echo "Подключение к БД (внутри контейнера):"
	@echo "make shell-db"
	@echo ""
	@echo "Подключение к Redis (внутри контейнера):"
	@echo "make shell-redis"
	@echo ""
	@echo "Файлы:"
	@echo "- Конфигурация: .env.client"
	@echo "- Логи: ./logs/"
	@echo "- Статика: ./static/"
	@echo "- Резервные копии: ./backups/"
	@echo ""
	@echo "=== Автоматические бэкапы ==="
	@echo "- Ежедневно в 3:00 утра (UTC)"
	@echo "- Еженедельно в воскресенье в 2:00 утра (только VPS)"
	@echo "- Автоочистка старше 30 дней в 4:00 утра"
	@echo "- Ручное управление через админку бота"
	@echo ""
	@echo "Команды бэкапов:"
	@echo "make backup-auto     # Создать сейчас"
	@echo "make backup-list     # Список бэкапов"  
	@echo "make backup-cleanup  # Очистить старые"
	@echo "make up-backup       # Запуск с бэкапами"

# === МОНИТОРИНГ ===

stats: ## Показать статистику использования ресурсов
	docker stats magic_frame_bot magic_frame_postgres magic_frame_redis --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}"

top: ## Показать процессы в контейнерах
	@echo "=== Процессы в боте ==="
	docker-compose -f $(COMPOSE_FILE) --env-file .env.client exec $(SERVICE_NAME) ps aux
	@echo ""
	@echo "=== Процессы в PostgreSQL ==="
	docker-compose -f $(COMPOSE_FILE) --env-file .env.client exec postgres ps aux 
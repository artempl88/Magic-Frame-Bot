#!/bin/bash

# Скрипт резервного копирования для Seedance Bot
# Автор: Seedance Team

set -e

# Переменные
BACKUP_DIR="/backups"
DATE=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="seedance_backup_${DATE}.sql"
RETENTION_DAYS=${BACKUP_RETENTION_DAYS:-7}

# Цвета для логов
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')] INFO:${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[$(date '+%Y-%m-%d %H:%M:%S')] WARN:${NC} $1"
}

log_error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1"
}

# Создание директории для бэкапов
mkdir -p "$BACKUP_DIR"

# Проверка переменных окружения
if [ -z "$PGUSER" ] || [ -z "$PGPASSWORD" ] || [ -z "$PGDATABASE" ]; then
    log_error "Не заданы необходимые переменные окружения для PostgreSQL"
    exit 1
fi

log_info "Начинаем создание резервной копии базы данных $PGDATABASE"

# Создание резервной копии
if pg_dump -h "$PGHOST" -U "$PGUSER" -d "$PGDATABASE" > "$BACKUP_DIR/$BACKUP_FILE"; then
    log_info "Резервная копия создана: $BACKUP_FILE"
    
    # Сжатие файла
    if gzip "$BACKUP_DIR/$BACKUP_FILE"; then
        log_info "Резервная копия сжата: ${BACKUP_FILE}.gz"
        BACKUP_FILE="${BACKUP_FILE}.gz"
    else
        log_warn "Не удалось сжать резервную копию"
    fi
else
    log_error "Ошибка при создании резервной копии"
    exit 1
fi

# Удаление старых бэкапов
log_info "Удаление резервных копий старше $RETENTION_DAYS дней"
find "$BACKUP_DIR" -name "seedance_backup_*.sql.gz" -mtime +$RETENTION_DAYS -delete

# Проверка размера резервной копии
BACKUP_SIZE=$(du -h "$BACKUP_DIR/$BACKUP_FILE" | cut -f1)
log_info "Размер резервной копии: $BACKUP_SIZE"

# Список текущих резервных копий
BACKUP_COUNT=$(find "$BACKUP_DIR" -name "seedance_backup_*.sql.gz" | wc -l)
log_info "Всего резервных копий: $BACKUP_COUNT"

log_info "Резервное копирование завершено успешно" 
#!/bin/bash

# ===================================================================
# Скрипт автоматического деплоя Telegram-бота на Ubuntu 24.04
# Для Python 3.12 с использованием библиотеки aiogram 3.19.0
# ===================================================================

# Цвета для вывода сообщений
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Функция для вывода сообщений с временной меткой
log() {
    echo -e "[$(date +"%Y-%m-%d %H:%M:%S")] ${1}"
}

# Функция для проверки результата выполнения команды
check_result() {
    if [ $? -ne 0 ]; then
        log "${RED}ОШИБКА: $1${NC}"
        exit 1
    else
        log "${GREEN}УСПЕХ: $2${NC}"
    fi
}

# Получаем имя текущего пользователя для создания пути установки
CURRENT_USER=$(whoami)
if [ "$CURRENT_USER" != "root" ]; then
    log "${RED}Скрипт должен быть запущен с правами root${NC}"
    exit 1
fi

# Запрашиваем информацию о репозитории
log "${BLUE}Введите URL репозитория GitHub (например, https://github.com/username/repo.git):${NC}"
read -r REPO_URL

# Проверяем, что URL не пустой
if [ -z "$REPO_URL" ]; then
    log "${RED}URL репозитория не может быть пустым${NC}"
    exit 1
fi

# Извлекаем имя репозитория из URL
REPO_NAME=$(basename "$REPO_URL" .git)

# Настройка переменных окружения для бота
log "${BLUE}Настройка переменных окружения для бота...${NC}"
log "${YELLOW}Введите токен бота Telegram:${NC}"
read -r BOT_TOKEN

log "${YELLOW}Введите API ключ OpenAI:${NC}"
read -r OPENAI_API_KEY

# Проверка введенных данных
if [ -z "$BOT_TOKEN" ] || [ -z "$OPENAI_API_KEY" ]; then
    log "${RED}Токен бота Telegram и API ключ OpenAI не могут быть пустыми${NC}"
    exit 1
fi

# Переменные для установки
INSTALL_DIR="/opt/$REPO_NAME"
VENV_DIR="$INSTALL_DIR/venv"
SERVICE_NAME="telegram-$REPO_NAME"
LOG_DIR="/var/log/$SERVICE_NAME"
ENV_FILE="$INSTALL_DIR/.env"

# Создаем пользователя для запуска сервиса
log "${BLUE}Создание пользователя для запуска сервиса...${NC}"
if ! id -u "$SERVICE_NAME" &>/dev/null; then
    useradd -r -s /bin/false "$SERVICE_NAME"
    check_result "Не удалось создать пользователя $SERVICE_NAME" "Пользователь $SERVICE_NAME создан"
else
    log "${YELLOW}Пользователь $SERVICE_NAME уже существует${NC}"
fi

# Обновление системы и установка необходимых зависимостей
log "${BLUE}Обновление системы и установка необходимых зависимостей...${NC}"
apt update
check_result "Не удалось обновить список пакетов" "Список пакетов обновлен"

apt install -y git python3.12 python3.12-venv python3.12-dev python3-pip sqlite3
check_result "Не удалось установить необходимые пакеты" "Необходимые пакеты установлены"

# Клонирование репозитория
log "${BLUE}Клонирование репозитория...${NC}"
if [ -d "$INSTALL_DIR" ]; then
    log "${YELLOW}Каталог $INSTALL_DIR уже существует. Удаляем...${NC}"
    rm -rf "$INSTALL_DIR"
fi

git clone "$REPO_URL" "$INSTALL_DIR"
check_result "Не удалось клонировать репозиторий" "Репозиторий успешно клонирован"

# Создание виртуального окружения Python
log "${BLUE}Создание виртуального окружения Python...${NC}"
python3.12 -m venv "$VENV_DIR"
check_result "Не удалось создать виртуальное окружение" "Виртуальное окружение успешно создано"

# Установка зависимостей из requirements.txt
log "${BLUE}Установка зависимостей из requirements.txt...${NC}"
source "$VENV_DIR/bin/activate"
pip install --upgrade pip
check_result "Не удалось обновить pip" "pip успешно обновлен"

cd "$INSTALL_DIR"
# Исправляем известную проблему с библиотекой python-dotenv
sed -i 's/dotenv/python-dotenv/g' requirements.txt
pip install -r requirements.txt
check_result "Не удалось установить зависимости" "Зависимости успешно установлены"

# Создание файла с переменными окружения
log "${BLUE}Создание файла с переменными окружения...${NC}"
cat > "$ENV_FILE" << EOF
BOT_TOKEN=$BOT_TOKEN
OPENAI_API_KEY=$OPENAI_API_KEY
EOF
check_result "Не удалось создать файл .env" "Файл .env успешно создан"

# Поиск главного файла для запуска
log "${BLUE}Поиск главного файла для запуска...${NC}"
MAIN_FILE=""
FILES_TO_CHECK=("app.py" "bot.py" "main.py")

for file in "${FILES_TO_CHECK[@]}"; do
    if [ -f "$INSTALL_DIR/$file" ]; then
        MAIN_FILE="$file"
        break
    fi
done

if [ -z "$MAIN_FILE" ]; then
    # Если стандартные имена не найдены, ищем файл с 'if __name__ == "__main__"'
    MAIN_FILE=$(grep -l "if __name__ == \"__main__\"" "$INSTALL_DIR"/*.py | head -1)
    if [ -z "$MAIN_FILE" ]; then
        log "${RED}Не удалось найти главный файл для запуска${NC}"
        exit 1
    else
        MAIN_FILE=$(basename "$MAIN_FILE")
    fi
fi

log "${GREEN}Найден главный файл для запуска: $MAIN_FILE${NC}"

# Создание директории для логов
log "${BLUE}Создание директории для логов...${NC}"
mkdir -p "$LOG_DIR"
check_result "Не удалось создать директорию для логов" "Директория для логов успешно создана"

# Установка прав доступа
log "${BLUE}Установка прав доступа...${NC}"
chown -R "$SERVICE_NAME:$SERVICE_NAME" "$INSTALL_DIR"
chown -R "$SERVICE_NAME:$SERVICE_NAME" "$LOG_DIR"
chmod 600 "$ENV_FILE"
check_result "Не удалось установить права доступа" "Права доступа успешно установлены"

# Создание файла службы systemd
log "${BLUE}Создание файла службы systemd...${NC}"
cat > "/etc/systemd/system/$SERVICE_NAME.service" << EOF
[Unit]
Description=Telegram Bot Service for $REPO_NAME
After=network.target

[Service]
User=$SERVICE_NAME
Group=$SERVICE_NAME
WorkingDirectory=$INSTALL_DIR
Environment="PATH=$VENV_DIR/bin"
ExecStart=$VENV_DIR/bin/python3 $INSTALL_DIR/$MAIN_FILE
Restart=always
RestartSec=10
StandardOutput=append:$LOG_DIR/bot.log
StandardError=append:$LOG_DIR/error.log

[Install]
WantedBy=multi-user.target
EOF
check_result "Не удалось создать файл службы systemd" "Файл службы systemd успешно создан"

# Перезагрузка systemd и запуск службы
log "${BLUE}Перезагрузка systemd и запуск службы...${NC}"
systemctl daemon-reload
check_result "Не удалось перезагрузить systemd" "systemd успешно перезагружен"

systemctl enable "$SERVICE_NAME"
check_result "Не удалось включить автозапуск службы" "Автозапуск службы успешно включен"

systemctl start "$SERVICE_NAME"
check_result "Не удалось запустить службу" "Служба успешно запущена"

# Вывод информации о статусе сервиса
log "${BLUE}Информация о статусе сервиса:${NC}"
systemctl status "$SERVICE_NAME" --no-pager

# Вывод завершающего сообщения
log "${GREEN}====================================================================================${NC}"
log "${GREEN}Деплой Telegram-бота успешно завершен!${NC}"
log "${GREEN}====================================================================================${NC}"
log "${YELLOW}Информация о боте:${NC}"
log "Директория установки: ${BLUE}$INSTALL_DIR${NC}"
log "Журналы доступны в: ${BLUE}$LOG_DIR${NC}"
log "Имя службы: ${BLUE}$SERVICE_NAME${NC}"
log "${YELLOW}Управление ботом:${NC}"
log "Запустить бота: ${BLUE}systemctl start $SERVICE_NAME${NC}"
log "Остановить бота: ${BLUE}systemctl stop $SERVICE_NAME${NC}"
log "Перезапустить бота: ${BLUE}systemctl restart $SERVICE_NAME${NC}"
log "Просмотреть статус: ${BLUE}systemctl status $SERVICE_NAME${NC}"
log "Просмотреть логи: ${BLUE}journalctl -u $SERVICE_NAME -f${NC}"
log "${GREEN}====================================================================================${NC}"

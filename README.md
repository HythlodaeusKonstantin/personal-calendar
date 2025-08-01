# Personal Calendar

Персональное календарное приложение с поддержкой привычек, задач и питания.

## Особенности
- 🔐 **HTTPS поддержка** - безопасное соединение
- 🐳 **Docker готовность** - простое развёртывание
- 📊 **Полнофункциональное приложение** - привычки, задачи, питание
- 🔐 **Аутентификация** - регистрация и вход пользователей
- 📱 **Мобильная адаптивность** - оптимизировано для телефонов и планшетов

## Зависимости
- Python 3.8+
- PostgreSQL
- Docker (опционально)

## Быстрый старт с Docker

### 1. Клонирование репозитория
```bash
git clone <your-repo-url>
cd personal-calendar
```

### 2. Генерация SSL сертификатов
**Windows:**
```bash
setup_ssl.bat
```

**Linux/macOS:**
```bash
chmod +x setup_ssl.sh
./setup_ssl.sh
```

### 3. Запуск приложения
```bash
docker compose up --build
```

### 4. Открытие в браузере
```
https://localhost:8443
```

⚠️ **Важно:** При первом открытии браузер покажет предупреждение о самоподписанном сертификате. Это нормально для разработки. Нажмите "Дополнительно" → "Перейти на localhost".

## Локальная разработка

### Установка зависимостей
```bash
pip install -r requirements.txt
```

### Генерация SSL сертификатов
```bash
python generate_ssl.py
```

### Запуск приложения
```bash
python run_ssl.py
```

## Переменные окружения

- `POSTGRES_DB` (по умолчанию: calendar_db)
- `POSTGRES_USER` (по умолчанию: calendar_user)
- `POSTGRES_PASSWORD` (по умолчанию: admin123)
- `POSTGRES_HOST` (по умолчанию: localhost)
- `POSTGRES_PORT` (по умолчанию: 5432)

## Технологии
- **Бэкенд:** FastAPI
- **Фронтенд:** HTMX + Jinja2 + Tailwind CSS
- **БД:** PostgreSQL (чистый SQL через psycopg2)
- **Безопасность:** HTTPS с самоподписанными сертификатами
- **UI/UX:** Адаптивный дизайн с мобильным меню и оптимизированными таблицами

## Безопасность

⚠️ **Важно:** Самоподписанные сертификаты используются только для разработки. Для продакшена используйте Let's Encrypt или другие доверенные центры сертификации.

Сертификаты (`*.pem` файлы) автоматически исключены из Git репозитория для безопасности.
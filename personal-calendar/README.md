# Personal Calendar (минимальный шаблон)

## Зависимости
- Python 3.8+
- PostgreSQL

## Установка

```bash
pip install -r requirements.txt
```

## Переменные окружения для подключения к БД

- POSTGRES_DB (по умолчанию: calendar_db)
- POSTGRES_USER (по умолчанию: calendar_user)
- POSTGRES_PASSWORD (по умолчанию: calendar_pass)
- POSTGRES_HOST (по умолчанию: localhost)
- POSTGRES_PORT (по умолчанию: 5432)

## Запуск приложения

```bash
uvicorn main:app --reload
```

## Описание
- Бэкенд: FastAPI
- Фронтенд: HTMX + Jinja2
- БД: PostgreSQL (чистый SQL через psycopg2) 

## Запуск POSTGRES

docker run --name personal-calendar-postgres -e POSTGRES_DB=calendar_db -e POSTGRES_USER=calendar_user -e POSTGRES_PASSWORD=admin123 -p 5432:5432 -d postgres:15
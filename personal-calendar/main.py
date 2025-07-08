from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape
import psycopg2
import os
from psycopg2 import sql

app = FastAPI()

# Настройка Jinja2
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=select_autoescape(["html", "xml"])
)

# Настройки подключения к БД
DB_CONFIG = {
    'dbname': os.getenv('POSTGRES_DB', 'calendar_db'),
    'user': os.getenv('POSTGRES_USER', 'calendar_user'),
    'password': os.getenv('POSTGRES_PASSWORD', 'admin123'),
    'host': os.getenv('POSTGRES_HOST', 'localhost'),
    'port': os.getenv('POSTGRES_PORT', '5432'),
}

SCHEMA = {
    "habits": [
        ("id", "SERIAL PRIMARY KEY"),
        ("title", "VARCHAR(255) NOT NULL"),
        ("event_date", "DATE"),
        ("description", "TEXT")
    ]
}

def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)

def init_db_schema():
    conn = get_db_connection()
    cur = conn.cursor()

    # Получаем все таблицы в public
    cur.execute("""
        SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';
    """)
    existing_tables = {row[0] for row in cur.fetchall()}
    schema_tables = set(SCHEMA.keys())

    # Удаляем лишние таблицы
    for table in existing_tables - schema_tables:
        cur.execute(sql.SQL("DROP TABLE IF EXISTS {} CASCADE;").format(sql.Identifier(table)))

    for table, columns in SCHEMA.items():
        # Проверяем, существует ли таблица
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = %s
            );
        """, (table,))
        exists = cur.fetchone()[0]
        if not exists:
            # Создаём таблицу
            columns_sql = ", ".join(f"{name} {type}" for name, type in columns)
            cur.execute(sql.SQL("CREATE TABLE {} ({});").format(
                sql.Identifier(table),
                sql.SQL(columns_sql)
            ))
        else:
            # Проверяем наличие всех нужных столбцов
            cur.execute("""
                SELECT column_name FROM information_schema.columns WHERE table_name = %s;
            """, (table,))
            existing_columns = {row[0] for row in cur.fetchall()}
            schema_columns = {name for name, _ in columns}
            # Удаляем лишние столбцы
            for col in existing_columns - schema_columns:
                cur.execute(sql.SQL("ALTER TABLE {} DROP COLUMN IF EXISTS {} CASCADE;").format(
                    sql.Identifier(table),
                    sql.Identifier(col)
                ))
            # Добавляем недостающие столбцы
            for name, type in columns:
                if name not in existing_columns:
                    cur.execute(sql.SQL("ALTER TABLE {} ADD COLUMN {} {};").format(
                        sql.Identifier(table),
                        sql.Identifier(name),
                        sql.SQL(type)
                    ))
    conn.commit()
    cur.close()
    conn.close()

@app.on_event("startup")
def on_startup():
    init_db_schema()

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    template = env.get_template("index.html")
    html_content = template.render(request=request)
    return HTMLResponse(content=html_content)

@app.get("/events", response_class=HTMLResponse)
async def get_events(request: Request):
    # Пример запроса к БД (пока без реальных данных)
    # conn = get_db_connection()
    # cur = conn.cursor()
    # cur.execute("SELECT id, title FROM events LIMIT 10;")
    # events = cur.fetchall()
    # cur.close()
    # conn.close()
    events = [
        {"id": 1, "title": "Встреча с друзьями"},
        {"id": 2, "title": "День рождения"},
    ]
    html = "<ul>" + "".join(f'<li>{e["title"]}</li>' for e in events) + "</ul>"
    return HTMLResponse(content=html) 
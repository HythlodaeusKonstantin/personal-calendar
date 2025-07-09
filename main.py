from fastapi import FastAPI, Request, APIRouter, Form, Query, HTTPException, Response, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape
import psycopg2
import os
from psycopg2 import sql
import uuid
from datetime import date, timedelta, datetime
import hashlib
import secrets

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
    # Пользователи
    "users": [
        ("id", "UUID PRIMARY KEY"),
        ("username", "VARCHAR(255) UNIQUE NOT NULL"),
        ("password_hash", "VARCHAR(255) NOT NULL"),
        ("created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
    ],
    # Сессии
    "sessions": [
        ("id", "UUID PRIMARY KEY"),
        ("user_id", "UUID REFERENCES users(id)"),
        ("session_token", "VARCHAR(64) UNIQUE NOT NULL"),
        ("created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
    ],
    # Категории привычек
    "habit_category": [
        ("id", "UUID PRIMARY KEY"),
        ("name", "VARCHAR(255) NOT NULL")
    ],
    # Привычки
    "habit": [
        ("id", "UUID PRIMARY KEY"),
        ("name", "VARCHAR(255) NOT NULL"),
        ("description", "TEXT"),
        ("category_id", "UUID REFERENCES habit_category(id)"),
        ("priority", "habit_priority_enum NOT NULL")
    ],
    # Записи по привычкам
    "habit_entry": [
        ("id", "UUID PRIMARY KEY"),
        ("habit_id", "UUID REFERENCES habit(id)"),
        ("date", "DATE NOT NULL"),
        ("completed", "BOOLEAN NOT NULL")
    ],
    # Категории задач
    "task_category": [
        ("id", "UUID PRIMARY KEY"),
        ("name", "VARCHAR(255) NOT NULL")
    ],
    # Задачи
    "task": [
        ("id", "UUID PRIMARY KEY"),
        ("name", "VARCHAR(255) NOT NULL"),
        ("description", "TEXT"),
        ("category_id", "UUID REFERENCES task_category(id)"),
        ("date", "DATE NOT NULL"),
        ("repeat", "task_repeat_enum NOT NULL")
    ],
    # Записи по задачам
    "task_entry": [
        ("id", "UUID PRIMARY KEY"),
        ("task_id", "UUID REFERENCES task(id)"),
        ("date", "DATE NOT NULL"),
        ("completed", "BOOLEAN NOT NULL")
    ],
    # Продукты
    "product": [
        ("id", "UUID PRIMARY KEY"),
        ("name", "VARCHAR(255) NOT NULL"),
        ("calories_per_100g", "FLOAT NOT NULL"),
        ("micro_description", "TEXT")
    ],
    # Блюда
    "dish": [
        ("id", "UUID PRIMARY KEY"),
        ("name", "VARCHAR(255) NOT NULL"),
        ("description", "TEXT")
    ],
    # Ингредиенты блюда (DishIngredient)
    "dish_ingredient": [
        ("id", "UUID PRIMARY KEY"),
        ("dish_id", "UUID REFERENCES dish(id) ON DELETE CASCADE"),
        ("product_id", "UUID REFERENCES product(id) ON DELETE CASCADE"),
        ("grams", "FLOAT NOT NULL")
    ],
    # Лог приёмов пищи
    "meal_log": [
        ("id", "UUID PRIMARY KEY"),
        ("date", "DATE NOT NULL"),
        ("dish_id", "UUID REFERENCES dish(id) ON DELETE CASCADE"),
        ("consumed_grams", "FLOAT NOT NULL")
    ],
    # Целевые калории
    "calories_goal": [
        ("id", "UUID PRIMARY KEY"),
        ("target_calories", "INTEGER NOT NULL")
    ],
    # Личные данные
    "personal_data": [
        ("id", "UUID PRIMARY KEY"),
        ("date", "DATE NOT NULL"),
        ("weight", "FLOAT NOT NULL")
    ],
}

def create_enum(cur, name, values):
    cur.execute(f"""DO $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = '{name}') THEN
            CREATE TYPE {name} AS ENUM ({', '.join(f"'{v}'" for v in values)});
        END IF;
    END$$;
    """)

def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)

def hash_password(password: str) -> str:
    """Хеширует пароль с солью"""
    salt = secrets.token_hex(16)
    hash_obj = hashlib.sha256()
    hash_obj.update((password + salt).encode())
    return salt + hash_obj.hexdigest()

def verify_password(password: str, password_hash: str) -> bool:
    """Проверяет пароль"""
    if len(password_hash) < 32:  # Минимальная длина для salt + hash
        return False
    salt = password_hash[:32]
    stored_hash = password_hash[32:]
    hash_obj = hashlib.sha256()
    hash_obj.update((password + salt).encode())
    return stored_hash == hash_obj.hexdigest()

def check_user_exists() -> bool:
    """Проверяет, есть ли пользователи в БД"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users;")
    count = cur.fetchone()[0]
    cur.close()
    conn.close()
    return count > 0

def get_user_by_username(username: str):
    """Получает пользователя по логину"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, username, password_hash FROM users WHERE username = %s;", (username,))
    user = cur.fetchone()
    cur.close()
    conn.close()
    return user

def create_user(username: str, password: str):
    """Создает нового пользователя"""
    conn = get_db_connection()
    cur = conn.cursor()
    password_hash = hash_password(password)
    cur.execute(
        "INSERT INTO users (id, username, password_hash) VALUES (%s, %s, %s);",
        (str(uuid.uuid4()), username, password_hash)
    )
    conn.commit()
    cur.close()
    conn.close()

def init_db_schema():
    conn = get_db_connection()
    cur = conn.cursor()

    # Создаём ENUM-ы, если их нет
    create_enum(cur, 'habit_priority_enum', ['HIGH', 'MEDIUM', 'LOW'])
    create_enum(cur, 'task_repeat_enum', ['NONE', 'DAILY', 'WEEKLY'])

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
async def index(request: Request, session_token: str = Cookie(None)):
    # Если есть активная сессия — редиректим на /app
    user = get_user_by_session_token(session_token)
    if user:
        return RedirectResponse("/app")
    # Проверяем, есть ли пользователи в БД
    if not check_user_exists():
        # Если пользователей нет, показываем форму регистрации
        template = env.get_template("auth/register.html")
        html_content = template.render()
        return HTMLResponse(content=html_content)
    else:
        # Если пользователи есть, показываем форму входа
        template = env.get_template("auth/login.html")
        html_content = template.render()
        return HTMLResponse(content=html_content)

@app.post("/register", response_class=HTMLResponse)
async def register(username: str = Form(...), password: str = Form(...)):
    if check_user_exists():
        return HTMLResponse("<div class='error' style='color:red;text-align:center;margin-bottom:16px;'>Регистрация уже завершена</div>", status_code=400)
    if len(username) < 3:
        return HTMLResponse("<div class='error' style='color:red;text-align:center;margin-bottom:16px;'>Логин должен содержать минимум 3 символа</div>", status_code=400)
    if len(password) < 6:
        return HTMLResponse("<div class='error' style='color:red;text-align:center;margin-bottom:16px;'>Пароль должен содержать минимум 6 символов</div>", status_code=400)
    try:
        create_user(username, password)
        # После успешной регистрации показываем форму входа
        template = env.get_template("auth/login.html")
        return HTMLResponse(content=template.render())
    except Exception as e:
        return HTMLResponse(f"<div class='error' style='color:red;text-align:center;margin-bottom:16px;'>Ошибка при создании пользователя: {str(e)}</div>", status_code=500)

@app.post("/login", response_class=HTMLResponse)
async def login(username: str = Form(...), password: str = Form(...)):
    user = get_user_by_username(username)
    if not user or not verify_password(password, user[2]):
        return HTMLResponse(
            "<div class='error' style='color:red;text-align:center;margin-bottom:16px;'>Неверный логин или пароль</div>",
            status_code=401
        )
    # Успешный вход — создаём сессию и устанавливаем cookie
    token = create_session(user[0])
    response = HTMLResponse(headers={"HX-Redirect": "/app"})
    response.set_cookie("session_token", token, httponly=True)
    return response

@app.get("/app", response_class=HTMLResponse)
async def app_main(request: Request, session_token: str = Cookie(None)):
    user = get_user_by_session_token(session_token)
    if not user:
        return RedirectResponse("/")
    # Главная страница приложения (после входа)
    template = env.get_template("index.html")
    html_content = template.render(request=request)
    return HTMLResponse(content=html_content)

@app.get("/events", response_class=HTMLResponse)
async def get_events(request: Request):
    events = [
        {"id": 1, "title": "Встреча с друзьями"},
        {"id": 2, "title": "День рождения"},
    ]
    html = "<ul>" + "".join(f'<li>{e["title"]}</li>' for e in events) + "</ul>"
    return HTMLResponse(content=html)

# HTML-шаблоны для habit_category
HABIT_CATEGORY_LIST_TEMPLATE = '''
<div id="habit-category-list">
<h2 class="text-xl lg:text-2xl font-bold mb-4">Категории привычек</h2>
<form hx-post="/section/habits/category/add" hx-target="#habit-category-list" hx-swap="outerHTML" class="mb-4 mobile-form">
    <input class="border p-2 rounded w-full mb-2" type="text" name="name" placeholder="Название категории" required>
    <button class="bg-blue-500 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded mobile-btn" type="submit">Добавить</button>
</form>
<div class="responsive-table">
<table class="table-auto w-full border-collapse border border-slate-400">
    <thead>
        <tr>
            <th class="border border-slate-300 p-2">Название</th>
            <th class="border border-slate-300 p-2 text-center whitespace-nowrap w-1">Действия</th>
        </tr>
    </thead>
    <tbody>
    {rows}
    </tbody>
</table>
</div>
</div>
'''

HABIT_CATEGORY_ROW_TEMPLATE = '''
<tr id="edit-habit-category-row-{id}">
    <td class="border border-slate-300 p-2">{name}</td>
    <td class="border border-slate-300 p-2 text-center whitespace-nowrap w-1">
        <button class="bg-yellow-500 hover:bg-yellow-700 text-white font-bold py-1 px-2 rounded mobile-btn" hx-get="/section/habits/category/edit/{id}" hx-target="#edit-habit-category-row-{id}" hx-swap="outerHTML">✏️</button>
        <button class="bg-red-500 hover:bg-red-700 text-white font-bold py-1 px-2 rounded mobile-btn" hx-delete="/section/habits/category/delete/{id}" hx-target="#habit-category-list" hx-swap="outerHTML">🗑️</button>
    </td>
</tr>
'''

HABIT_CATEGORY_EDIT_TEMPLATE = '''
<tr id="edit-habit-category-row-{id}">
    <td colspan="2" class="p-2">
        <form hx-post="/section/habits/category/edit/{id}" hx-target="#habit-category-list" hx-swap="outerHTML">
            <input class="border p-2 rounded w-full mb-2" type="text" name="name" value="{name}" required>
            <button class="bg-green-500 hover:bg-green-700 text-white font-bold py-2 px-4 rounded mobile-btn" type="submit">Сохранить</button>
            <button class="bg-gray-500 hover:bg-gray-700 text-white font-bold py-2 px-4 rounded mobile-btn" type="button" 
                hx-get="/section/habits/category/row/{id}" 
                hx-target="#edit-habit-category-row-{id}" 
                hx-swap="outerHTML">
                Отмена
            </button>
        </form>
    </td>
</tr>
'''

def render_habit_category_list():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name FROM habit_category ORDER BY name;")
    rows = "".join(
        HABIT_CATEGORY_ROW_TEMPLATE.format(id=row[0], name=row[1]) for row in cur.fetchall()
    )
    cur.close()
    conn.close()
    return HABIT_CATEGORY_LIST_TEMPLATE.format(rows=rows)

HABITS_SECTION_TEMPLATE = '''
<div>
    <div class="flex border-b mobile-tabs tabs overflow-x-auto">
        <button class="tab py-2 px-4 text-gray-500 border-b-2 border-transparent hover:border-blue-500 hover:text-blue-500 {active_marks} mobile-btn" id="tab-habit-marks" hx-get="/section/habits/marks" hx-target="#habits-subsection" hx-swap="innerHTML" onclick="setActiveSubTab(this)">Отметки</button>
        <button class="tab py-2 px-4 text-gray-500 border-b-2 border-transparent hover:border-blue-500 hover:text-blue-500 {active_categories} mobile-btn" id="tab-habit-categories" hx-get="/section/habits/categories" hx-target="#habits-subsection" hx-swap="innerHTML" onclick="setActiveSubTab(this)">Категории</button>
        <button class="tab py-2 px-4 text-gray-500 border-b-2 border-transparent hover:border-blue-500 hover:text-blue-500 {active_habits} mobile-btn" id="tab-habit-habits" hx-get="/section/habits/habits" hx-target="#habits-subsection" hx-swap="innerHTML" onclick="setActiveSubTab(this)">Карточки привычек</button>
    </div>
    <div id="habits-subsection" class="p-2 lg:p-4">{content}</div>
</div>
<script>
function setActiveSubTab(tab) {{
    document.querySelectorAll('.tabs .tab').forEach(btn => btn.classList.remove('active'));
    tab.classList.add('active');
}}
</script>
'''

@app.get("/section/habits", response_class=HTMLResponse)
async def section_habits():
    # При нажатии на корневую вкладку всегда показываем актуальный раздел "Отметки"
    content = (await habits_marks()).body.decode()
    html = HABITS_SECTION_TEMPLATE.format(
        active_marks="active", active_categories="", active_habits="",
        content=content
    )
    return HTMLResponse(html)

@app.get("/section/habits/marks", response_class=HTMLResponse)
async def habits_marks():
    today = date.today()
    conn = get_db_connection()
    cur = conn.cursor()
    # Получаем все привычки
    cur.execute("SELECT id, name FROM habit ORDER BY name;")
    habits = cur.fetchall()
    # Проверяем, есть ли записи habit_entry на сегодня для каждой привычки
    for habit_id, _ in habits:
        cur.execute("SELECT 1 FROM habit_entry WHERE habit_id = %s AND date = %s;", (habit_id, today))
        if not cur.fetchone():
            cur.execute(
                "INSERT INTO habit_entry (id, habit_id, date, completed) VALUES (%s, %s, %s, %s);",
                (str(uuid.uuid4()), habit_id, today, False)
            )
    conn.commit()
    # Получаем все записи habit_entry на сегодня с названиями привычек
    cur.execute('''
        SELECT e.id, h.name, e.completed
        FROM habit_entry e JOIN habit h ON e.habit_id = h.id
        WHERE e.date = %s
        ORDER BY h.name;
    ''', (today,))
    rows = ""
    for entry_id, habit_name, completed in cur.fetchall():
        checked = "checked" if completed else ""
        row_class = ' class="bg-green-100"' if completed else ''
        rows += f'''<tr{row_class}><td class="border border-slate-300 p-2">{habit_name}</td><td class="border border-slate-300 p-2 cursor-pointer" hx-post="/section/habits/marks/toggle/{entry_id}" hx-target="#habits-marks-table-area" hx-swap="outerHTML"><input type="checkbox" {checked} class="pointer-events-none"></td></tr>'''
    cur.close()
    conn.close()
    html = f'''
    <div id="habits-marks-table-area">
        <h2 class="text-xl lg:text-2xl font-bold mb-4">Отметки за {today.strftime('%d.%m.%Y')}</h2>
        <div class="responsive-table">
        <table id="habits-marks-table" class="table-auto w-full border-collapse border border-slate-400">
            <thead>
                <tr>
                    <th class="border border-slate-300 p-2">Привычка</th>
                    <th class="border border-slate-300 p-2">Выполнено</th>
                </tr>
            </thead>
            <tbody>
            {rows}
            </tbody>
        </table>
        </div>
    </div>
    '''
    return HTMLResponse(html)

@app.post("/section/habits/marks/toggle/{entry_id}", response_class=HTMLResponse)
async def toggle_habit_entry(entry_id: str):
    conn = get_db_connection()
    cur = conn.cursor()
    # Получаем текущее значение
    cur.execute("SELECT completed FROM habit_entry WHERE id = %s;", (entry_id,))
    row = cur.fetchone()
    if not row:
        cur.close()
        conn.close()
        return HTMLResponse("")
    new_value = not row[0]
    cur.execute("UPDATE habit_entry SET completed = %s WHERE id = %s;", (new_value, entry_id))
    conn.commit()
    cur.close()
    conn.close()
    # Возвращаем всю таблицу
    return await habits_marks()

@app.get("/section/habits/categories", response_class=HTMLResponse)
async def habits_categories():
    html = render_habit_category_list()
    return HTMLResponse(html)

# --- Карточки привычек (habit) ---
HABIT_LIST_TEMPLATE = '''
<div id="habit-list">
<h2 class="text-xl lg:text-2xl font-bold mb-4">Карточки привычек</h2>
<form hx-post="/section/habits/habits/add" hx-target="#habit-list" hx-swap="outerHTML" class="mb-4 mobile-form">
    <input class="border p-2 rounded w-full mb-2" type="text" name="name" placeholder="Название привычки" required>
    <input class="border p-2 rounded w-full mb-2" type="text" name="description" placeholder="Описание">
    <select class="border p-2 rounded w-full mb-2" name="category_id" required>
        <option value="">Категория...</option>
        {category_options}
    </select>
    <select class="border p-2 rounded w-full mb-2" name="priority" required>
        <option value="HIGH">Высокий</option>
        <option value="MEDIUM">Средний</option>
        <option value="LOW">Низкий</option>
    </select>
    <button class="bg-blue-500 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded mobile-btn" type="submit">Добавить</button>
</form>
<div class="responsive-table">
<table class="table-auto w-full border-collapse border border-slate-400">
    <thead>
        <tr>
            <th class="border border-slate-300 p-2">Название</th>
            <th class="border border-slate-300 p-2">Описание</th>
            <th class="border border-slate-300 p-2">Категория</th>
            <th class="border border-slate-300 p-2">Приоритет</th>
            <th class="border border-slate-300 p-2 text-center whitespace-nowrap w-1">Действия</th>
        </tr>
    </thead>
    <tbody>
    {rows}
    </tbody>
</table>
</div>
</div>
'''

HABIT_ROW_TEMPLATE = '''
<tr id="edit-habit-row-{id}">
    <td class="border border-slate-300 p-2">{name}</td>
    <td class="border border-slate-300 p-2">{description}</td>
    <td class="border border-slate-300 p-2">{category}</td>
    <td class="border border-slate-300 p-2">{priority}</td>
    <td class="border border-slate-300 p-2 text-center whitespace-nowrap w-1">
        <button class="bg-yellow-500 hover:bg-yellow-700 text-white font-bold py-1 px-2 rounded mobile-btn" hx-get="/section/habits/habits/edit/{id}" hx-target="#edit-habit-row-{id}" hx-swap="outerHTML">✏️</button>
        <button class="bg-red-500 hover:bg-red-700 text-white font-bold py-1 px-2 rounded mobile-btn" hx-delete="/section/habits/habits/delete/{id}" hx-target="#habit-list" hx-swap="outerHTML">🗑️</button>
    </td>
</tr>
'''

HABIT_EDIT_TEMPLATE = '''
<tr id="edit-habit-row-{id}">
    <td colspan="5" class="p-2">
        <form hx-post="/section/habits/habits/edit/{id}" hx-target="#habit-list" hx-swap="outerHTML">
            <input class="border p-2 rounded w-full mb-2" type="text" name="name" value="{name}" required>
            <input class="border p-2 rounded w-full mb-2" type="text" name="description" value="{description}">
            <select class="border p-2 rounded w-full mb-2" name="category_id" required>
                {category_options}
            </select>
            <select class="border p-2 rounded w-full mb-2" name="priority" required>
                <option value="HIGH" {high}>Высокий</option>
                <option value="MEDIUM" {medium}>Средний</option>
                <option value="LOW" {low}>Низкий</option>
            </select>
            <button class="bg-green-500 hover:bg-green-700 text-white font-bold py-2 px-4 rounded mobile-btn" type="submit">Сохранить</button>
            <button class="bg-gray-500 hover:bg-gray-700 text-white font-bold py-2 px-4 rounded mobile-btn" type="button" 
                hx-get="/section/habits/habits/row/{id}" 
                hx-target="#edit-habit-row-{id}" 
                hx-swap="outerHTML">
                Отмена
            </button>
        </form>
    </td>
</tr>
'''

def get_habit_category_options(selected=None):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name FROM habit_category ORDER BY name;")
    options = ""
    for row in cur.fetchall():
        sel = " selected" if selected and row[0] == selected else ""
        options += f'<option value="{row[0]}"{sel}>{row[1]}</option>'
    cur.close()
    conn.close()
    return options

def render_habit_list():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        SELECT h.id, h.name, h.description, h.category_id, h.priority, c.name
        FROM habit h LEFT JOIN habit_category c ON h.category_id = c.id
        ORDER BY h.name;
    ''')
    rows = ""
    for row in cur.fetchall():
        rows += HABIT_ROW_TEMPLATE.format(
            id=row[0], name=row[1], description=row[2] or "", category=row[5] or "", priority=row[4]
        )
    cur.close()
    conn.close()
    return HABIT_LIST_TEMPLATE.format(rows=rows, category_options=get_habit_category_options())

@app.get("/section/habits/habits", response_class=HTMLResponse)
async def habits_habits():
    return HTMLResponse(render_habit_list())

@app.post("/section/habits/habits/add", response_class=HTMLResponse)
async def add_habit(
    name: str = Form(...),
    description: str = Form(None),
    category_id: str = Form(...),
    priority: str = Form(...)
):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO habit (id, name, description, category_id, priority) VALUES (%s, %s, %s, %s, %s);",
        (str(uuid.uuid4()), name, description, category_id, priority)
    )
    conn.commit()
    cur.close()
    conn.close()
    return render_habit_list()

@app.get("/section/habits/habits/edit/{habit_id}", response_class=HTMLResponse)
async def edit_habit_form(habit_id: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name, description, category_id, priority FROM habit WHERE id = %s;", (habit_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        return HTMLResponse("<tr><td colspan='5'>Привычка не найдена</td></tr>")
    category_options = get_habit_category_options(selected=row[3])
    return HABIT_EDIT_TEMPLATE.format(
        id=row[0], name=row[1], description=row[2] or "", category_options=category_options,
        high="selected" if row[4] == "HIGH" else "", medium="selected" if row[4] == "MEDIUM" else "", low="selected" if row[4] == "LOW" else ""
    )

@app.post("/section/habits/habits/edit/{habit_id}", response_class=HTMLResponse)
async def edit_habit(habit_id: str, name: str = Form(...), description: str = Form(None), category_id: str = Form(...), priority: str = Form(...)):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE habit SET name = %s, description = %s, category_id = %s, priority = %s WHERE id = %s;",
        (name, description, category_id, priority, habit_id)
    )
    conn.commit()
    cur.close()
    conn.close()
    return render_habit_list()

@app.delete("/section/habits/habits/delete/{habit_id}", response_class=HTMLResponse)
async def delete_habit(habit_id: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM habit WHERE id = %s;", (habit_id,))
    conn.commit()
    cur.close()
    conn.close()
    return render_habit_list()

@app.post("/section/habits/category/add", response_class=HTMLResponse)
async def add_habit_category(name: str = Form(...)):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO habit_category (id, name) VALUES (%s, %s);", (str(uuid.uuid4()), name))
    conn.commit()
    cur.close()
    conn.close()
    return render_habit_category_list()

@app.get("/section/habits/category/edit/{cat_id}", response_class=HTMLResponse)
async def edit_habit_category_form(cat_id: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name FROM habit_category WHERE id = %s;", (cat_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        return HTMLResponse("<tr><td colspan='2'>Категория не найдена</td></tr>")
    return HABIT_CATEGORY_EDIT_TEMPLATE.format(id=row[0], name=row[1])

@app.post("/section/habits/category/edit/{cat_id}", response_class=HTMLResponse)
async def edit_habit_category(cat_id: str, name: str = Form(...)):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE habit_category SET name = %s WHERE id = %s;", (name, cat_id))
    conn.commit()
    cur.close()
    conn.close()
    return render_habit_category_list()

@app.delete("/section/habits/category/delete/{cat_id}", response_class=HTMLResponse)
async def delete_habit_category(cat_id: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM habit_category WHERE id = %s;", (cat_id,))
    conn.commit()
    cur.close()
    conn.close()
    return render_habit_category_list()

@app.get("/section/habits/category/row/{cat_id}", response_class=HTMLResponse)
async def habit_category_row(cat_id: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name FROM habit_category WHERE id = %s", (cat_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        return HTMLResponse("<tr><td colspan='2'>Категория не найдена</td></tr>")
    return HABIT_CATEGORY_ROW_TEMPLATE.format(id=row[0], name=row[1])

# --- Раздел Задачи ---
TASKS_SECTION_TEMPLATE = '''
<div>
    <div class="flex border-b mobile-tabs tabs overflow-x-auto">
        <button class="tab py-2 px-4 text-gray-500 border-b-2 border-transparent hover:border-blue-500 hover:text-blue-500 {active_marks} mobile-btn" id="tab-task-marks" hx-get="/section/tasks/marks" hx-target="#tasks-subsection" hx-swap="innerHTML" onclick="setActiveSubTab(this)">Отметки</button>
        <button class="tab py-2 px-4 text-gray-500 border-b-2 border-transparent hover:border-blue-500 hover:text-blue-500 {active_categories} mobile-btn" id="tab-task-categories" hx-get="/section/tasks/categories" hx-target="#tasks-subsection" hx-swap="innerHTML" onclick="setActiveSubTab(this)">Категории</button>
        <button class="tab py-2 px-4 text-gray-500 border-b-2 border-transparent hover:border-blue-500 hover:text-blue-500 {active_tasks} mobile-btn" id="tab-task-tasks" hx-get="/section/tasks/tasks" hx-target="#tasks-subsection" hx-swap="innerHTML" onclick="setActiveSubTab(this)">Карточки задач</button>
    </div>
    <div id="tasks-subsection" class="p-2 lg:p-4">{content}</div>
</div>
<script>
function setActiveSubTab(tab) {{
    document.querySelectorAll('.tabs .tab').forEach(btn => btn.classList.remove('active'));
    tab.classList.add('active');
}}
</script>
'''

@app.get("/section/tasks", response_class=HTMLResponse)
async def section_tasks():
    content = (await tasks_marks()).body.decode()
    html = TASKS_SECTION_TEMPLATE.format(
        active_marks="active", active_categories="", active_tasks="",
        content=content
    )
    return HTMLResponse(html)

# --- Категории задач ---
TASK_CATEGORY_LIST_TEMPLATE = '''
<div id="task-category-list">
<h2 class="text-xl lg:text-2xl font-bold mb-4">Категории задач</h2>
<form hx-post="/section/tasks/categories/add" hx-target="#task-category-list" hx-swap="outerHTML" class="mb-4 mobile-form">
    <input class="border p-2 rounded w-full mb-2" type="text" name="name" placeholder="Название категории" required>
    <button class="bg-blue-500 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded mobile-btn" type="submit">Добавить</button>
</form>
<div class="responsive-table">
<table class="table-auto w-full border-collapse border border-slate-400">
    <thead>
        <tr>
            <th class="border border-slate-300 p-2">Название</th>
            <th class="border border-slate-300 p-2 text-center whitespace-nowrap w-1">Действия</th>
        </tr>
    </thead>
    <tbody>
    {rows}
    </tbody>
</table>
</div>
</div>
'''

TASK_CATEGORY_ROW_TEMPLATE = '''
<tr id="edit-task-category-row-{id}">
    <td class="border border-slate-300 p-2">{name}</td>
    <td class="border border-slate-300 p-2 text-center whitespace-nowrap w-1">
        <button class="bg-yellow-500 hover:bg-yellow-700 text-white font-bold py-1 px-2 rounded mobile-btn" hx-get="/section/tasks/categories/edit/{id}" hx-target="#edit-task-category-row-{id}" hx-swap="outerHTML">✏️</button>
        <button class="bg-red-500 hover:bg-red-700 text-white font-bold py-1 px-2 rounded mobile-btn" hx-delete="/section/tasks/categories/delete/{id}" hx-target="#task-category-list" hx-swap="outerHTML">🗑️</button>
    </td>
</tr>
'''

TASK_CATEGORY_EDIT_TEMPLATE = '''
<tr id="edit-task-category-row-{id}">
    <td colspan="2" class="p-2">
        <form hx-post="/section/tasks/categories/edit/{id}" hx-target="#task-category-list" hx-swap="outerHTML">
            <input class="border p-2 rounded w-full mb-2" type="text" name="name" value="{name}" required>
            <button class="bg-green-500 hover:bg-green-700 text-white font-bold py-2 px-4 rounded mobile-btn" type="submit">Сохранить</button>
            <button class="bg-gray-500 hover:bg-gray-700 text-white font-bold py-2 px-4 rounded mobile-btn" type="button" 
                hx-get="/section/tasks/categories/row/{id}" 
                hx-target="#edit-task-category-row-{id}" 
                hx-swap="outerHTML">
                Отмена
            </button>
        </form>
    </td>
</tr>
'''

def render_task_category_list():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name FROM task_category ORDER BY name;")
    rows = "".join(
        TASK_CATEGORY_ROW_TEMPLATE.format(id=row[0], name=row[1]) for row in cur.fetchall()
    )
    cur.close()
    conn.close()
    return TASK_CATEGORY_LIST_TEMPLATE.format(rows=rows)

@app.get("/section/tasks/categories", response_class=HTMLResponse)
async def tasks_categories():
    return HTMLResponse(render_task_category_list())

@app.post("/section/tasks/categories/add", response_class=HTMLResponse)
async def add_task_category(name: str = Form(...)):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO task_category (id, name) VALUES (%s, %s);", (str(uuid.uuid4()), name))
    conn.commit()
    cur.close()
    conn.close()
    return render_task_category_list()

@app.get("/section/tasks/categories/edit/{cat_id}", response_class=HTMLResponse)
async def edit_task_category_form(cat_id: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name FROM task_category WHERE id = %s;", (cat_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        return HTMLResponse("<tr><td colspan='2'>Категория не найдена</td></tr>")
    return TASK_CATEGORY_EDIT_TEMPLATE.format(id=row[0], name=row[1])

@app.post("/section/tasks/categories/edit/{cat_id}", response_class=HTMLResponse)
async def edit_task_category(cat_id: str, name: str = Form(...)):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE task_category SET name = %s WHERE id = %s;", (name, cat_id))
    conn.commit()
    cur.close()
    conn.close()
    return render_task_category_list()

@app.delete("/section/tasks/categories/delete/{cat_id}", response_class=HTMLResponse)
async def delete_task_category(cat_id: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM task_category WHERE id = %s;", (cat_id,))
    conn.commit()
    cur.close()
    conn.close()
    return render_task_category_list()

@app.get("/section/tasks/categories/row/{cat_id}", response_class=HTMLResponse)
async def task_category_row(cat_id: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name FROM task_category WHERE id = %s", (cat_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        return HTMLResponse("<tr><td colspan='2'>Категория не найдена</td></tr>")
    return TASK_CATEGORY_ROW_TEMPLATE.format(id=row[0], name=row[1])

# --- Карточки задач ---
TASK_LIST_TEMPLATE = '''
<div id="task-list">
<h2 class="text-xl lg:text-2xl font-bold mb-4">Карточки задач</h2>
<form hx-post="/section/tasks/tasks/add" hx-target="#task-list" hx-swap="outerHTML" class="mb-4 mobile-form">
    <input class="border p-2 rounded w-full mb-2" type="text" name="name" placeholder="Название задачи" required>
    <input class="border p-2 rounded w-full mb-2" type="text" name="description" placeholder="Описание">
    <select class="border p-2 rounded w-full mb-2" name="category_id" required>
        <option value="">Категория...</option>
        {category_options}
    </select>
    <input class="border p-2 rounded w-full mb-2" type="date" name="date" required>
    <select class="border p-2 rounded w-full mb-2" name="repeat" required>
        <option value="NONE">Нет</option>
        <option value="DAILY">Ежедневно</option>
        <option value="WEEKLY">Еженедельно</option>
    </select>
    <button class="bg-blue-500 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded mobile-btn" type="submit">Добавить</button>
</form>
<div class="responsive-table">
<table class="table-auto w-full border-collapse border border-slate-400">
    <thead>
        <tr>
            <th class="border border-slate-300 p-2">Название</th>
            <th class="border border-slate-300 p-2">Описание</th>
            <th class="border border-slate-300 p-2">Категория</th>
            <th class="border border-slate-300 p-2">Дата</th>
            <th class="border border-slate-300 p-2">Повтор</th>
            <th class="border border-slate-300 p-2 text-center whitespace-nowrap w-1">Действия</th>
        </tr>
    </thead>
    <tbody>
    {rows}
    </tbody>
</table>
</div>
</div>
'''

TASK_ROW_TEMPLATE = '''
<tr id="edit-task-row-{id}">
    <td class="border border-slate-300 p-2">{name}</td>
    <td class="border border-slate-300 p-2">{description}</td>
    <td class="border border-slate-300 p-2">{category}</td>
    <td class="border border-slate-300 p-2">{date}</td>
    <td class="border border-slate-300 p-2">{repeat}</td>
    <td class="border border-slate-300 p-2 text-center whitespace-nowrap w-1">
        <button class="bg-yellow-500 hover:bg-yellow-700 text-white font-bold py-1 px-2 rounded mobile-btn" hx-get="/section/tasks/tasks/edit/{id}" hx-target="#edit-task-row-{id}" hx-swap="outerHTML">✏️</button>
        <button class="bg-red-500 hover:bg-red-700 text-white font-bold py-1 px-2 rounded mobile-btn" hx-delete="/section/tasks/tasks/delete/{id}" hx-target="#task-list" hx-swap="outerHTML">🗑️</button>
    </td>
</tr>
'''

TASK_EDIT_TEMPLATE = '''
<tr id="edit-task-row-{id}">
    <td colspan="6" class="p-2">
        <form hx-post="/section/tasks/tasks/edit/{id}" hx-target="#task-list" hx-swap="outerHTML">
            <input class="border p-2 rounded w-full mb-2" type="text" name="name" value="{name}" required>
            <input class="border p-2 rounded w-full mb-2" type="text" name="description" value="{description}">
            <select class="border p-2 rounded w-full mb-2" name="category_id" required>
                {category_options}
            </select>
            <input class="border p-2 rounded w-full mb-2" type="date" name="date" value="{date}" required>
            <select class="border p-2 rounded w-full mb-2" name="repeat" required>
                <option value="NONE" {none}>Нет</option>
                <option value="DAILY" {daily}>Ежедневно</option>
                <option value="WEEKLY" {weekly}>Еженедельно</option>
            </select>
            <button class="bg-green-500 hover:bg-green-700 text-white font-bold py-2 px-4 rounded mobile-btn" type="submit">Сохранить</button>
            <button class="bg-gray-500 hover:bg-gray-700 text-white font-bold py-2 px-4 rounded mobile-btn" type="button" 
                hx-get="/section/tasks/tasks/row/{id}" 
                hx-target="#edit-task-row-{id}" 
                hx-swap="outerHTML">
                Отмена
            </button>
        </form>
    </td>
</tr>
'''

def get_task_category_options(selected=None):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name FROM task_category ORDER BY name;")
    options = ""
    for row in cur.fetchall():
        sel = " selected" if selected and row[0] == selected else ""
        options += f'<option value="{row[0]}"{sel}>{row[1]}</option>'
    cur.close()
    conn.close()
    return options

def render_task_list():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        SELECT t.id, t.name, t.description, t.category_id, t.date, t.repeat, c.name
        FROM task t LEFT JOIN task_category c ON t.category_id = c.id
        ORDER BY t.name;
    ''')
    rows = ""
    for row in cur.fetchall():
        rows += TASK_ROW_TEMPLATE.format(
            id=row[0], name=row[1], description=row[2] or "", category=row[6] or "", date=row[4], repeat=row[5]
        )
    cur.close()
    conn.close()
    return TASK_LIST_TEMPLATE.format(rows=rows, category_options=get_task_category_options())

@app.get("/section/tasks/tasks", response_class=HTMLResponse)
async def tasks_tasks():
    return HTMLResponse(render_task_list())

@app.post("/section/tasks/tasks/add", response_class=HTMLResponse)
async def add_task(
    name: str = Form(...),
    description: str = Form(None),
    category_id: str = Form(...),
    date: str = Form(...),
    repeat: str = Form(...)
):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO task (id, name, description, category_id, date, repeat) VALUES (%s, %s, %s, %s, %s, %s);",
        (str(uuid.uuid4()), name, description, category_id, date, repeat)
    )
    conn.commit()
    cur.close()
    conn.close()
    return render_task_list()

@app.get("/section/tasks/tasks/edit/{task_id}", response_class=HTMLResponse)
async def edit_task_form(task_id: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name, description, category_id, date, repeat FROM task WHERE id = %s;", (task_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        return HTMLResponse("<tr><td colspan='6'>Задача не найдена</td></tr>")
    category_options = get_task_category_options(selected=row[3])
    return TASK_EDIT_TEMPLATE.format(
        id=row[0], name=row[1], description=row[2] or "", category_options=category_options, date=row[4],
        none="selected" if row[5] == "NONE" else "", daily="selected" if row[5] == "DAILY" else "", weekly="selected" if row[5] == "WEEKLY" else ""
    )

@app.post("/section/tasks/tasks/edit/{task_id}", response_class=HTMLResponse)
async def edit_task(task_id: str, name: str = Form(...), description: str = Form(None), category_id: str = Form(...), date: str = Form(...), repeat: str = Form(...)):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE task SET name = %s, description = %s, category_id = %s, date = %s, repeat = %s WHERE id = %s;",
        (name, description, category_id, date, repeat, task_id)
    )
    conn.commit()
    cur.close()
    conn.close()
    return render_task_list()

@app.delete("/section/tasks/tasks/delete/{task_id}", response_class=HTMLResponse)
async def delete_task(task_id: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM task WHERE id = %s;", (task_id,))
    conn.commit()
    cur.close()
    conn.close()
    return render_task_list()

@app.get("/section/tasks/marks", response_class=HTMLResponse)
async def tasks_marks(show_completed: str = "0"):
    today = date.today()
    conn = get_db_connection()
    cur = conn.cursor()
    # 1. Для всех задач task ищем записи в task_entry, если нет — создаём
    cur.execute("SELECT id FROM task;")
    all_task_ids = [row[0] for row in cur.fetchall()]
    for task_id in all_task_ids:
        cur.execute("SELECT 1 FROM task_entry WHERE task_id = %s AND date = %s;", (task_id, today))
        if not cur.fetchone():
            cur.execute(
                "INSERT INTO task_entry (id, task_id, date, completed) VALUES (%s, %s, %s, %s);",
                (str(uuid.uuid4()), task_id, today, False)
            )
    conn.commit()
    # 2. Для выполненных задач с repeat = DAILY или WEEKLY создаём новые записи, если нужно
    # DAILY
    cur.execute('''
        SELECT t.id, MAX(e.date) as last_date
        FROM task t
        JOIN task_entry e ON t.id = e.task_id
        WHERE t.repeat = 'DAILY' AND e.completed = TRUE
        GROUP BY t.id
    ''')
    for task_id, last_date in cur.fetchall():
        if last_date is not None and (today - last_date).days >= 1:
            cur.execute("SELECT 1 FROM task_entry WHERE task_id = %s AND date = %s;", (task_id, today))
            if not cur.fetchone():
                cur.execute(
                    "INSERT INTO task_entry (id, task_id, date, completed) VALUES (%s, %s, %s, %s);",
                    (str(uuid.uuid4()), task_id, today, False)
                )
    # WEEKLY
    cur.execute('''
        SELECT t.id, MAX(e.date) as last_date
        FROM task t
        JOIN task_entry e ON t.id = e.task_id
        WHERE t.repeat = 'WEEKLY' AND e.completed = TRUE
        GROUP BY t.id
    ''')
    for task_id, last_date in cur.fetchall():
        if last_date is not None and (today - last_date).days >= 7:
            cur.execute("SELECT 1 FROM task_entry WHERE task_id = %s AND date = %s;", (task_id, today))
            if not cur.fetchone():
                cur.execute(
                    "INSERT INTO task_entry (id, task_id, date, completed) VALUES (%s, %s, %s, %s);",
                    (str(uuid.uuid4()), task_id, today, False)
                )
    conn.commit()
    # 3. Получаем задачи
    if show_completed == "1":
        cur.execute('''
            SELECT e.id, t.name, t.description, t.date, t.repeat, e.date, e.completed
            FROM task_entry e
            JOIN task t ON e.task_id = t.id
            ORDER BY e.date ASC
        ''')
    else:
        cur.execute('''
            SELECT e.id, t.name, t.description, t.date, t.repeat, e.date, e.completed
            FROM task_entry e
            JOIN task t ON e.task_id = t.id
            WHERE e.completed = FALSE
            ORDER BY e.date ASC
        ''')
    rows = ""
    for entry_id, name, description, task_date, repeat, entry_date, completed in cur.fetchall():
        checked = "checked" if completed else ""
        is_overdue = not completed and entry_date < today
        row_class = ' class="bg-green-100"' if completed else (' class="bg-red-100"' if is_overdue else '')
        delete_btn = f'<button class="bg-red-500 hover:bg-red-700 text-white font-bold py-1 px-2 rounded mobile-btn" hx-delete="/section/tasks/marks/delete/{entry_id}" hx-target="closest tr" hx-swap="outerHTML">🗑️</button>' if show_completed == "1" else ""
        last_col = f'<td class="border border-slate-300 p-2">{delete_btn}</td>' if show_completed == "1" else ""
        rows += f'''<tr{row_class}><td class="border border-slate-300 p-2">{name}</td><td class="border border-slate-300 p-2">{description or ''}</td><td class="border border-slate-300 p-2">{task_date}</td><td class="border border-slate-300 p-2">{repeat}</td><td class="border border-slate-300 p-2">{entry_date}</td><td class="border border-slate-300 p-2 cursor-pointer" hx-post="/section/tasks/marks/toggle/{entry_id}" hx-target="#tasks-marks-table-area" hx-swap="outerHTML"><input type="checkbox" {checked} class="pointer-events-none"></td>{last_col}</tr>'''
    cur.close()
    conn.close()
    checked_flag = "checked" if show_completed == "1" else ""
    table_width = "100%"
    th_delete = '<th></th>' if show_completed == "1" else ''
    html = f'''
    <div id="tasks-marks-table-area">
        <h2 class="text-xl lg:text-2xl font-bold mb-4">Задачи</h2>
        <label class="inline-flex items-center mb-4">
            <input type="checkbox" id="show-completed-tasks" {checked_flag} hx-get="/section/tasks/marks" hx-target="#tasks-subsection" hx-swap="innerHTML" hx-vals='{{"show_completed": "{1 if show_completed == "0" else 0}"}}' class="form-checkbox h-5 w-5 text-blue-600">
            <span class="ml-2 text-gray-700">Показывать выполненные задачи</span>
        </label>
        <div class="responsive-table">
        <table id="tasks-marks-table" class="table-auto w-full border-collapse border border-slate-400">
            <thead>
                <tr>
                    <th class="border border-slate-300 p-2">Название</th>
                    <th class="border border-slate-300 p-2">Описание</th>
                    <th class="border border-slate-300 p-2">Дата задачи</th>
                    <th class="border border-slate-300 p-2">Повтор</th>
                    <th class="border border-slate-300 p-2">Дата отметки</th>
                    <th class="border border-slate-300 p-2">Выполнено</th>
                    {th_delete}
                </tr>
            </thead>
            <tbody>
            {rows}
            </tbody>
        </table>
        </div>
    </div>
    '''
    return HTMLResponse(html)

@app.post("/section/tasks/marks/toggle/{entry_id}", response_class=HTMLResponse)
async def toggle_task_entry(entry_id: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT completed FROM task_entry WHERE id = %s;", (entry_id,))
    row = cur.fetchone()
    if not row:
        cur.close()
        conn.close()
        return HTMLResponse("")
    new_value = not row[0]
    cur.execute("UPDATE task_entry SET completed = %s WHERE id = %s;", (new_value, entry_id))
    conn.commit()
    cur.close()
    conn.close()
    # Возвращаем всю таблицу
    return await tasks_marks()

@app.delete("/section/tasks/marks/delete/{entry_id}", response_class=HTMLResponse)
async def delete_task_entry(entry_id: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM task_entry WHERE id = %s;", (entry_id,))
    conn.commit()
    cur.close()
    conn.close()
    return HTMLResponse("")

# --- Раздел Питание ---
NUTRITION_SECTION_TEMPLATE = '''
<div>
    <div class="flex border-b mobile-tabs tabs overflow-x-auto">
        <button class="tab py-2 px-4 text-gray-500 border-b-2 border-transparent hover:border-blue-500 hover:text-blue-500 {active_meal_log} mobile-btn" id="tab-nutrition-meal-log" hx-get="/section/nutrition/meal-log" hx-target="#nutrition-subsection" hx-swap="innerHTML" onclick="setActiveSubTab(this)">Приемы пищи</button>
        <button class="tab py-2 px-4 text-gray-500 border-b-2 border-transparent hover:border-blue-500 hover:text-blue-500 {active_products} mobile-btn" id="tab-nutrition-products" hx-get="/section/nutrition/products" hx-target="#nutrition-subsection" hx-swap="innerHTML" onclick="setActiveSubTab(this)">Продукты</button>
        <button class="tab py-2 px-4 text-gray-500 border-b-2 border-transparent hover:border-blue-500 hover:text-blue-500 {active_dishes} mobile-btn" id="tab-nutrition-dishes" hx-get="/section/nutrition/dishes" hx-target="#nutrition-subsection" hx-swap="innerHTML" onclick="setActiveSubTab(this)">Блюда</button>
        <button class="tab py-2 px-4 text-gray-500 border-b-2 border-transparent hover:border-blue-500 hover:text-blue-500 {active_weight} mobile-btn" id="tab-nutrition-weight" hx-get="/section/nutrition/weight" hx-target="#nutrition-subsection" hx-swap="innerHTML" onclick="setActiveSubTab(this)">Вес</button>
    </div>
    <div id="nutrition-subsection" class="p-2 lg:p-4">{content}</div>
</div>
<script>
function setActiveSubTab(tab) {{
    document.querySelectorAll('.tabs .tab').forEach(btn => btn.classList.remove('active'));
    tab.classList.add('active');
}}
</script>
'''

MEAL_LOG_LIST_TEMPLATE = '''
<div id="meal-log-list">
<h2 class="text-xl lg:text-2xl font-bold mb-4">Приемы пищи</h2>
<form hx-post="/section/nutrition/meal-log/add" hx-target="#meal-log-list" hx-swap="outerHTML" class="mb-4 mobile-form">
    <input class="border p-2 rounded" type="date" name="date" value="{date}" required>
    <select class="border p-2 rounded" name="dish_id" required>
        <option value="">Блюдо...</option>
        {dish_options}
    </select>
    <input class="border p-2 rounded" type="number" step="0.01" name="consumed_grams" placeholder="Граммы" required>
    <button class="bg-blue-500 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded mobile-btn" type="submit">Добавить</button>
</form>
<div class="responsive-table">
<table class="table-auto w-full border-collapse border border-slate-400">
    <thead>
        <tr>
            <th class="border border-slate-300 p-2">Блюдо</th>
            <th class="border border-slate-300 p-2">Граммы</th>
            <th class="border border-slate-300 p-2 text-center whitespace-nowrap w-1">Действия</th>
        </tr>
    </thead>
    <tbody>
    {rows}
    </tbody>
</table>
</div>
</div>
'''

MEAL_LOG_ROW_TEMPLATE = '''
<tr id="edit-meal-log-row-{id}">
    <td class="border border-slate-300 p-2">{dish_name}</td>
    <td class="border border-slate-300 p-2">{consumed_grams}</td>
    <td class="border border-slate-300 p-2 text-center whitespace-nowrap w-1">
        <button class="bg-yellow-500 hover:bg-yellow-700 text-white font-bold py-1 px-2 rounded mobile-btn" hx-get="/section/nutrition/meal-log/edit/{id}?date={date}" hx-target="#edit-meal-log-row-{id}" hx-swap="outerHTML">✏️</button>
        <button class="bg-red-500 hover:bg-red-700 text-white font-bold py-1 px-2 rounded mobile-btn" hx-delete="/section/nutrition/meal-log/delete/{id}?date={date}" hx-target="#meal-log-list" hx-swap="outerHTML">🗑️</button>
    </td>
</tr>
'''

MEAL_LOG_EDIT_TEMPLATE = '''
<tr id="edit-meal-log-row-{id}">
    <td colspan="3" class="p-2">
        <form hx-post="/section/nutrition/meal-log/edit/{id}?date={date}" hx-target="#meal-log-list" hx-swap="outerHTML">
            <select class="border p-2 rounded w-full mb-2" name="dish_id" required>
                {dish_options}
            </select>
            <input class="border p-2 rounded w-full mb-2" type="number" step="0.01" name="consumed_grams" value="{consumed_grams}" required>
            <input type="hidden" name="date" value="{date}">
            <button class="bg-green-500 hover:bg-green-700 text-white font-bold py-2 px-4 rounded mobile-btn" type="submit">Сохранить</button>
            <button class="bg-gray-500 hover:bg-gray-700 text-white font-bold py-2 px-4 rounded mobile-btn" type="button" 
                hx-get="/section/nutrition/meal-log/row/{id}?date={date}" 
                hx-target="#edit-meal-log-row-{id}" 
                hx-swap="outerHTML">
                Отмена
            </button>
        </form>
    </td>
</tr>
'''

def get_dish_options(selected=None):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name FROM dish ORDER BY name;")
    options = ""
    for row in cur.fetchall():
        sel = " selected" if selected and row[0] == selected else ""
        options += f'<option value="{row[0]}"{sel}>{row[1]}</option>'
    cur.close()
    conn.close()
    return options

def render_meal_log_list(date_str):
    conn = get_db_connection()
    cur = conn.cursor()
    # Получаем все приёмы пищи за день
    cur.execute('''
        SELECT m.id, d.name, m.dish_id, m.consumed_grams
        FROM meal_log m JOIN dish d ON m.dish_id = d.id
        WHERE m.date = %s
        ORDER BY d.name;
    ''', (date_str,))
    meal_rows = cur.fetchall()
    rows = "".join(
        MEAL_LOG_ROW_TEMPLATE.format(id=row[0], dish_name=row[1], consumed_grams=row[3], date=date_str) for row in meal_rows
    )
    # --- КАЛОРИИ ---
    # Для каждого блюда считаем калории
    total_calories = 0.0
    for _, _, dish_id, consumed_grams in meal_rows:
        # Получаем ингредиенты блюда
        cur.execute('''
            SELECT di.grams, p.calories_per_100g
            FROM dish_ingredient di JOIN product p ON di.product_id = p.id
            WHERE di.dish_id = %s
        ''', (dish_id,))
        ingredients = cur.fetchall()
        # Считаем калорийность блюда на 1 грамм
        dish_calories_per_gram = 0.0
        for grams, cal_per_100g in ingredients:
            if grams and cal_per_100g:
                dish_calories_per_gram += (grams / 100.0) * cal_per_100g
        if ingredients:
            dish_calories_per_gram = dish_calories_per_gram / sum(g for g, _ in ingredients) if sum(g for g, _ in ingredients) > 0 else 0
        # Калории за приём пищи
        total_calories += dish_calories_per_gram * consumed_grams
    # Получаем целевое значение
    target_calories = get_calories_goal()
    calories_block = f'<div class="mb-3"><b>Количество калорий:</b> {int(total_calories)}</div>'
    if total_calories < target_calories:
        diff = int(target_calories - total_calories)
        calories_block = f'<div class="mb-2"><b>Количество калорий:</b> {int(total_calories)}</div>' \
                        f'<div class="text-orange-600 mb-3">До целевого веса: {diff}</div>'
    else:
        calories_block = f'<div class="mb-2"><b>Количество калорий:</b> {int(total_calories)}</div>' \
                        f'<div class="text-green-600 font-bold mb-3">Цель по калориям выполнена</div>'
    cur.close()
    conn.close()
    return MEAL_LOG_LIST_TEMPLATE.format(rows=rows, dish_options=get_dish_options(), date=date_str).replace('<table', calories_block + '<table', 1)

@app.get("/section/nutrition/meal-log", response_class=HTMLResponse)
async def nutrition_meal_log(date: str = Query(None)):
    if not date:
        date = datetime.now().date().isoformat()
    return HTMLResponse(render_meal_log_list(date))

@app.post("/section/nutrition/meal-log/add", response_class=HTMLResponse)
async def add_meal_log(dish_id: str = Form(...), consumed_grams: float = Form(...), date: str = Form(...)):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO meal_log (id, date, dish_id, consumed_grams) VALUES (%s, %s, %s, %s);", (str(uuid.uuid4()), date, dish_id, consumed_grams))
    conn.commit()
    cur.close()
    conn.close()
    return render_meal_log_list(date)

@app.get("/section/nutrition/meal-log/edit/{log_id}", response_class=HTMLResponse)
async def edit_meal_log_form(log_id: str, date: str = Query(...)):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, dish_id, consumed_grams FROM meal_log WHERE id = %s;", (log_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        return HTMLResponse(f"<tr><td colspan='3'>Запись не найдена</td></tr>")
    return MEAL_LOG_EDIT_TEMPLATE.format(id=row[0], dish_options=get_dish_options(selected=row[1]), consumed_grams=row[2], date=date)

@app.post("/section/nutrition/meal-log/edit/{log_id}", response_class=HTMLResponse)
async def edit_meal_log(log_id: str, dish_id: str = Form(...), consumed_grams: float = Form(...), date: str = Form(...)):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE meal_log SET dish_id = %s, consumed_grams = %s WHERE id = %s;", (dish_id, consumed_grams, log_id))
    conn.commit()
    cur.close()
    conn.close()
    return render_meal_log_list(date)

@app.delete("/section/nutrition/meal-log/delete/{log_id}", response_class=HTMLResponse)
async def delete_meal_log(log_id: str, date: str = Query(...)):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM meal_log WHERE id = %s;", (log_id,))
    conn.commit()
    cur.close()
    conn.close()
    return render_meal_log_list(date)

@app.get("/section/nutrition", response_class=HTMLResponse)
async def section_nutrition():
    content = render_meal_log_list(datetime.now().date().isoformat())
    html = NUTRITION_SECTION_TEMPLATE.format(
        active_products="", active_dishes="", active_meal_log="active", active_weight="",
        content=content
    )
    return HTMLResponse(html)

# --- Продукты ---
PRODUCT_LIST_TEMPLATE = '''
<div id="product-list">
<h2 class="text-xl lg:text-2xl font-bold mb-4">Продукты</h2>
<form hx-post="/section/nutrition/products/add" hx-target="#product-list" hx-swap="outerHTML" class="mb-4 mobile-form">
    <input class="border p-2 rounded w-full mb-2" type="text" name="name" placeholder="Название продукта" required>
    <input class="border p-2 rounded w-full mb-2" type="number" step="0.01" name="calories_per_100g" placeholder="Ккал на 100г" required>
    <input class="border p-2 rounded w-full mb-2" type="text" name="micro_description" placeholder="Описание">
    <button class="bg-blue-500 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded mobile-btn" type="submit">Добавить</button>
</form>
<div class="responsive-table">
<table class="table-auto w-full border-collapse border border-slate-400">
    <thead>
        <tr>
            <th class="border border-slate-300 p-2">Название</th>
            <th class="border border-slate-300 p-2">Ккал на 100г</th>
            <th class="border border-slate-300 p-2">Описание</th>
            <th class="border border-slate-300 p-2 text-center whitespace-nowrap w-1">Действия</th>
        </tr>
    </thead>
    <tbody>
    {rows}
    </tbody>
</table>
</div>
</div>
'''

PRODUCT_ROW_TEMPLATE = '''
<tr id="edit-product-row-{id}">
    <td class="border border-slate-300 p-2">{name}</td>
    <td class="border border-slate-300 p-2">{calories_per_100g}</td>
    <td class="border border-slate-300 p-2">{micro_description}</td>
    <td class="border border-slate-300 p-2 text-center whitespace-nowrap w-1">
        <button class="bg-yellow-500 hover:bg-yellow-700 text-white font-bold py-1 px-2 rounded mobile-btn" hx-get="/section/nutrition/products/edit/{id}" hx-target="#edit-product-row-{id}" hx-swap="outerHTML">✏️</button>
        <button class="bg-red-500 hover:bg-red-700 text-white font-bold py-1 px-2 rounded mobile-btn" hx-delete="/section/nutrition/products/delete/{id}" hx-target="#product-list" hx-swap="outerHTML">🗑️</button>
    </td>
</tr>
'''

PRODUCT_EDIT_TEMPLATE = '''
<tr id="edit-product-row-{id}">
    <td colspan="4" class="p-2">
        <form hx-post="/section/nutrition/products/edit/{id}" hx-target="#product-list" hx-swap="outerHTML">
            <input class="border p-2 rounded w-full mb-2" type="text" name="name" value="{name}" required>
            <input class="border p-2 rounded w-full mb-2" type="number" step="0.01" name="calories_per_100g" value="{calories_per_100g}" required>
            <input class="border p-2 rounded w-full mb-2" type="text" name="micro_description" value="{micro_description}">
            <button class="bg-green-500 hover:bg-green-700 text-white font-bold py-2 px-4 rounded mobile-btn" type="submit">Сохранить</button>
            <button class="bg-gray-500 hover:bg-gray-700 text-white font-bold py-2 px-4 rounded mobile-btn" type="button" 
                hx-get="/section/nutrition/products/row/{id}" 
                hx-target="#edit-product-row-{id}" 
                hx-swap="outerHTML">
                Отмена
            </button>
        </form>
    </td>
</tr>
'''

def render_product_list():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name, calories_per_100g, micro_description FROM product ORDER BY name;")
    rows = "".join(
        PRODUCT_ROW_TEMPLATE.format(id=row[0], name=row[1], calories_per_100g=row[2], micro_description=row[3] or "") for row in cur.fetchall()
    )
    cur.close()
    conn.close()
    return PRODUCT_LIST_TEMPLATE.format(rows=rows)

@app.get("/section/nutrition/products", response_class=HTMLResponse)
async def nutrition_products():
    return HTMLResponse(render_product_list())

@app.post("/section/nutrition/products/add", response_class=HTMLResponse)
async def add_product(name: str = Form(...), calories_per_100g: float = Form(...), micro_description: str = Form(None)):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO product (id, name, calories_per_100g, micro_description) VALUES (%s, %s, %s, %s);", (str(uuid.uuid4()), name, calories_per_100g, micro_description))
    conn.commit()
    cur.close()
    conn.close()
    return render_product_list()

@app.get("/section/nutrition/products/edit/{product_id}", response_class=HTMLResponse)
async def edit_product_form(product_id: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name, calories_per_100g, micro_description FROM product WHERE id = %s;", (product_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        return HTMLResponse("<tr><td colspan='4'>Продукт не найден</td></tr>")
    return PRODUCT_EDIT_TEMPLATE.format(id=row[0], name=row[1], calories_per_100g=row[2], micro_description=row[3] or "")

@app.post("/section/nutrition/products/edit/{product_id}", response_class=HTMLResponse)
async def edit_product(product_id: str, name: str = Form(...), calories_per_100g: float = Form(...), micro_description: str = Form(None)):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE product SET name = %s, calories_per_100g = %s, micro_description = %s WHERE id = %s;", (name, calories_per_100g, micro_description, product_id))
    conn.commit()
    cur.close()
    conn.close()
    return render_product_list()

@app.delete("/section/nutrition/products/delete/{product_id}", response_class=HTMLResponse)
async def delete_product(product_id: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM product WHERE id = %s;", (product_id,))
    conn.commit()
    cur.close()
    conn.close()
    return render_product_list()

@app.get("/section/nutrition/products/row/{product_id}", response_class=HTMLResponse)
async def product_row(product_id: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name, calories_per_100g, micro_description FROM product WHERE id = %s", (product_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        return HTMLResponse("<tr><td colspan='4'>Продукт не найден</td></tr>")
    return PRODUCT_ROW_TEMPLATE.format(
        id=row[0], name=row[1], calories_per_100g=row[2], micro_description=row[3] or ""
    )

# --- Блюда ---
DISH_LIST_TEMPLATE = '''
<div id="dish-list">
<h2 class="text-xl lg:text-2xl font-bold mb-4">Блюда</h2>
<form hx-post="/section/nutrition/dishes/add" hx-target="#dish-list" hx-swap="outerHTML" class="mb-4 mobile-form">
    <input class="border p-2 rounded w-full mb-2" type="text" name="name" placeholder="Название блюда" required>
    <input class="border p-2 rounded w-full mb-2" type="text" name="description" placeholder="Описание">
    <button class="bg-blue-500 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded mobile-btn" type="submit">Добавить</button>
</form>
<div class="responsive-table">
<table class="table-auto w-full border-collapse border border-slate-400">
    <thead>
        <tr>
            <th class="border border-slate-300 p-2">Название</th>
            <th class="border border-slate-300 p-2">Описание</th>
            <th class="border border-slate-300 p-2 text-center whitespace-nowrap w-1">Действия</th>
        </tr>
    </thead>
    <tbody>
    {rows}
    </tbody>
</table>
</div>
</div>
'''

DISH_ROW_TEMPLATE = '''
<tr id="edit-dish-row-{id}">
    <td class="border border-slate-300 p-2">{name}</td>
    <td class="border border-slate-300 p-2">{description}</td>
    <td class="border border-slate-300 p-2 text-center whitespace-nowrap w-1">
        <button class="bg-yellow-500 hover:bg-yellow-700 text-white font-bold py-1 px-2 rounded mobile-btn" hx-get="/section/nutrition/dishes/edit/{id}" hx-target="#edit-dish-row-{id}" hx-swap="outerHTML">✏️</button>
        <button class="bg-red-500 hover:bg-red-700 text-white font-bold py-1 px-2 rounded mobile-btn" hx-delete="/section/nutrition/dishes/delete/{id}" hx-target="#dish-list" hx-swap="outerHTML">🗑️</button>
    </td>
</tr>
'''

DISH_EDIT_TEMPLATE = '''
<tr id="edit-dish-row-{id}">
    <td colspan="3" class="p-2">
        <form hx-post="/section/nutrition/dishes/edit/{id}" hx-target="#dish-list" hx-swap="outerHTML">
            <input class="border p-2 rounded w-full mb-2" type="text" name="name" value="{name}" required>
            <input class="border p-2 rounded w-full mb-2" type="text" name="description" value="{description}">
            <button class="bg-green-500 hover:bg-green-700 text-white font-bold py-2 px-4 rounded mobile-btn" type="submit">Сохранить</button>
            <button class="bg-gray-500 hover:bg-gray-700 text-white font-bold py-2 px-4 rounded mobile-btn" type="button" 
                hx-get="/section/nutrition/dishes/row/{id}" 
                hx-target="#edit-dish-row-{id}" 
                hx-swap="outerHTML">
                Отмена
            </button>
        </form>
    </td>
</tr>
'''

def render_dish_list():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name, description FROM dish ORDER BY name;")
    rows = "".join(
        DISH_ROW_TEMPLATE.format(id=row[0], name=row[1], description=row[2] or "") for row in cur.fetchall()
    )
    cur.close()
    conn.close()
    return DISH_LIST_TEMPLATE.format(rows=rows)

@app.get("/section/nutrition/dishes", response_class=HTMLResponse)
async def nutrition_dishes():
    return HTMLResponse(render_dish_list())

@app.post("/section/nutrition/dishes/add", response_class=HTMLResponse)
async def add_dish(name: str = Form(...), description: str = Form(None)):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO dish (id, name, description) VALUES (%s, %s, %s);", (str(uuid.uuid4()), name, description))
    conn.commit()
    cur.close()
    conn.close()
    return render_dish_list()

@app.get("/section/nutrition/dishes/edit/{dish_id}", response_class=HTMLResponse)
async def edit_dish_form(dish_id: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name, description FROM dish WHERE id = %s;", (dish_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        return HTMLResponse("<tr><td colspan='3'>Блюдо не найдено</td></tr>")
    return DISH_EDIT_TEMPLATE.format(id=row[0], name=row[1], description=row[2] or "")

@app.post("/section/nutrition/dishes/edit/{dish_id}", response_class=HTMLResponse)
async def edit_dish(dish_id: str, name: str = Form(...), description: str = Form(None)):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE dish SET name = %s, description = %s WHERE id = %s;", (name, description, dish_id))
    conn.commit()
    cur.close()
    conn.close()
    return render_dish_list()

@app.delete("/section/nutrition/dishes/delete/{dish_id}", response_class=HTMLResponse)
async def delete_dish(dish_id: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM dish WHERE id = %s;", (dish_id,))
    conn.commit()
    cur.close()
    conn.close()
    return render_dish_list()

WEIGHT_LIST_TEMPLATE = '''
<div id="weight-list">
<h2 class="text-xl lg:text-2xl font-bold mb-4">Вес</h2>
<form hx-post="/section/nutrition/weight/add" hx-target="#weight-list" hx-swap="outerHTML" class="mb-4 mobile-form">
    <input class="border p-2 rounded" type="date" name="date" value="{today}" required>
    <input class="border p-2 rounded" type="number" step="0.01" name="weight" placeholder="Вес (кг)" required>
    <button class="bg-blue-500 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded mobile-btn" type="submit">Добавить</button>
</form>
<div class="responsive-table">
<table class="table-auto w-full border-collapse border border-slate-400">
    <thead>
        <tr>
            <th class="border border-slate-300 p-2">Дата</th>
            <th class="border border-slate-300 p-2">Вес (кг)</th>
            <th class="border border-slate-300 p-2 text-center whitespace-nowrap w-1">Действия</th>
        </tr>
    </thead>
    <tbody>
    {rows}
    </tbody>
</table>
</div>
</div>
'''

WEIGHT_ROW_TEMPLATE = '''
<tr id="edit-weight-row-{id}">
    <td class="border border-slate-300 p-2">{date}</td>
    <td class="border border-slate-300 p-2">{weight}</td>
    <td class="border border-slate-300 p-2 text-center whitespace-nowrap w-1">
        <button class="bg-yellow-500 hover:bg-yellow-700 text-white font-bold py-1 px-2 rounded mobile-btn" hx-get="/section/nutrition/weight/edit/{id}" hx-target="#edit-weight-row-{id}" hx-swap="outerHTML">✏️</button>
        <button class="bg-red-500 hover:bg-red-700 text-white font-bold py-1 px-2 rounded mobile-btn" hx-delete="/section/nutrition/weight/delete/{id}" hx-target="#weight-list" hx-swap="outerHTML">🗑️</button>
    </td>
</tr>
'''

WEIGHT_EDIT_TEMPLATE = '''
<tr id="edit-weight-row-{id}">
    <td colspan="3" class="p-2">
        <form hx-post="/section/nutrition/weight/edit/{id}" hx-target="#weight-list" hx-swap="outerHTML">
            <input class="border p-2 rounded w-full mb-2" type="date" name="date" value="{date}" required>
            <input class="border p-2 rounded w-full mb-2" type="number" step="0.01" name="weight" value="{weight}" required>
            <button class="bg-green-500 hover:bg-green-700 text-white font-bold py-2 px-4 rounded mobile-btn" type="submit">Сохранить</button>
            <button class="bg-gray-500 hover:bg-gray-700 text-white font-bold py-2 px-4 rounded mobile-btn" type="button" 
                hx-get="/section/nutrition/weight/row/{id}" 
                hx-target="#edit-weight-row-{id}" 
                hx-swap="outerHTML">
                Отмена
            </button>
        </form>
    </td>
</tr>
'''

def render_weight_list():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, date, weight FROM personal_data ORDER BY date DESC;")
    rows = "".join(
        WEIGHT_ROW_TEMPLATE.format(id=row[0], date=row[1], weight=row[2]) for row in cur.fetchall()
    )
    cur.close()
    conn.close()
    from datetime import date as dtdate
    return WEIGHT_LIST_TEMPLATE.format(rows=rows, today=dtdate.today().isoformat())

@app.get("/section/nutrition/weight", response_class=HTMLResponse)
async def nutrition_weight():
    return HTMLResponse(render_weight_list())

@app.post("/section/nutrition/weight/add", response_class=HTMLResponse)
async def add_weight(date: str = Form(...), weight: float = Form(...)):
    conn = get_db_connection()
    cur = conn.cursor()
    import uuid
    cur.execute("INSERT INTO personal_data (id, date, weight) VALUES (%s, %s, %s);", (str(uuid.uuid4()), date, weight))
    conn.commit()
    cur.close()
    conn.close()
    return render_weight_list()

@app.get("/section/nutrition/weight/edit/{weight_id}", response_class=HTMLResponse)
async def edit_weight_form(weight_id: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, date, weight FROM personal_data WHERE id = %s;", (weight_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        return HTMLResponse(f"<tr><td colspan='3'>Запись не найдена</td></tr>")
    return WEIGHT_EDIT_TEMPLATE.format(id=row[0], date=row[1], weight=row[2])

@app.post("/section/nutrition/weight/edit/{weight_id}", response_class=HTMLResponse)
async def edit_weight(weight_id: str, date: str = Form(...), weight: float = Form(...)):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE personal_data SET date = %s, weight = %s WHERE id = %s;", (date, weight, weight_id))
    conn.commit()
    cur.close()
    conn.close()
    return render_weight_list()

@app.delete("/section/nutrition/weight/delete/{weight_id}", response_class=HTMLResponse)
async def delete_weight(weight_id: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM personal_data WHERE id = %s;", (weight_id,))
    conn.commit()
    cur.close()
    conn.close()
    return render_weight_list()

@app.get("/section/nutrition/weight/row/{weight_id}", response_class=HTMLResponse)
async def weight_row(weight_id: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, date, weight FROM personal_data WHERE id = %s", (weight_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        return HTMLResponse("<tr><td colspan='3'>Запись не найдена</td></tr>")
    return WEIGHT_ROW_TEMPLATE.format(
        id=row[0], date=row[1], weight=row[2]
    )

SETTINGS_SECTION_TEMPLATE = '''
<div>
    <div class="flex border-b tabs">
        <button class="tab py-2 px-4 text-gray-500 border-b-2 border-transparent hover:border-blue-500 hover:text-blue-500 active" id="tab-settings-general" hx-get="/section/settings/general" hx-target="#settings-subsection" hx-swap="innerHTML" onclick="setActiveSubTab(this)">Общие</button>
    </div>
    <div id="settings-subsection" class="p-4">{content}</div>
</div>
<script>
function setActiveSubTab(tab) {{
    document.querySelectorAll('.tabs .tab').forEach(btn => btn.classList.remove('active'));
    tab.classList.add('active');
}}
</script>
'''

SETTINGS_TEMPLATE = '''
<div class="max-w-md mx-auto bg-white p-4 lg:p-6 rounded-lg shadow-md" id="settings-goal-form">
    <h2 class="text-xl lg:text-2xl font-bold mb-4 text-gray-800">Настройки калорий</h2>
    <form hx-post="/section/settings/calories-goal" hx-target="#settings-goal-form" hx-swap="outerHTML" class="space-y-4 mobile-form">
        <div>
            <label class="block text-gray-700 text-sm font-bold mb-2" for="target_calories">
                Целевые калории в день:
            </label>
            <input class="shadow appearance-none border rounded w-full py-2 px-3 text-gray-700 leading-tight focus:outline-none focus:shadow-outline" id="target_calories" type="number" name="target_calories" value="{target_calories}" min="0" required>
        </div>
        <button class="bg-blue-500 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded focus:outline-none focus:shadow-outline mobile-btn" type="submit">Сохранить</button>
    </form>
</div>
'''

def get_calories_goal():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT target_calories FROM calories_goal LIMIT 1;")
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row[0] if row else 2000

@app.get("/section/settings", response_class=HTMLResponse)
async def section_settings():
    content = (await settings_general()).body.decode()
    html = SETTINGS_SECTION_TEMPLATE.format(
        content=content
    )
    return HTMLResponse(html)

@app.get("/section/settings/general", response_class=HTMLResponse)
async def settings_general():
    target_calories = get_calories_goal()
    return HTMLResponse(SETTINGS_TEMPLATE.format(target_calories=target_calories))

@app.post("/section/settings/calories-goal", response_class=HTMLResponse)
async def set_calories_goal(target_calories: int = Form(...)):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM calories_goal LIMIT 1;")
    row = cur.fetchone()
    if row:
        cur.execute("UPDATE calories_goal SET target_calories = %s WHERE id = %s;", (target_calories, row[0]))
    else:
        import uuid
        cur.execute("INSERT INTO calories_goal (id, target_calories) VALUES (%s, %s);", (str(uuid.uuid4()), target_calories))
    conn.commit()
    cur.close()
    conn.close()
    return HTMLResponse(SETTINGS_TEMPLATE.format(target_calories=target_calories))

def create_session(user_id):
    token = secrets.token_hex(32)
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO sessions (id, user_id, session_token) VALUES (%s, %s, %s);",
                (str(uuid.uuid4()), user_id, token))
    conn.commit()
    cur.close()
    conn.close()
    return token

def get_user_by_session_token(token):
    if not token:
        return None
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT users.id, users.username FROM sessions
        JOIN users ON sessions.user_id = users.id
        WHERE session_token = %s;
    """, (token,))
    user = cur.fetchone()
    cur.close()
    conn.close()
    return user

@app.get("/logout")
def logout(session_token: str = Cookie(None)):
    if session_token:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM sessions WHERE session_token = %s;", (session_token,))
        conn.commit()
        cur.close()
        conn.close()
    response = RedirectResponse("/")
    response.delete_cookie("session_token")
    return response

@app.get("/section/habits/habits/row/{habit_id}", response_class=HTMLResponse)
async def habit_row(habit_id: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        SELECT h.id, h.name, h.description, h.category_id, h.priority, c.name
        FROM habit h LEFT JOIN habit_category c ON h.category_id = c.id
        WHERE h.id = %s
    ''', (habit_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        return HTMLResponse("<tr><td colspan='5'>Привычка не найдена</td></tr>")
    return HABIT_ROW_TEMPLATE.format(
        id=row[0], name=row[1], description=row[2] or "", category=row[5] or "", priority=row[4]
    )

@app.get("/section/tasks/tasks/row/{task_id}", response_class=HTMLResponse)
async def task_row(task_id: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        SELECT t.id, t.name, t.description, t.category_id, t.date, t.repeat, c.name
        FROM task t LEFT JOIN task_category c ON t.category_id = c.id
        WHERE t.id = %s
    ''', (task_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        return HTMLResponse("<tr><td colspan='6'>Задача не найдена</td></tr>")
    return TASK_ROW_TEMPLATE.format(
        id=row[0], name=row[1], description=row[2] or "", category=row[6] or "", date=row[4], repeat=row[5]
    )

@app.get("/section/nutrition/dishes/row/{dish_id}", response_class=HTMLResponse)
async def dish_row(dish_id: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name, description FROM dish WHERE id = %s", (dish_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        return HTMLResponse("<tr><td colspan='3'>Блюдо не найдено</td></tr>")
    return DISH_ROW_TEMPLATE.format(
        id=row[0], name=row[1], description=row[2] or ""
    )

@app.get("/section/nutrition/meal-log/row/{log_id}", response_class=HTMLResponse)
async def meal_log_row(log_id: str, date: str = Query(...)):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        SELECT m.id, d.name, m.dish_id, m.consumed_grams
        FROM meal_log m JOIN dish d ON m.dish_id = d.id
        WHERE m.id = %s
    ''', (log_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        return HTMLResponse(f"<tr><td colspan='3'>Запись не найдена</td></tr>")
    return MEAL_LOG_ROW_TEMPLATE.format(id=row[0], dish_name=row[1], consumed_grams=row[3], date=date)
  
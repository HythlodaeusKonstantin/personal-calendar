from fastapi import FastAPI, Request, APIRouter, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape
import psycopg2
import os
from psycopg2 import sql
import uuid
from datetime import date

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
    ]
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

# HTML-шаблоны для habit_category
HABIT_CATEGORY_LIST_TEMPLATE = '''
<div id="habit-category-list">
<h2>Категории привычек</h2>
<form hx-post="/section/habits/category/add" hx-target="#habit-category-list" hx-swap="outerHTML" style="margin-bottom: 16px;">
    <input type="text" name="name" placeholder="Название категории" required>
    <button type="submit">Добавить</button>
</form>
<table border="1" cellpadding="8" style="border-collapse: collapse; width: 100%;">
    <tr><th>Название</th><th>Действия</th></tr>
    {rows}
</table>
</div>
'''

HABIT_CATEGORY_ROW_TEMPLATE = '''
<tr id="edit-row-{id}">
    <td>{name}</td>
    <td>
        <button hx-get="/section/habits/category/edit/{id}" hx-target="#edit-row-{id}" hx-swap="outerHTML">✏️</button>
        <button hx-delete="/section/habits/category/delete/{id}" hx-target="#habit-category-list" hx-swap="outerHTML">🗑️</button>
    </td>
</tr>
'''

HABIT_CATEGORY_EDIT_TEMPLATE = '''
<tr id="edit-row-{id}">
    <td colspan="2">
        <form hx-post="/section/habits/category/edit/{id}" hx-target="#habit-category-list" hx-swap="outerHTML">
            <input type="text" name="name" value="{name}" required>
            <button type="submit">Сохранить</button>
            <button type="button" onclick="window.location.reload()">Отмена</button>
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
    <div class="tabs" style="margin-bottom: 0;">
        <button class="tab {active_marks}" id="tab-habit-marks" hx-get="/section/habits/marks" hx-target="#habits-subsection" hx-swap="innerHTML" onclick="setActiveSubTab(this)">Отметки</button>
        <button class="tab {active_categories}" id="tab-habit-categories" hx-get="/section/habits/categories" hx-target="#habits-subsection" hx-swap="innerHTML" onclick="setActiveSubTab(this)">Категории</button>
        <button class="tab {active_habits}" id="tab-habit-habits" hx-get="/section/habits/habits" hx-target="#habits-subsection" hx-swap="innerHTML" onclick="setActiveSubTab(this)">Карточки привычек</button>
    </div>
    <div id="habits-subsection" class="tab-content" style="margin-top:0;">{content}</div>
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
    # При нажатии на корневую вкладку всегда показываем "Отметки"
    html = HABITS_SECTION_TEMPLATE.format(
        active_marks="active", active_categories="", active_habits="",
        content="<div>Отметки</div>"
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
        rows += f'''<tr><td>{habit_name}</td><td><input type="checkbox" hx-post="/section/habits/marks/toggle/{entry_id}" hx-target="this" hx-swap="outerHTML" {checked}></td></tr>'''
    cur.close()
    conn.close()
    html = f'''
    <h2>Отметки за {today.strftime('%d.%m.%Y')}</h2>
    <table border="1" cellpadding="8" style="border-collapse: collapse; width: 100%;">
        <tr><th>Привычка</th><th>Выполнено</th></tr>
        {rows}
    </table>
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
    # Получаем имя привычки
    cur.execute("SELECT h.name FROM habit_entry e JOIN habit h ON e.habit_id = h.id WHERE e.id = %s;", (entry_id,))
    habit_name = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    checked = "checked" if new_value else ""
    return HTMLResponse(f'<input type="checkbox" hx-post="/section/habits/marks/toggle/{entry_id}" hx-target="this" hx-swap="outerHTML" {checked}>')

@app.get("/section/habits/categories", response_class=HTMLResponse)
async def habits_categories():
    html = render_habit_category_list()
    return HTMLResponse(html)

# --- Карточки привычек (habit) ---
HABIT_LIST_TEMPLATE = '''
<div id="habit-list">
<h2>Карточки привычек</h2>
<form hx-post="/section/habits/habits/add" hx-target="#habit-list" hx-swap="outerHTML" style="margin-bottom: 16px;">
    <input type="text" name="name" placeholder="Название привычки" required>
    <input type="text" name="description" placeholder="Описание">
    <select name="category_id" required>
        <option value="">Категория...</option>
        {category_options}
    </select>
    <select name="priority" required>
        <option value="HIGH">Высокий</option>
        <option value="MEDIUM">Средний</option>
        <option value="LOW">Низкий</option>
    </select>
    <button type="submit">Добавить</button>
</form>
<table border="1" cellpadding="8" style="border-collapse: collapse; width: 100%;">
    <tr><th>Название</th><th>Описание</th><th>Категория</th><th>Приоритет</th><th>Действия</th></tr>
    {rows}
</table>
</div>
'''

HABIT_ROW_TEMPLATE = '''
<tr id="edit-habit-row-{id}">
    <td>{name}</td>
    <td>{description}</td>
    <td>{category}</td>
    <td>{priority}</td>
    <td>
        <button hx-get="/section/habits/habits/edit/{id}" hx-target="#edit-habit-row-{id}" hx-swap="outerHTML">✏️</button>
        <button hx-delete="/section/habits/habits/delete/{id}" hx-target="#habit-list" hx-swap="outerHTML">🗑️</button>
    </td>
</tr>
'''

HABIT_EDIT_TEMPLATE = '''
<tr id="edit-habit-row-{id}">
    <td colspan="5">
        <form hx-post="/section/habits/habits/edit/{id}" hx-target="#habit-list" hx-swap="outerHTML">
            <input type="text" name="name" value="{name}" required>
            <input type="text" name="description" value="{description}">
            <select name="category_id" required>
                {category_options}
            </select>
            <select name="priority" required>
                <option value="HIGH" {high}>Высокий</option>
                <option value="MEDIUM" {medium}>Средний</option>
                <option value="LOW" {low}>Низкий</option>
            </select>
            <button type="submit">Сохранить</button>
            <button type="button" onclick="window.location.reload()">Отмена</button>
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

@app.get("/section/tasks", response_class=HTMLResponse)
async def section_tasks():
    return HTMLResponse("<div>Задачи</div>")

@app.get("/section/nutrition", response_class=HTMLResponse)
async def section_nutrition():
    return HTMLResponse("<div>Питание</div>")

@app.get("/section/sport", response_class=HTMLResponse)
async def section_sport():
    return HTMLResponse("<div>Спорт</div>") 
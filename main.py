from fastapi import FastAPI, Request, APIRouter, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape
import psycopg2
import os
from psycopg2 import sql
import uuid
from datetime import date, timedelta, datetime

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
        row_style = ' style="background: #d4edda;"' if completed else ''
        rows += f'''<tr{row_style}><td>{habit_name}</td><td><input type="checkbox" hx-post="/section/habits/marks/toggle/{entry_id}" hx-target="#habits-marks-table-area" hx-swap="outerHTML" {checked}></td></tr>'''
    cur.close()
    conn.close()
    html = f'''
    <div id="habits-marks-table-area">
        <h2>Отметки за {today.strftime('%d.%m.%Y')}</h2>
        <table id="habits-marks-table" border="1" cellpadding="8" style="border-collapse: collapse; width: 100%;">
            <tr><th>Привычка</th><th>Выполнено</th></tr>
            {rows}
        </table>
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

# --- Раздел Задачи ---
TASKS_SECTION_TEMPLATE = '''
<div>
    <div class="tabs" style="margin-bottom: 0;">
        <button class="tab {active_marks}" id="tab-task-marks" hx-get="/section/tasks/marks" hx-target="#tasks-subsection" hx-swap="innerHTML" onclick="setActiveSubTab(this)">Отметки</button>
        <button class="tab {active_categories}" id="tab-task-categories" hx-get="/section/tasks/categories" hx-target="#tasks-subsection" hx-swap="innerHTML" onclick="setActiveSubTab(this)">Категории</button>
        <button class="tab {active_tasks}" id="tab-task-tasks" hx-get="/section/tasks/tasks" hx-target="#tasks-subsection" hx-swap="innerHTML" onclick="setActiveSubTab(this)">Карточки задач</button>
    </div>
    <div id="tasks-subsection" class="tab-content" style="margin-top:0;">{content}</div>
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
<h2>Категории задач</h2>
<form hx-post="/section/tasks/categories/add" hx-target="#task-category-list" hx-swap="outerHTML" style="margin-bottom: 16px;">
    <input type="text" name="name" placeholder="Название категории" required>
    <button type="submit">Добавить</button>
</form>
<table border="1" cellpadding="8" style="border-collapse: collapse; width: 100%;">
    <tr><th>Название</th><th>Действия</th></tr>
    {rows}
</table>
</div>
'''

TASK_CATEGORY_ROW_TEMPLATE = '''
<tr id="edit-task-category-row-{id}">
    <td>{name}</td>
    <td>
        <button hx-get="/section/tasks/categories/edit/{id}" hx-target="#edit-task-category-row-{id}" hx-swap="outerHTML">✏️</button>
        <button hx-delete="/section/tasks/categories/delete/{id}" hx-target="#task-category-list" hx-swap="outerHTML">🗑️</button>
    </td>
</tr>
'''

TASK_CATEGORY_EDIT_TEMPLATE = '''
<tr id="edit-task-category-row-{id}">
    <td colspan="2">
        <form hx-post="/section/tasks/categories/edit/{id}" hx-target="#task-category-list" hx-swap="outerHTML">
            <input type="text" name="name" value="{name}" required>
            <button type="submit">Сохранить</button>
            <button type="button" onclick="window.location.reload()">Отмена</button>
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

# --- Карточки задач ---
TASK_LIST_TEMPLATE = '''
<div id="task-list">
<h2>Карточки задач</h2>
<form hx-post="/section/tasks/tasks/add" hx-target="#task-list" hx-swap="outerHTML" style="margin-bottom: 16px;">
    <input type="text" name="name" placeholder="Название задачи" required>
    <input type="text" name="description" placeholder="Описание">
    <select name="category_id" required>
        <option value="">Категория...</option>
        {category_options}
    </select>
    <input type="date" name="date" required>
    <select name="repeat" required>
        <option value="NONE">Без повтора</option>
        <option value="DAILY">Ежедневно</option>
        <option value="WEEKLY">Еженедельно</option>
    </select>
    <button type="submit">Добавить</button>
</form>
<table border="1" cellpadding="8" style="border-collapse: collapse; width: 100%;">
    <tr><th>Название</th><th>Описание</th><th>Категория</th><th>Дата</th><th>Повтор</th><th>Действия</th></tr>
    {rows}
</table>
</div>
'''

TASK_ROW_TEMPLATE = '''
<tr id="edit-task-row-{id}">
    <td>{name}</td>
    <td>{description}</td>
    <td>{category}</td>
    <td>{date}</td>
    <td>{repeat}</td>
    <td>
        <button hx-get="/section/tasks/tasks/edit/{id}" hx-target="#edit-task-row-{id}" hx-swap="outerHTML">✏️</button>
        <button hx-delete="/section/tasks/tasks/delete/{id}" hx-target="#task-list" hx-swap="outerHTML">🗑️</button>
    </td>
</tr>
'''

TASK_EDIT_TEMPLATE = '''
<tr id="edit-task-row-{id}">
    <td colspan="6">
        <form hx-post="/section/tasks/tasks/edit/{id}" hx-target="#task-list" hx-swap="outerHTML">
            <input type="text" name="name" value="{name}" required>
            <input type="text" name="description" value="{description}">
            <select name="category_id" required>
                {category_options}
            </select>
            <input type="date" name="date" value="{date}" required>
            <select name="repeat" required>
                <option value="NONE" {none}>Без повтора</option>
                <option value="DAILY" {daily}>Ежедневно</option>
                <option value="WEEKLY" {weekly}>Еженедельно</option>
            </select>
            <button type="submit">Сохранить</button>
            <button type="button" onclick="window.location.reload()">Отмена</button>
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
        row_style = ' style="background: #d4edda;"' if completed else (' style="background: #f8d7da;"' if is_overdue else '')
        delete_btn = f'<button hx-delete="/section/tasks/marks/delete/{entry_id}" hx-target="closest tr" hx-swap="outerHTML">🗑️</button>' if show_completed == "1" else ""
        last_col = f'<td>{delete_btn}</td>' if show_completed == "1" else ""
        rows += f'''<tr{row_style}><td>{name}</td><td>{description or ''}</td><td>{task_date}</td><td>{repeat}</td><td>{entry_date}</td><td><input type="checkbox" hx-post="/section/tasks/marks/toggle/{entry_id}" hx-target="#tasks-marks-table-area" hx-swap="outerHTML" {checked}></td>{last_col}</tr>'''
    cur.close()
    conn.close()
    checked_flag = "checked" if show_completed == "1" else ""
    table_width = "100%"
    th_delete = '<th></th>' if show_completed == "1" else ''
    html = f'''
    <div id="tasks-marks-table-area">
        <h2>Задачи</h2>
        <label><input type="checkbox" id="show-completed-tasks" {checked_flag} hx-get="/section/tasks/marks" hx-target="#tasks-subsection" hx-swap="innerHTML" hx-vals='{{"show_completed": "{1 if show_completed == "0" else 0}"}}'> Показывать выполненные задачи</label>
        <table id="tasks-marks-table" border="1" cellpadding="8" style="border-collapse: collapse; width: {table_width};">
            <tr><th>Название</th><th>Описание</th><th>Дата задачи</th><th>Повтор</th><th>Дата отметки</th><th>Выполнено</th>{th_delete}</tr>
            {rows}
        </table>
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
    <div class="tabs" style="margin-bottom: 0;">
        <button class="tab {active_meal_log}" id="tab-nutrition-meal-log" hx-get="/section/nutrition/meal-log" hx-target="#nutrition-subsection" hx-swap="innerHTML" onclick="setActiveSubTab(this)">Приемы пищи</button>
        <button class="tab {active_products}" id="tab-nutrition-products" hx-get="/section/nutrition/products" hx-target="#nutrition-subsection" hx-swap="innerHTML" onclick="setActiveSubTab(this)">Продукты</button>
        <button class="tab {active_dishes}" id="tab-nutrition-dishes" hx-get="/section/nutrition/dishes" hx-target="#nutrition-subsection" hx-swap="innerHTML" onclick="setActiveSubTab(this)">Блюда</button>
        <button class="tab {active_weight}" id="tab-nutrition-weight" hx-get="/section/nutrition/weight" hx-target="#nutrition-subsection" hx-swap="innerHTML" onclick="setActiveSubTab(this)">Вес</button>
    </div>
    <div id="nutrition-subsection" class="tab-content" style="margin-top:0;">{content}</div>
</div>
<script>
function setActiveSubTab(tab) {{
    document.querySelectorAll('.tabs .tab').forEach(btn => btn.classList.remove('active'));
    tab.classList.add('active');
}}
</script>
'''

from fastapi import Query
from datetime import datetime

MEAL_LOG_LIST_TEMPLATE = '''
<div id="meal-log-list">
<h2>Приемы пищи</h2>
<form id="meal-log-date-form" style="margin-bottom: 16px;">
    <label>Дата: <input type="date" name="date" value="{date}" hx-get="/section/nutrition/meal-log" hx-target="#nutrition-subsection" hx-swap="innerHTML"></label>
</form>
<form hx-post="/section/nutrition/meal-log/add" hx-target="#meal-log-list" hx-swap="outerHTML" style="margin-bottom: 16px; display: flex; gap: 8px; align-items: center;">
    <select name="dish_id" required>
        <option value="">Блюдо...</option>
        {dish_options}
    </select>
    <input type="number" step="0.01" name="consumed_grams" placeholder="Граммы" required style="width:90px;">
    <input type="hidden" name="date" value="{date}">
    <button type="submit">Добавить</button>
</form>
<table border="1" cellpadding="8" style="border-collapse: collapse; width: 100%;">
    <tr><th>Блюдо</th><th>Граммы</th><th>Действия</th></tr>
    {rows}
</table>
</div>
'''

MEAL_LOG_ROW_TEMPLATE = '''
<tr id="edit-meal-log-row-{id}">
    <td>{dish_name}</td>
    <td>{consumed_grams}</td>
    <td>
        <button hx-get="/section/nutrition/meal-log/edit/{id}?date={date}" hx-target="#edit-meal-log-row-{id}" hx-swap="outerHTML">✏️</button>
        <button hx-delete="/section/nutrition/meal-log/delete/{id}?date={date}" hx-target="#meal-log-list" hx-swap="outerHTML">🗑️</button>
    </td>
</tr>
'''

MEAL_LOG_EDIT_TEMPLATE = '''
<tr id="edit-meal-log-row-{id}">
    <td colspan="3">
        <form hx-post="/section/nutrition/meal-log/edit/{id}" hx-target="#meal-log-list" hx-swap="outerHTML">
            <select name="dish_id" required>
                {dish_options}
            </select>
            <input type="number" step="0.01" name="consumed_grams" value="{consumed_grams}" required style="width:90px;">
            <input type="hidden" name="date" value="{date}">
            <button type="submit">Сохранить</button>
            <button type="button" onclick="window.location.reload()">Отмена</button>
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
    calories_block = f'<div style="margin-bottom:12px;"><b>Количество калорий:</b> {int(total_calories)}</div>'
    if total_calories < target_calories:
        diff = int(target_calories - total_calories)
        calories_block = f'<div style="margin-bottom:8px;"><b>Количество калорий:</b> {int(total_calories)}</div>' \
                        f'<div style="color:#d35400;margin-bottom:12px;">До целевого веса: {diff}</div>'
    else:
        calories_block = f'<div style="margin-bottom:8px;"><b>Количество калорий:</b> {int(total_calories)}</div>' \
                        f'<div style="color:green;font-weight:bold;margin-bottom:12px;">Цель по калориям выполнена</div>'
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
<h2>Продукты</h2>
<form hx-post="/section/nutrition/products/add" hx-target="#product-list" hx-swap="outerHTML" style="margin-bottom: 16px;">
    <input type="text" name="name" placeholder="Название" required>
    <input type="number" step="0.01" name="calories_per_100g" placeholder="Ккал на 100г" required>
    <input type="text" name="micro_description" placeholder="Микроэлементы">
    <button type="submit">Добавить</button>
</form>
<table border="1" cellpadding="8" style="border-collapse: collapse; width: 100%;">
    <tr><th>Название</th><th>Ккал/100г</th><th>Микроэлементы</th><th>Действия</th></tr>
    {rows}
</table>
</div>
'''

PRODUCT_ROW_TEMPLATE = '''
<tr id="edit-product-row-{id}">
    <td>{name}</td>
    <td>{calories_per_100g}</td>
    <td>{micro_description}</td>
    <td>
        <button hx-get="/section/nutrition/products/edit/{id}" hx-target="#edit-product-row-{id}" hx-swap="outerHTML">✏️</button>
        <button hx-delete="/section/nutrition/products/delete/{id}" hx-target="#product-list" hx-swap="outerHTML">🗑️</button>
    </td>
</tr>
'''

PRODUCT_EDIT_TEMPLATE = '''
<tr id="edit-product-row-{id}">
    <td colspan="4">
        <form hx-post="/section/nutrition/products/edit/{id}" hx-target="#product-list" hx-swap="outerHTML">
            <input type="text" name="name" value="{name}" required>
            <input type="number" step="0.01" name="calories_per_100g" value="{calories_per_100g}" required>
            <input type="text" name="micro_description" value="{micro_description}">
            <button type="submit">Сохранить</button>
            <button type="button" onclick="window.location.reload()">Отмена</button>
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

# --- Блюда ---
DISH_LIST_TEMPLATE = '''
<div id="dish-list">
<h2>Блюда</h2>
<form hx-post="/section/nutrition/dishes/add" hx-target="#dish-list" hx-swap="outerHTML" style="margin-bottom: 16px;">
    <input type="text" name="name" placeholder="Название" required>
    <input type="text" name="description" placeholder="Описание">
    <button type="submit">Добавить</button>
</form>
<table border="1" cellpadding="8" style="border-collapse: collapse; width: 100%;">
    <tr><th>Название</th><th>Описание</th><th>Действия</th></tr>
    {rows}
</table>
</div>
'''

DISH_ROW_TEMPLATE = '''
<tr id="edit-dish-row-{id}">
    <td>{name}</td>
    <td>{description}</td>
    <td>
        <button hx-get="/section/nutrition/dishes/edit/{id}" hx-target="#edit-dish-row-{id}" hx-swap="outerHTML">✏️</button>
        <button hx-get="/section/nutrition/dishes/ingredients/{id}" hx-target="#ingredients-row-{id}" hx-swap="outerHTML">Ингредиенты</button>
        <button hx-delete="/section/nutrition/dishes/delete/{id}" hx-target="#dish-list" hx-swap="outerHTML">🗑️</button>
    </td>
</tr>
<tr id="ingredients-row-{id}"></tr>
'''

# Шаблон для ингредиентов блюда
DISH_INGREDIENTS_TEMPLATE = '''
<td colspan="3">
    <div style="background:#f9f9f9; padding:12px; border-radius:8px;">
        <b>Ингредиенты:</b>
        <form hx-post="/section/nutrition/dishes/ingredients/add/{dish_id}" hx-target="#ingredients-row-{dish_id}" hx-swap="outerHTML" style="margin-bottom:8px; display:flex; gap:8px; align-items:center;">
            <select name="product_id" required>
                <option value="">Продукт...</option>
                {product_options}
            </select>
            <input type="number" step="0.01" name="grams" placeholder="Граммы" required style="width:90px;">
            <button type="submit">Добавить</button>
        </form>
        <table border="1" cellpadding="6" style="border-collapse:collapse; width:100%;">
            <tr><th>Продукт</th><th>Граммы</th><th></th></tr>
            {rows}
        </table>
    </div>
</td>
'''

DISH_INGREDIENT_ROW_TEMPLATE = '''
<tr>
    <td>{product_name}</td>
    <td>{grams}</td>
    <td><button hx-delete="/section/nutrition/dishes/ingredients/delete/{ingredient_id}" hx-target="#ingredients-row-{dish_id}" hx-swap="outerHTML">🗑️</button></td>
</tr>
'''

def get_product_options(selected=None):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name FROM product ORDER BY name;")
    options = ""
    for row in cur.fetchall():
        sel = " selected" if selected and row[0] == selected else ""
        options += f'<option value="{row[0]}"{sel}>{row[1]}</option>'
    cur.close()
    conn.close()
    return options

def render_dish_ingredients(dish_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        SELECT di.id, di.grams, p.name
        FROM dish_ingredient di JOIN product p ON di.product_id = p.id
        WHERE di.dish_id = %s
        ORDER BY p.name;
    ''', (dish_id,))
    rows = "".join(
        DISH_INGREDIENT_ROW_TEMPLATE.format(
            ingredient_id=row[0], grams=row[1], product_name=row[2], dish_id=dish_id
        ) for row in cur.fetchall()
    )
    cur.close()
    conn.close()
    inner = DISH_INGREDIENTS_TEMPLATE.format(
        dish_id=dish_id,
        product_options=get_product_options(),
        rows=rows
    )
    return f'<tr id="ingredients-row-{dish_id}">{inner}</tr>'

@app.get("/section/nutrition/dishes/ingredients/{dish_id}", response_class=HTMLResponse)
async def dish_ingredients(dish_id: str):
    return HTMLResponse(render_dish_ingredients(dish_id))

@app.post("/section/nutrition/dishes/ingredients/add/{dish_id}", response_class=HTMLResponse)
async def add_dish_ingredient(dish_id: str, product_id: str = Form(...), grams: float = Form(...)):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO dish_ingredient (id, dish_id, product_id, grams) VALUES (%s, %s, %s, %s);", (str(uuid.uuid4()), dish_id, product_id, grams))
    conn.commit()
    cur.close()
    conn.close()
    return render_dish_ingredients(dish_id)

@app.delete("/section/nutrition/dishes/ingredients/delete/{ingredient_id}", response_class=HTMLResponse)
async def delete_dish_ingredient(ingredient_id: str):
    # Получаем dish_id для рендера
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT dish_id FROM dish_ingredient WHERE id = %s;", (ingredient_id,))
    row = cur.fetchone()
    dish_id = row[0] if row else None
    if dish_id:
        cur.execute("DELETE FROM dish_ingredient WHERE id = %s;", (ingredient_id,))
        conn.commit()
    cur.close()
    conn.close()
    if dish_id:
        return render_dish_ingredients(dish_id)
    return HTMLResponse("")

DISH_EDIT_TEMPLATE = '''
<tr id="edit-dish-row-{id}">
    <td colspan="3">
        <form hx-post="/section/nutrition/dishes/edit/{id}" hx-target="#dish-list" hx-swap="outerHTML">
            <input type="text" name="name" value="{name}" required>
            <input type="text" name="description" value="{description}">
            <button type="submit">Сохранить</button>
            <button type="button" onclick="window.location.reload()">Отмена</button>
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
<h2>Вес</h2>
<form hx-post="/section/nutrition/weight/add" hx-target="#weight-list" hx-swap="outerHTML" style="margin-bottom: 16px; display: flex; gap: 8px; align-items: center;">
    <input type="date" name="date" value="{today}" required>
    <input type="number" step="0.01" name="weight" placeholder="Вес (кг)" required style="width:90px;">
    <button type="submit">Добавить</button>
</form>
<table border="1" cellpadding="8" style="border-collapse: collapse; width: 100%;">
    <tr><th>Дата</th><th>Вес (кг)</th><th>Действия</th></tr>
    {rows}
</table>
</div>
'''

WEIGHT_ROW_TEMPLATE = '''
<tr id="edit-weight-row-{id}">
    <td>{date}</td>
    <td>{weight}</td>
    <td>
        <button hx-get="/section/nutrition/weight/edit/{id}" hx-target="#edit-weight-row-{id}" hx-swap="outerHTML">✏️</button>
        <button hx-delete="/section/nutrition/weight/delete/{id}" hx-target="#weight-list" hx-swap="outerHTML">🗑️</button>
    </td>
</tr>
'''

WEIGHT_EDIT_TEMPLATE = '''
<tr id="edit-weight-row-{id}">
    <td colspan="3">
        <form hx-post="/section/nutrition/weight/edit/{id}" hx-target="#weight-list" hx-swap="outerHTML">
            <input type="date" name="date" value="{date}" required>
            <input type="number" step="0.01" name="weight" value="{weight}" required style="width:90px;">
            <button type="submit">Сохранить</button>
            <button type="button" onclick="window.location.reload()">Отмена</button>
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

SETTINGS_TEMPLATE = '''
<div style="max-width:400px;margin:0 auto;">
    <form hx-post="/section/settings/calories-goal" hx-target="#settings-goal-form" hx-swap="outerHTML" id="settings-goal-form" style="display:flex;gap:8px;align-items:center;">
        <label>Целевые калории в день:
            <input type="number" name="target_calories" value="{target_calories}" min="0" required style="width:120px;">
        </label>
        <button type="submit">Сохранить</button>
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

@app.get("/section/sport", response_class=HTMLResponse)
async def section_settings():
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
    return SETTINGS_TEMPLATE.format(target_calories=target_calories) 
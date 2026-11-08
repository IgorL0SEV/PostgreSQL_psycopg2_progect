# Справочник: PostgreSQL и psycopg2

Справочник проекта VPc06: термины, синтаксис, отличия от SQLite, частые ошибки.

---

## 1. PostgreSQL vs SQLite

| | SQLite | PostgreSQL |
|---|---|---|
| Что это | библиотека + файл `.db` на диске | **сервер**, к которому подключаются по сети |
| Запуск | файла достаточно | нужна служба (`postgresql-x64-18`) и порт 5432 |
| Доступ | кто открыл файл, тот и хозяин | логин + пароль, роли, права на схему |
| Типы | динамическая типизация | строгие типы: `INT`, `TEXT`, `NUMERIC(10,2)` |
| Нагрузка | одна запись за раз | параллельные подключения, большие объёмы |
| Кому | прототип, локальный скрипт, бот на диске | боевое приложение, несколько клиентов |

Практический вывод: SQLite — «база в файле», PostgreSQL — «база как сервис».
Локальное и удалённое подключение отличается **одной строкой** `host`.

---

## 2. Термины

- **Кластер** — экземпляр сервера PostgreSQL, обслуживающий набор баз.
- **База данных (database)** — изолированный набор схем. В курсе: `test`.
- **Схема (schema)** — пространство имён внутри базы. По умолчанию `public`.
- **Роль / пользователь (role / user)** — учётка для входа. Суперпользователь
  `postgres` есть после установки; для проекта лучше отдельная роль — принцип
  наименьших прав.
- **Порт** — 5432 по умолчанию. `localhost:5432` = «сервер на этой же машине».
- **DSN / строка подключения** — параметры соединения: `host`, `port`, `dbname`,
  `user`, `password`.

---

## 3. Установка и проверка (Windows)

```powershell
# служба запущена?
Get-Service -Name '*postgres*'

# порт слушает?
Test-NetConnection localhost -Port 5432

# клиент командной строки (идёт вместе с сервером)
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -h localhost -d postgres
```

Аутентификация обычно `scram-sha-256`, то есть **пароль обязателен**.
Он задаётся при установке и больше нигде не хранится — только у человека.

---

## 4. Подключение из Python

```python
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()   # читает .env в переменные окружения

conn = psycopg2.connect(
    host=os.getenv("DB_HOST"),
    port=os.getenv("DB_PORT"),
    dbname=os.getenv("DB_NAME"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
)
```

Зависимости (`requirements.txt`):

```text
psycopg2-binary
python-dotenv
```

`psycopg2-binary` — та же библиотека, но с уже собранным драйвером: не нужен
компилятор C на машине. Для учебных и большинства рабочих задач этого достаточно.

### Что НЕ надо делать

- **Не читать `.env` вручную** через `open()` и `split("=")` — модуль
  `python-dotenv` делает это корректно: кавычки, комментарии, пробелы, `export`.
- **Не держать пароль в коде** — он попадёт в git и останется в истории навсегда.
- **Не коммитить `.env`** — в `.gitignore` он должен быть с первого коммита.

---

## 5. Параметризованные запросы

```python
cur.execute("INSERT INTO users (name, age) VALUES (%s, %s)", ("Алиса", 28))
```

Правильно: `%s` — драйвер сам экранирует значение и подставит его как данные.

```python
# ТАК НЕЛЬЗЯ — SQL-инъекция
cur.execute(f"INSERT INTO users (name) VALUES ('{name}')")
```

Важное для PostgreSQL: плейсхолдер — **всегда `%s`**, независимо от типа.
Не `?` (это SQLite) и не `%d`.

Идентификатор (имя таблицы, базы) через `%s` подставить нельзя — для него есть
`psycopg2.sql`:

```python
from psycopg2 import sql
cur.execute(sql.SQL("CREATE DATABASE {};").format(sql.Identifier("test")))
```

Причина: `%s` подставляет литерал, поэтому `SELECT COUNT(*) FROM %s` с параметром
`"users"` даёт `FROM 'users'` и ошибку `42601` — после `FROM` ожидается идентификатор.

Правило выбора:

| Что подставляется | Чем |
|---|---|
| значение (строка, число, дата) | `%s` + кортеж параметров |
| идентификатор (таблица, колонка, база) | `sql.Identifier` |
| структура запроса (ключевые слова) | `sql.SQL` |
| внешние данные в f-строке | не подставляются |

Если имя таблицы берётся из ограниченного набора, допустим белый список: `count_rows()`
в проекте пропускает только `users` и `orders` и поэтому использует f-строку
(с `# noqa: S608`).

---

## 6. Транзакции

```python
with conn:              # commit при успехе, rollback при исключении
    with conn.cursor() as cur:
        cur.execute("INSERT INTO users (name, age) VALUES (%s, %s)", ("Борис", 35))
```

- `with conn:` — транзакция. Всё внутри либо применяется целиком, либо не
  применяется вовсе.
- `with conn.cursor() as cur:` — курсор закрывается автоматически.
- По умолчанию psycopg2 открывает транзакцию при первом запросе и **не**
  коммитит сама. Забыли `commit`/`with conn:` — данные не сохранятся.
- `with conn:` управляет транзакцией, но **не закрывает** соединение. Закрытие —
  отдельная ответственность: в проекте её выполняет `PostgresDriver.__enter__`/`__exit__`
  (`with driver:`). Два менеджера решают разные задачи: `with driver:` — канал до сервера,
  `with conn:` — применятся ли изменения.

---

## 7. Обработка ошибок и закрытие соединения

```python
try:
    with PostgresDriver.from_env() as driver:
        driver.create_tables()
except psycopg2.Error as exc:
    print(f"Ошибка PostgreSQL: {exc}")
finally:
    # при использовании with-менеджера закрытие уже произошло;
    # в «ручном» варианте: if conn: conn.close()
    ...
```

Полезные поля и коды:

| Что | Значение |
|---|---|
| `psycopg2.Error.pgcode` | SQLSTATE, например `28P01` — неверный пароль |
| `28P01` | `INVALID_PASSWORD` |
| `3D000` | `INVALID_CATALOG_NAME` — базы нет |
| `42P01` | `UNDEFINED_TABLE` — таблицы нет |
| `42501` | `INSUFFICIENT_PRIVILEGE` — нет прав на схему |
| `42601` | `SYNTAX_ERROR` — например, имя таблицы передали через `%s` |
| `None` | ошибка на уровне соединения (сервер не отвечает) |

Соединение закрывать **в `finally`** (или через контекстный менеджер): иначе при
исключении в пул сервера останется висеть подключение.

---

## 8. Схема задания: пользователи и заказы

```sql
CREATE TABLE IF NOT EXISTS users (
    id   SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    age  INT  CHECK (age >= 0)
);

CREATE TABLE IF NOT EXISTS orders (
    id         SERIAL PRIMARY KEY,
    user_id    INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    amount     NUMERIC(10,2) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);
```

- `SERIAL` — автоинкрементный целочисленный ключ (в новой терминологии —
  `GENERATED BY DEFAULT AS IDENTITY`).
- `REFERENCES users(id)` — внешний ключ: заказ не может ссылаться на
  несуществующего пользователя.
- `ON DELETE CASCADE` — удалили пользователя, его заказы удалились сами.
  Без этого PostgreSQL запретит удаление (`violates foreign key constraint`).
- `NUMERIC(10,2)` для денег: точно, без ошибок округления, в отличие от `FLOAT`.

---

## 9. Агрегация: LEFT JOIN + SUM

```sql
SELECT u.id,
       u.name,
       COALESCE(SUM(o.amount), 0) AS total_amount
FROM users u
LEFT JOIN orders o ON o.user_id = u.id
GROUP BY u.id, u.name
ORDER BY total_amount DESC, u.name ASC;
```

- `LEFT JOIN` — все пользователи, даже те, у кого заказов нет.
  `INNER JOIN` таких бы отбросил.
- `COALESCE(SUM(...), 0)` — у пользователя без заказов `SUM` вернёт `NULL`;
  `COALESCE` заменяет его нулём.
- `GROUP BY u.id, u.name` — группировка по пользователю. PostgreSQL требует,
  чтобы все неагрегированные поля в `SELECT` были в `GROUP BY`.
- `ORDER BY total_amount DESC` — по убыванию суммы, как в задании.

---

## 10. Частые ошибки

| Симптом | Причина | Что делать |
|---|---|---|
| `connection refused` / `could not connect` | служба PostgreSQL не запущена | `Get-Service *postgres*`, запустить службу |
| `password authentication failed` | неверный пароль в `.env` | исправить `DB_PASSWORD` |
| `database "test" does not exist` | база не создана | `CREATE DATABASE test;` или `python ensure_database.py` |
| `relation "users" does not exist` | не выполнены `CREATE TABLE` | запустить `create_tables()` |
| `permission denied for schema public` | у роли нет прав на `public` | выдать права роли на схему `public` |
| `syntax error at or near "?"` | плейсхолдер от SQLite | заменить `?` на `%s` |
| `violates foreign key constraint` | удаление пользователя с заказами | добавить `ON DELETE CASCADE` или сначала удалить заказы |
| данные «не сохранились» | нет `commit` | использовать `with conn:` |
| `KeyError`/`None` в параметрах подключения | `.env` не найден или пуст | `load_dotenv()`, проверить `.env` рядом со скриптом |
| `ModuleNotFoundError: psycopg2` | зависимости не установлены / не активирован venv | `pip install -r requirements.txt` |
| `UnicodeDecodeError: 'utf-8' codec can't decode byte 0xc2` | `lc_messages = 'Russian_Russia.1251'`: сервер шлёт текст ошибки в cp1251, psycopg2 ждёт UTF-8 | достать байты из `exc.object` и декодировать в cp1251 (см. ниже) |

---

## 11. Ловушка Windows: cp1251 в сообщениях сервера

Если `postgresql.conf` содержит `lc_messages = 'Russian_Russia.1251'` (обычный выбор
при русской установке), сервер отдаёт текст ошибки в cp1251. psycopg2 декодирует его
как UTF-8 и падает с `UnicodeDecodeError` **раньше**, чем покажет причину — вместо
«неверный пароль» видно только кракозябры или трейсбек.

Исходные байты при этом никуда не деваются — они лежат в атрибуте `exc.object`:

```python
try:
    conn = psycopg2.connect(**params)
except UnicodeDecodeError as exc:
    print(exc.object.decode("cp1251"))   # настоящий текст ошибки
```

Альтернатива на уровне сервера — `lc_messages = 'C'` в `postgresql.conf`
(нужны права администратора и перезапуск службы). Тогда сообщения будут
на английском, но читаемыми без обходов.

---

## 12. Чек-лист перед сдачей

- [ ] `python main.py` запускается без правок в коде
- [ ] `.env` не в git, `.env.example` — в git и без реального пароля
- [ ] выводятся пользователи и суммы заказов
- [ ] суммы считаются через `LEFT JOIN + COALESCE(SUM(...))`, сортировка по убыванию
- [ ] есть пользователь без заказов — и он виден в отчёте с нулём
- [ ] исключения `psycopg2.Error` обработаны, соединение закрывается
- [ ] второй запуск не дублирует данные
- [ ] `README.md` объясняет, как развернуть и запустить

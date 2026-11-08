# VPc06 проект — PostgreSQL и psycopg2

**Модуль:** 4. Базы данных · **СУБД:** PostgreSQL 18 · **Клиент:** DBeaver / psql

**Статус:** ✅ выполнено (оба трека прогнаны на живой базе). План и точка фиксации — в [PLAN.md](PLAN.md).

## Что осваиваем

- чем PostgreSQL отличается от SQLite (сервер vs файл);
- установка и подключение к серверу, роль и доступы;
- подключение PostgreSQL из Python через `psycopg2` и `python-dotenv`;
- параметризованные запросы (`%s`) и транзакции (`with conn:`);
- CRUD-драйвер и обработка ошибок `psycopg2.Error`.

## Материалы

| Файл | Что внутри |
|---|---|
| [CONSPECT.md](CONSPECT.md) | Конспект проекта: теория, разбор задания и нашего кода, самопроверка |
| [PLAN.md](PLAN.md) | План по шагам, статус, результат проверки |
| [project/](project/) | Код: `main.py`, `postgres_driver.py`, `ensure_database.py`, README |
| [reference/postgresql-psycopg2.md](reference/postgresql-psycopg2.md) | Справочник: термины, синтаксис, SQLite vs PostgreSQL, частые ошибки |

## Проект

```text
project/
├── main.py              # точка входа: оба трека задания
├── postgres_driver.py   # CRUD-драйвер (create_tables, add_user, add_order, get_user_totals)
├── ensure_database.py   # создаёт базу test, если её нет (замена pgAdmin)
├── requirements.txt     # psycopg2-binary, python-dotenv
├── .env.example         # шаблон переменных окружения (без секретов)
├── README.md            # как запустить и что проверяет зачёт
└── .gitignore           # .env, venv, __pycache__ — не в git
```

## Быстрый старт

```powershell
cd project
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env                  # вписать пароль пользователя postgres
python ensure_database.py     # создать базу test
python main.py                # таблицы, данные, отчёт
```

В VS Code: открыть папку `project`, `Ctrl+Shift+P` → *Python: Select Interpreter* →
`.\venv\Scripts\python.exe`.

## Что получилось

```text
=== Суммы заказов по пользователям (LEFT JOIN + SUM) ===
  Алиса —   1570.50
  Борис —    780.00
  Вера  —      0.00
```

Пользователь без заказов (`Вера`) виден благодаря `LEFT JOIN`, сумма у неё `0.00`
за счёт `COALESCE`. Повторный запуск не дублирует данные.

## Заметки

- На машине, где велась работа, PostgreSQL 18 установлен локально, служба `postgresql-x64-18`
  запущена, порт 5432 слушает. Аутентификация — `scram-sha-256`, поэтому нужен пароль.
- pgAdmin не установлен — используем DBeaver.
- Сообщения сервера приходят в cp1251 (`lc_messages = 'Russian_Russia.1251'`), из-за чего
  psycopg2 падает с `UnicodeDecodeError` раньше, чем показывает причину. В проекте это
  обходит `readable_server_error()` в `postgres_driver.py`; подробности — в `PLAN.md`.

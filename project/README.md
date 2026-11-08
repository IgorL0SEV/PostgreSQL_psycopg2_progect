# VPc06 — проект: PostgreSQL + psycopg2

VPc06 проект: домашнее задание. Реализованы оба трека: базовый (чтение из `users`)
и средний (связи `users` ↔ `orders`, параметризованные вставки, `LEFT JOIN + SUM`).

## Состав

| Файл | Что делает |
|---|---|
| `main.py` | Точка входа: подключение, создание таблиц, наполнение, отчёты, проверка каскада |
| `postgres_driver.py` | CRUD-драйвер: `create_tables`, `add_user`, `add_order`, `get_user_totals` |
| `ensure_database.py` | Создаёт базу `test`, если её ещё нет (замена ручному шагу в pgAdmin) |
| `requirements.txt` | `psycopg2-binary`, `python-dotenv` |
| `.env.example` | Шаблон переменных окружения (без секретов) |

## Запуск

```powershell
# 1. Окружение
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2. Настройки: скопировать шаблон и вписать свой пароль пользователя postgres
Copy-Item .env.example .env
notepad .env

# 3. Первый запуск — создать базу (в курсе это шаг в pgAdmin)
python ensure_database.py

# 4. Основной скрипт
python main.py
```

Повторный запуск безопасен: таблицы создаются через `IF NOT EXISTS`, данные
добавляются только если таблицы пусты.

## Запуск на другой машине (другой пароль)

Пароль PostgreSQL у каждой установки свой и в git не хранится — это нормально.
Порядок на любой машине одинаковый:

```powershell
# 1. Свежий код из репозитория
git clone https://github.com/IgorL0SEV/PostgreSQL_psycopg2_progect.git
cd PostgreSQL_psycopg2_progect\project
# если папка уже есть: cd PostgreSQL_psycopg2_progect && git pull origin main

# 2. Проверить, что сервер этой машины работает
Get-Service -Name '*postgres*'
Test-NetConnection localhost -Port 5432

# 3. Окружение (venv в git не хранится — создаётся заново, ~10 секунд)
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 4. Свой .env для этой машины
Copy-Item .env.example .env
notepad .env                     # DB_PASSWORD = пароль ЭТОЙ установки

# 5. База и прогон
python ensure_database.py
python main.py
```

Если PostgreSQL на машине ещё не установлен — поставить с postgresql.org (порт 5432,
пароль суперпользователя `postgres` запомнить). В облачном варианте (например, Aiven)
меняются только `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` — код не трогаем.

### Как проверить, что результат тот же

Ожидаемый вывод на машине с чистой базой `test`:

```text
=== Суммы заказов по пользователям (LEFT JOIN + SUM) ===
  Алиса —   1570.50
  Борис —    780.00
  Вера  —      0.00
```

Контрольный прогон:

```powershell
python main.py        # первый запуск: создаёт и наполняет
python main.py        # второй запуск: «вставку пропускаю», суммы те же
```

Если после второго запуска суммы те же, а в базе `users: 3`, `orders: 3` — результат
воспроизведён.

### Если таблица `users` уже существует с другой структурой

Симптом: `no results to fetch`, ошибка внешнего ключа или пустой отчёт. Причина — таблицу
`users` когда-то создали вручную в pgAdmin, и `IF NOT EXISTS` её не пересоздаст.
Чистое состояние:

```sql
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS users;
```

Выполнить в DBeaver/psql, затем снова `python main.py`. Скрипт создаст обе таблицы
по схеме задания и наполнит их.

## Переменные окружения

| Переменная | Значение по умолчанию | Комментарий |
|---|---|---|
| `DB_HOST` | `localhost` | адрес сервера |
| `DB_PORT` | `5432` | стандартный порт PostgreSQL |
| `DB_NAME` | `test` | база из задания |
| `DB_USER` | `postgres` | пользователь |
| `DB_PASSWORD` | — | **вписывается вручную**, в git не попадает |

## Что проверяет зачёт

- таблицы `users` и `orders` созданы, `orders.user_id` ссылается на `users.id`
  с `ON DELETE CASCADE`;
- минимум 3 пользователя и 2 заказа у разных пользователей;
- суммы считаются `LEFT JOIN + COALESCE(SUM(...))`, сортировка по убыванию;
- исключения `psycopg2.Error` обработаны, соединение закрывается всегда.

## Ожидаемый вывод

```text
Подключение к PostgreSQL установлено.
Таблицы users и orders готовы.

Наполнение данными:
  + пользователь Алиса (id=1, age=28)
  ...

=== Пользователи (users) ===
  id=1   Алиса    возраст: 28
  ...

=== Суммы заказов по пользователям (LEFT JOIN + SUM) ===
  Алиса  —   1570.50
  Борис  —    780.00
  Вера   —      0.00
```

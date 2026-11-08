"""VPc06 — домашнее задание: базовый + средний трек.

Что делает скрипт:
1. Подключается к PostgreSQL через psycopg2, параметры — из .env (python-dotenv).
2. Создаёт таблицы users и orders (средний трек).
3. Наполняет их через параметризованные запросы, если база ещё пустая.
4. Печатает всех пользователей (базовый трек) и суммы заказов по каждому
   пользователю через LEFT JOIN + COALESCE(SUM(...)) (средний трек).
5. Показывает работу ON DELETE CASCADE — на временном пользователе,
   изменения откатываются, реальные данные не трогаются.
6. Обрабатывает ошибки psycopg2 и закрывает соединение в finally.

Запуск:
    python main.py
"""

from __future__ import annotations

import sys

import psycopg2
from psycopg2 import errorcodes

from postgres_driver import PostgresDriver, readable_server_error

# Данные для первого запуска. Повторный запуск ничего не дублирует:
# наполнение выполняется только если таблицы пусты.
SEED_USERS: list[tuple[str, int]] = [
    ("Алиса", 28),
    ("Борис", 35),
    ("Вера", 22),
]

# (имя пользователя, сумма заказа) — заказы у разных пользователей.
SEED_ORDERS: list[tuple[str, float]] = [
    ("Алиса", 1250.00),
    ("Алиса", 320.50),
    ("Борис", 780.00),
]


def seed_if_empty(driver: PostgresDriver) -> None:
    """Наполняет таблицы, только если они пустые, — запуск идемпотентен."""
    if driver.count_rows("users") == 0:
        ids: dict[str, int] = {}
        for name, age in SEED_USERS:
            ids[name] = driver.add_user(name, age)
            print(f"  + пользователь {name} (id={ids[name]}, age={age})")
    else:
        print("  users уже заполнены — вставку пропускаю")
        ids = {name: user_id for user_id, name, _ in driver.get_users()}

    if driver.count_rows("orders") == 0:
        for name, amount in SEED_ORDERS:
            order_id = driver.add_order(ids[name], amount)
            print(f"  + заказ id={order_id}: {name} — {amount:.2f}")
    else:
        print("  orders уже заполнены — вставку пропускаю")


def print_users(driver: PostgresDriver) -> None:
    """Базовый трек: SELECT * FROM users."""
    print("\n=== Пользователи (users) ===")
    for user_id, name, age in driver.get_users():
        print(f"  id={user_id:<3} {name:<8} возраст: {age}")


def print_totals(driver: PostgresDriver) -> None:
    """Средний трек: сумма заказов по каждому пользователю, по убыванию."""
    print("\n=== Суммы заказов по пользователям (LEFT JOIN + SUM) ===")
    totals = driver.get_user_totals()
    if not totals:
        print("  (пользователей нет)")
        return
    width = max(len(name) for _, name, _ in totals)
    for _, name, total in totals:
        print(f"  {name:<{width}} — {total:>9.2f}")


def demonstrate_cascade(driver: PostgresDriver) -> None:
    """Проверка ON DELETE CASCADE без порчи данных: всё откатывается.

    Внутри одной транзакции создаём пользователя с заказом, удаляем его
    и смотрим, сколько заказов осталось. Затем явный откат.
    """
    print("\n=== Проверка ON DELETE CASCADE (изменения откатываются) ===")
    conn = driver._connection()  # noqa: SLF001 — учебный пример, доступ к соединению нужен намеренно
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO users (name, age) VALUES (%s, %s) RETURNING id;",
                    ("Временный", 99),
                )
                temp_id = cur.fetchone()[0]
                cur.execute(
                    "INSERT INTO orders (user_id, amount) VALUES (%s, %s);",
                    (temp_id, 10.00),
                )
                cur.execute(
                    "SELECT COUNT(*) FROM orders WHERE user_id = %s;", (temp_id,)
                )
                before = cur.fetchone()[0]

                cur.execute("DELETE FROM users WHERE id = %s;", (temp_id,))
                cur.execute(
                    "SELECT COUNT(*) FROM orders WHERE user_id = %s;", (temp_id,)
                )
                after = cur.fetchone()[0]

            print(f"  заказов у временного пользователя до удаления: {before}")
            print(f"  после удаления пользователя:                  {after}")
            print("  => каскад работает" if after == 0 else "  => каскад НЕ сработал")

            raise _Rollback  # выходим из with conn с исключением → откат
    except _Rollback:
        print("  транзакция откачена: временные данные не сохранены")


class _Rollback(Exception):
    """Служебное исключение, чтобы `with conn:` откатил транзакцию."""


def main() -> int:
    try:
        driver = PostgresDriver.from_env()
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 1

    try:
        with driver:  # connect() на входе, close() на выходе
            print("Подключение к PostgreSQL установлено.")
            driver.create_tables()
            print("Таблицы users и orders готовы.")

            print("\nНаполнение данными:")
            seed_if_empty(driver)

            print_users(driver)
            print_totals(driver)
            demonstrate_cascade(driver)

        print("\nСоединение закрыто.")
        return 0

    except UnicodeDecodeError as exc:
        # Сервер прислал сообщение в cp1251 (lc_messages=Russian_Russia.1251),
        # psycopg2 не смог его прочитать — достаём текст сами.
        message = readable_server_error(exc)
        print(f"\nОшибка PostgreSQL: {message}", file=sys.stderr)
        if "парол" in message.lower() or "password" in message.lower():
            print("Подсказка: проверьте DB_PASSWORD в .env.", file=sys.stderr)
        return 1

    except psycopg2.Error as exc:
        # Разбираем частые случаи, чтобы сообщение было понятнее человеку.
        hint = _hint_for(exc)
        print(f"\nОшибка PostgreSQL: {exc}", file=sys.stderr)
        if hint:
            print(f"Подсказка: {hint}", file=sys.stderr)
        return 1


def _hint_for(exc: psycopg2.Error) -> str | None:
    code = exc.pgcode
    if code == errorcodes.INVALID_PASSWORD:
        return "Проверьте DB_PASSWORD в .env — пароль пользователя postgres."
    if code == errorcodes.INVALID_CATALOG_NAME:
        return (
            "Базы DB_NAME (test) нет. Создайте её: python ensure_database.py"
        )
    if code == errorcodes.CONNECTION_FAILURE or code is None:
        return "Проверьте, что служба PostgreSQL запущена и порт 5432 открыт."
    return None


if __name__ == "__main__":
    raise SystemExit(main())

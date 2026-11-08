"""Драйвер PostgreSQL для урока VPc06.

Собирает всё общение с базой в один класс: подключение, создание таблиц,
вставка пользователей и заказов, агрегирующий отчёт.

Параметры подключения берутся из окружения (файл .env, см. .env.example).
"""

from __future__ import annotations

import os
from decimal import Decimal

import psycopg2
from dotenv import load_dotenv

# Схемы таблиц — из задания урока.
# IF NOT EXISTS делает create_tables() безопасным при повторном запуске.
CREATE_USERS_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id   SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    age  INT  CHECK (age >= 0)
);
"""

CREATE_ORDERS_SQL = """
CREATE TABLE IF NOT EXISTS orders (
    id         SERIAL PRIMARY KEY,
    user_id    INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    amount     NUMERIC(10,2) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);
"""

# Агрегат из задания: LEFT JOIN оставляет пользователей без заказов,
# COALESCE превращает NULL в 0, сортировка — по сумме по убыванию.
TOTALS_SQL = """
SELECT u.id,
       u.name,
       COALESCE(SUM(o.amount), 0) AS total_amount
FROM users u
LEFT JOIN orders o ON o.user_id = u.id
GROUP BY u.id, u.name
ORDER BY total_amount DESC, u.name ASC;
"""


def readable_server_error(exc: UnicodeDecodeError) -> str:
    """Достаёт текст ошибки сервера, который psycopg2 не смог раскодировать.

    Причина: на Windows PostgreSQL часто ставится с
    `lc_messages = 'Russian_Russia.1251'`. Сообщение об ошибке приходит
    в cp1251, а psycopg2 декодирует его как UTF-8 и падает с
    UnicodeDecodeError ещё до того, как покажет настоящую причину.
    Исходные байты остаются в атрибуте `object` — декодируем их сами.
    """
    raw = bytes(exc.object or b"")
    for encoding in ("cp1251", "utf-8"):
        try:
            return raw.decode(encoding).strip()
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace").strip()


class PostgresDriver:
    """Тонкая обёртка над psycopg2 с CRUD-методами из задания."""

    def __init__(
        self,
        host: str,
        port: int,
        dbname: str,
        user: str,
        password: str,
    ) -> None:
        self._params = {
            "host": host,
            "port": port,
            "dbname": dbname,
            "user": user,
            "password": password,
        }
        self._conn: psycopg2.extensions.connection | None = None

    # --- подключение -------------------------------------------------

    @classmethod
    def from_env(cls) -> "PostgresDriver":
        """Собирает драйвер из переменных окружения (.env)."""
        load_dotenv()
        missing = [
            var
            for var in ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD")
            if not os.getenv(var)
        ]
        if missing:
            raise RuntimeError(
                "Не заданы переменные окружения: "
                + ", ".join(missing)
                + ". Скопируйте .env.example в .env и заполните значения."
            )
        return cls(
            host=os.environ["DB_HOST"],
            port=int(os.environ["DB_PORT"]),
            dbname=os.environ["DB_NAME"],
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
        )

    def connect(self) -> "PostgresDriver":
        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(**self._params)
        return self

    def close(self) -> None:
        if self._conn is not None and not self._conn.closed:
            self._conn.close()

    def __enter__(self) -> "PostgresDriver":
        return self.connect()

    def __exit__(self, exc_type, exc, tb) -> None:
        # Соединение закрывается всегда — даже если внутри было исключение.
        self.close()

    def _connection(self) -> psycopg2.extensions.connection:
        if self._conn is None or self._conn.closed:
            raise RuntimeError("Соединение не открыто: вызовите connect()")
        return self._conn

    # --- DDL ---------------------------------------------------------

    def create_tables(self) -> None:
        """Создаёт users и orders, если их ещё нет."""
        conn = self._connection()
        with conn, conn.cursor() as cur:
            cur.execute(CREATE_USERS_SQL)
            cur.execute(CREATE_ORDERS_SQL)

    # --- CRUD --------------------------------------------------------

    def add_user(self, name: str, age: int) -> int:
        """Вставляет пользователя параметризованным запросом, возвращает id."""
        conn = self._connection()
        with conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (name, age) VALUES (%s, %s) RETURNING id;",
                (name, age),
            )
            return cur.fetchone()[0]

    def add_order(self, user_id: int, amount: Decimal | float | int) -> int:
        """Вставляет заказ; amount приводится к Decimal, чтобы не терять копейки."""
        conn = self._connection()
        with conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO orders (user_id, amount) VALUES (%s, %s) RETURNING id;",
                (user_id, Decimal(str(amount))),
            )
            return cur.fetchone()[0]

    def delete_user(self, user_id: int) -> int:
        """Удаляет пользователя, возвращает число удалённых строк.

        Заказы уходят вместе с ним за счёт ON DELETE CASCADE.
        """
        conn = self._connection()
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM users WHERE id = %s;", (user_id,))
            return cur.rowcount

    # --- чтение ------------------------------------------------------

    def get_users(self) -> list[tuple[int, str, int]]:
        conn = self._connection()
        with conn.cursor() as cur:
            cur.execute("SELECT id, name, age FROM users ORDER BY id;")
            return cur.fetchall()

    def count_rows(self, table: str) -> int:
        """Считает строки в таблице. Имя таблицы — только из белого списка."""
        if table not in {"users", "orders"}:
            raise ValueError(f"Неизвестная таблица: {table}")
        conn = self._connection()
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {table};")  # noqa: S608 — белый список выше
            return cur.fetchone()[0]

    def get_user_totals(self) -> list[tuple[int, str, Decimal]]:
        conn = self._connection()
        with conn.cursor() as cur:
            cur.execute(TOTALS_SQL)
            return cur.fetchall()

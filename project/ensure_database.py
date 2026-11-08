"""Создаёт базу DB_NAME (по умолчанию test), если её ещё нет.

В курсе это делают мышкой в pgAdmin. Скрипт нужен, чтобы ту же операцию
можно было повторить на любой машине одной командой:

    python ensure_database.py

Скрипт подключается к служебной базе postgres, потому что CREATE DATABASE
нельзя выполнить из подключения к создаваемой базе.
"""

from __future__ import annotations

import os
import sys

import psycopg2
from dotenv import load_dotenv
from psycopg2 import sql

from postgres_driver import readable_server_error


def main() -> int:
    load_dotenv()

    required = ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD")
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        print(
            "Не заданы переменные окружения: " + ", ".join(missing),
            file=sys.stderr,
        )
        print("Скопируйте .env.example в .env и заполните значения.", file=sys.stderr)
        return 1

    target = os.environ["DB_NAME"]

    try:
        conn = psycopg2.connect(
            host=os.environ["DB_HOST"],
            port=int(os.environ["DB_PORT"]),
            dbname="postgres",  # служебная база, она есть после установки
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
        )
    except UnicodeDecodeError as exc:
        # См. readable_server_error(): сервер отдаёт сообщение в cp1251.
        print(
            f"Не удалось подключиться к серверу: {readable_server_error(exc)}",
            file=sys.stderr,
        )
        return 1
    except psycopg2.Error as exc:
        print(f"Не удалось подключиться к серверу: {exc}", file=sys.stderr)
        return 1

    try:
        conn.autocommit = True  # CREATE DATABASE нельзя выполнять в транзакции
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s;", (target,))
            if cur.fetchone() is not None:
                print(f"База {target!r} уже существует — ничего не делаю.")
                return 0

            # Имя базы нельзя передать через %s — это не значение, а идентификатор.
            cur.execute(
                sql.SQL("CREATE DATABASE {};").format(sql.Identifier(target))
            )
            print(f"База {target!r} создана.")
            return 0
    except UnicodeDecodeError as exc:
        print(
            f"Ошибка при создании базы: {readable_server_error(exc)}",
            file=sys.stderr,
        )
        return 1
    except psycopg2.Error as exc:
        print(f"Ошибка при создании базы: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())

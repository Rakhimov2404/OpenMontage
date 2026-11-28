import sqlite3
import time
from contextlib import closing

from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL,
    username      TEXT,
    product_key   TEXT NOT NULL,
    product_name  TEXT NOT NULL,
    price         INTEGER NOT NULL,
    player_id     TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'awaiting_payment',
    yupay_order_id TEXT,
    note          TEXT,
    created_at    INTEGER NOT NULL,
    updated_at    INTEGER NOT NULL
);
"""
# status: awaiting_payment -> payment_sent -> processing -> completed | failed | rejected


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init():
    with closing(_conn()) as c, c:
        c.executescript(SCHEMA)


def create_order(user_id, username, product, player_id) -> int:
    now = int(time.time())
    with closing(_conn()) as c, c:
        cur = c.execute(
            "INSERT INTO orders (user_id, username, product_key, product_name, price, player_id,"
            " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
            (user_id, username, product["key"], product["name"], product["price"], player_id, now, now),
        )
        return cur.lastrowid


def get(order_id: int):
    with closing(_conn()) as c:
        return c.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()


def get_by_yupay(yupay_order_id: str):
    with closing(_conn()) as c:
        return c.execute("SELECT * FROM orders WHERE yupay_order_id=?", (str(yupay_order_id),)).fetchone()


def update(order_id: int, **fields):
    fields["updated_at"] = int(time.time())
    cols = ", ".join(f"{k}=?" for k in fields)
    with closing(_conn()) as c, c:
        c.execute(f"UPDATE orders SET {cols} WHERE id=?", (*fields.values(), order_id))


def set_status_if(order_id: int, expected: str, new: str) -> bool:
    """Holatni faqat kutilgan holatda bo'lsa o'zgartiradi (ikki marta bosilishdan himoya)."""
    with closing(_conn()) as c, c:
        cur = c.execute(
            "UPDATE orders SET status=?, updated_at=? WHERE id=? AND status=?",
            (new, int(time.time()), order_id, expected),
        )
        return cur.rowcount == 1


def user_orders(user_id: int, limit: int = 10):
    with closing(_conn()) as c:
        return c.execute(
            "SELECT * FROM orders WHERE user_id=? ORDER BY id DESC LIMIT ?", (user_id, limit)
        ).fetchall()

"""
AutoERP Database Layer
Uses PostgreSQL (via psycopg2) on Vercel, with the same db_conn()/get_db()
interface the rest of the app already relies on.
"""

import os
import psycopg2
import psycopg2.extras
from contextlib import contextmanager

DATABASE_URL = os.environ.get("DATABASE_URL")


class _CursorWrapper:
    def __init__(self, cursor):
        self._cursor = cursor

    def execute(self, query, params=()):
        query = query.replace("?", "%s")
        self._cursor.execute(query, params)
        return self

    def executescript(self, script):
        self._cursor.execute(script)
        return self

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    @property
    def lastrowid(self):
        try:
            return self._cursor.fetchone()[0]
        except Exception:
            return None


class _ConnWrapper:
    def __init__(self, conn):
        self._conn = conn
        self._cursor = _CursorWrapper(conn.cursor())

    def execute(self, query, params=()):
        if query.strip().upper().startswith("INSERT") and "RETURNING" not in query.upper():
            query = query.rstrip().rstrip(";") + " RETURNING id"
        return self._cursor.execute(query, params)

    def executescript(self, script):
        return self._cursor.executescript(script)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


def get_db():
    """Return a wrapped psycopg2 connection that supports .execute() directly,
    matching the app's original sqlite-style usage."""
    raw_conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    return _ConnWrapper(raw_conn)


@contextmanager
def db_conn():
    conn = get_db()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    _seed_defaults()


def _seed_defaults():
    from werkzeug.security import generate_password_hash
    with db_conn() as conn:
        defaults = [
            ('admin', 'admin@autoerp.com', 'System Administrator', 'admin', 'admin123'),
            ('manager', 'manager@autoerp.com', 'Floor Manager', 'manager', 'manager123'),
            ('staff', 'staff@autoerp.com', 'Staff User', 'staff', 'staff123'),
        ]
        for username, email, full_name, role, pwd in defaults:
            exists = conn.execute('SELECT id FROM users WHERE username=?', (username,)).fetchone()
            if not exists:
                conn.execute(
                    'INSERT INTO users (username,email,full_name,password_hash,role) VALUES (?,?,?,?,?)',
                    (username, email, full_name, generate_password_hash(pwd), role)
                )

        cats = ['Engine', 'Transmission', 'Brakes', 'Suspension', 'Electrical', 'Body Parts', 'Accessories', 'Tires', 'Fluids']
        for cat in cats:
            exists = conn.execute('SELECT id FROM categories WHERE name=?', (cat,)).fetchone()
            if not exists:
                conn.execute('INSERT INTO categories (name,description) VALUES (?,?)', (cat, f'{cat} components and parts'))

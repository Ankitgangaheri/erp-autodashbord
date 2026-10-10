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


def get_db():
    """Return a psycopg2 connection with dict-like row access."""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    return conn


class _CursorWrapper:
    """Makes psycopg2's '%s' placeholders work with the app's '?' style calls,
    and makes execute() return self so existing .fetchone()/.fetchall() calls work."""
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
        # Auto-return inserted id for INSERT statements (mimics sqlite lastrowid)
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


@contextmanager
def db_conn():
    """Context manager — auto-commits or rolls back."""
    raw_conn = get_db()
    conn = _ConnWrapper(raw_conn)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Tables already created in Supabase — just seed defaults if missing."""
    _seed_defaults()


def _seed_defaults():
    """Insert default users and categories if not present."""
    from werkzeug.security import generate_password_hash
    with db_conn() as conn:
        defaults = [
            ('admin',   'admin@autoerp.com',   'System Administrator', 'admin',   'admin123'),
            ('manager', 'manager@autoerp.com', 'Floor Manager',        'manager', 'manager123'),
            ('staff',   'staff@autoerp.com',   'Staff User',           'staff',   'staff123'),
        ]
        for username, email, full_name, role, pwd in defaults:
            exists = conn.execute('SELECT id FROM users WHERE username=?', (username,)).fetchone()
            if not exists:
                conn.execute(
                    'INSERT INTO users (username,email,full_name,password_hash,role) VALUES (?,?,?,?,?)',
                    (username, email, full_name, generate_password_hash(pwd), role)
                )

        cats = ['Engine', 'Transmission', 'Brakes', 'Suspension',
                'Electrical', 'Body Parts', 'Accessories', 'Tires', 'Fluids']
        for cat in cats:
            exists = conn.execute('SELECT id FROM categories WHERE name=?', (cat,)).fetchone()
            if not exists:

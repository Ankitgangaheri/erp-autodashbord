"""
AutoERP Database Layer
Uses Python's built-in sqlite3 module — no ORM needed.
Provides a clean connection helper and schema initialisation.
"""

import sqlite3
import os
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'instance', 'autoerp.db')


def get_db():
    """Return a sqlite3 connection with Row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def db_conn():
    """Context manager — auto-commits or rolls back."""
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
    """Create all tables and seed default data."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with db_conn() as conn:
        conn.executescript(SCHEMA_SQL)
    _seed_defaults()


# ──────────────────────────────────────────────
#  SCHEMA
# ──────────────────────────────────────────────
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    username    TEXT UNIQUE NOT NULL,
    email       TEXT UNIQUE NOT NULL,
    full_name   TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role        TEXT NOT NULL DEFAULT 'staff',
    is_active   INTEGER NOT NULL DEFAULT 1,
    last_login  TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS categories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT UNIQUE NOT NULL,
    description TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS products (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    sku                 TEXT UNIQUE NOT NULL,
    name                TEXT NOT NULL,
    description         TEXT,
    category_id         INTEGER NOT NULL REFERENCES categories(id),
    unit                TEXT NOT NULL DEFAULT 'pcs',
    cost_price          REAL NOT NULL DEFAULT 0,
    selling_price       REAL NOT NULL DEFAULT 0,
    quantity            INTEGER NOT NULL DEFAULT 0,
    low_stock_threshold INTEGER NOT NULL DEFAULT 10,
    is_active           INTEGER NOT NULL DEFAULT 1,
    created_at          TEXT DEFAULT (datetime('now')),
    updated_at          TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS stock_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id      INTEGER NOT NULL REFERENCES products(id),
    change_type     TEXT NOT NULL,
    quantity_change INTEGER NOT NULL,
    quantity_before INTEGER NOT NULL,
    quantity_after  INTEGER NOT NULL,
    reference_id    INTEGER,
    reference_type  TEXT,
    notes           TEXT,
    created_by      INTEGER REFERENCES users(id),
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS suppliers (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    contact_person  TEXT,
    email           TEXT,
    phone           TEXT,
    address         TEXT,
    city            TEXT,
    country         TEXT DEFAULT 'India',
    gst_number      TEXT,
    payment_terms   TEXT,
    is_active       INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS purchases (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    po_number       TEXT UNIQUE NOT NULL,
    supplier_id     INTEGER NOT NULL REFERENCES suppliers(id),
    status          TEXT NOT NULL DEFAULT 'pending',
    order_date      TEXT DEFAULT (datetime('now')),
    expected_date   TEXT,
    received_date   TEXT,
    total_amount    REAL DEFAULT 0,
    notes           TEXT,
    created_by      INTEGER REFERENCES users(id),
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS purchase_items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    purchase_id INTEGER NOT NULL REFERENCES purchases(id) ON DELETE CASCADE,
    product_id  INTEGER NOT NULL REFERENCES products(id),
    quantity    INTEGER NOT NULL,
    unit_price  REAL NOT NULL,
    total_price REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS customers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    email       TEXT,
    phone       TEXT,
    address     TEXT,
    city        TEXT,
    gst_number  TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sales (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_number  TEXT UNIQUE NOT NULL,
    customer_id     INTEGER REFERENCES customers(id),
    customer_name   TEXT,
    status          TEXT NOT NULL DEFAULT 'completed',
    sale_date       TEXT DEFAULT (datetime('now')),
    subtotal        REAL DEFAULT 0,
    discount        REAL DEFAULT 0,
    tax             REAL DEFAULT 0,
    total_amount    REAL DEFAULT 0,
    payment_method  TEXT DEFAULT 'cash',
    notes           TEXT,
    created_by      INTEGER REFERENCES users(id),
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sale_items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_id     INTEGER NOT NULL REFERENCES sales(id) ON DELETE CASCADE,
    product_id  INTEGER NOT NULL REFERENCES products(id),
    quantity    INTEGER NOT NULL,
    unit_price  REAL NOT NULL,
    total_price REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS production_orders (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    order_number        TEXT UNIQUE NOT NULL,
    product_id          INTEGER NOT NULL REFERENCES products(id),
    quantity_planned    INTEGER NOT NULL,
    quantity_produced   INTEGER DEFAULT 0,
    status              TEXT NOT NULL DEFAULT 'planned',
    start_date          TEXT,
    end_date            TEXT,
    notes               TEXT,
    created_by          INTEGER REFERENCES users(id),
    created_at          TEXT DEFAULT (datetime('now')),
    updated_at          TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS production_materials (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    production_order_id     INTEGER NOT NULL REFERENCES production_orders(id) ON DELETE CASCADE,
    product_id              INTEGER NOT NULL REFERENCES products(id),
    quantity_required       INTEGER NOT NULL,
    quantity_consumed       INTEGER DEFAULT 0
);
"""


def _seed_defaults():
    """Insert default users and categories if not present."""
    from werkzeug.security import generate_password_hash
    with db_conn() as conn:
        # Default users
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

        # Default categories
        cats = ['Engine', 'Transmission', 'Brakes', 'Suspension',
                'Electrical', 'Body Parts', 'Accessories', 'Tires', 'Fluids']
        for cat in cats:
            exists = conn.execute('SELECT id FROM categories WHERE name=?', (cat,)).fetchone()
            if not exists:
                conn.execute('INSERT INTO categories (name,description) VALUES (?,?)',
                             (cat, f'{cat} components and parts'))

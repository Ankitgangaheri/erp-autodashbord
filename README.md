# AutoERP — Automobile Inventory & Production Management System

A complete, production-ready ERP system built with pure Flask + SQLite.
No heavy ORM dependencies. Runs anywhere Python 3.8+ is installed.

---

## 🚀 QUICK START — 3 Steps

### Step 1 — Install Flask
```bash
pip install flask werkzeug
```
> All other libraries (sqlite3, csv, datetime, logging) are Python built-ins.

### Step 2 — Run
```bash
cd autoerp
python run.py
```

### Step 3 — Open browser
Visit **http://127.0.0.1:5000**

---

## 🔐 Default Login Credentials

| Role    | Username  | Password    | Access                      |
|---------|-----------|-------------|-----------------------------|
| Admin   | admin     | admin123    | Full system access          |
| Manager | manager   | manager123  | All operations              |
| Staff   | staff     | staff123    | View + create sales         |

**Click any credential card on the login page to auto-fill.**

---

## 📁 Project Structure

```
autoerp/
├── run.py                    ← Entry point
├── requirements.txt          ← Dependency notes
├── .env                      ← Config (SECRET_KEY)
├── README.md
├── instance/
│   └── autoerp.db            ← SQLite DB (auto-created)
├── logs/
│   └── autoerp.log           ← App log (auto-created)
└── app/
    ├── __init__.py           ← Flask factory
    ├── database.py           ← Schema + sqlite3 helpers
    ├── auth_helpers.py       ← login_required decorators
    ├── routes/               ← 8 blueprints
    │   ├── auth.py
    │   ├── dashboard.py
    │   ├── inventory.py
    │   ├── suppliers.py
    │   ├── purchases.py
    │   ├── production.py
    │   ├── sales.py
    │   └── reports.py
    ├── static/
    │   ├── css/main.css      ← Dark industrial theme
    │   └── js/main.js        ← Autocomplete + charts
    └── templates/            ← Jinja2 HTML templates
        ├── base.html
        ├── auth/
        ├── dashboard/
        ├── inventory/
        ├── suppliers/
        ├── purchases/
        ├── production/
        ├── sales/
        └── reports/
```

---

## 📦 Modules

| Module         | Features                                                            |
|----------------|---------------------------------------------------------------------|
| Dashboard       | KPI cards, 7-day revenue chart, low-stock alerts, activity log     |
| Inventory       | Add/edit/deactivate products, stock adjustment, movement history   |
| Categories      | Manage product categories                                          |
| Low Stock       | Alert list for items needing reorder                               |
| Suppliers       | Full supplier profiles, purchase history                           |
| Purchase Orders | Multi-line POs, receive stock (auto-updates inventory)             |
| Production      | Work orders, BOM materials, start/complete flow                    |
| Sales           | Invoices, stock auto-deduction, cancel with stock restore          |
| Customers       | Customer records linked to invoices                                |
| Reports         | Inventory / Sales / Production / Stock-movement + CSV export       |
| User Management | Add/edit users, role-based access (Admin/Manager/Staff)           |

---

## ⚙️ Configuration (.env)

```
SECRET_KEY=change-this-to-a-long-random-string
FLASK_ENV=development
```

---

## 🗄️ Database Tables

users · categories · products · stock_history ·
suppliers · purchases · purchase_items ·
customers · sales · sale_items ·
production_orders · production_materials

**Backup:**
```bash
cp instance/autoerp.db instance/autoerp_backup_$(date +%Y%m%d).db
```

**Reset (fresh start):**
```bash
rm instance/autoerp.db && python run.py
```

---

## 🛡️ Production Deployment

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:8000 "run:app"
```

Set `FLASK_ENV=production` and a strong `SECRET_KEY` in `.env`.
Run behind nginx with HTTPS.

---

## 🧩 Tech Stack

- **Backend:** Python 3.8+ · Flask · Werkzeug
- **Database:** SQLite (Python built-in sqlite3)
- **Frontend:** HTML5 · CSS3 · Vanilla JavaScript
- **Auth:** Flask sessions + Werkzeug password hashing
- **UI:** Dark industrial theme (IBM Plex Sans + Syne via Google Fonts)
- **Zero external JS/CSS frameworks**


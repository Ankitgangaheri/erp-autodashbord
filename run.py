"""
AutoERP — Entry Point
Run: python run.py
Then open: http://127.0.0.1:5000
"""

import os
from app import create_app

app = create_app()

if __name__ == '__main__':
    print("=" * 55)
    print("  AutoERP — Automobile Inventory & Production ERP")
    print("=" * 55)
    print("  URL     : http://127.0.0.1:5000")
    print("  Admin   : admin   / admin123")
    print("  Manager : manager / manager123")
    print("  Staff   : staff   / staff123")
    print("=" * 55)
    app.run(debug=True, host='0.0.0.0', port=5000)

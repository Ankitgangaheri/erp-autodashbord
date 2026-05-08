"""
AutoERP Application Factory
Pure Flask — no third-party extensions beyond Flask itself.
"""

import os
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, session, g


def create_app():
    app = Flask(__name__,
                template_folder='templates',
                static_folder='static')

    app.secret_key = os.environ.get('SECRET_KEY', 'autoerp-dev-secret-2024-change-in-prod')
    app.config['ITEMS_PER_PAGE'] = 15
    app.config['LOW_STOCK_THRESHOLD'] = 10

    # ── Logging ──
    os.makedirs('logs', exist_ok=True)
    fh = RotatingFileHandler('logs/autoerp.log', maxBytes=1_000_000, backupCount=5)
    fh.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    fh.setLevel(logging.INFO)
    app.logger.addHandler(fh)
    app.logger.setLevel(logging.INFO)

    # ── Init DB ──
    from app.database import init_db
    init_db()

    # ── Inject current_user into every template ──
    @app.before_request
    def load_user():
        from app.auth_helpers import get_current_user
        g.current_user = get_current_user()

    @app.context_processor
    def inject_globals():
        from app.database import get_db
        low_stock_count = 0
        try:
            db = get_db()
            row = db.execute(
                'SELECT COUNT(*) AS c FROM products WHERE quantity <= low_stock_threshold AND is_active=1'
            ).fetchone()
            low_stock_count = row['c'] if row else 0
            db.close()
        except Exception:
            pass
        return dict(current_user=g.current_user,
                    low_stock_count=low_stock_count,
                    is_manager=lambda: session.get('user_role') in ('admin', 'manager'),
                    is_admin=lambda: session.get('user_role') == 'admin')

    # ── Register blueprints ──
    from app.routes.auth       import auth_bp
    from app.routes.dashboard  import dashboard_bp
    from app.routes.inventory  import inventory_bp
    from app.routes.suppliers  import suppliers_bp
    from app.routes.purchases  import purchases_bp
    from app.routes.production import production_bp
    from app.routes.sales      import sales_bp
    from app.routes.reports    import reports_bp

    app.register_blueprint(auth_bp,       url_prefix='/auth')
    app.register_blueprint(dashboard_bp,  url_prefix='/')
    app.register_blueprint(inventory_bp,  url_prefix='/inventory')
    app.register_blueprint(suppliers_bp,  url_prefix='/suppliers')
    app.register_blueprint(purchases_bp,  url_prefix='/purchases')
    app.register_blueprint(production_bp, url_prefix='/production')
    app.register_blueprint(sales_bp,      url_prefix='/sales')
    app.register_blueprint(reports_bp,    url_prefix='/reports')

    return app

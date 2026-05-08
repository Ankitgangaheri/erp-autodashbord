"""Dashboard Blueprint."""

from datetime import datetime, timedelta
from flask import Blueprint, render_template
from app.database import get_db
from app.auth_helpers import login_required

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/')
@login_required
def index():
    db = get_db()

    total_products = db.execute(
        'SELECT COUNT(*) AS c FROM products WHERE is_active=1').fetchone()['c']

    low_stock_items = db.execute(
        '''SELECT p.*,c.name AS cat_name FROM products p
           JOIN categories c ON c.id=p.category_id
           WHERE p.quantity<=p.low_stock_threshold AND p.is_active=1
           ORDER BY p.quantity ASC LIMIT 8''').fetchall()

    stock_value_row = db.execute(
        'SELECT SUM(quantity*cost_price) AS sv FROM products WHERE is_active=1').fetchone()
    total_stock_value = stock_value_row['sv'] or 0

    month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0).strftime('%Y-%m-%d %H:%M:%S')

    monthly_sales_row = db.execute(
        "SELECT SUM(total_amount) AS s, COUNT(*) AS c FROM sales WHERE created_at>=? AND status='completed'",
        (month_start,)).fetchone()
    monthly_sales      = monthly_sales_row['s'] or 0
    monthly_sale_count = monthly_sales_row['c'] or 0

    monthly_purchases_row = db.execute(
        'SELECT SUM(total_amount) AS s FROM purchases WHERE created_at>=?', (month_start,)).fetchone()
    monthly_purchases = monthly_purchases_row['s'] or 0

    active_production = db.execute(
        "SELECT COUNT(*) AS c FROM production_orders WHERE status IN ('planned','in_progress')").fetchone()['c']

    pending_purchases = db.execute(
        "SELECT COUNT(*) AS c FROM purchases WHERE status='pending'").fetchone()['c']

    recent_activities = db.execute(
        '''SELECT sh.*,p.name AS product_name,p.sku FROM stock_history sh
           JOIN products p ON p.id=sh.product_id
           ORDER BY sh.created_at DESC LIMIT 10''').fetchall()

    recent_sales = db.execute(
        '''SELECT s.*,u.full_name AS creator FROM sales s
           LEFT JOIN users u ON u.id=s.created_by
           WHERE s.status='completed' ORDER BY s.created_at DESC LIMIT 5''').fetchall()

    # 7-day sales trend
    sales_trend = []
    now = datetime.utcnow()
    for i in range(6, -1, -1):
        day = now - timedelta(days=i)
        d_start = day.strftime('%Y-%m-%d 00:00:00')
        d_end   = day.strftime('%Y-%m-%d 23:59:59')
        row = db.execute(
            "SELECT SUM(total_amount) AS s FROM sales WHERE created_at BETWEEN ? AND ? AND status='completed'",
            (d_start, d_end)).fetchone()
        sales_trend.append({'date': day.strftime('%b %d'), 'amount': round(row['s'] or 0, 2)})

    db.close()

    return render_template('dashboard/index.html',
        total_products=total_products,
        low_stock_items=[dict(r) for r in low_stock_items],
        low_stock_count=len(low_stock_items),
        total_stock_value=total_stock_value,
        monthly_sales=monthly_sales,
        monthly_sale_count=monthly_sale_count,
        monthly_purchases=monthly_purchases,
        active_production=active_production,
        pending_purchases=pending_purchases,
        recent_activities=[dict(r) for r in recent_activities],
        recent_sales=[dict(r) for r in recent_sales],
        sales_trend=sales_trend,
    )

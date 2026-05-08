"""Reports Blueprint — CSV exports and analytics."""

import csv
import io
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, make_response
from app.database import get_db
from app.auth_helpers import login_required

reports_bp = Blueprint('reports', __name__)


def _date_range():
    d_from = request.args.get('date_from', '')
    d_to   = request.args.get('date_to', '')
    now    = datetime.utcnow()
    try:
        date_from = datetime.strptime(d_from, '%Y-%m-%d') if d_from else now - timedelta(days=30)
    except ValueError:
        date_from = now - timedelta(days=30)
    try:
        date_to = datetime.strptime(d_to, '%Y-%m-%d').replace(hour=23, minute=59) if d_to else now
    except ValueError:
        date_to = now
    return date_from, date_to


@reports_bp.route('/')
@login_required
def index():
    return render_template('reports/index.html')


@reports_bp.route('/inventory')
@login_required
def inventory_report():
    cat_f    = request.args.get('category', '')
    stock_f  = request.args.get('stock', '')
    db       = get_db()
    cats     = db.execute('SELECT * FROM categories ORDER BY name').fetchall()
    sql      = 'SELECT p.*,c.name AS cat_name FROM products p JOIN categories c ON c.id=p.category_id WHERE p.is_active=1'
    args     = []
    if cat_f:
        sql += ' AND p.category_id=?'; args.append(int(cat_f))
    if stock_f == 'low':
        sql += ' AND p.quantity<=p.low_stock_threshold'
    elif stock_f == 'out':
        sql += ' AND p.quantity=0'
    sql += ' ORDER BY p.name'
    products = [dict(r) for r in db.execute(sql, args).fetchall()]
    db.close()

    for p in products:
        p['stock_value'] = p['quantity'] * p['cost_price']
        p['is_low_stock'] = p['quantity'] <= p['low_stock_threshold']

    total_value     = sum(p['stock_value'] for p in products)
    low_stock_count = sum(1 for p in products if p['is_low_stock'])

    if request.args.get('export') == 'csv':
        out = io.StringIO()
        w   = csv.writer(out)
        w.writerow(['SKU','Product','Category','Unit','Qty','Cost','Sell Price','Value','Low Stock?'])
        for p in products:
            w.writerow([p['sku'],p['name'],p['cat_name'],p['unit'],p['quantity'],
                        p['cost_price'],p['selling_price'],round(p['stock_value'],2),
                        'Yes' if p['is_low_stock'] else 'No'])
        r = make_response(out.getvalue())
        r.headers['Content-Disposition'] = 'attachment; filename=inventory_report.csv'
        r.headers['Content-type'] = 'text/csv'
        return r

    return render_template('reports/inventory_report.html',
        products=products, categories=[dict(c) for c in cats],
        category_id=cat_f, stock_filter=stock_f,
        total_value=total_value, total_items=len(products), low_stock_count=low_stock_count)


@reports_bp.route('/sales')
@login_required
def sales_report():
    date_from, date_to = _date_range()
    df = date_from.strftime('%Y-%m-%d %H:%M:%S')
    dt = date_to.strftime('%Y-%m-%d %H:%M:%S')

    db    = get_db()
    sales = [dict(r) for r in db.execute(
        "SELECT * FROM sales WHERE created_at BETWEEN ? AND ? AND status='completed' ORDER BY created_at DESC",
        (df, dt)).fetchall()]

    top_products = db.execute(
        '''SELECT p.name, SUM(si.quantity) AS total_qty, SUM(si.total_price) AS total_revenue
           FROM sale_items si JOIN products p ON p.id=si.product_id
           JOIN sales s ON s.id=si.sale_id
           WHERE s.created_at BETWEEN ? AND ? AND s.status='completed'
           GROUP BY p.id ORDER BY total_revenue DESC LIMIT 10''', (df, dt)).fetchall()
    db.close()

    total_revenue = sum(s['total_amount'] for s in sales)

    if request.args.get('export') == 'csv':
        out = io.StringIO()
        w   = csv.writer(out)
        w.writerow(['Invoice','Date','Customer','Payment','Subtotal','Discount','Tax','Total'])
        for s in sales:
            w.writerow([s['invoice_number'],s['created_at'],s['customer_name'] or '',
                        s['payment_method'],s['subtotal'],s['discount'],s['tax'],s['total_amount']])
        r = make_response(out.getvalue())
        r.headers['Content-Disposition'] = 'attachment; filename=sales_report.csv'
        r.headers['Content-type'] = 'text/csv'
        return r

    return render_template('reports/sales_report.html',
        sales=sales, total_revenue=total_revenue, total_sales=len(sales),
        top_products=[dict(t) for t in top_products],
        date_from=date_from.strftime('%Y-%m-%d'),
        date_to=date_to.strftime('%Y-%m-%d'))


@reports_bp.route('/production')
@login_required
def production_report():
    status = request.args.get('status', '')
    db     = get_db()
    sql    = 'SELECT po.*,p.name AS product_name,p.sku FROM production_orders po JOIN products p ON p.id=po.product_id WHERE 1=1'
    args   = []
    if status:
        sql += ' AND po.status=?'; args.append(status)
    sql += ' ORDER BY po.created_at DESC'
    orders = [dict(r) for r in db.execute(sql, args).fetchall()]
    db.close()

    for o in orders:
        o['completion_percent'] = min(100, int((o['quantity_produced']/o['quantity_planned'])*100)) if o['quantity_planned'] else 0
    total_produced = sum(o['quantity_produced'] for o in orders if o['status'] == 'completed')

    if request.args.get('export') == 'csv':
        out = io.StringIO()
        w   = csv.writer(out)
        w.writerow(['Work Order','Product','Planned','Produced','Status','Start','End'])
        for o in orders:
            w.writerow([o['order_number'],o['product_name'],o['quantity_planned'],
                        o['quantity_produced'],o['status'],
                        o['start_date'] or '',o['end_date'] or ''])
        r = make_response(out.getvalue())
        r.headers['Content-Disposition'] = 'attachment; filename=production_report.csv'
        r.headers['Content-type'] = 'text/csv'
        return r

    return render_template('reports/production_report.html',
                           orders=orders, total_produced=total_produced, status=status)


@reports_bp.route('/stock-movement')
@login_required
def stock_movement():
    date_from, date_to = _date_range()
    df = date_from.strftime('%Y-%m-%d %H:%M:%S')
    dt = date_to.strftime('%Y-%m-%d %H:%M:%S')

    db        = get_db()
    movements = [dict(r) for r in db.execute(
        '''SELECT sh.*,p.name AS product_name,p.sku FROM stock_history sh
           JOIN products p ON p.id=sh.product_id
           WHERE sh.created_at BETWEEN ? AND ? ORDER BY sh.created_at DESC''',
        (df, dt)).fetchall()]
    db.close()

    if request.args.get('export') == 'csv':
        out = io.StringIO()
        w   = csv.writer(out)
        w.writerow(['Date','Product','SKU','Type','Change','Before','After','Notes'])
        for m in movements:
            w.writerow([m['created_at'],m['product_name'],m['sku'],m['change_type'],
                        m['quantity_change'],m['quantity_before'],m['quantity_after'],m['notes'] or ''])
        r = make_response(out.getvalue())
        r.headers['Content-Disposition'] = 'attachment; filename=stock_movement.csv'
        r.headers['Content-type'] = 'text/csv'
        return r

    return render_template('reports/stock_movement.html',
        movements=movements,
        date_from=date_from.strftime('%Y-%m-%d'),
        date_to=date_to.strftime('%Y-%m-%d'))

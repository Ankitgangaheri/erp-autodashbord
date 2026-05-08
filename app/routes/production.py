"""Production Blueprint."""

from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from app.database import db_conn, get_db
from app.auth_helpers import login_required, manager_required

production_bp = Blueprint('production', __name__)
PER_PAGE = 15


class _Page:
    """Simple pagination container with attribute access for templates."""
    def __init__(self, items, total, page, pages, per_page):
        self.items    = items
        self.total    = total
        self.page     = page
        self.pages    = pages
        self.per_page = per_page
        self.has_prev = page > 1
        self.has_next = page < pages
        self.prev_num = page - 1
        self.next_num = page + 1

def _paginate(rows, page, per_page=PER_PAGE):
    total = len(rows)
    items = rows[(page-1)*per_page : page*per_page]
    pages = max(1, (total + per_page - 1) // per_page)
    return _Page(items, total, page, pages, per_page)


def _gen_wo(conn):
    row = conn.execute('SELECT MAX(id) AS m FROM production_orders').fetchone()
    num = (row['m'] or 0) + 1
    return f"WO-{datetime.utcnow().year}-{num:05d}"


@production_bp.route('/')
@login_required
def index():
    page   = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    status = request.args.get('status', '')
    db     = get_db()
    sql    = '''SELECT po.*,p.name AS product_name,p.sku FROM production_orders po
                JOIN products p ON p.id=po.product_id WHERE 1=1'''
    args   = []
    if search:
        sql += ' AND po.order_number LIKE ?'
        args.append(f'%{search}%')
    if status:
        sql += ' AND po.status=?'
        args.append(status)
    sql += ' ORDER BY po.created_at DESC'
    rows = db.execute(sql, args).fetchall()
    db.close()
    orders = _paginate([dict(r) for r in rows], page)
    return render_template('production/index.html', orders=orders, search=search, status=status)


@production_bp.route('/create', methods=['GET', 'POST'])
@manager_required
def create_order():
    db       = get_db()
    products = db.execute(
        'SELECT p.*,c.name AS cat_name FROM products p JOIN categories c ON c.id=p.category_id WHERE p.is_active=1 ORDER BY p.name').fetchall()
    db.close()

    if request.method == 'POST':
        product_id    = request.form.get('product_id', type=int)
        qty_planned   = request.form.get('quantity_planned', 0, type=int)
        start_date    = request.form.get('start_date', '') or None
        end_date      = request.form.get('end_date', '') or None
        notes         = request.form.get('notes', '').strip()
        material_ids  = request.form.getlist('material_id[]')
        material_qtys = request.form.getlist('material_qty[]')

        if not product_id or qty_planned <= 0:
            flash('Product and planned quantity required.', 'danger')
            return render_template('production/create_order.html', products=[dict(p) for p in products])

        with db_conn() as conn:
            wo_num = _gen_wo(conn)
            cur    = conn.execute(
                '''INSERT INTO production_orders (order_number,product_id,quantity_planned,
                   start_date,end_date,notes,created_by) VALUES (?,?,?,?,?,?,?)''',
                (wo_num, product_id, qty_planned, start_date, end_date,
                 notes, session.get('user_id')))
            wo_id = cur.lastrowid
            for mid, mqty_s in zip(material_ids, material_qtys):
                try:
                    mqty = int(mqty_s)
                    if mqty <= 0: continue
                    conn.execute(
                        'INSERT INTO production_materials (production_order_id,product_id,quantity_required) VALUES (?,?,?)',
                        (wo_id, int(mid), mqty))
                except (ValueError, TypeError):
                    continue

        flash(f'Work Order {wo_num} created.', 'success')
        return redirect(url_for('production.view_order', order_id=wo_id))

    return render_template('production/create_order.html', products=[dict(p) for p in products])


@production_bp.route('/view/<int:order_id>')
@login_required
def view_order(order_id):
    db    = get_db()
    order = db.execute(
        'SELECT po.*,p.name AS product_name,p.sku FROM production_orders po JOIN products p ON p.id=po.product_id WHERE po.id=?',
        (order_id,)).fetchone()
    if not order:
        flash('Work order not found.', 'danger')
        return redirect(url_for('production.index'))
    materials = db.execute(
        '''SELECT pm.*,p.name AS mat_name,p.sku,p.unit,p.quantity AS stock
           FROM production_materials pm JOIN products p ON p.id=pm.product_id
           WHERE pm.production_order_id=?''', (order_id,)).fetchall()
    db.close()
    o = dict(order)
    o['completion_percent'] = min(100, int((o['quantity_produced'] / o['quantity_planned']) * 100)) if o['quantity_planned'] else 0
    return render_template('production/view_order.html',
                           order=o, materials=[dict(m) for m in materials])


@production_bp.route('/start/<int:order_id>', methods=['POST'])
@manager_required
def start_order(order_id):
    db    = get_db()
    order = db.execute('SELECT * FROM production_orders WHERE id=?', (order_id,)).fetchone()
    if not order or order['status'] != 'planned':
        flash('Only planned orders can be started.', 'warning')
        return redirect(url_for('production.view_order', order_id=order_id))
    mats  = db.execute('SELECT pm.*,p.name,p.quantity AS stock FROM production_materials pm JOIN products p ON p.id=pm.product_id WHERE pm.production_order_id=?', (order_id,)).fetchall()
    db.close()

    errors = [f'Insufficient {m["name"]}: need {m["quantity_required"]}, have {m["stock"]}'
              for m in mats if m['stock'] < m['quantity_required']]
    if errors:
        for e in errors: flash(e, 'danger')
        return redirect(url_for('production.view_order', order_id=order_id))

    with db_conn() as conn:
        for m in mats:
            prod = conn.execute('SELECT * FROM products WHERE id=?', (m['product_id'],)).fetchone()
            old  = prod['quantity']
            new  = old - m['quantity_required']
            conn.execute("UPDATE products SET quantity=?,updated_at=datetime('now') WHERE id=?", (new, prod['id']))
            conn.execute(
                '''INSERT INTO stock_history (product_id,change_type,quantity_change,
                   quantity_before,quantity_after,reference_id,reference_type,notes,created_by)
                   VALUES (?,?,?,?,?,?,?,?,?)''',
                (prod['id'], 'production', -m['quantity_required'], old, new,
                 order_id, 'production', f"Consumed for {order['order_number']}", session.get('user_id')))
            conn.execute('UPDATE production_materials SET quantity_consumed=? WHERE id=?',
                         (m['quantity_required'], m['id']))
        conn.execute(
            "UPDATE production_orders SET status='in_progress',start_date=COALESCE(start_date,datetime('now')) WHERE id=?",
            (order_id,))

    flash(f"Work Order {order['order_number']} started. Materials deducted.", 'success')
    return redirect(url_for('production.view_order', order_id=order_id))


@production_bp.route('/complete/<int:order_id>', methods=['POST'])
@manager_required
def complete_order(order_id):
    db    = get_db()
    order = db.execute('SELECT * FROM production_orders WHERE id=?', (order_id,)).fetchone()
    db.close()
    if not order or order['status'] != 'in_progress':
        flash('Only in-progress orders can be completed.', 'warning')
        return redirect(url_for('production.view_order', order_id=order_id))

    qty_produced = request.form.get('quantity_produced', order['quantity_planned'], type=int)
    if qty_produced <= 0:
        flash('Quantity must be positive.', 'danger')
        return redirect(url_for('production.view_order', order_id=order_id))

    with db_conn() as conn:
        prod = conn.execute('SELECT * FROM products WHERE id=?', (order['product_id'],)).fetchone()
        old  = prod['quantity']
        new  = old + qty_produced
        conn.execute("UPDATE products SET quantity=?,updated_at=datetime('now') WHERE id=?", (new, prod['id']))
        conn.execute(
            '''INSERT INTO stock_history (product_id,change_type,quantity_change,
               quantity_before,quantity_after,reference_id,reference_type,notes,created_by)
               VALUES (?,?,?,?,?,?,?,?,?)''',
            (prod['id'], 'production', qty_produced, old, new,
             order_id, 'production', f"Produced via {order['order_number']}", session.get('user_id')))
        conn.execute(
            "UPDATE production_orders SET status='completed',quantity_produced=?,end_date=datetime('now') WHERE id=?",
            (qty_produced, order_id))

    flash(f"Work Order {order['order_number']} completed. {qty_produced} units added to stock.", 'success')
    return redirect(url_for('production.view_order', order_id=order_id))


@production_bp.route('/cancel/<int:order_id>', methods=['POST'])
@manager_required
def cancel_order(order_id):
    db    = get_db()
    order = db.execute('SELECT * FROM production_orders WHERE id=?', (order_id,)).fetchone()
    db.close()
    if not order or order['status'] in ('completed', 'cancelled'):
        flash('Cannot cancel this order.', 'warning')
        return redirect(url_for('production.view_order', order_id=order_id))
    with db_conn() as conn:
        conn.execute("UPDATE production_orders SET status='cancelled' WHERE id=?", (order_id,))
    flash('Work order cancelled.', 'warning')
    return redirect(url_for('production.index'))

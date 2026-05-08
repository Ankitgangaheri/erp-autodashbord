"""Purchases Blueprint."""

from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from app.database import db_conn, get_db
from app.auth_helpers import login_required, manager_required

purchases_bp = Blueprint('purchases', __name__)
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


def _gen_po_number(conn):
    row = conn.execute('SELECT MAX(id) AS m FROM purchases').fetchone()
    num = (row['m'] or 0) + 1
    return f"PO-{datetime.utcnow().year}-{num:05d}"


@purchases_bp.route('/')
@login_required
def index():
    page   = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    status = request.args.get('status', '')
    db     = get_db()
    sql    = '''SELECT p.*,s.name AS supplier_name FROM purchases p
                JOIN suppliers s ON s.id=p.supplier_id WHERE 1=1'''
    args   = []
    if search:
        sql += ' AND (p.po_number LIKE ? OR s.name LIKE ?)'
        args += [f'%{search}%', f'%{search}%']
    if status:
        sql += ' AND p.status=?'
        args.append(status)
    sql += ' ORDER BY p.created_at DESC'
    rows = db.execute(sql, args).fetchall()
    db.close()
    purchases = _paginate([dict(r) for r in rows], page)
    return render_template('purchases/index.html',
                           purchases=purchases, search=search, status=status)


@purchases_bp.route('/create', methods=['GET', 'POST'])
@manager_required
def create_purchase():
    db        = get_db()
    suppliers = db.execute('SELECT * FROM suppliers WHERE is_active=1 ORDER BY name').fetchall()
    products  = db.execute('SELECT p.*,c.name AS cat_name FROM products p JOIN categories c ON c.id=p.category_id WHERE p.is_active=1 ORDER BY p.name').fetchall()
    db.close()

    if request.method == 'POST':
        supplier_id   = request.form.get('supplier_id', type=int)
        expected_date = request.form.get('expected_date', '')
        notes         = request.form.get('notes', '').strip()
        product_ids   = request.form.getlist('product_id[]')
        quantities    = request.form.getlist('quantity[]')
        unit_prices   = request.form.getlist('unit_price[]')

        if not supplier_id:
            flash('Select a supplier.', 'danger')
            return render_template('purchases/create_purchase.html',
                                   suppliers=[dict(s) for s in suppliers],
                                   products=[dict(p) for p in products])
        if not product_ids:
            flash('Add at least one product.', 'danger')
            return render_template('purchases/create_purchase.html',
                                   suppliers=[dict(s) for s in suppliers],
                                   products=[dict(p) for p in products])

        with db_conn() as conn:
            po_num = _gen_po_number(conn)
            exp    = expected_date if expected_date else None
            cur    = conn.execute(
                'INSERT INTO purchases (po_number,supplier_id,expected_date,notes,created_by) VALUES (?,?,?,?,?)',
                (po_num, supplier_id, exp, notes, session.get('user_id')))
            po_id  = cur.lastrowid
            total  = 0.0
            for pid, qty_s, price_s in zip(product_ids, quantities, unit_prices):
                try:
                    qty   = int(qty_s)
                    price = float(price_s)
                    if qty <= 0: continue
                    line  = qty * price
                    conn.execute(
                        'INSERT INTO purchase_items (purchase_id,product_id,quantity,unit_price,total_price) VALUES (?,?,?,?,?)',
                        (po_id, int(pid), qty, price, line))
                    total += line
                except (ValueError, TypeError):
                    continue
            conn.execute('UPDATE purchases SET total_amount=? WHERE id=?', (total, po_id))

        flash(f'Purchase Order {po_num} created.', 'success')
        return redirect(url_for('purchases.view_purchase', po_id=po_id))

    return render_template('purchases/create_purchase.html',
                           suppliers=[dict(s) for s in suppliers],
                           products=[dict(p) for p in products])


@purchases_bp.route('/view/<int:po_id>')
@login_required
def view_purchase(po_id):
    db  = get_db()
    po  = db.execute(
        'SELECT p.*,s.name AS supplier_name FROM purchases p JOIN suppliers s ON s.id=p.supplier_id WHERE p.id=?',
        (po_id,)).fetchone()
    if not po:
        flash('PO not found.', 'danger')
        return redirect(url_for('purchases.index'))
    items = db.execute(
        'SELECT pi.*,pr.name AS product_name,pr.sku,pr.unit FROM purchase_items pi JOIN products pr ON pr.id=pi.product_id WHERE pi.purchase_id=?',
        (po_id,)).fetchall()
    db.close()
    return render_template('purchases/view_purchase.html',
                           purchase=dict(po), items=[dict(i) for i in items])


@purchases_bp.route('/receive/<int:po_id>', methods=['POST'])
@manager_required
def receive_purchase(po_id):
    db = get_db()
    po = db.execute('SELECT * FROM purchases WHERE id=?', (po_id,)).fetchone()
    if not po or po['status'] != 'pending':
        flash('Only pending orders can be received.', 'warning')
        return redirect(url_for('purchases.view_purchase', po_id=po_id))
    items = db.execute('SELECT * FROM purchase_items WHERE purchase_id=?', (po_id,)).fetchall()
    db.close()

    with db_conn() as conn:
        for item in items:
            prod = conn.execute('SELECT * FROM products WHERE id=?', (item['product_id'],)).fetchone()
            if prod:
                old = prod['quantity']
                new = old + item['quantity']
                conn.execute("UPDATE products SET quantity=?,updated_at=datetime('now') WHERE id=?",
                             (new, prod['id']))
                conn.execute(
                    '''INSERT INTO stock_history (product_id,change_type,quantity_change,
                       quantity_before,quantity_after,reference_id,reference_type,notes,created_by)
                       VALUES (?,?,?,?,?,?,?,?,?)''',
                    (prod['id'], 'purchase', item['quantity'], old, new,
                     po_id, 'purchase', f"Received via PO {po['po_number']}", session.get('user_id')))
        conn.execute(
            "UPDATE purchases SET status='received',received_date=datetime('now') WHERE id=?", (po_id,))

    flash(f"PO {po['po_number']} received. Stock updated.", 'success')
    return redirect(url_for('purchases.view_purchase', po_id=po_id))


@purchases_bp.route('/cancel/<int:po_id>', methods=['POST'])
@manager_required
def cancel_purchase(po_id):
    db = get_db()
    po = db.execute('SELECT * FROM purchases WHERE id=?', (po_id,)).fetchone()
    db.close()
    if not po or po['status'] == 'received':
        flash('Cannot cancel.', 'danger')
        return redirect(url_for('purchases.view_purchase', po_id=po_id))
    with db_conn() as conn:
        conn.execute("UPDATE purchases SET status='cancelled' WHERE id=?", (po_id,))
    flash('Purchase order cancelled.', 'warning')
    return redirect(url_for('purchases.index'))

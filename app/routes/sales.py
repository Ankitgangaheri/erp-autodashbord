"""Sales Blueprint."""

from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from app.database import db_conn, get_db
from app.auth_helpers import login_required, manager_required

sales_bp = Blueprint('sales', __name__)
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


def _gen_invoice(conn):
    row = conn.execute('SELECT MAX(id) AS m FROM sales').fetchone()
    num = (row['m'] or 0) + 1
    return f"INV-{datetime.utcnow().year}-{num:05d}"


@sales_bp.route('/')
@login_required
def index():
    page   = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    status = request.args.get('status', '')
    db     = get_db()
    sql    = 'SELECT * FROM sales WHERE 1=1'
    args   = []
    if search:
        sql += ' AND (invoice_number LIKE ? OR customer_name LIKE ?)'
        args += [f'%{search}%', f'%{search}%']
    if status:
        sql += ' AND status=?'
        args.append(status)
    sql += ' ORDER BY created_at DESC'
    rows = db.execute(sql, args).fetchall()
    db.close()
    sales = _paginate([dict(r) for r in rows], page)
    return render_template('sales/index.html', sales=sales, search=search, status=status)


@sales_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create_sale():
    db        = get_db()
    products  = db.execute(
        'SELECT p.*,c.name AS cat_name FROM products p JOIN categories c ON c.id=p.category_id WHERE p.is_active=1 AND p.quantity>0 ORDER BY p.name').fetchall()
    customers = db.execute('SELECT * FROM customers ORDER BY name').fetchall()
    db.close()

    if request.method == 'POST':
        cust_id     = request.form.get('customer_id', '') or None
        cust_name   = request.form.get('customer_name', 'Walk-in Customer').strip()
        payment     = request.form.get('payment_method', 'cash')
        discount    = request.form.get('discount', 0, type=float)
        tax         = request.form.get('tax', 0, type=float)
        notes       = request.form.get('notes', '').strip()
        product_ids = request.form.getlist('product_id[]')
        quantities  = request.form.getlist('quantity[]')
        unit_prices = request.form.getlist('unit_price[]')

        if not product_ids:
            flash('Add at least one product.', 'danger')
            return render_template('sales/create_sale.html',
                                   products=[dict(p) for p in products],
                                   customers=[dict(c) for c in customers])

        # Validate stock
        items_data = []
        errors     = []
        db2        = get_db()
        for pid, qty_s, price_s in zip(product_ids, quantities, unit_prices):
            try:
                qty   = int(qty_s)
                price = float(price_s)
                if qty <= 0: continue
                prod  = db2.execute('SELECT * FROM products WHERE id=?', (int(pid),)).fetchone()
                if not prod:
                    errors.append(f'Product ID {pid} not found.')
                    continue
                if prod['quantity'] < qty:
                    errors.append(f'Insufficient stock for {prod["name"]}. Available: {prod["quantity"]}')
                    continue
                items_data.append({'prod': dict(prod), 'qty': qty, 'price': price})
            except (ValueError, TypeError):
                continue
        db2.close()

        if errors:
            for e in errors: flash(e, 'danger')
            return render_template('sales/create_sale.html',
                                   products=[dict(p) for p in products],
                                   customers=[dict(c) for c in customers])

        with db_conn() as conn:
            inv_num  = _gen_invoice(conn)
            subtotal = sum(d['qty'] * d['price'] for d in items_data)
            tax_amt  = subtotal * (tax / 100)
            total    = subtotal - discount + tax_amt

            cur = conn.execute(
                '''INSERT INTO sales (invoice_number,customer_id,customer_name,payment_method,
                   subtotal,discount,tax,total_amount,notes,created_by)
                   VALUES (?,?,?,?,?,?,?,?,?,?)''',
                (inv_num, cust_id, cust_name, payment,
                 subtotal, discount, tax, total, notes, session.get('user_id')))
            sale_id = cur.lastrowid

            for d in items_data:
                p   = d['prod']
                qty = d['qty']
                conn.execute(
                    'INSERT INTO sale_items (sale_id,product_id,quantity,unit_price,total_price) VALUES (?,?,?,?,?)',
                    (sale_id, p['id'], qty, d['price'], qty * d['price']))
                old = p['quantity']
                new = old - qty
                conn.execute("UPDATE products SET quantity=?,updated_at=datetime('now') WHERE id=?",
                             (new, p['id']))
                conn.execute(
                    '''INSERT INTO stock_history (product_id,change_type,quantity_change,
                       quantity_before,quantity_after,reference_id,reference_type,notes,created_by)
                       VALUES (?,?,?,?,?,?,?,?,?)''',
                    (p['id'], 'sale', -qty, old, new, sale_id, 'sale',
                     f'Sold via {inv_num}', session.get('user_id')))

        flash(f'Invoice {inv_num} created. Stock updated.', 'success')
        return redirect(url_for('sales.view_sale', sale_id=sale_id))

    return render_template('sales/create_sale.html',
                           products=[dict(p) for p in products],
                           customers=[dict(c) for c in customers])


@sales_bp.route('/view/<int:sale_id>')
@login_required
def view_sale(sale_id):
    db   = get_db()
    sale = db.execute('SELECT * FROM sales WHERE id=?', (sale_id,)).fetchone()
    if not sale:
        flash('Invoice not found.', 'danger')
        return redirect(url_for('sales.index'))
    items = db.execute(
        'SELECT si.*,p.name AS product_name,p.sku,p.unit FROM sale_items si JOIN products p ON p.id=si.product_id WHERE si.sale_id=?',
        (sale_id,)).fetchall()
    db.close()
    return render_template('sales/view_sale.html',
                           sale=dict(sale), items=[dict(i) for i in items])


@sales_bp.route('/cancel/<int:sale_id>', methods=['POST'])
@manager_required
def cancel_sale(sale_id):
    db   = get_db()
    sale = db.execute('SELECT * FROM sales WHERE id=?', (sale_id,)).fetchone()
    if not sale or sale['status'] == 'cancelled':
        flash('Cannot cancel.', 'warning')
        return redirect(url_for('sales.index'))
    items = db.execute('SELECT * FROM sale_items WHERE sale_id=?', (sale_id,)).fetchall()
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
                    (prod['id'], 'sale_cancellation', item['quantity'], old, new,
                     sale_id, 'sale', f"Restored — {sale['invoice_number']} cancelled",
                     session.get('user_id')))
        conn.execute("UPDATE sales SET status='cancelled' WHERE id=?", (sale_id,))

    flash(f"Invoice {sale['invoice_number']} cancelled. Stock restored.", 'warning')
    return redirect(url_for('sales.index'))


# ── Customers ──

@sales_bp.route('/customers')
@login_required
def customers():
    page   = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    db     = get_db()
    if search:
        rows = db.execute(
            'SELECT * FROM customers WHERE name LIKE ? OR email LIKE ? OR phone LIKE ? ORDER BY name',
            (f'%{search}%',)*3).fetchall()
    else:
        rows = db.execute('SELECT * FROM customers ORDER BY name').fetchall()
    db.close()
    custs = _paginate([dict(r) for r in rows], page)
    return render_template('sales/customers.html', customers=custs, search=search)


@sales_bp.route('/customers/add', methods=['GET', 'POST'])
@login_required
def add_customer():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        if not name:
            flash('Customer name required.', 'danger')
            return render_template('sales/add_customer.html')
        with db_conn() as conn:
            conn.execute(
                'INSERT INTO customers (name,email,phone,address,city,gst_number) VALUES (?,?,?,?,?,?)',
                (name,
                 request.form.get('email','').strip(),
                 request.form.get('phone','').strip(),
                 request.form.get('address','').strip(),
                 request.form.get('city','').strip(),
                 request.form.get('gst_number','').strip()))
        flash(f'Customer "{name}" added.', 'success')
        return redirect(url_for('sales.customers'))
    return render_template('sales/add_customer.html')

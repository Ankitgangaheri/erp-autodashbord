"""Inventory Blueprint — products, categories, stock adjustment."""

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, session
from app.database import db_conn, get_db
from app.auth_helpers import login_required, manager_required, admin_required

inventory_bp = Blueprint('inventory', __name__)
PER_PAGE = 15


class _Page:
    """Pagination container with attribute access for templates."""
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


def _paginate(query_rows, page, per_page=PER_PAGE):
    total = len(query_rows)
    items = query_rows[(page-1)*per_page : page*per_page]
    pages = max(1, (total + per_page - 1) // per_page)
    return _Page(items, total, page, pages, per_page)


@inventory_bp.route('/')
@login_required
def index():
    page       = request.args.get('page', 1, type=int)
    search     = request.args.get('search', '')
    cat_filter = request.args.get('category', '')
    status_f   = request.args.get('status', 'active')

    db   = get_db()
    cats = db.execute('SELECT * FROM categories ORDER BY name').fetchall()

    sql  = '''SELECT p.*,c.name AS cat_name FROM products p
              JOIN categories c ON c.id=p.category_id WHERE 1=1'''
    args = []

    if status_f == 'active':   sql += ' AND p.is_active=1'
    elif status_f == 'inactive': sql += ' AND p.is_active=0'
    if search:
        sql += ' AND (p.name LIKE ? OR p.sku LIKE ?)'
        args += [f'%{search}%', f'%{search}%']
    if cat_filter:
        sql += ' AND p.category_id=?'
        args.append(int(cat_filter))
    sql += ' ORDER BY p.name'

    rows = db.execute(sql, args).fetchall()
    db.close()
    products = _paginate([dict(r) for r in rows], page)

    return render_template('inventory/index.html',
        products=products, categories=[dict(c) for c in cats],
        search=search, category_id=cat_filter, status_filter=status_f)


@inventory_bp.route('/add', methods=['GET', 'POST'])
@manager_required
def add_product():
    db   = get_db()
    cats = db.execute('SELECT * FROM categories ORDER BY name').fetchall()
    db.close()

    if request.method == 'POST':
        sku        = request.form.get('sku', '').strip().upper()
        name       = request.form.get('name', '').strip()
        cat_id     = request.form.get('category_id', type=int)
        desc       = request.form.get('description', '').strip()
        unit       = request.form.get('unit', 'pcs')
        cost       = request.form.get('cost_price', 0, type=float)
        sell       = request.form.get('selling_price', 0, type=float)
        qty        = request.form.get('quantity', 0, type=int)
        threshold  = request.form.get('low_stock_threshold', 10, type=int)

        errors = []
        if not sku:  errors.append('SKU required.')
        if not name: errors.append('Name required.')
        if not cat_id: errors.append('Category required.')
        db2 = get_db()
        if db2.execute('SELECT id FROM products WHERE sku=?', (sku,)).fetchone():
            errors.append(f'SKU {sku} already exists.')
        db2.close()

        if errors:
            for e in errors: flash(e, 'danger')
            return render_template('inventory/add_product.html', categories=[dict(c) for c in cats])

        with db_conn() as conn:
            cur = conn.execute(
                '''INSERT INTO products (sku,name,description,category_id,unit,
                   cost_price,selling_price,quantity,low_stock_threshold)
                   VALUES (?,?,?,?,?,?,?,?,?)''',
                (sku, name, desc, cat_id, unit, cost, sell, qty, threshold))
            pid = cur.lastrowid
            if qty > 0:
                conn.execute(
                    '''INSERT INTO stock_history (product_id,change_type,quantity_change,
                       quantity_before,quantity_after,notes,created_by)
                       VALUES (?,?,?,?,?,?,?)''',
                    (pid, 'initial', qty, 0, qty, 'Initial stock entry', session.get('user_id')))
        flash(f'Product "{name}" added.', 'success')
        return redirect(url_for('inventory.index'))

    return render_template('inventory/add_product.html', categories=[dict(c) for c in cats])


@inventory_bp.route('/edit/<int:pid>', methods=['GET', 'POST'])
@manager_required
def edit_product(pid):
    db   = get_db()
    prod = db.execute('SELECT * FROM products WHERE id=?', (pid,)).fetchone()
    cats = db.execute('SELECT * FROM categories ORDER BY name').fetchall()
    db.close()
    if not prod:
        flash('Product not found.', 'danger')
        return redirect(url_for('inventory.index'))

    if request.method == 'POST':
        with db_conn() as conn:
            conn.execute(
                '''UPDATE products SET name=?,description=?,category_id=?,unit=?,
                   cost_price=?,selling_price=?,low_stock_threshold=?,is_active=?,
                   updated_at=datetime('now') WHERE id=?''',
                (request.form.get('name','').strip(),
                 request.form.get('description','').strip(),
                 request.form.get('category_id', type=int),
                 request.form.get('unit','pcs'),
                 request.form.get('cost_price', 0, type=float),
                 request.form.get('selling_price', 0, type=float),
                 request.form.get('low_stock_threshold', 10, type=int),
                 1 if request.form.get('is_active') else 0,
                 pid))
        flash('Product updated.', 'success')
        return redirect(url_for('inventory.index'))

    return render_template('inventory/edit_product.html',
                           product=dict(prod), categories=[dict(c) for c in cats])


@inventory_bp.route('/view/<int:pid>')
@login_required
def view_product(pid):
    db   = get_db()
    prod = db.execute(
        'SELECT p.*,c.name AS cat_name FROM products p JOIN categories c ON c.id=p.category_id WHERE p.id=?',
        (pid,)).fetchone()
    if not prod:
        flash('Product not found.', 'danger')
        return redirect(url_for('inventory.index'))
    hist = db.execute(
        '''SELECT sh.*,u.username FROM stock_history sh
           LEFT JOIN users u ON u.id=sh.created_by
           WHERE sh.product_id=? ORDER BY sh.created_at DESC LIMIT 20''', (pid,)).fetchall()
    db.close()
    return render_template('inventory/view_product.html',
                           product=dict(prod), history=[dict(h) for h in hist])


@inventory_bp.route('/adjust/<int:pid>', methods=['POST'])
@manager_required
def adjust_stock(pid):
    db   = get_db()
    prod = db.execute('SELECT * FROM products WHERE id=?', (pid,)).fetchone()
    db.close()
    if not prod:
        flash('Product not found.', 'danger')
        return redirect(url_for('inventory.index'))

    adj   = request.form.get('adjustment', 0, type=int)
    notes = request.form.get('notes', 'Manual adjustment')
    old   = prod['quantity']
    new   = old + adj

    if new < 0:
        flash('Adjustment would result in negative stock.', 'danger')
        return redirect(url_for('inventory.view_product', pid=pid))

    with db_conn() as conn:
        conn.execute("UPDATE products SET quantity=?,updated_at=datetime('now') WHERE id=?", (new, pid))
        conn.execute(
            '''INSERT INTO stock_history (product_id,change_type,quantity_change,
               quantity_before,quantity_after,notes,created_by) VALUES (?,?,?,?,?,?,?)''',
            (pid, 'adjustment', adj, old, new, notes, session.get('user_id')))
    flash(f'Stock adjusted by {adj:+d}. New quantity: {new}', 'success')
    return redirect(url_for('inventory.view_product', pid=pid))


@inventory_bp.route('/delete/<int:pid>', methods=['POST'])
@admin_required
def delete_product(pid):
    with db_conn() as conn:
        conn.execute('UPDATE products SET is_active=0 WHERE id=?', (pid,))
    flash('Product deactivated.', 'success')
    return redirect(url_for('inventory.index'))


# ── Categories ──

@inventory_bp.route('/categories')
@login_required
def categories():
    db   = get_db()
    cats = db.execute('SELECT * FROM categories ORDER BY name').fetchall()
    counts = {r['category_id']: r['cnt'] for r in
              db.execute('SELECT category_id, COUNT(*) AS cnt FROM products GROUP BY category_id').fetchall()}
    db.close()
    return render_template('inventory/categories.html',
                           categories=[dict(c) for c in cats], counts=counts)


@inventory_bp.route('/categories/add', methods=['POST'])
@manager_required
def add_category():
    name = request.form.get('name', '').strip()
    desc = request.form.get('description', '').strip()
    if not name:
        flash('Category name required.', 'danger')
        return redirect(url_for('inventory.categories'))
    db = get_db()
    if db.execute('SELECT id FROM categories WHERE name=?', (name,)).fetchone():
        db.close()
        flash('Category already exists.', 'danger')
        return redirect(url_for('inventory.categories'))
    db.close()
    with db_conn() as conn:
        conn.execute('INSERT INTO categories (name,description) VALUES (?,?)', (name, desc))
    flash(f'Category "{name}" added.', 'success')
    return redirect(url_for('inventory.categories'))


@inventory_bp.route('/low-stock')
@login_required
def low_stock():
    db    = get_db()
    items = db.execute(
        '''SELECT p.*,c.name AS cat_name FROM products p
           JOIN categories c ON c.id=p.category_id
           WHERE p.quantity<=p.low_stock_threshold AND p.is_active=1
           ORDER BY p.quantity ASC''').fetchall()
    db.close()
    return render_template('inventory/low_stock.html', items=[dict(i) for i in items])


# ── API endpoints for JS autocomplete ──

@inventory_bp.route('/api/product/<int:pid>')
@login_required
def api_product(pid):
    db   = get_db()
    prod = db.execute('SELECT * FROM products WHERE id=?', (pid,)).fetchone()
    db.close()
    if not prod:
        return jsonify({'error': 'Not found'}), 404
    p = dict(prod)
    return jsonify({'id': p['id'], 'name': p['name'], 'sku': p['sku'],
                    'unit': p['unit'], 'cost_price': p['cost_price'],
                    'selling_price': p['selling_price'], 'quantity': p['quantity']})


@inventory_bp.route('/api/products/search')
@login_required
def api_search_products():
    q  = request.args.get('q', '')
    db = get_db()
    rows = db.execute(
        '''SELECT id,name,sku,unit,quantity,selling_price,cost_price FROM products
           WHERE (name LIKE ? OR sku LIKE ?) AND is_active=1 AND quantity>0 LIMIT 10''',
        (f'%{q}%', f'%{q}%')).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

"""Suppliers Blueprint."""

from flask import Blueprint, render_template, redirect, url_for, flash, request
from app.database import db_conn, get_db
from app.auth_helpers import login_required, manager_required, admin_required

suppliers_bp = Blueprint('suppliers', __name__)
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


@suppliers_bp.route('/')
@login_required
def index():
    page   = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    db     = get_db()
    if search:
        rows = db.execute(
            '''SELECT s.*,
               (SELECT COUNT(*) FROM purchases WHERE supplier_id=s.id) AS purchase_count,
               (SELECT COALESCE(SUM(total_amount),0) FROM purchases WHERE supplier_id=s.id) AS total_purchases
               FROM suppliers s
               WHERE s.name LIKE ? OR s.contact_person LIKE ? OR s.email LIKE ?
               ORDER BY s.name''',
            (f'%{search}%',)*3).fetchall()
    else:
        rows = db.execute(
            '''SELECT s.*,
               (SELECT COUNT(*) FROM purchases WHERE supplier_id=s.id) AS purchase_count,
               (SELECT COALESCE(SUM(total_amount),0) FROM purchases WHERE supplier_id=s.id) AS total_purchases
               FROM suppliers s ORDER BY s.name''').fetchall()
    db.close()
    suppliers = _paginate([dict(r) for r in rows], page)
    return render_template('suppliers/index.html', suppliers=suppliers, search=search)


@suppliers_bp.route('/add', methods=['GET', 'POST'])
@manager_required
def add_supplier():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        if not name:
            flash('Supplier name required.', 'danger')
            return render_template('suppliers/add_supplier.html')
        with db_conn() as conn:
            conn.execute(
                '''INSERT INTO suppliers (name,contact_person,email,phone,address,city,country,gst_number,payment_terms)
                   VALUES (?,?,?,?,?,?,?,?,?)''',
                (name,
                 request.form.get('contact_person','').strip(),
                 request.form.get('email','').strip(),
                 request.form.get('phone','').strip(),
                 request.form.get('address','').strip(),
                 request.form.get('city','').strip(),
                 request.form.get('country','India').strip(),
                 request.form.get('gst_number','').strip(),
                 request.form.get('payment_terms','').strip()))
        flash(f'Supplier "{name}" added.', 'success')
        return redirect(url_for('suppliers.index'))
    return render_template('suppliers/add_supplier.html')


@suppliers_bp.route('/edit/<int:sid>', methods=['GET', 'POST'])
@manager_required
def edit_supplier(sid):
    db  = get_db()
    sup = db.execute('SELECT * FROM suppliers WHERE id=?', (sid,)).fetchone()
    db.close()
    if not sup:
        flash('Supplier not found.', 'danger')
        return redirect(url_for('suppliers.index'))

    if request.method == 'POST':
        with db_conn() as conn:
            conn.execute(
                '''UPDATE suppliers SET name=?,contact_person=?,email=?,phone=?,address=?,
                   city=?,country=?,gst_number=?,payment_terms=?,is_active=?,updated_at=datetime('now') WHERE id=?''',
                (request.form.get('name','').strip(),
                 request.form.get('contact_person','').strip(),
                 request.form.get('email','').strip(),
                 request.form.get('phone','').strip(),
                 request.form.get('address','').strip(),
                 request.form.get('city','').strip(),
                 request.form.get('country','India').strip(),
                 request.form.get('gst_number','').strip(),
                 request.form.get('payment_terms','').strip(),
                 1 if request.form.get('is_active') else 0,
                 sid))
        flash('Supplier updated.', 'success')
        return redirect(url_for('suppliers.index'))
    return render_template('suppliers/edit_supplier.html', supplier=dict(sup))


@suppliers_bp.route('/view/<int:sid>')
@login_required
def view_supplier(sid):
    db  = get_db()
    sup = db.execute(
        '''SELECT s.*,
           (SELECT COUNT(*) FROM purchases WHERE supplier_id=s.id) AS purchase_count,
           (SELECT COALESCE(SUM(total_amount),0) FROM purchases WHERE supplier_id=s.id) AS total_purchases
           FROM suppliers s WHERE s.id=?''', (sid,)).fetchone()
    if not sup:
        flash('Supplier not found.', 'danger')
        return redirect(url_for('suppliers.index'))
    purchases = db.execute(
        'SELECT * FROM purchases WHERE supplier_id=? ORDER BY created_at DESC LIMIT 10', (sid,)).fetchall()
    db.close()
    return render_template('suppliers/view_supplier.html',
                           supplier=dict(sup), purchases=[dict(p) for p in purchases])

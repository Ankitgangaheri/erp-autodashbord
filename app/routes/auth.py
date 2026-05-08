"""Auth Blueprint — login, logout, user management."""

from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from werkzeug.security import generate_password_hash, check_password_hash
from app.database import db_conn, get_db
from app.auth_helpers import login_required, admin_required

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('user_id'):
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if not username or not password:
            flash('Enter both username and password.', 'danger')
            return render_template('auth/login.html')

        db = get_db()
        user = db.execute('SELECT * FROM users WHERE username=? AND is_active=1',
                          (username,)).fetchone()
        db.close()

        if user and check_password_hash(user['password_hash'], password):
            session.permanent = request.form.get('remember') == 'on'
            session['user_id']   = user['id']
            session['user_name'] = user['full_name']
            session['user_role'] = user['role']
            with db_conn() as conn:
                conn.execute("UPDATE users SET last_login=? WHERE id=?",
                             (datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'), user['id']))
            flash(f"Welcome back, {user['full_name']}!", 'success')
            return redirect(request.args.get('next') or url_for('dashboard.index'))
        else:
            flash('Invalid username or password.', 'danger')

    return render_template('auth/login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/users')
@admin_required
def users():
    db = get_db()
    users_list = db.execute('SELECT * FROM users ORDER BY created_at DESC').fetchall()
    db.close()
    return render_template('auth/users.html', users=[dict(u) for u in users_list])


@auth_bp.route('/users/add', methods=['GET', 'POST'])
@admin_required
def add_user():
    if request.method == 'POST':
        username  = request.form.get('username', '').strip()
        email     = request.form.get('email', '').strip()
        full_name = request.form.get('full_name', '').strip()
        role      = request.form.get('role', 'staff')
        password  = request.form.get('password', '')

        errors = []
        if not username:  errors.append('Username required.')
        if not email:     errors.append('Email required.')
        if not full_name: errors.append('Full name required.')
        if len(password) < 6: errors.append('Password must be ≥ 6 chars.')

        db = get_db()
        if db.execute('SELECT id FROM users WHERE username=?', (username,)).fetchone():
            errors.append('Username already exists.')
        if db.execute('SELECT id FROM users WHERE email=?', (email,)).fetchone():
            errors.append('Email already exists.')
        db.close()

        if errors:
            for e in errors: flash(e, 'danger')
            return render_template('auth/add_user.html')

        with db_conn() as conn:
            conn.execute(
                'INSERT INTO users (username,email,full_name,password_hash,role) VALUES (?,?,?,?,?)',
                (username, email, full_name, generate_password_hash(password), role)
            )
        flash(f'User {full_name} created.', 'success')
        return redirect(url_for('auth.users'))

    return render_template('auth/add_user.html')


@auth_bp.route('/users/edit/<int:uid>', methods=['GET', 'POST'])
@admin_required
def edit_user(uid):
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
    db.close()
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('auth.users'))

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email     = request.form.get('email', '').strip()
        role      = request.form.get('role', 'staff')
        is_active = 1 if request.form.get('is_active') else 0
        new_pwd   = request.form.get('password', '').strip()

        if new_pwd and len(new_pwd) < 6:
            flash('Password must be ≥ 6 chars.', 'danger')
            return render_template('auth/edit_user.html', user=dict(user))

        with db_conn() as conn:
            if new_pwd:
                conn.execute(
                    'UPDATE users SET full_name=?,email=?,role=?,is_active=?,password_hash=? WHERE id=?',
                    (full_name, email, role, is_active, generate_password_hash(new_pwd), uid)
                )
            else:
                conn.execute(
                    'UPDATE users SET full_name=?,email=?,role=?,is_active=? WHERE id=?',
                    (full_name, email, role, is_active, uid)
                )
        flash('User updated.', 'success')
        return redirect(url_for('auth.users'))

    return render_template('auth/edit_user.html', user=dict(user))


@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        full_name    = request.form.get('full_name', '').strip()
        email        = request.form.get('email', '').strip()
        cur_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')

        if not full_name or not email:
            flash('Name and email required.', 'danger')
            return render_template('auth/profile.html')

        uid = session['user_id']
        db  = get_db()
        user = db.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
        db.close()

        if new_password:
            if not check_password_hash(user['password_hash'], cur_password):
                flash('Current password incorrect.', 'danger')
                return render_template('auth/profile.html')
            if len(new_password) < 6:
                flash('New password must be ≥ 6 chars.', 'danger')
                return render_template('auth/profile.html')
            with db_conn() as conn:
                conn.execute(
                    'UPDATE users SET full_name=?,email=?,password_hash=? WHERE id=?',
                    (full_name, email, generate_password_hash(new_password), uid)
                )
        else:
            with db_conn() as conn:
                conn.execute('UPDATE users SET full_name=?,email=? WHERE id=?',
                             (full_name, email, uid))

        session['user_name'] = full_name
        flash('Profile updated.', 'success')
    return render_template('auth/profile.html')

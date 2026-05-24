from flask import Flask, render_template, request, redirect, url_for, flash, session
import sqlite3
import json
from datetime import datetime
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'feite-erp-2024'

DB_PATH = 'erp.db'


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            username     TEXT    NOT NULL UNIQUE,
            password     TEXT    NOT NULL,
            display_name TEXT    DEFAULT '',
            role         TEXT    DEFAULT 'staff'
        );
        CREATE TABLE IF NOT EXISTS outbound_orders (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            recipient_name   TEXT    NOT NULL,
            phone            TEXT    NOT NULL,
            region           TEXT,
            address          TEXT,
            logistics        TEXT,
            tracking_number  TEXT,
            shipping_fee     REAL    DEFAULT 0,
            shipping_payment TEXT    DEFAULT 'prepaid',
            warehouse        TEXT,
            payment_method   TEXT,
            payment_note     TEXT,
            cod_amount       REAL    DEFAULT 0,
            total_amount     REAL    DEFAULT 0,
            discount         REAL    DEFAULT 0,
            deposit          REAL    DEFAULT 0,
            prepaid_deposit  REAL    DEFAULT 0,
            prepaid_goods    REAL    DEFAULT 0,
            handling_fee     REAL    DEFAULT 0,
            salesperson      TEXT,
            order_time       TEXT,
            remark           TEXT,
            status           TEXT    DEFAULT '处理中',
            created_at       TEXT    DEFAULT (datetime('now', 'localtime'))
        );
        CREATE TABLE IF NOT EXISTS outbound_goods (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id    INTEGER NOT NULL,
            goods_name  TEXT,
            spec        TEXT,
            unit        TEXT    DEFAULT '袋',
            quantity    REAL    DEFAULT 0,
            unit_price  REAL    DEFAULT 0,
            amount      REAL    DEFAULT 0,
            note        TEXT,
            is_gift     INTEGER DEFAULT 0,
            FOREIGN KEY (order_id) REFERENCES outbound_orders(id)
        );
    ''')
    # 默认管理员账号（仅首次运行时创建）
    if not conn.execute("SELECT id FROM users WHERE username = 'admin'").fetchone():
        conn.execute(
            "INSERT INTO users (username, password, display_name, role) VALUES (?,?,?,?)",
            ('admin', generate_password_hash('admin123'), '管理员', 'admin')
        )
    conn.commit()
    conn.close()


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('请先登录', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('outbound_list'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        conn = get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        conn.close()
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['display_name'] or user['username']
            session['role'] = user['role']
            return redirect(url_for('outbound_list'))
        flash('用户名或密码错误', 'danger')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/')
def index():
    return redirect(url_for('outbound_list'))


@app.route('/outbound')
@login_required
def outbound_list():
    conn = get_db()
    orders = conn.execute(
        'SELECT * FROM outbound_orders ORDER BY created_at DESC'
    ).fetchall()

    today = datetime.now().strftime('%Y-%m-%d')
    row = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(total_amount), 0) FROM outbound_orders "
        "WHERE date(created_at) = ?", (today,)
    ).fetchone()
    conn.close()

    stats = {
        'today_count': row[0],
        'total_orders': len(orders),
        'today_amount': row[1],
    }
    return render_template('outbound_list.html', orders=orders, stats=stats)


@app.route('/outbound/new', methods=['GET', 'POST'])
@login_required
def outbound_new():
    if request.method == 'POST':
        f = request.form
        conn = get_db()
        try:
            cur = conn.execute('''
                INSERT INTO outbound_orders
                    (recipient_name, phone, region, address, logistics, tracking_number,
                     shipping_fee, shipping_payment, warehouse, payment_method, payment_note,
                     cod_amount, total_amount, discount, deposit, prepaid_deposit, prepaid_goods,
                     handling_fee, salesperson, order_time, remark, status)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ''', (
                f.get('recipient_name', '').strip(),
                f.get('phone', '').strip(),
                f.get('region', ''),
                f.get('address', '').strip(),
                f.get('logistics', ''),
                f.get('tracking_number', '').strip(),
                float(f.get('shipping_fee') or 0),
                f.get('shipping_payment', 'prepaid'),
                f.get('warehouse', ''),
                f.get('payment_method', ''),
                f.get('payment_note', '').strip(),
                float(f.get('cod_amount') or 0),
                float(f.get('total_amount') or 0),
                float(f.get('discount') or 0),
                float(f.get('deposit') or 0),
                float(f.get('prepaid_deposit') or 0),
                float(f.get('prepaid_goods') or 0),
                float(f.get('handling_fee') or 0),
                f.get('salesperson', ''),
                f.get('order_time', datetime.now().strftime('%Y-%m-%dT%H:%M')),
                f.get('remark', '').strip(),
                '处理中',
            ))
            order_id = cur.lastrowid

            goods_list = json.loads(f.get('goods_data', '[]'))
            for g in goods_list:
                name = g.get('name', '').strip()
                if name:
                    conn.execute('''
                        INSERT INTO outbound_goods
                            (order_id, goods_name, spec, unit, quantity, unit_price, amount, note, is_gift)
                        VALUES (?,?,?,?,?,?,?,?,?)
                    ''', (
                        order_id, name,
                        g.get('spec', '').strip(),
                        g.get('unit', '袋'),
                        float(g.get('quantity') or 0),
                        float(g.get('unit_price') or 0),
                        float(g.get('amount') or 0),
                        g.get('note', '').strip(),
                        1 if g.get('is_gift') else 0,
                    ))
            conn.commit()
            flash('出库单保存成功！', 'success')
        except Exception as e:
            conn.rollback()
            flash(f'保存失败：{str(e)}', 'danger')
        finally:
            conn.close()
        return redirect(url_for('outbound_list'))

    now = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    return render_template('outbound_form.html', now=now)


if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)

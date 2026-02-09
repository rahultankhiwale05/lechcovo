import os
import secrets
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2
from psycopg2.extras import DictCursor

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

DATABASE_URL = os.environ.get('DATABASE_URL')
ADMIN_SECRET_TOKEN = os.environ.get('ADMIN_SECRET_TOKEN')
LOCAL_TZ = ZoneInfo("Europe/Paris")

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

def get_db():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

class User(UserMixin):
    def __init__(self, id, name, email, is_admin):
        self.id = id
        self.name = name
        self.email = email
        self.is_admin = bool(is_admin)

@login_manager.user_loader
def load_user(user_id):
    conn = get_db()
    cur = conn.cursor(cursor_factory=DictCursor)
    cur.execute("SELECT id, name, email, is_admin FROM users WHERE id = %s", (user_id,))
    u = cur.fetchone()
    cur.close(); conn.close()
    if u: return User(u['id'], u['name'], u['email'], u['is_admin'])
    return None

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS users (id SERIAL PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL, password TEXT NOT NULL, is_admin BOOLEAN DEFAULT FALSE)")
    cur.execute("CREATE TABLE IF NOT EXISTS rides (id SERIAL PRIMARY KEY, departure TEXT NOT NULL, destination TEXT NOT NULL, date TEXT NOT NULL, time TEXT NOT NULL, seats INTEGER NOT NULL, departure_ts INTEGER NOT NULL, contact TEXT NOT NULL, active BOOLEAN DEFAULT TRUE, user_id INTEGER REFERENCES users(id) ON DELETE CASCADE)")
    cur.execute("CREATE TABLE IF NOT EXISTS reservations (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id) ON DELETE CASCADE, ride_id INTEGER REFERENCES rides(id) ON DELETE CASCADE, status TEXT DEFAULT 'confirmed', UNIQUE(user_id, ride_id))")
    conn.commit(); cur.close(); conn.close()

if DATABASE_URL: init_db()

@app.route('/')
def index():
    conn = get_db()
    cur = conn.cursor(cursor_factory=DictCursor)
    user_reservations = []
    if current_user.is_authenticated:
        cur.execute("SELECT ride_id FROM reservations WHERE user_id = %s AND status = 'confirmed'", (current_user.id,))
        user_reservations = [r['ride_id'] for r in cur.fetchall()]

    cur.execute("SELECT r.*, u.name as driver_name FROM rides r LEFT JOIN users u ON r.user_id = u.id WHERE r.active = TRUE ORDER BY r.departure_ts ASC")
    rides = cur.fetchall()
    cur.close(); conn.close()
    return render_template('index.html', rides=rides, user_reservations=user_reservations)

@app.route('/publish', methods=['POST'])
@login_required
def publish():
    try:
        raw_date = request.form['date'] # YYYY-MM-DD from browser
        dt_obj = datetime.strptime(raw_date, "%Y-%m-%d")
        formatted_date = dt_obj.strftime("%d-%m-%Y") # Save as DD-MM-YYYY

        dt_str = f"{raw_date} {request.form['time']}"
        local_dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M").replace(tzinfo=LOCAL_TZ)
        
        conn = get_db()
        cur = conn.cursor()
        cur.execute("INSERT INTO rides (user_id, departure, destination, date, time, seats, departure_ts, contact) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                   (current_user.id, request.form['departure'], request.form['destination'], formatted_date, request.form['time'], int(request.form['seats']), int(local_dt.timestamp()), request.form['contact']))
        conn.commit(); cur.close(); conn.close()
    except Exception as e: flash(f"Erreur: {e}")
    return redirect(url_for('index'))

@app.route('/delete-account', methods=['POST'])
@login_required
def delete_account():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM users WHERE id = %s", (current_user.id,)) # Right to erasure
    conn.commit(); cur.close(); conn.close()
    logout_user()
    flash("Votre compte et vos données ont été supprimés.")
    return redirect(url_for('index'))

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        is_admin = (request.form.get('admin_token') == ADMIN_SECRET_TOKEN) if ADMIN_SECRET_TOKEN else False
        conn = get_db()
        cur = conn.cursor()
        try:
            cur.execute("INSERT INTO users (name, email, password, is_admin) VALUES (%s, %s, %s, %s)",
                       (request.form['name'], request.form['email'], generate_password_hash(request.form['password']), is_admin))
            conn.commit()
            return redirect(url_for('login'))
        except: flash("Email déjà utilisé.")
        finally: cur.close(); conn.close()
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        conn = get_db()
        cur = conn.cursor(cursor_factory=DictCursor)
        cur.execute("SELECT * FROM users WHERE email = %s", (request.form['email'],))
        u = cur.fetchone()
        cur.close(); conn.close()
        if u and check_password_hash(u['password'], request.form['password']):
            login_user(User(u['id'], u['name'], u['email'], u['is_admin']))
            return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/reserve/<int:ride_id>')
@login_required
def reserve(ride_id):
    conn = get_db()
    cur = conn.cursor(cursor_factory=DictCursor)
    try:
        cur.execute("SELECT seats, user_id FROM rides WHERE id = %s", (ride_id,))
        ride = cur.fetchone()
        if ride and ride['user_id'] != current_user.id:
            status = 'confirmed' if ride['seats'] > 0 else 'waiting'
            cur.execute("INSERT INTO reservations (user_id, ride_id, status) VALUES (%s, %s, %s)", (current_user.id, ride_id, status))
            if status == 'confirmed':
                cur.execute("UPDATE rides SET seats = seats - 1 WHERE id = %s", (ride_id,))
            conn.commit()
    except: flash("Déjà inscrit.")
    finally: cur.close(); conn.close()
    return redirect(url_for("index"))

@app.route('/unreserve/<int:ride_id>')
@login_required
def unreserve(ride_id):
    conn = get_db()
    cur = conn.cursor(cursor_factory=DictCursor)
    cur.execute("SELECT status FROM reservations WHERE user_id = %s AND ride_id = %s", (current_user.id, ride_id))
    res = cur.fetchone()
    if res:
        was_confirmed = (res['status'] == 'confirmed')
        cur.execute("DELETE FROM reservations WHERE user_id = %s AND ride_id = %s", (current_user.id, ride_id))
        if was_confirmed:
            cur.execute("UPDATE rides SET seats = seats + 1 WHERE id = %s", (ride_id,))
            cur.execute("SELECT id FROM reservations WHERE ride_id = %s AND status = 'waiting' ORDER BY id ASC LIMIT 1", (ride_id,))
            waiter = cur.fetchone()
            if waiter:
                cur.execute("UPDATE reservations SET status = 'confirmed' WHERE id = %s", (waiter['id'],))
                cur.execute("UPDATE rides SET seats = seats - 1 WHERE id = %s", (ride_id,))
        conn.commit()
    cur.close(); conn.close()
    return redirect(url_for("my_account"))

@app.route("/delete/<int:ride_id>")
@login_required
def delete_ride(ride_id):
    conn = get_db()
    cur = conn.cursor()
    if current_user.is_admin:
        cur.execute("UPDATE rides SET active = FALSE WHERE id = %s", (ride_id,))
    else:
        cur.execute("UPDATE rides SET active = FALSE WHERE id = %s AND user_id = %s", (ride_id, current_user.id))
    conn.commit(); cur.close(); conn.close()
    return redirect(url_for("index"))

@app.route('/my-account')
@login_required
def my_account():
    conn = get_db()
    cur = conn.cursor(cursor_factory=DictCursor)
    cur.execute("SELECT * FROM rides WHERE user_id = %s ORDER BY departure_ts DESC", (current_user.id,))
    driving = cur.fetchall()
    cur.execute("SELECT r.*, res.status FROM rides r JOIN reservations res ON r.id = res.ride_id WHERE res.user_id = %s ORDER BY r.departure_ts DESC", (current_user.id,))
    joined = cur.fetchall()
    cur.close(); conn.close()
    return render_template('my_account.html', driving=driving, joined=joined)

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))

if __name__ == "__main__":
    app.run()
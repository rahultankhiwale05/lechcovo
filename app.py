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

# Configuration
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
    if u:
        return User(u['id'], u['name'], u['email'], u['is_admin'])
    return None

def init_db():
    conn = get_db()
    cur = conn.cursor()
    # 1. Users Table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            is_admin BOOLEAN DEFAULT FALSE
        )
    """)
    # 2. Rides Table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS rides (
            id SERIAL PRIMARY KEY,
            departure TEXT NOT NULL,
            destination TEXT NOT NULL,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            seats INTEGER NOT NULL,
            departure_ts INTEGER NOT NULL,
            contact TEXT NOT NULL,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    # AUTO-FIX: Check if 'active' column exists, if not, add it
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='rides' AND column_name='active';")
    if not cur.fetchone():
        cur.execute("ALTER TABLE rides ADD COLUMN active BOOLEAN DEFAULT TRUE;")
    
    # 3. Reservations Table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS reservations (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            ride_id INTEGER REFERENCES rides(id) ON DELETE CASCADE,
            UNIQUE(user_id, ride_id)
        )
    """)
    conn.commit()
    cur.close(); conn.close()

if DATABASE_URL:
    init_db()

@app.route('/')
def index():
    conn = get_db()
    cur = conn.cursor(cursor_factory=DictCursor)
    cur.execute("""
        SELECT r.*, u.name as driver_name 
        FROM rides r 
        LEFT JOIN users u ON r.user_id = u.id 
        WHERE r.active = TRUE 
        ORDER BY r.departure_ts ASC
    """)
    rides = cur.fetchall()
    cur.close(); conn.close()
    return render_template('index.html', rides=rides)

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
        except:
            flash("Email déjà utilisé.")
        finally:
            cur.close(); conn.close()
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

@app.route('/publish', methods=['POST'])
@login_required
def publish():
    try:
        local_dt = datetime.strptime(request.form["date"] + " " + request.form["time"], "%Y-%m-%d %H:%M").replace(tzinfo=LOCAL_TZ)
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO rides (user_id, departure, destination, date, time, seats, departure_ts, contact, active)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, TRUE)
        """, (current_user.id, request.form["departure"], request.form["destination"],
              request.form["date"], request.form["time"], int(request.form["seats"]),
              int(local_dt.timestamp()), request.form["contact"]))
        conn.commit(); cur.close(); conn.close()
    except Exception as e:
        flash(f"Erreur: {e}")
    return redirect(url_for('index'))

@app.route('/reserve/<int:ride_id>')
@login_required
def reserve(ride_id):
    conn = get_db()
    cur = conn.cursor(cursor_factory=DictCursor)
    try:
        cur.execute("SELECT seats, user_id FROM rides WHERE id = %s AND active = TRUE", (ride_id,))
        ride = cur.fetchone()
        if ride and ride['user_id'] != current_user.id and ride['seats'] > 0:
            cur.execute("INSERT INTO reservations (user_id, ride_id) VALUES (%s, %s)", (current_user.id, ride_id))
            cur.execute("UPDATE rides SET seats = seats - 1 WHERE id = %s", (ride_id,))
            conn.commit()
    except:
        flash("Déjà réservé.")
    finally:
        cur.close(); conn.close()
    return redirect(url_for("index"))

@app.route('/my-account')
@login_required
def my_account():
    conn = get_db()
    cur = conn.cursor(cursor_factory=DictCursor)
    cur.execute("SELECT * FROM rides WHERE user_id = %s ORDER BY departure_ts DESC", (current_user.id,))
    driving = cur.fetchall()
    cur.execute("""
        SELECT r.* FROM rides r JOIN reservations res ON r.id = res.ride_id 
        WHERE res.user_id = %s ORDER BY r.departure_ts DESC
    """, (current_user.id,))
    joined = cur.fetchall()
    cur.close(); conn.close()
    return render_template('my_account.html', driving=driving, joined=joined)

@app.route("/delete/<int:ride_id>")
@login_required
def delete_ride(ride_id):
    conn = get_db()
    cur = conn.cursor()
    # SOFT DELETE: Sets active to False instead of deleting row
    if current_user.is_admin:
        cur.execute("UPDATE rides SET active = FALSE WHERE id = %s", (ride_id,))
    else:
        cur.execute("UPDATE rides SET active = FALSE WHERE id = %s AND user_id = %s", (ride_id, current_user.id))
    conn.commit(); cur.close(); conn.close()
    return redirect(url_for("index"))

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))

if __name__ == "__main__":
    app.run()
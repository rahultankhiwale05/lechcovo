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

# --- DATE FORMAT FILTER ---
@app.template_filter('date_french')
def date_french(date_str):
    """Converts YYYY-MM-DD to DD-MM-YYYY for the UI."""
    try:
        if len(date_str) == 10 and date_str[2] == '-' and date_str[5] == '-':
            return date_str
        dt = datetime.strptime(date_str, '%Y-%m-%d')
        return dt.strftime('%d-%m-%Y')
    except:
        return date_str

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
        raw_date = request.form['date'] 
        time_input = request.form['time']
        dt_str = f"{raw_date} {time_input}"
        local_dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M").replace(tzinfo=LOCAL_TZ)
        conn = get_db()
        cur = conn.cursor()
        cur.execute("INSERT INTO rides (user_id, departure, destination, date, time, seats, departure_ts, contact) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                   (current_user.id, request.form['departure'], request.form['destination'], raw_date, time_input, int(request.form['seats']), int(local_dt.timestamp()), request.form['contact']))
        conn.commit(); cur.close(); conn.close()
    except Exception as e: flash(f"Erreur: {e}")
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

@app.route('/delete-account', methods=['POST'])
@login_required
def delete_account():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM users WHERE id = %s", (current_user.id,)) # GDPR
    conn.commit(); cur.close(); conn.close()
    logout_user()
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))

if __name__ == "__main__":
    app.run()
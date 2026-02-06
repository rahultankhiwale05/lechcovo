import os
import time
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

# Flask-Login Setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

DATABASE_URL = os.environ.get('DATABASE_URL')
LOCAL_TZ = ZoneInfo("Europe/Paris")

def get_db():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

# User Class for Flask-Login
class User(UserMixin):
    def __init__(self, id, name, email):
        self.id = id
        self.name = name
        self.email = email

@login_manager.user_loader
def load_user(user_id):
    conn = get_db()
    cur = conn.cursor(cursor_factory=DictCursor)
    cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    u = cur.fetchone()
    cur.close()
    conn.close()
    if u:
        return User(u['id'], u['name'], u['email'])
    return None

def init_db():
    conn = get_db()
    cur = conn.cursor()
    # Create Users Table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)
    # Create Rides Table with user_id link
    cur.execute("""
        CREATE TABLE IF NOT EXISTS rides (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            departure TEXT NOT NULL,
            destination TEXT NOT NULL,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            seats INTEGER NOT NULL,
            departure_ts INTEGER NOT NULL,
            contact TEXT NOT NULL
        )
    """)
    conn.commit()
    cur.close()
    conn.close()

def cleanup_old_rides():
    now_ts = int(time.time())
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM rides WHERE departure_ts < %s", (now_ts,))
    conn.commit()
    cur.close()
    conn.close()

if DATABASE_URL:
    init_db()

# --- ROUTES ---

@app.route('/')
def index():
    cleanup_old_rides()
    conn = get_db()
    cur = conn.cursor(cursor_factory=DictCursor)
    cur.execute("""
        SELECT r.*, u.name as driver_name 
        FROM rides r 
        JOIN users u ON r.user_id = u.id 
        ORDER BY r.departure_ts ASC
    """)
    rides = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('index.html', rides=rides)

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = generate_password_hash(request.form['password'])
        
        conn = get_db()
        cur = conn.cursor()
        try:
            cur.execute("INSERT INTO users (name, email, password) VALUES (%s, %s, %s)", (name, email, password))
            conn.commit()
            flash("Compte créé ! Connectez-vous.", "success")
            return redirect(url_for('login'))
        except:
            flash("Email déjà utilisé.", "error")
        finally:
            cur.close()
            conn.close()
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        conn = get_db()
        cur = conn.cursor(cursor_factory=DictCursor)
        cur.execute("SELECT * FROM users WHERE email = %s", (request.form['email'],))
        user_data = cur.fetchone()
        cur.close()
        conn.close()

        if user_data and check_password_hash(user_data['password'], request.form['password']):
            user_obj = User(user_data['id'], user_data['name'], user_data['email'])
            login_user(user_obj)
            return redirect(url_for('index'))
        flash("Email ou mot de passe incorrect.", "error")
    return render_template('login.html')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/publish', methods=['POST'])
@login_required
def publish():
    local_dt = datetime.strptime(
        request.form["date"] + " " + request.form["time"],
        "%Y-%m-%d %H:%M"
    ).replace(tzinfo=LOCAL_TZ)

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO rides (user_id, departure, destination, date, time, seats, departure_ts, contact)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, (current_user.id, request.form["departure"], request.form["destination"],
          request.form["date"], request.form["time"], int(request.form["seats"]),
          int(local_dt.timestamp()), request.form["contact"]))
    conn.commit()
    cur.close()
    conn.close()
    flash("Trajet publié !", "success")
    return redirect(url_for('index'))

@app.route("/reserve/<int:ride_id>")
def reserve(ride_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE rides SET seats = seats - 1 WHERE id = %s AND seats > 0", (ride_id,))
    conn.commit()
    cur.close()
    conn.close()
    flash("Place réservée !", "success")
    return redirect(url_for("index"))

@app.route("/delete/<int:ride_id>")
@login_required
def delete_ride(ride_id):
    conn = get_db()
    cur = conn.cursor()
    # Check if the current user is the owner
    cur.execute("DELETE FROM rides WHERE id = %s AND user_id = %s", (ride_id, current_user.id))
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run()
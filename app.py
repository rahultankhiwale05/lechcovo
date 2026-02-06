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
        self.is_admin = is_admin

@login_manager.user_loader
def load_user(user_id):
    conn = get_db()
    cur = conn.cursor(cursor_factory=DictCursor)
    cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    u = cur.fetchone()
    cur.close()
    conn.close()
    if u:
        return User(u['id'], u['name'], u['email'], u.get('is_admin', False))
    return None

def init_db():
    conn = get_db()
    cur = conn.cursor()
    # 1. Users table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            is_admin BOOLEAN DEFAULT FALSE
        )
    """)
    # 2. Rides table (Note: 'name' is removed or made optional here)
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
    # 3. MIGRATION: Fix the 'NotNullViolation' by making 'name' optional in the DB
    cur.execute("""
        DO $$ 
        BEGIN 
            IF EXISTS (SELECT 1 FROM information_schema.columns 
                       WHERE table_name='rides' AND column_name='name') THEN
                ALTER TABLE rides ALTER COLUMN name DROP NOT NULL;
            END IF;
            
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                           WHERE table_name='rides' AND column_name='user_id') THEN
                ALTER TABLE rides ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE CASCADE;
            END IF;
        END $$;
    """)
    conn.commit()
    cur.close()
    conn.close()

if DATABASE_URL:
    init_db()

@app.route('/')
def index():
    conn = get_db()
    cur = conn.cursor(cursor_factory=DictCursor)
    # Using a LEFT JOIN ensures we get the driver name from the users table
    cur.execute("""
        SELECT r.*, u.name as driver_name 
        FROM rides r 
        LEFT JOIN users u ON r.user_id = u.id 
        ORDER BY r.departure_ts ASC
    """)
    rides = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('index.html', rides=rides)

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        user_token = request.form.get('admin_token')
        is_admin = (ADMIN_SECRET_TOKEN and user_token == ADMIN_SECRET_TOKEN)
        
        conn = get_db()
        cur = conn.cursor()
        try:
            cur.execute("""
                INSERT INTO users (name, email, password, is_admin) 
                VALUES (%s, %s, %s, %s)
            """, (request.form['name'], request.form['email'], 
                  generate_password_hash(request.form['password']), is_admin))
            conn.commit()
            flash("Compte créé !", "success")
            return redirect(url_for('login'))
        except:
            flash("Erreur : l'email existe peut-être déjà.")
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
            user_obj = User(u['id'], u['name'], u['email'], u['is_admin'])
            login_user(user_obj)
            return redirect(url_for('index'))
        flash("Email ou mot de passe incorrect.")
    return render_template('login.html')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/publish', methods=['POST'])
@login_required
def publish():
    try:
        local_dt = datetime.strptime(
            request.form["date"] + " " + request.form["time"],
            "%Y-%m-%d %H:%M"
        ).replace(tzinfo=LOCAL_TZ)

        conn = get_db()
        cur = conn.cursor()
        # We only send columns that exist and aren't 'name'
        cur.execute("""
            INSERT INTO rides (user_id, departure, destination, date, time, seats, departure_ts, contact)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (current_user.id, request.form["departure"], request.form["destination"],
              request.form["date"], request.form["time"], int(request.form["seats"]),
              int(local_dt.timestamp()), request.form["contact"]))
        conn.commit()
        cur.close(); conn.close()
        flash("Trajet publié !", "success")
    except Exception as e:
        flash(f"Erreur lors de la publication : {e}")
    return redirect(url_for('index'))

@app.route("/reserve/<int:ride_id>")
def reserve(ride_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE rides SET seats = seats - 1 WHERE id = %s AND seats > 0", (ride_id,))
    conn.commit()
    cur.close(); conn.close()
    return redirect(url_for("index"))

@app.route("/delete/<int:ride_id>")
@login_required
def delete_ride(ride_id):
    conn = get_db()
    cur = conn.cursor()
    if current_user.is_admin:
        cur.execute("DELETE FROM rides WHERE id = %s", (ride_id,))
    else:
        cur.execute("DELETE FROM rides WHERE id = %s AND user_id = %s", (ride_id, current_user.id))
    conn.commit()
    cur.close(); conn.close()
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run()
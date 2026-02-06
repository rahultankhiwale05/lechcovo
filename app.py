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
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            is_admin BOOLEAN DEFAULT FALSE
        )
    """)
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
        ORDER BY r.departure_ts ASC
    """)
    rides = cur.fetchall()
    cur.close(); conn.close()
    return render_template('index.html', rides=rides)

@app.route('/reserve/<int:ride_id>')
@login_required
def reserve(ride_id):
    conn = get_db()
    cur = conn.cursor(cursor_factory=DictCursor)
    try:
        cur.execute("SELECT seats, user_id FROM rides WHERE id = %s", (ride_id,))
        ride = cur.fetchone()
        if ride and ride['user_id'] != current_user.id and ride['seats'] > 0:
            cur.execute("INSERT INTO reservations (user_id, ride_id) VALUES (%s, %s)", (current_user.id, ride_id))
            cur.execute("UPDATE rides SET seats = seats - 1 WHERE id = %s", (ride_id,))
            conn.commit()
            flash("Réservation confirmée !", "success")
        elif ride and ride['user_id'] == current_user.id:
            flash("Vous ne pouvez pas réserver votre propre trajet.")
        else:
            flash("Plus de places disponibles.")
    except psycopg2.errors.UniqueViolation:
        flash("Vous avez déjà réservé ce trajet.")
    except Exception as e:
        flash(f"Erreur : {e}")
    finally:
        cur.close(); conn.close()
    return redirect(url_for("index"))

@app.route("/delete/<int:ride_id>")
@login_required
def delete_ride(ride_id):
    conn = get_db()
    cur = conn.cursor()
    if current_user.is_admin:
        cur.execute("DELETE FROM rides WHERE id = %s", (ride_id,))
        flash("Admin: Trajet supprimé.", "success")
    else:
        cur.execute("DELETE FROM rides WHERE id = %s AND user_id = %s", (ride_id, current_user.id))
        flash("Trajet supprimé.", "success")
    conn.commit(); cur.close(); conn.close()
    return redirect(url_for("index"))

# ... (rest of standard signup/login/publish routes remain the same)
@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))

if __name__ == "__main__":
    app.run()
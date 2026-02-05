import os
import secrets
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from flask import Flask, render_template, request, redirect, url_for, flash
import psycopg2
from psycopg2.extras import DictCursor

app = Flask(__name__)
# Required for flash notifications
app.secret_key = secrets.token_hex(16)

# Configuration: Railway provides DATABASE_URL automatically
DATABASE_URL = os.environ.get('DATABASE_URL')
LOCAL_TZ = ZoneInfo("Europe/Paris")

def get_db():
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL is not set in environment variables.")
    return psycopg2.connect(DATABASE_URL, sslmode='require')

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS rides (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            contact TEXT NOT NULL,
            departure TEXT NOT NULL,
            destination TEXT NOT NULL,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            seats INTEGER NOT NULL,
            departure_ts INTEGER NOT NULL,
            secret TEXT NOT NULL
        )
    """)
    conn.commit()
    cur.close()
    conn.close()

def cleanup_old_rides():
    """Deletes rides that have already happened based on UTC time."""
    now_ts = int(time.time())
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("DELETE FROM rides WHERE departure_ts < %s", (now_ts,))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Cleanup error: {e}")

# Initialize database once on startup
if DATABASE_URL:
    try:
        init_db()
    except Exception as e:
        print(f"Database Init Error: {e}")

@app.route("/", methods=["GET", "POST"])
def index():
    cleanup_old_rides()
    conn = get_db()
    cur = conn.cursor(cursor_factory=DictCursor)

    if request.method == "POST":
        # Parse user local time and convert to a timestamp for the database
        local_dt = datetime.strptime(
            request.form["date"] + " " + request.form["time"],
            "%Y-%m-%d %H:%M"
        ).replace(tzinfo=LOCAL_TZ)

        departure_ts = int(local_dt.timestamp())
        secret = secrets.token_urlsafe(16)

        cur.execute("""
            INSERT INTO rides 
            (name, contact, departure, destination, date, time, seats, departure_ts, secret)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            request.form["name"], request.form["contact"], request.form["departure"],
            request.form["destination"], request.form["date"], request.form["time"],
            int(request.form["seats"]), departure_ts, secret
        ))
        conn.commit()
        cur.close()
        conn.close()
        flash("Trajet publié avec succès !", "success")
        return redirect(url_for("index"))

    cur.execute("SELECT * FROM rides ORDER BY departure_ts ASC")
    rides = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("index.html", rides=rides)

@app.route("/reserve/<int:ride_id>")
def reserve(ride_id):
    conn = get_db()
    cur = conn.cursor(cursor_factory=DictCursor)
    
    # Check current seats in the database (Server-side validation)
    cur.execute("SELECT seats FROM rides WHERE id = %s", (ride_id,))
    ride = cur.fetchone()
    
    if ride and ride['seats'] > 0:
        cur.execute("UPDATE rides SET seats = seats - 1 WHERE id = %s", (ride_id,))
        conn.commit()
        flash("Place réservée !", "success")
    else:
        # User clicked on an outdated page; notify them it's full
        flash("Désolé, ce trajet est désormais complet.", "error")
    
    cur.close()
    conn.close()
    return redirect(url_for("index"))

@app.route("/delete/<int:ride_id>/<secret>")
def delete_ride(ride_id, secret):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM rides WHERE id = %s AND secret = %s", (ride_id, secret))
    conn.commit()
    cur.close()
    conn.close()
    flash("Annonce supprimée.", "success")
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run()
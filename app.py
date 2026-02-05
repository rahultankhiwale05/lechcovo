import os
import time
import secrets
from datetime import datetime
from zoneinfo import ZoneInfo
from flask import Flask, render_template, request, redirect, url_for
import psycopg2
from psycopg2.extras import DictCursor

app = Flask(__name__)

# Use an environment variable for the connection string
# On Heroku/Render, this is usually provided automatically
DATABASE_URL = os.environ.get('DATABASE_URL')
LOCAL_TZ = ZoneInfo("Europe/Paris")

def get_db():
    # Connect to PostgreSQL instead of a local SQLite file
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    # PostgreSQL uses slightly different syntax for AUTOINCREMENT
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

# Initialize DB on startup
if DATABASE_URL:
    init_db()

@app.route("/", methods=["GET", "POST"])
def index():
    conn = get_db()
    cur = conn.cursor(cursor_factory=DictCursor)

    if request.method == "POST":
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
        return redirect(url_for("index"))

    cur.execute("SELECT * FROM rides ORDER BY departure_ts")
    rides = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("index.html", rides=rides)

@app.route("/delete/<int:ride_id>/<secret>")
def delete_ride(ride_id, secret):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM rides WHERE id = %s AND secret = %s", (ride_id, secret))
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run()
from flask import Flask, render_template, request, redirect, url_for
import sqlite3
import os
import time
import secrets
from datetime import datetime

app = Flask(__name__, instance_relative_config=True)

DB_PATH = os.path.join(app.instance_path, "rides.db")


# ---------- DATABASE ----------
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    os.makedirs(app.instance_path, exist_ok=True)
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS rides (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    conn.close()


def cleanup_old_rides():
    now_ts = int(time.time())
    conn = get_db()
    conn.execute(
        "DELETE FROM rides WHERE departure_ts < ?",
        (now_ts,)
    )
    conn.commit()
    conn.close()


# Initialize DB on startup (Gunicorn-safe)
init_db()


# ---------- ROUTES ----------
@app.route("/", methods=["GET", "POST"])
def index():
    cleanup_old_rides()
    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":
        dt = datetime.strptime(
            request.form["date"] + " " + request.form["time"],
            "%Y-%m-%d %H:%M"
        )
        departure_ts = int(dt.timestamp())
        secret = secrets.token_urlsafe(16)

        cur.execute("""
            INSERT INTO rides
            (name, contact, departure, destination, date, time, seats, departure_ts, secret)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            request.form["name"],
            request.form["contact"],
            request.form["departure"],
            request.form["destination"],
            request.form["date"],
            request.form["time"],
            request.form["seats"],
            departure_ts,
            secret
        ))
        conn.commit()

    rides = cur.execute(
        "SELECT * FROM rides ORDER BY departure_ts"
    ).fetchall()

    conn.close()
    return render_template("index.html", rides=rides, now=int(time.time()))


@app.route("/delete/<int:ride_id>/<secret>")
def delete_ride(ride_id, secret):
    conn = get_db()
    conn.execute(
        "DELETE FROM rides WHERE id = ? AND secret = ?",
        (ride_id, secret)
    )
    conn.commit()
    conn.close()
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run()

from flask import Flask, render_template, request, redirect, url_for
import sqlite3, os, secrets
from datetime import datetime

app = Flask(__name__, instance_relative_config=True)

DB_PATH = os.path.join(app.instance_path, "rides.db")

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
            secret TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

init_db()

def cleanup_old_rides():
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    conn = get_db()
    conn.execute(
        "DELETE FROM rides WHERE date || ' ' || time < ?",
        (now,)
    )
    conn.commit()
    conn.close()

@app.route("/", methods=["GET", "POST"])
def index():
    cleanup_old_rides()

    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":
        secret = secrets.token_hex(4)
        cur.execute("""
            INSERT INTO rides
            (name, contact, departure, destination, date, time, seats, secret)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            request.form["name"],
            request.form["contact"],
            request.form["departure"],
            request.form["destination"],
            request.form["date"],
            request.form["time"],
            request.form["seats"],
            secret
        ))
        conn.commit()
        conn.close()
        return redirect(url_for("index", key=secret))

    search_from = request.args.get("from", "")
    search_to = request.args.get("to", "")

    rides = cur.execute("""
        SELECT * FROM rides
        WHERE departure LIKE ?
        AND destination LIKE ?
        ORDER BY date, time
    """, (
        f"%{search_from}%",
        f"%{search_to}%"
    )).fetchall()

    conn.close()
    return render_template(
        "index.html",
        rides=rides,
        key=request.args.get("key")
    )

@app.route("/delete", methods=["POST"])
def delete():
    conn = get_db()
    conn.execute(
        "DELETE FROM rides WHERE id=? AND secret=?",
        (request.form["ride_id"], request.form["secret"])
    )
    conn.commit()
    conn.close()
    return redirect(url_for("index"))

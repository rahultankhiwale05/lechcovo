from flask import Flask, render_template, request, redirect, url_for
import sqlite3
import os
from datetime import date
import secrets

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
            departure TEXT NOT NULL,
            destination TEXT NOT NULL,
            date TEXT NOT NULL,
            seats INTEGER NOT NULL,
            contact TEXT NOT NULL,
            secret TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

init_db()

@app.route("/", methods=["GET", "POST"])
def index():
    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":
        secret = secrets.token_hex(4)  # simple delete key
        cur.execute("""
            INSERT INTO rides (name, departure, destination, date, seats, contact, secret)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            request.form["name"],
            request.form["departure"],
            request.form["destination"],
            request.form["date"],
            request.form["seats"],
            request.form["contact"],
            secret
        ))
        conn.commit()
        conn.close()
        return redirect(url_for("index", key=secret))

    search_from = request.args.get("from", "")
    search_to = request.args.get("to", "")

    query = """
        SELECT * FROM rides
        WHERE date >= ?
        AND departure LIKE ?
        AND destination LIKE ?
        ORDER BY date
    """

    rides = cur.execute(query, (
        date.today().isoformat(),
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
def delete_ride():
    ride_id = request.form["ride_id"]
    secret = request.form["secret"]

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM rides WHERE id = ? AND secret = ?",
        (ride_id, secret)
    )
    conn.commit()
    conn.close()

    return redirect(url_for("index"))

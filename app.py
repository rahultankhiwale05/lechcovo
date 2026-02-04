from flask import Flask, render_template, request, redirect, url_for
import sqlite3
import os

app = Flask(__name__, instance_relative_config=True)

DB_PATH = os.path.join(app.instance_path, "rides.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.route("/", methods=["GET", "POST"])
def index():
    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":
        cur.execute("""
            INSERT INTO rides (name, departure, destination, date, seats, contact)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            request.form["name"],
            request.form["departure"],
            request.form["destination"],
            request.form["date"],
            request.form["seats"],
            request.form["contact"]
        ))
        conn.commit()

    rides = cur.execute("SELECT * FROM rides ORDER BY date").fetchall()
    conn.close()
    return render_template("index.html", rides=rides)

@app.route("/delete/<int:ride_id>")
def delete_ride(ride_id):
    conn = get_db()
    conn.execute("DELETE FROM rides WHERE id = ?", (ride_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("index"))

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
            contact TEXT NOT NULL
        )
    """)
    conn.close()

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=8080)

# app.py
import os
from flask import Flask, render_template, request, jsonify
from datetime import datetime
from dotenv import load_dotenv

# Load .env if running locally
load_dotenv()

app = Flask(__name__)

# Admin key from environment variable
ADMIN_KEY = os.environ.get("ADMIN_KEY", "default_admin_key")

# In-memory storage for posts
rides = []

# Helper to format datetime
def current_time():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

@app.route('/')
def index():
    return render_template('index.html', rides=rides)

@app.route('/add_ride', methods=['POST'])
def add_ride():
    data = request.json
    ride = {
        "id": len(rides) + 1,
        "from": data.get("from"),
        "to": data.get("to"),
        "date": data.get("date"),
        "time": data.get("time"),
        "seats": data.get("seats"),
        "posted_at": current_time()
    }
    rides.append(ride)
    return jsonify({"status": "success", "ride": ride})

@app.route('/delete_ride', methods=['POST'])
def delete_ride():
    data = request.json
    ride_id = int(data.get("id"))
    key = data.get("admin_key")

    global rides
    if key == ADMIN_KEY:
        # Admin can delete any ride
        rides = [r for r in rides if r["id"] != ride_id]
        return jsonify({"status": "deleted_by_admin"})
    else:
        # Optional: normal user deletion logic (e.g., only their own ride)
        return jsonify({"status": "unauthorized"}), 403

@app.route('/get_rides', methods=['GET'])
def get_rides():
    return jsonify(rides)

if __name__ == '__main__':
    app.run()

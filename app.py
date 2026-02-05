import os
import secrets
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)

# --- CONFIGURATION ---
# Railway provides DATABASE_URL. Defaulting to sqlite for local dev.
app.config['SQLALCHEMY_DATABASE_PATH'] = os.environ.get('DATABASE_URL', 'sqlite:///rides.db')
if app.config['SQLALCHEMY_DATABASE_PATH'].startswith("postgres://"):
    app.config['SQLALCHEMY_DATABASE_PATH'] = app.config['SQLALCHEMY_DATABASE_PATH'].replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_PATH']
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(24))

db = SQLAlchemy(app)
LOCAL_TZ = ZoneInfo("Europe/Paris") [cite: 1]

# --- MODELS ---
class Ride(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    contact = db.Column(db.String(100), nullable=False)
    departure = db.Column(db.String(100), nullable=False)
    destination = db.Column(db.String(100), nullable=False)
    date = db.Column(db.String(20), nullable=False)
    time = db.Column(db.String(10), nullable=False)
    seats = db.Column(db.Integer, nullable=False)
    departure_ts = db.Column(db.Integer, nullable=False)
    secret = db.Column(db.String(50), nullable=False)

# --- DATABASE INIT ---
with app.app_context():
    db.create_all()

def cleanup_old_rides():
    """Removes rides that have already departed."""
    now_utc_ts = int(time.time()) [cite: 1]
    Ride.query.filter(Ride.departure_ts < now_utc_ts).delete()
    db.session.commit()

# --- ROUTES ---
@app.route("/", methods=["GET", "POST"])
def index():
    cleanup_old_rides()
    
    search_query = request.args.get('q', '')
    
    if request.method == "POST":
        try:
            # Parse user local datetime (France) 
            local_dt = datetime.strptime(
                request.form["date"] + " " + request.form["time"],
                "%Y-%m-%d %H:%M"
            ).replace(tzinfo=LOCAL_TZ)

            departure_ts = int(local_dt.timestamp()) [cite: 1]
            
            # Validation: No past dates
            if departure_ts < time.time():
                flash("Erreur : La date du trajet est déjà passée.", "danger")
                return redirect(url_for("index"))

            new_ride = Ride(
                name=request.form["name"],
                contact=request.form["contact"],
                departure=request.form["departure"],
                destination=request.form["destination"],
                date=request.form["date"],
                time=request.form["time"],
                seats=int(request.form["seats"]),
                departure_ts=departure_ts,
                secret=secrets.token_urlsafe(16)
            )
            db.session.add(new_ride)
            db.session.commit()
            flash("Trajet publié avec succès !", "success")
            return redirect(url_for("index")) [cite: 1]
        except Exception as e:
            flash(f"Erreur lors de l'ajout : {str(e)}", "danger")

    # Fetch rides with optional search filter
    if search_query:
        rides = Ride.query.filter(
            (Ride.destination.ilike(f'%{search_query}%')) | 
            (Ride.departure.ilike(f'%{search_query}%'))
        ).order_by(Ride.departure_ts).all()
    else:
        rides = Ride.query.order_by(Ride.departure_ts).all()

    return render_template("index.html", rides=rides, search_query=search_query)

@app.route("/book/<int:ride_id>")
def book_seat(ride_id):
    ride = Ride.query.get_or_404(ride_id)
    if ride.seats > 0:
        ride.seats -= 1
        db.session.commit()
        flash(f"Place réservée ! Contactez {ride.name} au {ride.contact}.", "success")
    else:
        flash("Désolé, ce trajet est complet.", "warning")
    return redirect(url_for("index"))

@app.route("/delete/<int:ride_id>/<secret>")
def delete_ride(ride_id, secret):
    ride = Ride.query.filter_by(id=ride_id, secret=secret).first_or_404()
    db.session.delete(ride)
    db.session.commit()
    flash("Trajet supprimé.", "info")
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run()
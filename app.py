import os, csv, io, secrets
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, session, Response
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "change-this-secret-key")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///supreme_mobiles.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

class Registration(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    application_no = db.Column(db.String(32), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    mobile = db.Column(db.String(10), unique=True, nullable=False)
    network = db.Column(db.String(30), nullable=False)
    location = db.Column(db.String(255))
    latitude = db.Column(db.String(50))
    longitude = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    gift_collected = db.Column(db.Boolean, default=False, nullable=False)
    collected_at = db.Column(db.DateTime)

def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login"))
        return fn(*args, **kwargs)
    return wrapper

@app.route("/", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        mobile = request.form.get("mobile", "").strip()
        network = request.form.get("network", "").strip()
        location = request.form.get("location", "").strip()
        latitude = request.form.get("latitude", "").strip()
        longitude = request.form.get("longitude", "").strip()
        if not name or len(name) > 100:
            flash("Please enter a valid name.", "danger")
        elif not (mobile.isdigit() and len(mobile) == 10):
            flash("Enter a valid 10-digit mobile number.", "danger")
        elif network not in ["Jio", "Airtel", "Vi", "BSNL", "Other"]:
            flash("Please select your mobile network.", "danger")
        elif Registration.query.filter_by(mobile=mobile).first():
            flash("This mobile number is already registered.", "warning")
        else:
            app_no = "SM-XMAS-" + secrets.token_hex(3).upper()
            while Registration.query.filter_by(application_no=app_no).first():
                app_no = "SM-XMAS-" + secrets.token_hex(3).upper()
            item = Registration(
                application_no=app_no,
                name=name,
                mobile=mobile,
                network=network,
                location=location,
                latitude=latitude,
                longitude=longitude
            )
            db.session.add(item)
            db.session.commit()
            return render_template("success.html", item=item)
        return redirect(url_for("register"))
    return render_template("register.html")

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = os.getenv("ADMIN_USERNAME", "admin")
        password_hash = os.getenv("ADMIN_PASSWORD_HASH")
        password = os.getenv("ADMIN_PASSWORD", "ChangeMe123!")
        if request.form.get("username") == username and (
            (password_hash and check_password_hash(password_hash, request.form.get("password", ""))) or
            (not password_hash and request.form.get("password") == password)
        ):
            session["admin_logged_in"] = True
            return redirect(url_for("admin_dashboard"))
        flash("Incorrect username or password.", "danger")
    return render_template("admin_login.html")

@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))

@app.route("/admin")
@admin_required
def admin_dashboard():
    q = request.args.get("q", "").strip()
    query = Registration.query
    if q:
        query = query.filter(db.or_(Registration.name.ilike(f"%{q}%"),
                                    Registration.mobile.ilike(f"%{q}%"),
                                    Registration.application_no.ilike(f"%{q}%"),
                                    Registration.location.ilike(f"%{q}%")))
    registrations = query.order_by(Registration.created_at.desc()).all()
    total = Registration.query.count()
    collected = Registration.query.filter_by(gift_collected=True).count()
    return render_template("admin.html", registrations=registrations, total=total,
                           collected=collected, q=q)

@app.route("/admin/collect/<int:registration_id>", methods=["POST"])
@admin_required
def mark_collected(registration_id):
    item = Registration.query.get_or_404(registration_id)
    item.gift_collected = not item.gift_collected
    item.collected_at = datetime.utcnow() if item.gift_collected else None
    db.session.commit()
    flash("Gift collection status updated.", "success")
    return redirect(url_for("admin_dashboard", q=request.args.get("q", "")))

@app.route("/admin/export")
@admin_required
def export_csv():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Application Number", "Name", "Mobile", "Network", "Location", "Latitude", "Longitude", "Registered At", "Gift Collected"])
    for item in Registration.query.order_by(Registration.created_at.desc()).all():
        writer.writerow([item.application_no, item.name, item.mobile, item.network,
                         item.location or "", item.latitude or "", item.longitude or "",
                         item.created_at.strftime("%Y-%m-%d %H:%M"), "Yes" if item.gift_collected else "No"])
    return Response(output.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=supreme_registrations.csv"})

with app.app_context():
    db.create_all()
    # Lightweight auto-migration to add new columns to existing SQLite DB
    try:
        with db.engine.connect() as conn:
            existing_cols = [row[1] for row in conn.execute(db.text("PRAGMA table_info(registration)")).fetchall()]
            if "location" not in existing_cols:
                conn.execute(db.text("ALTER TABLE registration ADD COLUMN location VARCHAR(255)"))
            if "latitude" not in existing_cols:
                conn.execute(db.text("ALTER TABLE registration ADD COLUMN latitude VARCHAR(50)"))
            if "longitude" not in existing_cols:
                conn.execute(db.text("ALTER TABLE registration ADD COLUMN longitude VARCHAR(50)"))
            conn.commit()
    except Exception:
        pass

if __name__ == "__main__":
    app.run(debug=True)

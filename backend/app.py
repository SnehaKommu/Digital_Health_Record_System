from flask import Flask, render_template, request, redirect, session, flash, send_from_directory
from db_config import get_db
import os

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR  = os.path.dirname(BASE_DIR)                       # SE_Project_v2/
FRONTEND_DIR = os.path.join(PROJECT_DIR, "frontend")
UPLOAD_DIR   = os.path.join(PROJECT_DIR, "uploads")

app = Flask(
    __name__,
    template_folder=os.path.join(FRONTEND_DIR, "templates"),   # frontend/templates/
    static_folder=os.path.join(FRONTEND_DIR, "static"),        # frontend/static/
)
app.secret_key = "health_secret_2025"
app.config["UPLOAD_FOLDER"] = UPLOAD_DIR
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ── Auth guard ─────────────────────────────────────────────────────────────────
def require_login(role=None):
    if "user" not in session:
        flash("Please log in to continue.", "danger")
        return redirect("/")
    if role and session.get("role") != role:
        flash("Access denied.", "danger")
        return redirect("/")
    return None

# ══════════════════════════════════════════════════════════════════════════════
# HOME
# ══════════════════════════════════════════════════════════════════════════════
@app.route("/")
def home():
    return render_template("index.html")

# ══════════════════════════════════════════════════════════════════════════════
# LOGIN
# Worker login:
#   - Admin registers a worker with name + phone + password field.
#   - Worker logs in with their PHONE NUMBER as username and the password
#     set by admin.  Their worker_id is looked up from the workers table.
# ══════════════════════════════════════════════════════════════════════════════
@app.route("/login", methods=["GET", "POST"])
def login():
    role = request.args.get("role", "worker")

    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"].strip()
        role     = request.form["role"]

        con = get_db()
        cur = con.cursor()

        if role == "worker":
            # Workers authenticate directly against the workers table.
            # username = phone number, password = worker_password column.
            cur.execute(
                "SELECT id, name FROM workers WHERE phone=%s AND worker_password=%s",
                (username, password)
            )
            worker = cur.fetchone()

            if worker:
                session["user"]      = worker[1]          # display name
                session["role"]      = "worker"
                session["worker_id"] = worker[0]
                flash(f"Welcome, {worker[1]}!", "success")
                return redirect("/worker_dashboard")
            else:
                flash("Invalid phone number or password.", "danger")

        else:
            # Admin / Doctor authenticate against the users table
            cur.execute(
                "SELECT id, username FROM users WHERE username=%s AND password=%s AND role=%s",
                (username, password, role)
            )
            user = cur.fetchone()

            if user:
                session["user"] = user[1]
                session["role"] = role
                flash("Login successful! Welcome back.", "success")
                if role == "admin":
                    return redirect("/admin_dashboard")
                else:
                    return redirect("/doctor_dashboard")
            else:
                flash("Invalid credentials. Please try again.", "danger")

    return render_template("login.html", role=role)

# ══════════════════════════════════════════════════════════════════════════════
# LOGOUT
# ══════════════════════════════════════════════════════════════════════════════
@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully.", "success")
    return redirect("/")

# ══════════════════════════════════════════════════════════════════════════════
# ADMIN DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
@app.route("/admin_dashboard")
def admin_dashboard():
    guard = require_login("admin")
    if guard: return guard

    con = get_db()
    cur = con.cursor()

    cur.execute("SELECT COUNT(*) FROM workers")
    total_workers = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM records")
    total_records = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM reports")
    total_reports = cur.fetchone()[0]

    cur.execute("SELECT COUNT(DISTINCT region) FROM workers")
    regions = cur.fetchone()[0]

    cur.execute("SELECT * FROM workers ORDER BY id DESC LIMIT 5")
    recent_workers = cur.fetchall()

    return render_template(
        "admin_dashboard.html",
        workers=total_workers,
        records=total_records,
        reports=total_reports,
        regions=regions,
        recent_workers=recent_workers
    )

# ══════════════════════════════════════════════════════════════════════════════
# DOCTOR DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
@app.route("/doctor_dashboard")
def doctor_dashboard():
    guard = require_login("doctor")
    if guard: return guard

    con = get_db()
    cur = con.cursor()

    cur.execute("SELECT COUNT(*) FROM records")
    total_records = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM workers")
    total_workers = cur.fetchone()[0]

    cur.execute("""
        SELECT r.*, w.name
        FROM records r
        LEFT JOIN workers w ON r.worker_id = w.id
        ORDER BY r.visit_date DESC LIMIT 8
    """)
    recent_records = cur.fetchall()

    return render_template(
        "doctor_dashboard.html",
        total_records=total_records,
        total_workers=total_workers,
        recent_records=recent_records
    )

# ══════════════════════════════════════════════════════════════════════════════
# WORKER DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
@app.route("/worker_dashboard")
def worker_dashboard():
    guard = require_login("worker")
    if guard: return guard

    con = get_db()
    cur = con.cursor()

    worker_id   = session.get("worker_id")
    worker_info = None
    total_records = 0
    total_reports = 0

    if worker_id:
        cur.execute("SELECT * FROM workers WHERE id=%s", (worker_id,))
        worker_info = cur.fetchone()

        cur.execute("SELECT COUNT(*) FROM records WHERE worker_id=%s", (worker_id,))
        total_records = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM reports WHERE worker_id=%s", (worker_id,))
        total_reports = cur.fetchone()[0]

    return render_template(
        "worker_dashboard.html",
        worker_info=worker_info,
        total_records=total_records,
        total_reports=total_reports
    )

# ══════════════════════════════════════════════════════════════════════════════
# MY RECORDS  (worker sees own records)
# ══════════════════════════════════════════════════════════════════════════════
@app.route("/my_records")
def my_records():
    guard = require_login("worker")
    if guard: return guard

    worker_id = session.get("worker_id")
    records   = []

    if worker_id:
        con = get_db()
        cur = con.cursor()
        cur.execute(
            "SELECT * FROM records WHERE worker_id=%s ORDER BY visit_date DESC",
            (worker_id,)
        )
        records = cur.fetchall()

    return render_template("my_records.html", records=records)

# ══════════════════════════════════════════════════════════════════════════════
# MY REPORTS  (worker downloads own reports)
# ══════════════════════════════════════════════════════════════════════════════
@app.route("/my_reports")
def my_reports():
    guard = require_login("worker")
    if guard: return guard

    worker_id = session.get("worker_id")
    reports   = []

    if worker_id:
        con = get_db()
        cur = con.cursor()
        cur.execute(
            "SELECT id, filename FROM reports WHERE worker_id=%s",
            (worker_id,)
        )
        reports = cur.fetchall()

    return render_template("my_reports.html", reports=reports)

# ══════════════════════════════════════════════════════════════════════════════
# ALL WORKERS  (admin)
# ══════════════════════════════════════════════════════════════════════════════
@app.route("/all_workers")
def all_workers():
    guard = require_login("admin")
    if guard: return guard

    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT * FROM workers ORDER BY id DESC")
    workers = cur.fetchall()

    return render_template("all_workers.html", workers=workers)

# ══════════════════════════════════════════════════════════════════════════════
# ADD WORKER  (admin registers a migrant worker)
# The worker's phone number becomes their login username.
# Admin also sets a temporary password for the worker.
# ══════════════════════════════════════════════════════════════════════════════
@app.route("/add_worker", methods=["GET", "POST"])
def add_worker():
    guard = require_login("admin")
    if guard: return guard

    if request.method == "POST":
        name          = request.form["name"].strip()
        gender        = request.form["gender"]
        age           = request.form["age"]
        phone         = request.form["phone"].strip()
        region        = request.form["region"]
        origin_state  = request.form.get("origin_state", "")
        worker_password = request.form["worker_password"].strip()

        if len(phone) != 10 or not phone.isdigit():
            flash("Phone number must be exactly 10 digits.", "danger")
            return redirect("/add_worker")

        if len(worker_password) < 4:
            flash("Password must be at least 4 characters.", "danger")
            return redirect("/add_worker")

        con = get_db()
        cur = con.cursor()

        # Check duplicate phone
        cur.execute("SELECT id FROM workers WHERE phone=%s", (phone,))
        if cur.fetchone():
            flash("A worker with this phone number already exists.", "danger")
            return redirect("/add_worker")

        cur.execute(
            """INSERT INTO workers(name, gender, age, phone, region, origin_state, worker_password)
               VALUES(%s, %s, %s, %s, %s, %s, %s)""",
            (name, gender, age, phone, region, origin_state, worker_password)
        )
        con.commit()
        flash(
            f"Worker '{name}' registered! They can log in with phone: {phone} and the password you set.",
            "success"
        )
        return redirect("/add_worker")

    return render_template("add_worker.html")

# ══════════════════════════════════════════════════════════════════════════════
# ADD MEDICAL RECORD  (doctor)
# ══════════════════════════════════════════════════════════════════════════════
@app.route("/add_record", methods=["GET", "POST"])
def add_record():
    guard = require_login("doctor")
    if guard: return guard

    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT id, name FROM workers ORDER BY name")
    workers = cur.fetchall()

    if request.method == "POST":
        worker_id = request.form["worker_id"]
        symptoms  = request.form["symptoms"]
        diagnosis = request.form["diagnosis"]
        medicines = request.form["medicines"]
        doctor    = request.form["doctor"]

        cur.execute(
            """INSERT INTO records(worker_id, symptoms, diagnosis, medicines, doctor_name, visit_date)
               VALUES(%s, %s, %s, %s, %s, CURDATE())""",
            (worker_id, symptoms, diagnosis, medicines, doctor)
        )
        con.commit()
        flash("Medical record added successfully!", "success")
        return redirect("/add_record")

    return render_template("add_record.html", workers=workers)

# ══════════════════════════════════════════════════════════════════════════════
# SEARCH  (admin + doctor only)
# ══════════════════════════════════════════════════════════════════════════════
@app.route("/search", methods=["GET", "POST"])
def search():
    guard = require_login()
    if guard: return guard

    if session.get("role") == "worker":
        return redirect("/worker_dashboard")

    data    = []
    keyword = None

    if request.method == "POST":
        keyword = request.form["keyword"].strip()
        con = get_db()
        cur = con.cursor()
        cur.execute(
            """SELECT * FROM workers
               WHERE CAST(id AS CHAR) LIKE %s
               OR name LIKE %s
               OR phone LIKE %s""",
            ('%'+keyword+'%', '%'+keyword+'%', '%'+keyword+'%')
        )
        data = cur.fetchall()

    return render_template("search.html", data=data, keyword=keyword)

# ══════════════════════════════════════════════════════════════════════════════
# VIEW RECORDS  (admin, doctor, or the worker themselves)
# ══════════════════════════════════════════════════════════════════════════════
@app.route("/records/<int:id>")
def view_records(id):
    guard = require_login()
    if guard: return guard

    if session.get("role") == "worker" and session.get("worker_id") != id:
        flash("Access denied.", "danger")
        return redirect("/worker_dashboard")

    con = get_db()
    cur = con.cursor()

    cur.execute("SELECT * FROM workers WHERE id=%s", (id,))
    worker = cur.fetchone()

    cur.execute(
        "SELECT * FROM records WHERE worker_id=%s ORDER BY visit_date DESC",
        (id,)
    )
    records = cur.fetchall()

    return render_template("view_records.html", records=records, worker=worker)

# ══════════════════════════════════════════════════════════════════════════════
# FILE UPLOAD  (admin)
# ══════════════════════════════════════════════════════════════════════════════
@app.route("/upload", methods=["GET", "POST"])
def upload():
    guard = require_login("admin")
    if guard: return guard

    con = get_db()
    cur = con.cursor()

    cur.execute("SELECT id, name FROM workers ORDER BY name")
    workers = cur.fetchall()

    cur.execute("""
        SELECT r.id, r.worker_id, w.name, r.filename
        FROM reports r
        LEFT JOIN workers w ON r.worker_id = w.id
        ORDER BY r.id DESC LIMIT 10
    """)
    recent_uploads = cur.fetchall()

    if request.method == "POST":
        worker_id = request.form["worker_id"]
        file      = request.files["file"]

        if file.filename == "":
            flash("Please select a file to upload.", "danger")
            return redirect("/upload")

        allowed = {"pdf", "jpg", "jpeg", "png", "docx"}
        ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
        if ext not in allowed:
            flash("File type not allowed. Upload PDF, JPG, PNG, or DOCX.", "danger")
            return redirect("/upload")

        filepath = os.path.join(app.config["UPLOAD_FOLDER"], file.filename)
        file.save(filepath)

        cur.execute(
            "INSERT INTO reports(worker_id, filename) VALUES(%s, %s)",
            (worker_id, file.filename)
        )
        con.commit()
        flash("Report uploaded successfully!", "success")
        return redirect("/upload")

    return render_template("upload.html", workers=workers, recent_uploads=recent_uploads)

# ══════════════════════════════════════════════════════════════════════════════
# DOWNLOAD
# ══════════════════════════════════════════════════════════════════════════════
@app.route("/download/<filename>")
def download(filename):
    guard = require_login()
    if guard: return guard
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename, as_attachment=True)

# ══════════════════════════════════════════════════════════════════════════════
# ANALYTICS  (admin)
# ══════════════════════════════════════════════════════════════════════════════
@app.route("/analytics")
def analytics():
    guard = require_login("admin")
    if guard: return guard

    con = get_db()
    cur = con.cursor()

    cur.execute("SELECT COUNT(*) FROM workers")
    total_workers = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM records")
    total_records = cur.fetchone()[0]

    cur.execute("SELECT COUNT(DISTINCT diagnosis) FROM records")
    unique_diagnoses = cur.fetchone()[0]

    cur.execute("""
        SELECT COUNT(*) FROM records
        WHERE LOWER(diagnosis) LIKE '%fever%'
           OR LOWER(diagnosis) LIKE '%dengue%'
           OR LOWER(diagnosis) LIKE '%malaria%'
           OR LOWER(diagnosis) LIKE '%typhoid%'
           OR LOWER(diagnosis) LIKE '%covid%'
           OR LOWER(diagnosis) LIKE '%tuberculosis%'
           OR LOWER(diagnosis) LIKE '%tb%'
    """)
    infectious_cases = cur.fetchone()[0]

    cur.execute("SELECT region, COUNT(*) AS cnt FROM workers GROUP BY region ORDER BY cnt DESC")
    region_data = cur.fetchall()
    max_region  = max((r[1] for r in region_data), default=1)

    cur.execute("""
        SELECT diagnosis, COUNT(*) AS cnt
        FROM records GROUP BY diagnosis ORDER BY cnt DESC LIMIT 8
    """)
    diagnosis_data = cur.fetchall()
    max_diagnosis  = max((d[1] for d in diagnosis_data), default=1)

    cur.execute("SELECT gender, COUNT(*) FROM workers GROUP BY gender")
    gender_data = cur.fetchall()

    cur.execute("SELECT age FROM workers")
    ages = [row[0] for row in cur.fetchall()]
    age_buckets = {"18-25": 0, "26-35": 0, "36-45": 0, "46-55": 0, "55+": 0}
    for a in ages:
        if   a <= 25: age_buckets["18-25"] += 1
        elif a <= 35: age_buckets["26-35"] += 1
        elif a <= 45: age_buckets["36-45"] += 1
        elif a <= 55: age_buckets["46-55"] += 1
        else:         age_buckets["55+"]   += 1
    age_data = list(age_buckets.items())
    max_age  = max((v for _, v in age_data), default=1)

    cur.execute("""
        SELECT w.name, w.region, r.diagnosis, r.doctor_name, r.visit_date
        FROM records r
        LEFT JOIN workers w ON r.worker_id = w.id
        ORDER BY r.visit_date DESC LIMIT 15
    """)
    recent_records = cur.fetchall()

    return render_template(
        "analytics.html",
        total_workers=total_workers,
        total_records=total_records,
        unique_diagnoses=unique_diagnoses,
        infectious_cases=infectious_cases,
        region_data=region_data,
        max_region=max_region,
        diagnosis_data=diagnosis_data,
        max_diagnosis=max_diagnosis,
        gender_data=gender_data,
        age_data=age_data,
        max_age=max_age,
        recent_records=recent_records
    )

if __name__ == "__main__":
    app.run(debug=True)
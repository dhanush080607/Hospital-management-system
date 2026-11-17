from flask import Flask, render_template, request, redirect, url_for, session, flash
import mysql.connector
from functools import wraps

app = Flask(__name__)
import os

app.secret_key = os.environ.get("SECRET_KEY")

MYSQL_HOST = os.environ.get("MYSQL_HOST")
MYSQL_USER = os.environ.get("MYSQL_USER")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD")
MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE", "hospital_db")
MYSQL_PORT = int(os.environ.get("MYSQL_PORT", 3306))

# =========================================================
# CONSTANTS
# =========================================================

DEPARTMENTS = [
    "General Medicine",
    "Cardiology",
    "Neurology",
    "Orthopedics",
    "Pediatrics",
    "Dermatology",
    "Gynecology",
    "ENT",
    "Dental",
    "Emergency"
]

DOCTOR_AVAILABILITY = [
    "Available",
    "On Leave"
]

ROOM_TYPES = [
    "General",
    "Private",
    "ICU"
]

BED_STATUSES = [
    "Available",
    "Occupied"
]

# =========================================================
# DATABASE CONNECTION
# =========================================================

def get_db_connection(database=None):
    try:
        config = {
            "host": MYSQL_HOST,
            "user": MYSQL_USER,
            "password": MYSQL_PASSWORD,
            "port": MYSQL_PORT
        }

        if database:
            config["database"] = database

        return mysql.connector.connect(**config)

    except mysql.connector.Error as err:
        print("Database connection error:", err)
        return None


# =========================================================
# DATABASE SETUP
# =========================================================

def setup_database():

    # Create database
    connection = get_db_connection()

    if connection is None:
        print("Could not connect to MySQL.")
        return

    cursor = connection.cursor()

    cursor.execute(
        f"CREATE DATABASE IF NOT EXISTS {MYSQL_DATABASE}"
    )

    cursor.close()
    connection.close()

    # Connect to hospital database
    connection = get_db_connection(MYSQL_DATABASE)

    if connection is None:
        print("Could not connect to hospital database.")
        return

    cursor = connection.cursor()

    # -----------------------------------------------------
    # PATIENTS TABLE
    # -----------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS patients (
            patient_id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            age INT NOT NULL,
            gender VARCHAR(20) NOT NULL,
            phone VARCHAR(15),
            address VARCHAR(255),
            disease VARCHAR(100),
            status VARCHAR(20) DEFAULT 'Active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # -----------------------------------------------------
    # DOCTORS TABLE
    # -----------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS doctors (
            doctor_id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            specialization VARCHAR(100) NOT NULL,
            phone VARCHAR(15),
            experience INT,
            department VARCHAR(100) DEFAULT 'General Medicine',
            availability VARCHAR(20) DEFAULT 'Available',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # -----------------------------------------------------
    # APPOINTMENTS TABLE
    # -----------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS appointments (
            appointment_id INT AUTO_INCREMENT PRIMARY KEY,
            patient_id INT NOT NULL,
            doctor_id INT NOT NULL,
            appointment_date DATE NOT NULL,
            appointment_time TIME NOT NULL,
            reason VARCHAR(255),
            status VARCHAR(20) DEFAULT 'Scheduled',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (patient_id)
                REFERENCES patients(patient_id)
                ON DELETE CASCADE,
            FOREIGN KEY (doctor_id)
                REFERENCES doctors(doctor_id)
                ON DELETE CASCADE
        )
    """)

    # -----------------------------------------------------
    # ADD MISSING COLUMNS TO OLD DATABASE
    # -----------------------------------------------------

    # Patient status
    cursor.execute("""
        SELECT COUNT(*)
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = %s
        AND TABLE_NAME = 'patients'
        AND COLUMN_NAME = 'status'
    """, (MYSQL_DATABASE,))

    if cursor.fetchone()[0] == 0:
        cursor.execute("""
            ALTER TABLE patients
            ADD COLUMN status VARCHAR(20) DEFAULT 'Active'
        """)

    # Doctor department
    cursor.execute("""
        SELECT COUNT(*)
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = %s
        AND TABLE_NAME = 'doctors'
        AND COLUMN_NAME = 'department'
    """, (MYSQL_DATABASE,))

    if cursor.fetchone()[0] == 0:
        cursor.execute("""
            ALTER TABLE doctors
            ADD COLUMN department VARCHAR(100)
            DEFAULT 'General Medicine'
        """)

    # Doctor availability
    cursor.execute("""
        SELECT COUNT(*)
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = %s
        AND TABLE_NAME = 'doctors'
        AND COLUMN_NAME = 'availability'
    """, (MYSQL_DATABASE,))

    if cursor.fetchone()[0] == 0:
        cursor.execute("""
            ALTER TABLE doctors
            ADD COLUMN availability VARCHAR(20)
            DEFAULT 'Available'
        """)

    # Appointment status
    cursor.execute("""
        SELECT COUNT(*)
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = %s
        AND TABLE_NAME = 'appointments'
        AND COLUMN_NAME = 'status'
    """, (MYSQL_DATABASE,))

    if cursor.fetchone()[0] == 0:
        cursor.execute("""
            ALTER TABLE appointments
            ADD COLUMN status VARCHAR(20)
            DEFAULT 'Scheduled'
        """)

    # -----------------------------------------------------
    # BEDS TABLE
    # -----------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS beds (
            bed_id INT AUTO_INCREMENT PRIMARY KEY,
            room_number VARCHAR(20) NOT NULL,
            bed_number VARCHAR(20) NOT NULL,
            room_type VARCHAR(50) NOT NULL,
            patient_id INT NULL,
            status VARCHAR(20) DEFAULT 'Available',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            UNIQUE KEY unique_room_bed
            (room_number, bed_number),

            FOREIGN KEY (patient_id)
                REFERENCES patients(patient_id)
                ON DELETE SET NULL
        )
    """)

    connection.commit()

    cursor.close()
    connection.close()

    print("Database setup completed successfully.")


# =========================================================
# LOGIN REQUIRED
# =========================================================

def login_required(function):

    @wraps(function)
    def decorated_function(*args, **kwargs):

        if "logged_in" not in session:
            return redirect(url_for("login"))

        return function(*args, **kwargs)

    return decorated_function


# =========================================================
# HOME / DASHBOARD
# =========================================================

@app.route("/")
@login_required
def home():

    connection = get_db_connection(MYSQL_DATABASE)

    if connection is None:
        flash("Database connection failed.", "danger")
        return render_template("index.html")

    cursor = connection.cursor(dictionary=True)

    # -----------------------------------------------------
    # SEARCH VALUES
    # -----------------------------------------------------

    patient_search = request.args.get("patient_search", "").strip()
    doctor_search = request.args.get("doctor_search", "").strip()
    appointment_search = request.args.get("appointment_search", "").strip()
    bed_search = request.args.get("bed_search", "").strip()

    # -----------------------------------------------------
    # PATIENTS
    # -----------------------------------------------------

    if patient_search:

        patient_query = """
            SELECT *
            FROM patients
            WHERE name LIKE %s
               OR phone LIKE %s
               OR disease LIKE %s
               OR address LIKE %s
               OR gender LIKE %s
               OR status LIKE %s
            ORDER BY patient_id DESC
        """

        search_value = f"%{patient_search}%"

        cursor.execute(
            patient_query,
            (
                search_value,
                search_value,
                search_value,
                search_value,
                search_value,
                search_value
            )
        )

    else:

        cursor.execute("""
            SELECT *
            FROM patients
            ORDER BY patient_id DESC
        """)

    patients = cursor.fetchall()

    # -----------------------------------------------------
    # DOCTORS
    # -----------------------------------------------------

    if doctor_search:

        doctor_query = """
            SELECT *
            FROM doctors
            WHERE name LIKE %s
               OR specialization LIKE %s
               OR phone LIKE %s
               OR department LIKE %s
               OR availability LIKE %s
            ORDER BY doctor_id DESC
        """

        search_value = f"%{doctor_search}%"

        cursor.execute(
            doctor_query,
            (
                search_value,
                search_value,
                search_value,
                search_value,
                search_value
            )
        )

    else:

        cursor.execute("""
            SELECT *
            FROM doctors
            ORDER BY doctor_id DESC
        """)

    doctors = cursor.fetchall()

    # -----------------------------------------------------
    # APPOINTMENTS
    # -----------------------------------------------------

    if appointment_search:

        appointment_query = """
            SELECT
                a.*,
                p.name AS patient_name,
                d.name AS doctor_name,
                d.department AS doctor_department
            FROM appointments a
            JOIN patients p
                ON a.patient_id = p.patient_id
            JOIN doctors d
                ON a.doctor_id = d.doctor_id
            WHERE p.name LIKE %s
               OR d.name LIKE %s
               OR d.department LIKE %s
               OR a.reason LIKE %s
               OR a.status LIKE %s
            ORDER BY a.appointment_id DESC
        """

        search_value = f"%{appointment_search}%"

        cursor.execute(
            appointment_query,
            (
                search_value,
                search_value,
                search_value,
                search_value,
                search_value
            )
        )

    else:

        cursor.execute("""
            SELECT
                a.*,
                p.name AS patient_name,
                d.name AS doctor_name,
                d.department AS doctor_department
            FROM appointments a
            JOIN patients p
                ON a.patient_id = p.patient_id
            JOIN doctors d
                ON a.doctor_id = d.doctor_id
            ORDER BY a.appointment_id DESC
        """)

    appointments = cursor.fetchall()

    # -----------------------------------------------------
    # BEDS
    # -----------------------------------------------------

    if bed_search:

        bed_query = """
            SELECT
                b.*,
                p.name AS patient_name
            FROM beds b
            LEFT JOIN patients p
                ON b.patient_id = p.patient_id
            WHERE b.room_number LIKE %s
               OR b.bed_number LIKE %s
               OR b.room_type LIKE %s
               OR b.status LIKE %s
               OR p.name LIKE %s
            ORDER BY b.bed_id DESC
        """

        search_value = f"%{bed_search}%"

        cursor.execute(
            bed_query,
            (
                search_value,
                search_value,
                search_value,
                search_value,
                search_value
            )
        )

    else:

        cursor.execute("""
            SELECT
                b.*,
                p.name AS patient_name
            FROM beds b
            LEFT JOIN patients p
                ON b.patient_id = p.patient_id
            ORDER BY b.bed_id DESC
        """)

    beds = cursor.fetchall()

    # -----------------------------------------------------
    # DASHBOARD COUNTS
    # -----------------------------------------------------

    cursor.execute("SELECT COUNT(*) AS count FROM patients")
    patient_count = cursor.fetchone()["count"]

    cursor.execute("""
        SELECT COUNT(*)
        AS count
        FROM patients
        WHERE status = 'Active'
    """)
    active_patient_count = cursor.fetchone()["count"]

    cursor.execute("""
        SELECT COUNT(*)
        AS count
        FROM patients
        WHERE status = 'Discharged'
    """)
    discharged_patient_count = cursor.fetchone()["count"]

    cursor.execute("SELECT COUNT(*) AS count FROM doctors")
    doctor_count = cursor.fetchone()["count"]

    cursor.execute("""
        SELECT COUNT(*)
        AS count
        FROM doctors
        WHERE availability = 'Available'
    """)
    available_doctor_count = cursor.fetchone()["count"]

    cursor.execute("""
        SELECT COUNT(*)
        AS count
        FROM doctors
        WHERE availability = 'On Leave'
    """)
    on_leave_doctor_count = cursor.fetchone()["count"]

    cursor.execute("""
        SELECT COUNT(*)
        AS count
        FROM appointments
    """)
    appointment_count = cursor.fetchone()["count"]

    cursor.execute("""
        SELECT COUNT(*)
        AS count
        FROM appointments
        WHERE status = 'Scheduled'
    """)
    scheduled_appointment_count = cursor.fetchone()["count"]

    cursor.execute("""
        SELECT COUNT(*)
        AS count
        FROM appointments
        WHERE status = 'Completed'
    """)
    completed_appointment_count = cursor.fetchone()["count"]

    cursor.execute("""
        SELECT COUNT(*)
        AS count
        FROM appointments
        WHERE status = 'Cancelled'
    """)
    cancelled_appointment_count = cursor.fetchone()["count"]

    # -----------------------------------------------------
    # BED COUNTS
    # -----------------------------------------------------

    cursor.execute("""
        SELECT COUNT(*)
        AS count
        FROM beds
    """)
    total_bed_count = cursor.fetchone()["count"]

    cursor.execute("""
        SELECT COUNT(*)
        AS count
        FROM beds
        WHERE status = 'Available'
    """)
    available_bed_count = cursor.fetchone()["count"]

    cursor.execute("""
        SELECT COUNT(*)
        AS count
        FROM beds
        WHERE status = 'Occupied'
    """)
    occupied_bed_count = cursor.fetchone()["count"]

    cursor.close()
    connection.close()

    return render_template(
        "index.html",

        # Data
        patients=patients,
        doctors=doctors,
        appointments=appointments,
        beds=beds,

        # Search
        patient_search=patient_search,
        doctor_search=doctor_search,
        appointment_search=appointment_search,
        bed_search=bed_search,

        # Dropdowns
        departments=DEPARTMENTS,
        doctor_availability=DOCTOR_AVAILABILITY,
        room_types=ROOM_TYPES,
        bed_statuses=BED_STATUSES,

        # Dashboard
        patient_count=patient_count,
        active_patient_count=active_patient_count,
        discharged_patient_count=discharged_patient_count,

        doctor_count=doctor_count,
        available_doctor_count=available_doctor_count,
        on_leave_doctor_count=on_leave_doctor_count,

        appointment_count=appointment_count,
        scheduled_appointment_count=scheduled_appointment_count,
        completed_appointment_count=completed_appointment_count,
        cancelled_appointment_count=cancelled_appointment_count,

        total_bed_count=total_bed_count,
        available_bed_count=available_bed_count,
        occupied_bed_count=occupied_bed_count
    )


# =========================================================
# LOGIN
# =========================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if username == "admin" and password == "admin123":

            session["logged_in"] = True
            session["username"] = username

            flash("Login successful!", "success")

            return redirect(url_for("home"))

        flash("Invalid username or password.", "danger")

    return render_template("login.html")


# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
def logout():

    session.clear()

    flash("You have been logged out.", "success")

    return redirect(url_for("login"))


# =========================================================
# ADD PATIENT
# =========================================================

@app.route("/add_patient", methods=["POST"])
@login_required
def add_patient():

    name = request.form.get("name", "").strip()
    age = request.form.get("age", "").strip()
    gender = request.form.get("gender", "").strip()
    phone = request.form.get("phone", "").strip()
    address = request.form.get("address", "").strip()
    disease = request.form.get("disease", "").strip()
    status = request.form.get("status", "Active").strip()

    if not name or not age or not gender:

        flash(
            "Name, age and gender are required.",
            "danger"
        )

        return redirect(url_for("home"))

    try:
        age = int(age)

    except ValueError:

        flash("Age must be a number.", "danger")

        return redirect(url_for("home"))

    if status not in ["Active", "Discharged"]:
        status = "Active"

    connection = get_db_connection(MYSQL_DATABASE)
    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO patients
        (name, age, gender, phone, address, disease, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (
        name,
        age,
        gender,
        phone,
        address,
        disease,
        status
    ))

    connection.commit()

    cursor.close()
    connection.close()

    flash("Patient added successfully.", "success")

    return redirect(url_for("home"))


# =========================================================
# UPDATE PATIENT
# =========================================================

@app.route("/update_patient/<int:patient_id>", methods=["POST"])
@login_required
def update_patient(patient_id):

    name = request.form.get("name", "").strip()
    age = request.form.get("age", "").strip()
    gender = request.form.get("gender", "").strip()
    phone = request.form.get("phone", "").strip()
    address = request.form.get("address", "").strip()
    disease = request.form.get("disease", "").strip()
    status = request.form.get("status", "Active").strip()

    if not name or not age or not gender:

        flash(
            "Name, age and gender are required.",
            "danger"
        )

        return redirect(url_for("home"))

    try:
        age = int(age)

    except ValueError:

        flash("Age must be a number.", "danger")

        return redirect(url_for("home"))

    connection = get_db_connection(MYSQL_DATABASE)
    cursor = connection.cursor()

    cursor.execute("""
        UPDATE patients
        SET
            name = %s,
            age = %s,
            gender = %s,
            phone = %s,
            address = %s,
            disease = %s,
            status = %s
        WHERE patient_id = %s
    """, (
        name,
        age,
        gender,
        phone,
        address,
        disease,
        status,
        patient_id
    ))

    connection.commit()

    cursor.close()
    connection.close()

    flash("Patient updated successfully.", "success")

    return redirect(url_for("home"))


# =========================================================
# DELETE PATIENT
# =========================================================

@app.route("/delete_patient/<int:patient_id>")
@login_required
def delete_patient(patient_id):

    connection = get_db_connection(MYSQL_DATABASE)
    cursor = connection.cursor()

    cursor.execute("""
        UPDATE beds
        SET
            patient_id = NULL,
            status = 'Available'
        WHERE patient_id = %s
    """, (patient_id,))

    cursor.execute("""
        DELETE FROM patients
        WHERE patient_id = %s
    """, (patient_id,))

    connection.commit()

    cursor.close()
    connection.close()

    flash("Patient deleted successfully.", "success")

    return redirect(url_for("home"))


# =========================================================
# ADD DOCTOR
# =========================================================

@app.route("/add_doctor", methods=["POST"])
@login_required
def add_doctor():

    name = request.form.get("name", "").strip()
    specialization = request.form.get("specialization", "").strip()
    phone = request.form.get("phone", "").strip()
    experience = request.form.get("experience", "").strip()
    department = request.form.get(
        "department",
        "General Medicine"
    ).strip()

    availability = request.form.get(
        "availability",
        "Available"
    ).strip()

    if not name or not specialization:

        flash(
            "Doctor name and specialization are required.",
            "danger"
        )

        return redirect(url_for("home"))

    try:

        experience = int(experience) if experience else 0

    except ValueError:

        flash(
            "Experience must be a number.",
            "danger"
        )

        return redirect(url_for("home"))

    if department not in DEPARTMENTS:
        department = "General Medicine"

    if availability not in DOCTOR_AVAILABILITY:
        availability = "Available"

    connection = get_db_connection(MYSQL_DATABASE)
    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO doctors
        (
            name,
            specialization,
            phone,
            experience,
            department,
            availability
        )
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (
        name,
        specialization,
        phone,
        experience,
        department,
        availability
    ))

    connection.commit()

    cursor.close()
    connection.close()

    flash("Doctor added successfully.", "success")

    return redirect(url_for("home"))


# =========================================================
# UPDATE DOCTOR
# =========================================================

@app.route("/update_doctor/<int:doctor_id>", methods=["POST"])
@login_required
def update_doctor(doctor_id):

    name = request.form.get("name", "").strip()
    specialization = request.form.get("specialization", "").strip()
    phone = request.form.get("phone", "").strip()
    experience = request.form.get("experience", "").strip()

    department = request.form.get(
        "department",
        "General Medicine"
    ).strip()

    availability = request.form.get(
        "availability",
        "Available"
    ).strip()

    if not name or not specialization:

        flash(
            "Doctor name and specialization are required.",
            "danger"
        )

        return redirect(url_for("home"))

    try:

        experience = int(experience) if experience else 0

    except ValueError:

        flash(
            "Experience must be a number.",
            "danger"
        )

        return redirect(url_for("home"))

    if department not in DEPARTMENTS:
        department = "General Medicine"

    if availability not in DOCTOR_AVAILABILITY:
        availability = "Available"

    connection = get_db_connection(MYSQL_DATABASE)
    cursor = connection.cursor()

    cursor.execute("""
        UPDATE doctors
        SET
            name = %s,
            specialization = %s,
            phone = %s,
            experience = %s,
            department = %s,
            availability = %s
        WHERE doctor_id = %s
    """, (
        name,
        specialization,
        phone,
        experience,
        department,
        availability,
        doctor_id
    ))

    connection.commit()

    cursor.close()
    connection.close()

    flash("Doctor updated successfully.", "success")

    return redirect(url_for("home"))


# =========================================================
# DELETE DOCTOR
# =========================================================

@app.route("/delete_doctor/<int:doctor_id>")
@login_required
def delete_doctor(doctor_id):

    connection = get_db_connection(MYSQL_DATABASE)
    cursor = connection.cursor()

    cursor.execute("""
        DELETE FROM doctors
        WHERE doctor_id = %s
    """, (doctor_id,))

    connection.commit()

    cursor.close()
    connection.close()

    flash("Doctor deleted successfully.", "success")

    return redirect(url_for("home"))


# =========================================================
# ADD APPOINTMENT
# =========================================================

@app.route("/add_appointment", methods=["POST"])
@login_required
def add_appointment():

    patient_id = request.form.get("patient_id", "").strip()
    doctor_id = request.form.get("doctor_id", "").strip()
    appointment_date = request.form.get(
        "appointment_date",
        ""
    ).strip()

    appointment_time = request.form.get(
        "appointment_time",
        ""
    ).strip()

    reason = request.form.get("reason", "").strip()

    status = request.form.get(
        "status",
        "Scheduled"
    ).strip()

    if not patient_id or not doctor_id:
        flash(
            "Patient and doctor are required.",
            "danger"
        )

        return redirect(url_for("home"))

    if not appointment_date or not appointment_time:

        flash(
            "Appointment date and time are required.",
            "danger"
        )

        return redirect(url_for("home"))

    if status not in [
        "Scheduled",
        "Completed",
        "Cancelled"
    ]:
        status = "Scheduled"

    connection = get_db_connection(MYSQL_DATABASE)
    cursor = connection.cursor()

    cursor.execute("""
        SELECT patient_id
        FROM patients
        WHERE patient_id = %s
    """, (patient_id,))

    patient_exists = cursor.fetchone()

    cursor.execute("""
        SELECT doctor_id
        FROM doctors
        WHERE doctor_id = %s
    """, (doctor_id,))

    doctor_exists = cursor.fetchone()

    if not patient_exists:

        cursor.close()
        connection.close()

        flash(
            "Selected patient does not exist.",
            "danger"
        )

        return redirect(url_for("home"))

    if not doctor_exists:

        cursor.close()
        connection.close()

        flash(
            "Selected doctor does not exist.",
            "danger"
        )

        return redirect(url_for("home"))

    cursor.execute("""
        INSERT INTO appointments
        (
            patient_id,
            doctor_id,
            appointment_date,
            appointment_time,
            reason,
            status
        )
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (
        patient_id,
        doctor_id,
        appointment_date,
        appointment_time,
        reason,
        status
    ))

    connection.commit()

    cursor.close()
    connection.close()

    flash(
        "Appointment added successfully.",
        "success"
    )

    return redirect(url_for("home"))


# =========================================================
# UPDATE APPOINTMENT
# =========================================================

@app.route(
    "/update_appointment/<int:appointment_id>",
    methods=["POST"]
)
@login_required
def update_appointment(appointment_id):

    patient_id = request.form.get("patient_id", "").strip()
    doctor_id = request.form.get("doctor_id", "").strip()

    appointment_date = request.form.get(
        "appointment_date",
        ""
    ).strip()

    appointment_time = request.form.get(
        "appointment_time",
        ""
    ).strip()

    reason = request.form.get("reason", "").strip()

    status = request.form.get(
        "status",
        "Scheduled"
    ).strip()

    if not patient_id or not doctor_id:

        flash(
            "Patient and doctor are required.",
            "danger"
        )

        return redirect(url_for("home"))

    if not appointment_date or not appointment_time:

        flash(
            "Appointment date and time are required.",
            "danger"
        )

        return redirect(url_for("home"))

    if status not in [
        "Scheduled",
        "Completed",
        "Cancelled"
    ]:
        status = "Scheduled"

    connection = get_db_connection(MYSQL_DATABASE)
    cursor = connection.cursor()

    cursor.execute("""
        UPDATE appointments
        SET
            patient_id = %s,
            doctor_id = %s,
            appointment_date = %s,
            appointment_time = %s,
            reason = %s,
            status = %s
        WHERE appointment_id = %s
    """, (
        patient_id,
        doctor_id,
        appointment_date,
        appointment_time,
        reason,
        status,
        appointment_id
    ))

    connection.commit()

    cursor.close()
    connection.close()

    flash(
        "Appointment updated successfully.",
        "success"
    )

    return redirect(url_for("home"))


# =========================================================
# DELETE APPOINTMENT
# =========================================================

@app.route(
    "/delete_appointment/<int:appointment_id>"
)
@login_required
def delete_appointment(appointment_id):

    connection = get_db_connection(MYSQL_DATABASE)
    cursor = connection.cursor()

    cursor.execute("""
        DELETE FROM appointments
        WHERE appointment_id = %s
    """, (appointment_id,))

    connection.commit()

    cursor.close()
    connection.close()

    flash(
        "Appointment deleted successfully.",
        "success"
    )

    return redirect(url_for("home"))


# =========================================================
# ADD BED
# =========================================================

@app.route("/add_bed", methods=["POST"])
@login_required
def add_bed():

    room_number = request.form.get(
        "room_number",
        ""
    ).strip()

    bed_number = request.form.get(
        "bed_number",
        ""
    ).strip()

    room_type = request.form.get(
        "room_type",
        "General"
    ).strip()

    patient_id = request.form.get(
        "patient_id",
        ""
    ).strip()

    status = request.form.get(
        "status",
        "Available"
    ).strip()

    # -----------------------------------------------------
    # VALIDATION
    # -----------------------------------------------------

    if not room_number or not bed_number:

        flash(
            "Room number and bed number are required.",
            "danger"
        )

        return redirect(url_for("home"))

    if room_type not in ROOM_TYPES:
        room_type = "General"

    if status not in BED_STATUSES:
        status = "Available"

    # If a patient is selected, bed must be occupied
    if patient_id:
        status = "Occupied"
    else:
        status = "Available"
        patient_id = None

    connection = get_db_connection(MYSQL_DATABASE)
    cursor = connection.cursor()

    # -----------------------------------------------------
    # CHECK PATIENT
    # -----------------------------------------------------

    if patient_id:

        cursor.execute("""
            SELECT patient_id
            FROM patients
            WHERE patient_id = %s
        """, (patient_id,))

        patient_exists = cursor.fetchone()

        if not patient_exists:

            cursor.close()
            connection.close()

            flash(
                "Selected patient does not exist.",
                "danger"
            )

            return redirect(url_for("home"))

    # -----------------------------------------------------
    # CHECK DUPLICATE BED
    # -----------------------------------------------------

    cursor.execute("""
        SELECT bed_id
        FROM beds
        WHERE room_number = %s
        AND bed_number = %s
    """, (
        room_number,
        bed_number
    ))

    existing_bed = cursor.fetchone()

    if existing_bed:

        cursor.close()
        connection.close()

        flash(
            "This room and bed number already exists.",
            "danger"
        )

        return redirect(url_for("home"))

    # -----------------------------------------------------
    # INSERT BED
    # -----------------------------------------------------

    cursor.execute("""
        INSERT INTO beds
        (
            room_number,
            bed_number,
            room_type,
            patient_id,
            status
        )
        VALUES (%s, %s, %s, %s, %s)
    """, (
        room_number,
        bed_number,
        room_type,
        patient_id,
        status
    ))

    connection.commit()

    cursor.close()
    connection.close()

    flash(
        "Room and bed added successfully.",
        "success"
    )

    return redirect(url_for("home"))


# =========================================================
# UPDATE BED
# =========================================================

@app.route(
    "/update_bed/<int:bed_id>",
    methods=["POST"]
)
@login_required
def update_bed(bed_id):

    room_number = request.form.get(
        "room_number",
        ""
    ).strip()

    bed_number = request.form.get(
        "bed_number",
        ""
    ).strip()

    room_type = request.form.get(
        "room_type",
        "General"
    ).strip()

    patient_id = request.form.get(
        "patient_id",
        ""
    ).strip()

    status = request.form.get(
        "status",
        "Available"
    ).strip()

    # -----------------------------------------------------
    # VALIDATION
    # -----------------------------------------------------

    if not room_number or not bed_number:

        flash(
            "Room number and bed number are required.",
            "danger"
        )

        return redirect(url_for("home"))

    if room_type not in ROOM_TYPES:
        room_type = "General"

    if status not in BED_STATUSES:
        status = "Available"

    # If Available, remove patient
    if status == "Available":

        patient_id = None

    # If patient selected, mark occupied
    elif patient_id:

        status = "Occupied"

    else:

        status = "Available"
        patient_id = None

    connection = get_db_connection(MYSQL_DATABASE)
    cursor = connection.cursor()

    # -----------------------------------------------------
    # CHECK PATIENT
    # -----------------------------------------------------

    if patient_id:

        cursor.execute("""
            SELECT patient_id
            FROM patients
            WHERE patient_id = %s
        """, (patient_id,))

        patient_exists = cursor.fetchone()

        if not patient_exists:

            cursor.close()
            connection.close()

            flash(
                "Selected patient does not exist.",
                "danger"
            )

            return redirect(url_for("home"))

    # -----------------------------------------------------
    # CHECK DUPLICATE ROOM/BED
    # -----------------------------------------------------

    cursor.execute("""
        SELECT bed_id
        FROM beds
        WHERE room_number = %s
        AND bed_number = %s
        AND bed_id != %s
    """, (
        room_number,
        bed_number,
        bed_id
    ))

    duplicate = cursor.fetchone()

    if duplicate:

        cursor.close()
        connection.close()

        flash(
            "Another bed already uses this room and bed number.",
            "danger"
        )

        return redirect(url_for("home"))

    # -----------------------------------------------------
    # UPDATE
    # -----------------------------------------------------

    cursor.execute("""
        UPDATE beds
        SET
            room_number = %s,
            bed_number = %s,
            room_type = %s,
            patient_id = %s,
            status = %s
        WHERE bed_id = %s
    """, (
        room_number,
        bed_number,
        room_type,
        patient_id,
        status,
        bed_id
    ))

    connection.commit()

    cursor.close()
    connection.close()

    flash(
        "Room and bed updated successfully.",
        "success"
    )

    return redirect(url_for("home"))


# =========================================================
# DELETE BED
# =========================================================

@app.route("/delete_bed/<int:bed_id>")
@login_required
def delete_bed(bed_id):

    connection = get_db_connection(MYSQL_DATABASE)
    cursor = connection.cursor()

    cursor.execute("""
        DELETE FROM beds
        WHERE bed_id = %s
    """, (bed_id,))

    connection.commit()

    cursor.close()
    connection.close()

    flash(
        "Room and bed deleted successfully.",
        "success"
    )

    return redirect(url_for("home"))

setup_database()
# =========================================================
# RUN APPLICATION
# =========================================================

if __name__ == "__main__":

    setup_database()

    app.run(
        debug=True,
        host="127.0.0.1",
        port=5000
    )

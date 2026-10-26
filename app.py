import hmac
import io
import math
import os
import sqlite3
from datetime import datetime, timedelta
from uuid import uuid4

from flask import (
    Flask,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_wtf import CSRFProtect
from PIL import Image, UnidentifiedImageError
from werkzeug.utils import secure_filename

# ---------------------------------------------------------------------------
# App configuration
# ---------------------------------------------------------------------------

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY", "pijar-dev-secret-change-in-prod"
)
app.config["UPLOAD_FOLDER"] = os.path.join(BASE_DIR, "static", "uploads")
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # 8 MB hard limit
app.config["WTF_CSRF_TIME_LIMIT"] = 3600  # 1-hour token expiry

# CSRF protection — applies to every POST, PUT, PATCH, DELETE automatically.
csrf = CSRFProtect(app)

# PIN fetched from environment; compare_digest used for constant-time comparison.
RESOLVE_PIN: str = os.environ.get("PIJAR_PIN", "1234")

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}

# Ensure upload directory exists once at startup.
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# ---------------------------------------------------------------------------
# Database — Flask g object pattern (no connection leaks)
# ---------------------------------------------------------------------------

DATABASE = os.path.join(BASE_DIR, "pijar.db")


def get_db() -> sqlite3.Connection:
    """
    Return the per-request SQLite connection, creating it if needed.
    Stored on Flask's g object so it is closed exactly once per request.
    """
    if "_database" not in g:
        g._database = sqlite3.connect(DATABASE)
        g._database.row_factory = sqlite3.Row
        g._database.execute("PRAGMA journal_mode=WAL")
        g._database.execute("PRAGMA foreign_keys=ON")
    return g._database


@app.teardown_appcontext
def close_db(exception: BaseException | None) -> None:
    """Close the SQLite connection at the end of every request/app context."""
    db = g.pop("_database", None)
    if db is not None:
        db.close()


# ---------------------------------------------------------------------------
# Schema initialisation & seed data
# ---------------------------------------------------------------------------

def init_db() -> None:
    """Create the reports table and run additive column migrations."""
    db = get_db()
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS reports (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            title          TEXT    NOT NULL,
            category       TEXT    NOT NULL,
            description    TEXT,
            latitude       REAL,
            longitude      REAL,
            issue_image    TEXT,
            resolved_image TEXT,
            budget_spent   REAL,
            budget_source  TEXT,
            created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            upvotes        INTEGER   DEFAULT 0,
            status         TEXT      DEFAULT 'pending'
        )
        """
    )
    db.commit()
    # Additive migration: description column added after v1 schema.
    existing_cols = {
        row[1] for row in db.execute("PRAGMA table_info(reports)").fetchall()
    }
    if "description" not in existing_cols:
        db.execute("ALTER TABLE reports ADD COLUMN description TEXT")
        db.commit()


def seed_db() -> None:
    """
    Insert 5 representative rows on first run.
    States covered:
      - 2 pending > 7 days (SLA overdue)
      - 1 pending < 7 days (normal)
      - 2 resolved (with budget data)
    """
    db = get_db()
    count = db.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
    if count > 0:
        return

    now = datetime.utcnow()
    rows = [
        {
            "title": "Jalan Berlubang Parah di Depan Tunjungan Plaza",
            "category": "Jalan Rusak",
            "description": (
                "Terdapat beberapa lubang besar dengan diameter sekitar 40-60 cm "
                "dan kedalaman 10 cm di lajur kiri jalan arah selatan. Kondisi ini "
                "sudah berlangsung lebih dari dua minggu dan telah menyebabkan "
                "dua kecelakaan ringan pada pengendara sepeda motor."
            ),
            "latitude": -7.2575, "longitude": 112.7383,
            "issue_image": None, "resolved_image": None,
            "budget_spent": None, "budget_source": None,
            "created_at": now - timedelta(days=14),
            "upvotes": 42, "status": "pending",
        },
        {
            "title": "Drainase Tersumbat Sampah di Jl. Gubeng Pojok",
            "category": "Drainase",
            "description": (
                "Saluran drainase di sisi timur jalan tersumbat total oleh tumpukan "
                "sampah plastik dan lumpur. Setiap kali hujan deras, air meluap ke "
                "badan jalan sedalam 15-20 cm dan mengganggu arus lalu lintas."
            ),
            "latitude": -7.2651, "longitude": 112.7519,
            "issue_image": None, "resolved_image": None,
            "budget_spent": None, "budget_source": None,
            "created_at": now - timedelta(days=10),
            "upvotes": 18, "status": "pending",
        },
        {
            "title": "Trotoar Pecah di Jl. Darmo",
            "category": "Trotoar",
            "description": (
                "Beberapa segmen paving block trotoar pecah dan terangkat, "
                "menciptakan permukaan tidak rata yang berbahaya bagi pejalan kaki, "
                "terutama lansia dan pengguna kursi roda."
            ),
            "latitude": -7.2831, "longitude": 112.7310,
            "issue_image": None, "resolved_image": None,
            "budget_spent": None, "budget_source": None,
            "created_at": now - timedelta(days=3),
            "upvotes": 7, "status": "pending",
        },
        {
            "title": "Lampu PJU Mati Total di Jembatan Wonokromo",
            "category": "PJU",
            "description": (
                "Seluruh 8 unit lampu penerangan jalan umum di sepanjang Jembatan "
                "Wonokromo tidak berfungsi sejak 20 hari lalu. Kondisi ini sangat "
                "gelap pada malam hari dan meningkatkan risiko kejahatan serta "
                "kecelakaan lalu lintas."
            ),
            "latitude": -7.3018, "longitude": 112.7299,
            "issue_image": None, "resolved_image": None,
            "budget_spent": 12500000.0, "budget_source": "APBD Kota Surabaya 2024",
            "created_at": now - timedelta(days=20),
            "upvotes": 31, "status": "resolved",
        },
        {
            "title": "Aspal Terkelupas di Jl. Kenjeran Raya",
            "category": "Jalan Rusak",
            "description": (
                "Lapisan aspal terkelupas di area sekitar 50 meter persegi akibat "
                "genangan air yang berkepanjangan. Permukaan jalan menjadi kasar "
                "dan berlubang-lubang kecil yang berpotensi merusak kendaraan."
            ),
            "latitude": -7.2309, "longitude": 112.7784,
            "issue_image": None, "resolved_image": None,
            "budget_spent": 47800000.0,
            "budget_source": "Dana Alokasi Khusus Infrastruktur 2024",
            "created_at": now - timedelta(days=30),
            "upvotes": 55, "status": "resolved",
        },
    ]
    db.executemany(
        """
        INSERT INTO reports
            (title, category, description, latitude, longitude, issue_image,
             resolved_image, budget_spent, budget_source, created_at, upvotes, status)
        VALUES
            (:title, :category, :description, :latitude, :longitude, :issue_image,
             :resolved_image, :budget_spent, :budget_source, :created_at, :upvotes, :status)
        """,
        rows,
    )
    db.commit()


# ---------------------------------------------------------------------------
# File upload helpers
# ---------------------------------------------------------------------------

def _allowed_extension(filename: str) -> bool:
    """Return True if the filename's extension is in the whitelist."""
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


def _verify_image(file_storage) -> bool:
    """
    Use Pillow to confirm the upload is a real, decodable image.

    Strategy:
      1. Read all bytes from the FileStorage stream into a BytesIO buffer.
      2. Ask Pillow to open and fully decode (load) the image — this rejects
         any file whose bytes cannot be interpreted as a known image format.
      3. Rewind the underlying Werkzeug stream so file_storage.save() can
         still read the original bytes.

    Note: Image.verify() is intentionally avoided here because it is
    destructive (leaves the image object unusable) and rejects even
    structurally sound images with minor checksum variations in some
    encoders. Image.open() + load() provides the same security guarantee
    (non-images raise UnidentifiedImageError or DecompressionBombError)
    while being practical for all real-world image files.

    Returns True on success, False on any failure.
    """
    try:
        raw = file_storage.read()
        img = Image.open(io.BytesIO(raw))
        img.load()  # fully decode; raises on non-image or corrupt data

        # Rewind so Werkzeug's FileStorage.save() can still write the bytes.
        try:
            file_storage.stream.seek(0)
        except (AttributeError, OSError):
            file_storage.stream = io.BytesIO(raw)

        return True
    except Exception:
        return False


def _save_upload(file_storage) -> str | None:
    """
    Validate (extension + Pillow content check), sanitise the filename,
    and persist the upload.

    The extension is extracted *before* secure_filename() so that files
    whose base names are stripped entirely (e.g. '../../../etc/passwd.png')
    still retain the correct extension.

    Returns the stored filename on success, None otherwise.
    """
    if not file_storage or not file_storage.filename:
        return None

    original_name = file_storage.filename
    if not _allowed_extension(original_name):
        return None

    # Extract extension before sanitisation.
    ext = original_name.rsplit(".", 1)[1].lower()

    # Verify actual image content with Pillow (defeats polyglot / extension spoofing).
    if not _verify_image(file_storage):
        return None

    # Build a collision-proof, path-traversal-safe filename.
    # secure_filename may reduce a unicode name like "文件.png" to just "png"
    # (the extension without a dot), which would produce "uuid_png" instead of
    # "uuid.png". Guard against this by checking that safe_base still contains
    # a proper extension after sanitisation.
    safe_base = secure_filename(original_name)
    if safe_base and safe_base.lower() != ext:
        # safe_base has a meaningful stem — use it directly.
        unique_name = f"{uuid4().hex}_{safe_base}"
    else:
        # secure_filename stripped the entire base name (or left only the
        # extension string without a dot prefix); fall back to uuid + ext.
        unique_name = f"{uuid4().hex}.{ext}"

    save_path = os.path.join(app.config["UPLOAD_FOLDER"], unique_name)
    file_storage.save(save_path)
    return unique_name


# ---------------------------------------------------------------------------
# Route / enrichment helpers
# ---------------------------------------------------------------------------

def _parse_created_at(raw: str) -> datetime:
    """Parse SQLite timestamp strings, handling optional fractional seconds."""
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return datetime.utcnow()


def _enrich_reports(rows) -> list[dict]:
    """
    Enrich sqlite3.Row objects with:
      - days_old   : int
      - urgency    : int  — resolved reports always score 0 so overdue pending
                           reports always rank above them in the dashboard.
      - is_overdue : bool — pending AND older than 7 days
    """
    now = datetime.utcnow()
    enriched = []
    for row in rows:
        r = dict(row)
        created  = _parse_created_at(r["created_at"])
        days_old = (now - created).days
        r["days_old"]   = days_old
        r["is_overdue"] = (r["status"] == "pending") and (days_old > 7)
        # Resolved reports are pinned to urgency 0 so they never outrank
        # active overdue reports.
        if r["status"] == "resolved":
            r["urgency"] = 0
        else:
            r["urgency"] = (days_old + 1) * (r["upvotes"] + 1)
        enriched.append(r)
    return sorted(enriched, key=lambda x: x["urgency"], reverse=True)


def _validate_coords(lat_str: str, lon_str: str) -> tuple[float | None, float | None]:
    """
    Parse and range-check latitude/longitude strings.
    Returns (lat, lon) floats on success, (None, None) on any error.
    """
    try:
        lat = float(lat_str) if lat_str else None
        lon = float(lon_str) if lon_str else None
    except ValueError:
        return None, None

    if lat is not None and not (-90.0 <= lat <= 90.0):
        return None, None
    if lon is not None and not (-180.0 <= lon <= 180.0):
        return None, None
    return lat, lon


# ---------------------------------------------------------------------------
# Dashboard route
# ---------------------------------------------------------------------------

@app.route("/")
def dashboard():
    """Public dashboard sorted by urgency score descending."""
    db = get_db()
    rows = db.execute("SELECT * FROM reports ORDER BY created_at DESC").fetchall()
    reports = _enrich_reports(rows)

    return render_template(
        "index.html",
        reports=reports,
        total=len(reports),
        pending_count=sum(1 for r in reports if r["status"] == "pending"),
        resolved_count=sum(1 for r in reports if r["status"] == "resolved"),
        shame_count=sum(1 for r in reports if r["is_overdue"]),
        upvoted_ids=list(session.get("upvoted_ids", [])),
    )


# ---------------------------------------------------------------------------
# Report submission route
# ---------------------------------------------------------------------------

@app.route("/report", methods=["GET", "POST"])
def report():
    """Citizen form to submit a new infrastructure report."""
    # form_data is passed back on validation failure so the user's input
    # is not lost (form retention).
    form_data = {}

    if request.method == "POST":
        form_data = request.form.to_dict()

        title       = request.form.get("title", "").strip()
        category    = request.form.get("category", "").strip()
        description = request.form.get("description", "").strip()
        lat, lon    = _validate_coords(
            request.form.get("latitude", "").strip(),
            request.form.get("longitude", "").strip(),
        )

        if not title or not category:
            flash("Judul dan kategori wajib diisi.", "error")
            return render_template("report.html", form_data=form_data), 422

        file     = request.files.get("issue_image")
        filename = None
        if file and file.filename:
            filename = _save_upload(file)
            if filename is None:
                flash(
                    "File gambar tidak valid. Gunakan PNG, JPG, JPEG, atau GIF yang asli.",
                    "error",
                )
                return render_template("report.html", form_data=form_data), 422

        db = get_db()
        db.execute(
            """
            INSERT INTO reports
                (title, category, description, latitude, longitude,
                 issue_image, status, upvotes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 'pending', 0, ?)
            """,
            (title, category, description or None, lat, lon,
             filename, datetime.utcnow()),
        )
        db.commit()

        flash(f'Laporan \u201c{title}\u201d berhasil dikirim. Terima kasih!', "success")
        return redirect(url_for("dashboard"))

    return render_template("report.html", form_data=form_data)


# ---------------------------------------------------------------------------
# Report detail route
# ---------------------------------------------------------------------------

@app.route("/detail/<int:report_id>")
def detail(report_id: int):
    """Public detail page for a single report."""
    db  = get_db()
    row = db.execute(
        "SELECT * FROM reports WHERE id = ?", (report_id,)
    ).fetchone()

    if row is None:
        abort(404)

    r        = dict(row)
    created  = _parse_created_at(r["created_at"])
    now      = datetime.utcnow()
    days_old = (now - created).days
    r["days_old"]   = days_old
    r["is_overdue"] = (r["status"] == "pending") and (days_old > 7)
    r["urgency"]    = 0 if r["status"] == "resolved" else (days_old + 1) * (r["upvotes"] + 1)

    return render_template(
        "detail.html",
        report=r,
        upvoted_ids=list(session.get("upvoted_ids", [])),
    )


# ---------------------------------------------------------------------------
# Government resolution route
# ---------------------------------------------------------------------------

@app.route("/resolve/<int:report_id>", methods=["GET", "POST"])
def resolve(report_id: int):
    """Operator form to close a report, gated by a constant-time PIN check."""
    db  = get_db()
    row = db.execute(
        "SELECT * FROM reports WHERE id = ?", (report_id,)
    ).fetchone()

    if row is None:
        abort(404)

    report_data = dict(row)

    # Prevent resolving an already-resolved report.
    if report_data["status"] == "resolved":
        flash("Laporan ini sudah ditandai selesai sebelumnya.", "error")
        return redirect(url_for("detail", report_id=report_id))

    if request.method == "POST":
        submitted_pin = request.form.get("pin", "")
        # hmac.compare_digest prevents timing-based PIN oracle attacks.
        if not hmac.compare_digest(submitted_pin, RESOLVE_PIN):
            flash("PIN salah. Akses ditolak.", "error")
            return render_template("resolve.html", report=report_data), 403

        # File upload
        file     = request.files.get("resolved_image")
        filename = None
        if file and file.filename:
            filename = _save_upload(file)
            if filename is None:
                flash(
                    "File gambar tidak valid. Gunakan PNG, JPG, JPEG, atau GIF yang asli.",
                    "error",
                )
                return render_template("resolve.html", report=report_data), 422

        # Budget validation: must be finite and non-negative.
        try:
            budget_spent = float(request.form.get("budget_spent", "") or 0)
            if not math.isfinite(budget_spent) or budget_spent < 0:
                raise ValueError
        except ValueError:
            flash("Nilai anggaran tidak valid.", "error")
            return render_template("resolve.html", report=report_data), 422

        budget_source = request.form.get("budget_source", "").strip()

        db.execute(
            """
            UPDATE reports
            SET resolved_image = ?,
                budget_spent   = ?,
                budget_source  = ?,
                status         = 'resolved'
            WHERE id = ?
            """,
            (filename, budget_spent, budget_source, report_id),
        )
        db.commit()

        flash(
            f"Laporan #{report_id} berhasil ditandai selesai.",
            "success",
        )
        return redirect(url_for("dashboard"))

    return render_template("resolve.html", report=report_data)


# ---------------------------------------------------------------------------
# Community upvote route — session-based spam prevention
# ---------------------------------------------------------------------------

@app.route("/upvote/<int:report_id>", methods=["POST"])
def upvote(report_id: int):
    """
    Increment the upvote counter.
    A session set tracks which report IDs this browser session has already
    upvoted, preventing spam without requiring user accounts.
    """
    voted_key = "upvoted_ids"
    upvoted: set[int] = set(session.get(voted_key, []))

    if report_id in upvoted:
        flash("Anda sudah memberikan dukungan untuk laporan ini.", "error")
    else:
        db     = get_db()
        result = db.execute(
            "UPDATE reports SET upvotes = upvotes + 1 WHERE id = ?",
            (report_id,),
        )
        db.commit()
        if result.rowcount == 0:
            abort(404)
        upvoted.add(report_id)
        session[voted_key] = list(upvoted)

    referrer = request.referrer or ""
    if f"/detail/{report_id}" in referrer:
        return redirect(url_for("detail", report_id=report_id))
    return redirect(url_for("dashboard"))


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------

@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404


@app.errorhandler(413)
def file_too_large(e):
    flash("Ukuran file melebihi batas 8 MB.", "error")
    return redirect(request.referrer or url_for("dashboard"))


@app.errorhandler(400)
def bad_request(e):
    # Flask-WTF raises 400 on a missing/invalid CSRF token.
    flash("Permintaan tidak valid atau sesi telah kedaluwarsa. Silakan coba lagi.", "error")
    return redirect(request.referrer or url_for("dashboard"))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    with app.app_context():
        init_db()
        seed_db()
    app.run(debug=True)

# PIJAR — Pelaporan Infrastruktur Jalan dan Ruang
## Build Plan

### Top-Level Overview

Greenfield Flask + SQLite civic-tech web app. Citizens submit infrastructure damage reports with GPS coordinates and photo evidence. A government operator resolves reports via a PIN-protected form. A public dashboard ranks reports by urgency score and flags overdue items as a "Wall of Shame". No external dependencies beyond Flask and Pillow (optional). All HTML is rendered by Jinja2 templates styled with Tailwind CSS via CDN.

**Scope:** 5 files total.
- `app.py` — Flask application, DB init, all routes, seed data
- `templates/base.html` — shared layout shell
- `templates/index.html` — public dashboard
- `templates/report.html` — citizen submission form
- `templates/resolve.html` — government resolution form

**Non-goals:** user accounts, real auth, production deployment config, JS framework.

---

## Sub-Task 1 — Project Bootstrap & Database Layer

**Intent:** Create the Flask app skeleton, initialize the SQLite database schema, and wire up automatic seed data on first run.

**Expected Outcomes:**
- `app.py` runs with `python app.py` without errors.
- `pijar.db` is created automatically with a `reports` table on first run.
- `static/uploads/` directory is created automatically.
- 4–6 seed rows with Surabaya coordinates are inserted only when the table is empty.

**Todo List:**
1. Create `app.py` with Flask app instance, `SECRET_KEY`, `UPLOAD_FOLDER = 'static/uploads'`, `ALLOWED_EXTENSIONS`.
2. Define `get_db()` helper using `sqlite3.connect('pijar.db')` with `row_factory = sqlite3.Row`.
3. Write `init_db()` that runs `CREATE TABLE IF NOT EXISTS reports (...)` with all required columns:
   - `id INTEGER PRIMARY KEY AUTOINCREMENT`
   - `title TEXT NOT NULL`
   - `category TEXT NOT NULL`
   - `latitude REAL`
   - `longitude REAL`
   - `issue_image TEXT`
   - `resolved_image TEXT`
   - `budget_spent REAL`
   - `budget_source TEXT`
   - `created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`
   - `upvotes INTEGER DEFAULT 0`
   - `status TEXT DEFAULT 'pending'`
4. Write `seed_db()` that checks `SELECT COUNT(*) FROM reports` and inserts 5 dummy rows covering Surabaya landmarks (mix of categories, dates spread over 14 days, some resolved, some pending >7 days, some pending <7 days).
5. Call `init_db()` and `seed_db()` inside `if __name__ == '__main__':` block before `app.run(debug=True)`.
6. Create `static/uploads/.gitkeep` placeholder (ensure directory exists at runtime via `os.makedirs`).

**Relevant Context:** SQLite `row_factory = sqlite3.Row` lets templates access columns by name. `datetime.utcnow()` is used for urgency score calculation.

**Status:** [x] done

---

## Sub-Task 2 — Route: Dashboard `/`

**Intent:** Render all reports sorted by urgency score descending, with SLA-aware visual flags.

**Expected Outcomes:**
- `GET /` returns a rendered `index.html` with all reports.
- Reports are sorted by `(days_since_creation + 1) * (upvotes + 1)` descending (calculated in Python, passed as enriched dicts).
- Each report dict includes a `days_old` field and an `is_overdue` boolean (days_old > 7 and status == 'pending').

**Todo List:**
1. Add `@app.route('/')` view function `dashboard()`.
2. Query all reports from DB.
3. For each row, compute `days_old = (datetime.utcnow() - created_at).days` and `urgency = (days_old + 1) * (upvotes + 1)`.
4. Build enriched list of dicts, sort by `urgency` descending.
5. Render `index.html` with `reports=reports`.

**Relevant Context:** `sqlite3.Row` objects are not directly mutable; convert to `dict` before adding computed fields. Parse `created_at` string with `datetime.strptime(row['created_at'], '%Y-%m-%d %H:%M:%S')`.

**Status:** [x] done

---

## Sub-Task 3 — Route: Citizen Report Submission `/report`

**Intent:** Provide a public form for submitting a new infrastructure report with GPS coordinates and an evidence photo.

**Expected Outcomes:**
- `GET /report` renders the submission form.
- `POST /report` validates input, saves the uploaded image to `static/uploads/`, inserts a new DB row, and redirects to `/`.
- File upload only accepts `png`, `jpg`, `jpeg`, `gif`.
- Filename is sanitised with `werkzeug.utils.secure_filename` and prefixed with a UUID to avoid collisions.

**Todo List:**
1. Add `@app.route('/report', methods=['GET', 'POST'])` view function `report()`.
2. On POST: extract `title`, `category`, `latitude`, `longitude` from `request.form`.
3. Handle `issue_image` from `request.files` — validate extension, generate `uuid4().hex + '_' + secure_filename(f.filename)`, save to `UPLOAD_FOLDER`.
4. Insert row into `reports` table with `status='pending'`, `upvotes=0`.
5. Redirect to `/` with a flash success message.
6. On GET: render `report.html`.

**Relevant Context:** HTML5 Geolocation API is called via inline Vanilla JS in `report.html`; the JS writes lat/lng into hidden `<input>` fields that are then submitted with the form. `os.path.join(app.config['UPLOAD_FOLDER'], filename)` for save path.

**Status:** [x] done

---

## Sub-Task 4 — Route: Government Resolution `/resolve/<int:report_id>`

**Intent:** Allow a government operator to close a report by uploading a resolution photo and entering budget details, gated by a hardcoded PIN.

**Expected Outcomes:**
- `GET /resolve/<id>` renders the resolution form pre-populated with report title.
- `POST /resolve/<id>` with correct PIN (`1234`) saves the resolved image, updates `budget_spent`, `budget_source`, `status='resolved'`.
- Wrong PIN re-renders the form with an error message.
- Redirects to `/` on success.

**Todo List:**
1. Add `@app.route('/resolve/<int:report_id>', methods=['GET', 'POST'])` view function `resolve(report_id)`.
2. Fetch report by `id`; return 404 if not found.
3. On POST: check `request.form['pin'] == '1234'`; if wrong, re-render with `error='PIN salah'`.
4. If correct: handle `resolved_image` upload (same pattern as Sub-Task 3).
5. `UPDATE reports SET resolved_image=?, budget_spent=?, budget_source=?, status='resolved' WHERE id=?`.
6. Redirect to `/`.

**Relevant Context:** PIN is hardcoded as a module-level constant `RESOLVE_PIN = '1234'` in `app.py` for easy reference.

**Status:** [x] done

---

## Sub-Task 5 — Route: Community Upvote `/upvote/<int:report_id>`

**Intent:** Let any visitor increment the upvote counter on a report via a simple POST action.

**Expected Outcomes:**
- `POST /upvote/<id>` increments `upvotes` by 1 and redirects to `/`.
- No authentication required.

**Todo List:**
1. Add `@app.route('/upvote/<int:report_id>', methods=['POST'])` view function `upvote(report_id)`.
2. `UPDATE reports SET upvotes = upvotes + 1 WHERE id = ?`.
3. Redirect to `/`.

**Status:** [x] done

---

## Sub-Task 6 — Templates: `base.html` & `index.html`

**Intent:** Build the shared layout and the public dashboard with full SLA tracker UI.

**Expected Outcomes:**
- `base.html` loads Tailwind CSS CDN, sets `<meta charset>`, viewport, and defines `{% block content %}`.
- `index.html` extends `base.html` and renders a responsive card grid.
- Pending reports older than 7 days have a red left-border accent and a "🔴 Wall of Shame" badge.
- Resolved reports show before/after image thumbnails side-by-side and budget breakdown.
- All reports show a "📍 Lihat di Peta" link opening `https://www.openstreetmap.org/?mlat=LAT&mlon=LON&zoom=17` in a new tab.
- Upvote button submits a small form to `POST /upvote/<id>`.
- Dashboard header shows total report count, pending count, resolved count as stat cards.

**Relevant Context:**
- Tailwind CDN: `<script src="https://cdn.tailwindcss.com"></script>`.
- Semantic color palette: slate/gray for neutral, red-600 for overdue/shame, green-600 for resolved, blue-600 for pending normal, amber-500 for budget.
- Use `url_for('static', filename='uploads/' + report.issue_image)` for image src.
- Flash messages rendered in `base.html` using `get_flashed_messages(with_categories=True)`.

**Status:** [x] done

---

## Sub-Task 7 — Templates: `report.html` & `resolve.html`

**Intent:** Build the two action forms with clean civic aesthetics.

**Expected Outcomes:**
- `report.html`: form with title, category (select: Jalan Rusak / Drainase / Trotoar / PJU / Lainnya), hidden lat/lng inputs, file upload, and a "Deteksi Lokasi Saya" button that calls `navigator.geolocation.getCurrentPosition()` via inline JS.
- `resolve.html`: form with PIN input, resolved image upload, budget_spent (number), budget_source (text), showing the original report title.
- Both forms POST to their respective routes with `enctype="multipart/form-data"`.
- Both extend `base.html`.

**Relevant Context:**
- Geolocation JS snippet writes to `id="latitude"` and `id="longitude"` hidden inputs.
- Show a small status text `id="geo-status"` that updates to "✅ Lokasi terdeteksi" or "❌ Gagal mendeteksi lokasi".
- `resolve.html` receives `report` object from Flask to display the report title.

**Status:** [x] done

---

## File Map

```
PIJAR/
├── app.py
├── pijar.db                  (auto-created)
├── static/
│   └── uploads/              (auto-created, receives uploaded images)
└── templates/
    ├── base.html
    ├── index.html
    ├── report.html
    └── resolve.html
```

## Architecture Diagram

See chat response for Mermaid diagram.

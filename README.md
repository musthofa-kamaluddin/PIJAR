# PIJAR — Pelaporan Infrastruktur Jalan dan Ruang

Platform pelaporan infrastruktur publik berbasis data terbuka untuk mendorong akuntabilitas pemerintah dan partisipasi warga Kota Surabaya.

---

## Fitur Utama

| Fitur | Keterangan |
|---|---|
| **Dashboard publik** | Semua laporan diurutkan otomatis berdasarkan skor urgensi `(hari + 1) × (suara + 1)` |
| **Wall of Shame** | Laporan pending lebih dari 7 hari ditandai dengan border merah sebagai penanda SLA terlewat |
| **Kirim laporan** | Warga dapat melaporkan kerusakan dengan judul, kategori, deskripsi, foto bukti, dan koordinat GPS |
| **Peta interaktif** | Leaflet.js pada halaman laporan dan detail — penanda dapat diseret, auto-deteksi lokasi via Geolocation API |
| **Upload foto** | Drag-and-drop atau klik-browse, preview thumbnail real-time, progress bar, validasi tipe dan ukuran di sisi klien |
| **Lightbox foto** | Klik foto di halaman detail untuk melihat ukuran penuh, zoom native di mobile, tutup dengan Escape atau klik backdrop |
| **Penyelesaian laporan** | Operator pemerintah mengisi PIN, foto sesudah perbaikan, anggaran, dan sumber anggaran |
| **Transparansi anggaran** | Nominal dan sumber anggaran ditampilkan publik di halaman detail dan kartu dashboard |
| **Upvote komunitas** | Setiap browser session dapat mendukung satu laporan satu kali — disimpan di session Flask |
| **Dark mode** | Toggle di navbar, preferensi disimpan di `localStorage`, tidak ada flash saat refresh |
| **Peta ke OSM** | Tautan "Buka di OSM" dan "Laporkan ke OSM" (Map Notes API) di setiap halaman detail |

---

## Tumpukan Teknologi

| Lapisan | Teknologi |
|---|---|
| Backend | Python 3.11+, Flask 3.x |
| Database | SQLite 3 (WAL mode) |
| Template | Jinja2 |
| CSS | Tailwind CSS via CDN (darkMode: class) |
| Ikon | Lucide Icons via CDN |
| Peta | Leaflet 1.9.4 — **bundled lokal** di `static/vendor/leaflet/` |
| Font | Inter via Google Fonts |
| Keamanan | Flask-WTF CSRF, Pillow image validation, `hmac.compare_digest` PIN, `werkzeug.secure_filename` |

---

## Struktur Direktori

```
PIJAR/
├── app.py                        # Seluruh logika backend: routes, DB, upload, keamanan
├── pijar.db                      # SQLite database (dibuat otomatis saat pertama run)
├── pijar-plan.md                 # Dokumen perencanaan internal
├── README.md                     # File ini
│
├── static/
│   ├── uploads/                  # Foto laporan yang diunggah warga
│   │   └── .gitkeep
│   └── vendor/
│       └── leaflet/              # Leaflet JS + CSS + marker images (lokal, tanpa CDN)
│           ├── leaflet.js
│           ├── leaflet.css
│           └── images/
│               ├── marker-icon.png
│               ├── marker-icon-2x.png
│               └── marker-shadow.png
│
├── templates/
│   ├── base.html                 # Layout utama: nav, flash messages, footer, dark mode
│   ├── index.html                # Dashboard — kartu laporan + stat cards
│   ├── report.html               # Form laporan warga + peta + drag-drop upload
│   ├── detail.html               # Detail laporan + lightbox foto + peta + sidebar
│   ├── resolve.html              # Form penyelesaian operator (PIN-protected)
│   └── 404.html                  # Halaman error 404
│
└── .vscode/
    └── settings.json             # Matikan JS linter palsu untuk file Jinja2
```

---

## Instalasi dan Menjalankan Lokal

### 1. Clone / ekstrak project

```bash
cd d:\Hacktiv8\PIJAR
```

### 2. Buat virtual environment dan install dependensi

```bash
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS / Linux

pip install flask flask-wtf pillow
```

### 3. Jalankan server

```bash
python app.py
```

Buka browser ke **http://127.0.0.1:5000**

Database `pijar.db` dibuat otomatis saat pertama run, lengkap dengan 5 data seed representatif (2 laporan overdue SLA, 1 pending normal, 2 sudah selesai dengan data anggaran).

---

## Konfigurasi via Environment Variable

Semua nilai sensitif dibaca dari environment — tidak ada hardcode di kode produksi.

| Variable | Default (dev) | Keterangan |
|---|---|---|
| `SECRET_KEY` | `pijar-dev-secret-change-in-prod` | Flask session secret — **wajib diganti di produksi** |
| `PIJAR_PIN` | `1234` | PIN operator untuk halaman resolve |

Contoh penggunaan di Windows:

```powershell
$env:SECRET_KEY = "kunci-rahasia-panjang-acak"
$env:PIJAR_PIN  = "9876"
python app.py
```

Di Linux / macOS:

```bash
SECRET_KEY="kunci-rahasia-panjang-acak" PIJAR_PIN="9876" python app.py
```

---

## Routes

| Method | URL | Fungsi |
|---|---|---|
| `GET` | `/` | Dashboard — semua laporan diurutkan urgensi |
| `GET` | `/report` | Form kirim laporan |
| `POST` | `/report` | Proses submit laporan baru |
| `GET` | `/detail/<id>` | Halaman detail laporan |
| `GET` | `/resolve/<id>` | Form penyelesaian laporan (operator) |
| `POST` | `/resolve/<id>` | Proses penyelesaian — verifikasi PIN |
| `POST` | `/upvote/<id>` | Tambah satu suara komunitas |

---

## Skema Database

Tabel tunggal `reports`:

| Kolom | Tipe | Keterangan |
|---|---|---|
| `id` | INTEGER PK | Auto-increment |
| `title` | TEXT | Judul laporan — maks. 200 karakter |
| `category` | TEXT | Jalan Rusak / Drainase / Trotoar / PJU / Lainnya |
| `description` | TEXT | Deskripsi opsional |
| `latitude` | REAL | Koordinat GPS lintang |
| `longitude` | REAL | Koordinat GPS bujur |
| `issue_image` | TEXT | Nama file foto kondisi awal |
| `resolved_image` | TEXT | Nama file foto setelah perbaikan |
| `budget_spent` | REAL | Nominal anggaran yang digunakan (Rp) |
| `budget_source` | TEXT | Sumber anggaran — contoh: APBD Kota Surabaya 2024 |
| `created_at` | TIMESTAMP | Waktu laporan dibuat |
| `upvotes` | INTEGER | Jumlah suara komunitas |
| `status` | TEXT | `pending` atau `resolved` |

---

## Keamanan

- **CSRF** — Flask-WTF `CSRFProtect` aktif di semua POST form. Token `{{ csrf_token() }}` wajib ada di setiap form.
- **PIN operator** — dibandingkan dengan `hmac.compare_digest` (constant-time) untuk mencegah timing attack.
- **Upload file** — validasi ekstensi whitelist + verifikasi konten via `Pillow Image.open().load()`. Nama file diamankan dengan `secure_filename` + prefix `uuid4`.
- **Koordinat** — divalidasi rentang: lat ∈ [−90, 90], lon ∈ [−180, 180].
- **Anggaran** — divalidasi `math.isfinite` dan `>= 0`.
- **Upvote spam** — dicegah via `session['upvoted_ids']` per browser session.
- **SQL injection** — semua query pakai parameterized placeholder `?`, tidak ada f-string di SQL.
- **Secret key** — dibaca dari environment variable, tidak hardcode di kode.

---

## Catatan Deployment Lokal (Offline / Intranet)

Leaflet JS dan CSS sudah di-bundle lokal di `static/vendor/leaflet/` — peta tetap berfungsi tanpa akses internet. Tile peta OpenStreetMap (`*.tile.openstreetmap.org`) masih membutuhkan koneksi internet. Untuk deployment offline penuh, gunakan tile server lokal seperti [TileServer GL](https://tileserver.org/) atau cache tile via proxy.

Lucide Icons dan Tailwind CSS masih diambil dari CDN (`unpkg.com` dan `cdn.tailwindcss.com`). Untuk offline penuh, unduh dan bundel juga kedua aset tersebut ke `static/vendor/`.

---

## Lisensi

Data peta: &copy; [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors, lisensi [ODbL](https://opendatacommons.org/licenses/odbl/). Tile oleh [OSMF](https://operations.osmfoundation.org/policies/tiles/).

Kode sumber project ini dibuat untuk keperluan Civic Tech & Open Data Initiative Kota Surabaya.

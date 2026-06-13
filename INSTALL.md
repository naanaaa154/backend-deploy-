# Instalasi dan Menjalankan (Windows PowerShell)

Panduan singkat untuk menyiapkan dan menjalankan service FastAPI pada folder `backend/`.

## Prasyarat
- Python 3.10+ terpasang dan dapat diakses sebagai `python` di PATH.
- PostgreSQL (atau database lain sesuai `DATABASE_URL`) jika ingin menggunakan vector store.
- Akses ke layanan Ollama / Langchain yang diperlukan (lihat variabel .env).

> Catatan: projek ini memakai `python-dotenv` dan `pydantic-settings` untuk memuat konfigurasi dari file `.env`.

## Langkah instalasi (PowerShell)

1. Buka PowerShell dan pindah ke folder `backend/`:

```powershell
cd path\to\your\repo\backend
```

2. Buat virtual environment dan aktifkan (PowerShell):

```powershell
python -m venv .venv
# Jika PowerShell menolak menjalankan skrip karena ExecutionPolicy, jalankan baris berikut (sifatnya hanya untuk sesi ini):
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force

# Aktifkan venv
.\.venv\Scripts\Activate.ps1
```

3. Upgrade pip dan install dependencies:

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

4. Buat file `.env` di folder `backend/` (project mengharapkan `.env`) dan isi variabel lingkungan yang diperlukan. Contoh minimal `.env`:

```env
# Ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_LLM_MODEL=ollama-llm-model-name
OLLAMA_EMBEDDING_MODEL=ollama-embedding-model-name

# Database (contoh PostgreSQL)
DATABASE_URL=postgresql+psycopg://dbuser:dbpassword@localhost:5432/dbname

# LangChain / LangSmith
LANGCHAIN_PROJECT=your_project_name
LANGCHAIN_API_KEY=sk-xxxxxx

# Security
JWT_SECRET_KEY=ganti-dengan-string-acak-yang-panjang
```

Catatan penting:
- `LANGCHAIN_PROJECT` dan `LANGCHAIN_API_KEY` wajib ada; `app.core.langsmith.init_langsmith()` akan melempar error jika tidak ditemukan.
- Konfig `app.core.config.Settings` juga mencari `DATABASE_URL`, `OLLAMA_*`, dan `JWT_SECRET_KEY` (wajib). Jika salah satu tidak ada, aplikasi akan gagal start dengan error validasi konfigurasi.
- Pastikan database tersedia dan (untuk Postgres) ekstensi `vector` (pgvector) sudah di-enable bila diperlukan oleh `PGVector`.
- Fitur **memory percakapan per sesi** menggunakan LangGraph Postgres checkpointer dan akan membuat tabel internal otomatis saat startup.
	Pastikan `DATABASE_URL` mengarah ke PostgreSQL (bukan SQLite) agar memory per sesi bisa tersimpan.
	`session_id` dari API chat dipakai sebagai `thread_id` agar riwayat percakapan tersambung per sesi.

5. Jalankan aplikasi (development, reload):

```powershell
uvicorn app.main:app --reload --port 8000
```

Akses API di http://127.0.0.1:8000

## Tips & Troubleshooting
- Jika Anda menggunakan Docker untuk Postgres, pastikan `DATABASE_URL` mengarah ke service Docker yang benar.
- Jika ada error paket yang tidak ditemukan saat install, periksa versi Python yang kompatibel dengan paket (beberapa paket modern mungkin butuh Python 3.11+).
- Untuk menjalankan production, gunakan proses manager atau container, jangan `--reload` di production.

## Pengujian singkat
- Setelah server jalan, Anda bisa memanggil endpoint ingest (lihat `app/api/routes/ingest.py`) untuk menguji alur ingest.

## Lanjutan (opsional)
- Tambahkan `Makefile` atau skrip PowerShell untuk memudahkan perintah common.
- Tambahkan konfigurasi `docker-compose` dengan Postgres + pgvector bila ingin lingkungan reproducible.

---
Dokumentasi ini dibuat otomatis. Jika ada detail konfigurasi environment yang lain di repository, sesuaikan `.env` dengan kebutuhan layanan eksternal yang Anda pakai.
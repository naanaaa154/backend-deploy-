import sys
import os

# Tambahkan parent directory ke python path agar bisa import app...
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.core.database import engine, Base
from app.rag.models.chat import ChatSession, ChatMessage
from app.user.models.user import User

def fix_schema():
    print("Mencoba memperbaiki skema database...")
    
    with engine.connect() as connection:
        # Pastikan tabel transcripts ada sebelum alter
        try:
            connection.execute(text("CREATE TABLE IF NOT EXISTS transcripts (id UUID PRIMARY KEY)"))
            connection.commit()
        except Exception as e:
            print(f"Gagal memastikan tabel transcripts: {e}")

        # Tambahkan kolom baru jika belum ada (untuk start/end time & location)
        try:
            connection.execute(text("ALTER TABLE transcripts ADD COLUMN IF NOT EXISTS start_time VARCHAR(64)"))
            connection.execute(text("ALTER TABLE transcripts ADD COLUMN IF NOT EXISTS end_time VARCHAR(64)"))
            connection.execute(text("ALTER TABLE transcripts ADD COLUMN IF NOT EXISTS location VARCHAR(255)"))
            connection.commit()
            print("Kolom start_time, end_time, location sudah dipastikan ada.")
        except Exception as e:
            print(f"Gagal menambah kolom transcripts: {e}")

        # Hapus tabel yang bermasalah (chat_message bergantung pada chat_session)
        print("Menghapus tabel chat_message dan chat_session...")
        try:
            connection.execute(text("DROP TABLE IF EXISTS chat_message CASCADE"))
            connection.execute(text("DROP TABLE IF EXISTS chat_session CASCADE"))
            connection.commit()
            print("Tabel berhasil dihapus.")
        except Exception as e:
            print(f"Gagal menghapus tabel: {e}")
            return

    # Buat ulang tabel dengan definisi terbaru dari kode (Integer untuk user_id)
    print("Membuat ulang tabel...")
    Base.metadata.create_all(bind=engine)
    print("Selesai! Silakan jalankan ulang aplikasi backend Anda.")

if __name__ == "__main__":
    fix_schema()

from pathlib import Path
from datetime import datetime

BASE_DATA_DIR = Path("data")
SUMMARY_DIR = BASE_DATA_DIR / "summary"
TRANSCRIPT_DIR = BASE_DATA_DIR / "transcript"

def ensure_dirs():
    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
    TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)

def save_both_files(transcript_content: str, summary_content: str, original_filename: str):
    ensure_dirs()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = original_filename.replace(" ", "_")

    t_path = TRANSCRIPT_DIR / f"{timestamp}_transcript_{safe_name}"
    s_path = SUMMARY_DIR / f"{timestamp}_summary_{safe_name}"

    t_path.write_text(transcript_content, encoding="utf-8")
    s_path.write_text(summary_content, encoding="utf-8")

    return str(t_path), str(s_path)
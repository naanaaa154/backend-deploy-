import logging
import math
import re
from datetime import datetime

from langchain_core.documents import Document

from app.core.ollama import get_embedding
from app.vectorstore.pgvector import get_vectorstore

logger = logging.getLogger(__name__)

METADATA_LINE_ORDER = (
    "agenda",
    "tempat dilaksanakan",
    "tanggal pelaksanaan",
    "tahun pelaksanaan",
    "jam mulai",
    "jam selesai",
    "daftar hadir",
    "kata kunci",
)


# =========================================================
# UTILITIES & CLEANING HELPERS
# =========================================================
def normalize_whitespace(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def clean_metadata_value(val):
    if isinstance(val, str):
        return val.replace("**", "").strip().lower()
    if isinstance(val, list):
        return [clean_metadata_value(v) for v in val]
    if val is None:
        return None
    return str(val).lower()


def _to_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return str(value)


# =========================================================
# DATE & TIME PARSING HELPERS
# =========================================================
def _format_time_short(value: str | None) -> str:
    if not value:
        return ""
    s = str(value).strip()
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.strftime("%H:%M")
        except ValueError:
            continue
    return s


def format_indonesian_date(value: str | None) -> str:
    if not value or re.search(r"[a-zA-Z]", str(value)):
        return str(value).strip() if value else ""

    s = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            parsed = datetime.strptime(s, fmt)
            bulan = [
                "januari", "februari", "maret", "april", "mei", "juni",
                "juli", "agustus", "september", "oktober", "november", "desember"
            ]
            return f"{parsed.day} {bulan[parsed.month - 1]} {parsed.year}"
        except ValueError:
            continue
    return s


def split_date_components(value: str | None) -> tuple[str, str, str]:
    if not value:
        return "", "", ""

    s = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            parsed = datetime.strptime(s, fmt)
            return f"{parsed.day:02d}", str(parsed.month), str(parsed.year)
        except ValueError:
            continue

    m = re.search(r"(\d{1,2})[^0-9]+(\d{1,2})[^0-9]+(\d{2,4})", s)
    if m:
        d, mo, y = m.group(1), m.group(2), m.group(3)
        if len(y) == 2:
            y = "20" + y
        return f"{int(d):02d}", str(int(mo)), str(int(y))

    return "", "", ""


# =========================================================
# METADATA BUILDERS
# =========================================================
def format_metadata_prefix(meta: dict, include_summary: bool = False) -> str:
    topics = _to_text(meta.get("main_topic", meta.get("kata kunci", [])))
    participants = _to_text(meta.get("participants", meta.get("daftar hadir", [])))
    date_value = meta.get("date", meta.get("tanggal pelaksanaan", ""))
    
    formatted_date = format_indonesian_date(date_value)
    start_time = _format_time_short(meta.get("start_time", meta.get("jam mulai", "")))
    end_time = _format_time_short(meta.get("end_time", meta.get("jam selesai", "")))

    lines = [
        f"agenda: {meta.get('agenda', '')}",
        f"tempat dilaksanakan: {meta.get('location', meta.get('tempat dilaksanakan', ''))}",
        f"tanggal pelaksanaan: {formatted_date}",
        f"jam mulai: {start_time}",
        f"jam selesai: {end_time}",
        f"daftar hadir: {participants}",
        f"kata kunci: {topics}",
    ]

    summary = meta.get("summary", "")
    if include_summary and summary:
        lines.append(f"\n{summary}")

    return "\n".join(lines)


def build_metadata_lines(metadata_chunk_metadata: dict, full_metadata: dict) -> list[str]:
    values = {
        "agenda": _to_text(metadata_chunk_metadata.get("agenda")),
        "tempat dilaksanakan": _to_text(metadata_chunk_metadata.get("tempat dilaksanakan")),
        "tanggal pelaksanaan": _to_text(metadata_chunk_metadata.get("tanggal pelaksanaan")),
        "tahun pelaksanaan": _to_text(metadata_chunk_metadata.get("tahun pelaksanaan")),
        "jam mulai": _to_text(full_metadata.get("jam mulai")),
        "jam selesai": _to_text(full_metadata.get("jam selesai")),
        "daftar hadir": _to_text(metadata_chunk_metadata.get("daftar hadir")),
        "kata kunci": _to_text(metadata_chunk_metadata.get("kata kunci")),
    }
    return [f"{key}: {values.get(key, '')}" for key in METADATA_LINE_ORDER]


# =========================================================
# TRANSCRIPT PROCESSING & CHUNKING (IMPROVED)
# =========================================================
def parse_speaker_blocks(text: str) -> list[str]:
    text = text.replace("\ufeff", "")
    pattern = r"(?im)(?:^|\n)\s*(speaker[_\s]*\d*:|[a-z]+(?:\s+[a-z]+)*:)"
    parts = re.split(pattern, text)

    blocks = []
    speaker = None
    for part in parts:
        if re.match(r"(?i)speaker[_\s]*\d*:|[a-z]+(?:\s+[a-z]+)*:", part.strip()):
            speaker = part.strip()
        else:
            if speaker and part.strip():
                blocks.append(f"{speaker} {part.strip()}")
    return blocks


def _cosine_sim(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na != 0 and nb != 0 else 0.0


def semantic_chunk_by_speaker_with_overlap(
    blocks: list[str],
    embed,
    max_chars: int = 1500,
    min_chars: int = 750,
    topic_sim_threshold: float = 0.74,
    lookback: int = 3,
    overlap_blocks_count: int = 1,  # Mengamankan N blok pembicara sebelumnya sebagai overlap
) -> list[str]:
    """
    Membuat chunk berbasis semantik blok pembicara DAN menyertakan N blok pembicara 
    terakhir dari chunk sebelumnya sebagai overlap kontekstual yang utuh.
    """
    if not blocks:
        return []

    block_embeds = [embed(b) for b in blocks]
    chunks = []
    
    current_blocks: list[str] = []
    last_chunk_ending_blocks: list[str] = []

    for i, blk in enumerate(blocks):
        if not current_blocks:
            # Jika ini chunk baru dan ada overlap dari chunk sebelumnya, masukkan terlebih dahulu
            if last_chunk_ending_blocks:
                current_blocks.extend(last_chunk_ending_blocks)
            current_blocks.append(blk)
            continue

        # Hitung similarity semantik untuk pemotongan topik
        start = max(0, i - lookback)
        ctx_vecs = block_embeds[start:i]
        ctx = [sum(vals) / len(vals) for vals in zip(*ctx_vecs)] if ctx_vecs else block_embeds[i]
        sim = _cosine_sim(ctx, block_embeds[i])
        
        candidate_text = "\n".join(current_blocks + [blk])
        current_len = len("\n".join(current_blocks))
        
        too_long = len(candidate_text) > max_chars
        topic_break = sim < topic_sim_threshold

        if (topic_break and current_len >= min_chars) or (too_long and current_len >= min_chars):
            # Simpan chunk saat ini
            chunks.append("\n".join(current_blocks))
            
            # Ambil N blok pembicara terakhir dari riwayat murni SEBELUM blok baru ('blk') ditambahkan
            # Kita filter agar tidak mengambil text yang asalnya dari overlap chunk sebelumnya secara berlebihan
            actual_chunk_blocks = current_blocks
            last_chunk_ending_blocks = actual_chunk_blocks[-overlap_blocks_count:] if len(actual_chunk_blocks) >= overlap_blocks_count else actual_chunk_blocks
            
            # Reset chunk baru diisi dengan potongan overlap + blok saat ini
            current_blocks = []
            if last_chunk_ending_blocks:
                current_blocks.extend(last_chunk_ending_blocks)
            current_blocks.append(blk)
        else:
            current_blocks.append(blk)

    if current_blocks:
        chunks.append("\n".join(current_blocks))

    return chunks


# =========================================================
# PIPELINE INGEST TRANSCRIPT
# =========================================================
def prepare_metadata_environments(summary_metadata: dict) -> tuple[dict, dict, dict]:
    full_metadata = {
        "agenda": clean_metadata_value(summary_metadata.get("agenda", "Unagendad")),
        "tanggal pelaksanaan": clean_metadata_value(summary_metadata.get("date", None)),
        "jam mulai": _format_time_short(clean_metadata_value(summary_metadata.get("start_time", None))),
        "jam selesai": _format_time_short(clean_metadata_value(summary_metadata.get("end_time", None))),
        "tempat dilaksanakan": clean_metadata_value(summary_metadata.get("location", None)),
        "daftar hadir": clean_metadata_value(summary_metadata.get("participants", [])),
        "kata kunci": clean_metadata_value(summary_metadata.get("main_topic", [])),
        "meeting_id": clean_metadata_value(summary_metadata.get("meeting_id")),
    }

    day, month, year = split_date_components(full_metadata.get("tanggal pelaksanaan"))
    
    metadata_chunk_metadata = {
        **full_metadata,
        "tanggal pelaksanaan": format_indonesian_date(full_metadata.get("tanggal pelaksanaan")),
        "tanggal pelaksanaan (hari)": day,
        "bulan pelaksanaan": month,
        "tahun pelaksanaan": year,
    }

    prefix_metadata = {
        **full_metadata,
        "summary": clean_metadata_value(summary_metadata.get("summary", "")),
    }

    return full_metadata, metadata_chunk_metadata, prefix_metadata


def ingest_transcript(text: str, summary_metadata: dict):
    # 1️⃣ Ekstraksi & standarisasi metadata
    full_metadata, metadata_chunk_metadata, prefix_metadata = prepare_metadata_environments(summary_metadata)
    metadata_only_content = "\n".join(build_metadata_lines(metadata_chunk_metadata, full_metadata))

    try:
        # 2️⃣ Preprocess teks & Chunking
        text = text.lower()
        embedding = get_embedding()
        blocks = parse_speaker_blocks(text)
        
        if not blocks:
            logger.warning("Tidak ada blok pembicara ditemukan.")
            return

        # 🔥 IMPROVEMENT: Menggunakan chunking berbasis speaker tunggal langsung dengan overlap terintegrasi
        raw_chunks = semantic_chunk_by_speaker_with_overlap(
            blocks=blocks, 
            embed=embedding.embed_query,
            overlap_blocks_count=1 # Mengambil 1 speaker block pembicaraan sebelumnya sebagai overlap utuh
        )

        final_docs = []
        buffer_text = ""
        chunk_counter = 0

        # 3️⃣ Proses Dialog Chunks (Tipe: "all")
        for chunk_text in raw_chunks:
            clean_chunk = normalize_whitespace(chunk_text).lstrip(".")
            if not clean_chunk:
                continue

            if len(clean_chunk) < 50:
                buffer_text += " " + clean_chunk
                continue

            if buffer_text:
                clean_chunk = normalize_whitespace(buffer_text) + " " + clean_chunk
                buffer_text = ""

            prefix = format_metadata_prefix(prefix_metadata, include_summary=False)

            final_docs.append(
                Document(
                    page_content=f"{prefix}\n\nPotongan Dialog Percakapan: \n{clean_chunk}",
                    metadata={**full_metadata, "chunk_index": chunk_counter, "tipe": "all"},
                )
            )
            chunk_counter += 1

        if buffer_text:
            prefix = format_metadata_prefix(prefix_metadata, include_summary=False)
            final_docs.append(
                Document(
                    page_content=f"{prefix}\n\npotongan transkripsi:\n{normalize_whitespace(buffer_text)}",
                    metadata={**full_metadata, "chunk_index": chunk_counter, "tipe": "all"},
                )
            )

        # 4️⃣ Pembuatan Chunk Khusus: Metadata Only
        final_docs.append(
            Document(
                page_content=metadata_only_content,
                metadata={**metadata_chunk_metadata, "chunk_index": -1, "tipe": "metadata"},
            )
        )

        # 5️⃣ Pembuatan Chunk Khusus: Summary Only
        summary_text = _to_text(prefix_metadata.get("summary"))
        summary_content_lines = build_metadata_lines(metadata_chunk_metadata, full_metadata)
        summary_content = "\n".join(summary_content_lines) + (f"\n\n{summary_text}" if summary_text else "")

        final_docs.append(
            Document(
                page_content=summary_content,
                metadata={**metadata_chunk_metadata, "chunk_index": -2, "tipe": "summary"},
            )
        )

        # 6️⃣ Simpan ke Database Vector (Batch Insert)
        vector_store = get_vectorstore()
        batch_size = 10
        for i in range(0, len(final_docs), batch_size):
            vector_store.add_documents(final_docs[i : i + batch_size])

        logger.info(f"Berhasil simpan {len(final_docs)} chunk untuk meeting: {full_metadata['agenda']}")

    except Exception as e:
        logger.error(f"Gagal ingest transcript: {str(e)}", exc_info=True)
        raise
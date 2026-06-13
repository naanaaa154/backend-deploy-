import logging
import math
import re
from datetime import datetime

from langchain_experimental.text_splitter import SemanticChunker
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
# PREPROCESS TRANSCRIPT
# =========================================================
def normalize_transcript(text: str) -> str:
    """
    Menggabungkan teks per pembicara agar dialog lebih mengalir.
    Format input diasumsikan:
    SPEAKER_1: isi kalimat
    """
    text = text.replace("\ufeff", "")
    lines = text.splitlines()
    blocks = []
    current_speaker = None
    buffer = []

    for line in lines:
        line = re.sub(r"\s+", " ", line.strip())
        if not line:
            continue

        match = re.match(
            r"(?i)(speaker[_\s]*\d+|[a-z]+(?:\s+[a-z]+)*)\s*:\s*(.*)",
            line,
        )
        if match:
            # Simpan blok sebelumnya
            if current_speaker and buffer:
                blocks.append(f"{current_speaker}: {' '.join(buffer)}")

            current_speaker = match.group(1)
            buffer = [match.group(2)]
        else:
            buffer.append(line)

    # Simpan blok terakhir
    if current_speaker and buffer:
        blocks.append(f"{current_speaker}: {' '.join(buffer)}")

    return "\n\n".join(blocks)


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


def parse_speaker_blocks(text: str) -> list[str]:
    """
    Parse blok pembicara dari teks mentah.
    Menangkap pola seperti "Speaker 1:", "SPEAKER_01:", atau "Andi:".
    """
    text = text.replace("\ufeff", "")
    # Tangkap label speaker di awal baris (case-insensitive)
    pattern = r"(?im)(?:^|\n)\s*(speaker[_\s]*\d*:|[a-z]+(?:\s+[a-z]+)*:)"
    # Split menghasilkan [teks, speaker, teks, speaker, ...]
    parts = re.split(pattern, text)

    blocks = []
    speaker = None

    for part in parts:
        # Jika part adalah label speaker, set sebagai konteks aktif
        if re.match(r"(?i)speaker[_\s]*\d*:|[a-z]+(?:\s+[a-z]+)*:", part.strip()):
            speaker = part.strip()
        else:
            # Gabungkan teks dengan label speaker terakhir
            if speaker and part.strip():
                blocks.append(f"{speaker} {part.strip()}")

    return blocks


def split_into_sentences(text: str) -> list[str]:
    cleaned = normalize_whitespace(text)
    if not cleaned:
        return []

    parts = re.split(r"(?<=[.!?])\s+", cleaned)
    return [p.strip() for p in parts if p.strip()]


def apply_block_overlap(chunks: list[str]) -> list[str]:
    """
    Menambahkan overlap antar chunk berupa SATU BLOK PEMBICARA TERAKHIR
    dari chunk sebelumnya, bukan per kalimat.
    
    Format blok diasumsikan: "Speaker X: ..." dipisah dengan newline.
    """
    if not chunks:
        return []

    def _get_last_speaker_block(chunk_text: str) -> str:
        """Ambil satu blok pembicara terakhir dari sebuah chunk."""
        lines = [line.strip() for line in chunk_text.splitlines() if line.strip()]
        if not lines:
            return ""

        # Temukan indeks baris terakhir yang merupakan awal blok pembicara
        speaker_pattern = re.compile(
            r"(?i)^(speaker[_\s]*\d+|[a-z]+(?:\s+[a-z]+)*)\s*:"
        )

        last_speaker_idx = None
        for idx in range(len(lines) - 1, -1, -1):
            if speaker_pattern.match(lines[idx]):
                last_speaker_idx = idx
                break

        if last_speaker_idx is None:
            # Tidak ditemukan pola speaker, fallback ke baris terakhir saja
            return lines[-1]

        # Gabungkan semua baris dari blok speaker terakhir hingga akhir chunk
        return "\n".join(lines[last_speaker_idx:])

    overlapped = [chunks[0]]
    prev_chunk = chunks[0]

    for chunk in chunks[1:]:
        overlap_block = _get_last_speaker_block(prev_chunk)

        if overlap_block and not chunk.lstrip().startswith(overlap_block.splitlines()[0]):
            chunk = f"{overlap_block}\n{chunk}".strip()

        overlapped.append(chunk)
        prev_chunk = chunk

    return overlapped


def _cosine_sim(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def semantic_chunk_by_speaker(
    blocks: list[str],
    embed,
    max_chars: int = 1500,
    min_chars: int = 750,
    topic_sim_threshold: float = 0.74,
    lookback: int = 3,
) -> list[str]:
    """
    Chunk berdasarkan blok pembicara dengan deteksi perubahan topik
    via similarity embedding antar blok.
    """
    if not blocks:
        return []

    block_embeds = [embed(b) for b in blocks]

    chunks = []
    current_blocks: list[str] = []

    for i, blk in enumerate(blocks):
        if not current_blocks:
            current_blocks.append(blk)
            continue

        start = max(0, i - lookback)
        ctx_vecs = block_embeds[start:i]
        if not ctx_vecs:
            ctx = block_embeds[i]
        else:
            ctx = [sum(vals) / len(vals) for vals in zip(*ctx_vecs)]

        sim = _cosine_sim(ctx, block_embeds[i])
        candidate_text = "\n".join(current_blocks + [blk])

        too_long = len(candidate_text) > max_chars
        topic_break = sim < topic_sim_threshold

        if (
            (topic_break and len("\n".join(current_blocks)) >= min_chars)
            or (too_long and len("\n".join(current_blocks)) >= min_chars)
        ):
            chunks.append("\n".join(current_blocks))
            current_blocks = [blk]
        else:
            current_blocks.append(blk)

    if current_blocks:
        chunks.append("\n".join(current_blocks))

    return chunks


def format_metadata_prefix(meta: dict) -> str:
    def format_indonesian_date(value: str | None) -> str:
        if not value:
            return ""

        if not isinstance(value, str):
            value = str(value)

        value = value.strip()
        if not value:
            return ""

        if re.search(r"[a-zA-Z]", value):
            return value

        for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
            try:
                parsed = datetime.strptime(value, fmt)
                break
            except ValueError:
                parsed = None

        if not parsed:
            return value

        bulan = [
            "januari",
            "februari",
            "maret",
            "april",
            "mei",
            "juni",
            "juli",
            "agustus",
            "september",
            "oktober",
            "november",
            "desember",
        ]

        return f"{parsed.day} {bulan[parsed.month - 1]} {parsed.year}"

    topics = meta.get("main_topic", meta.get("kata kunci", []))
    participants = meta.get("participants", meta.get("daftar hadir", []))
    summary = meta.get("summary", "")
    date_value = meta.get("date", meta.get("tanggal pelaksanaan", ""))
    formatted_date = format_indonesian_date(date_value)
    start_time = _format_time_short(meta.get("start_time", meta.get("jam mulai", "")))
    end_time = _format_time_short(meta.get("end_time", meta.get("jam selesai", "")))
    location = meta.get("location", meta.get("tempat dilaksanakan", ""))

    if isinstance(topics, list):
        topics_str = ", ".join(topics)
    else:
        topics_str = str(topics)

    if isinstance(participants, list):
        participants_str = ", ".join(participants)
    else:
        participants_str = str(participants)

    # Susunan metadata sesuai permintaan:
    # agenda, tempat dilaksanakan, tanggal pelaksanaan, jam mulai, jam selesai, daftar hadir, kata kunci
    lines = [
        f"agenda: {meta.get('agenda', '')}",
        f"tempat dilaksanakan: {location}",
        f"tanggal pelaksanaan: {formatted_date}",
        f"jam mulai: {start_time}",
        f"jam selesai: {end_time}",
        f"daftar hadir: {participants_str}",
        f"kata kunci: {topics_str}",
    ]

    if summary:
        lines.append(f"\n{summary}")

    return "\n".join(lines)


def format_metadata_chunk_date(value) -> str:
    if value is None:
        return ""

    value = str(value).strip()
    if not value:
        return ""

    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            parsed = datetime.strptime(value, fmt)
            bulan = [
                "januari",
                "februari",
                "maret",
                "april",
                "mei",
                "juni",
                "juli",
                "agustus",
                "september",
                "oktober",
                "november",
                "desember",
            ]
            return f"{parsed.day:02d} {bulan[parsed.month - 1]} {parsed.year}"
        except ValueError:
            continue

    return value


def split_date_components(value: str | None) -> tuple[str, str, str]:
    if not value:
        return "", "", ""

    s = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            parsed = datetime.strptime(s, fmt)
            return (
                f"{parsed.day:02d}",
                str(parsed.month),
                str(parsed.year),
            )
        except ValueError:
            continue

    m = re.search(r"(\d{1,2})[^0-9]+(\d{1,2})[^0-9]+(\d{2,4})", s)
    if m:
        d, mo, y = m.group(1), m.group(2), m.group(3)
        if len(y) == 2:
            y = "20" + y
        return (f"{int(d):02d}", str(int(mo)), str(int(y)))

    return "", "", ""


def _format_time_short(value: str | None) -> str:
    """Format waktu dari `HH:MM:SS` atau `H:MM:SS` menjadi `HH:MM`.
    Jika format tidak dikenali, kembalikan string aslinya (atau kosong bila None).
    """
    if not value:
        return ""

    s = str(value).strip()
    # Coba parse dengan detik dulu, lalu tanpa detik
    try:
        dt = datetime.strptime(s, "%H:%M:%S")
        return dt.strftime("%H:%M")
    except Exception:
        pass

    try:
        dt = datetime.strptime(s, "%H:%M")
        return dt.strftime("%H:%M")
    except Exception:
        # Jika bukan format waktu yang dikenali, kembalikan apa adanya
        return s


def _to_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return str(value)


def build_metadata_lines(metadata_chunk_metadata: dict, full_metadata: dict) -> list[str]:
    values = {
        "agenda": _to_text(metadata_chunk_metadata.get("agenda")),
        "tempat dilaksanakan": _to_text(
            metadata_chunk_metadata.get("tempat dilaksanakan")
        ),
        "tanggal pelaksanaan": _to_text(
            metadata_chunk_metadata.get("tanggal pelaksanaan")
        ),
        "tahun pelaksanaan": _to_text(
            metadata_chunk_metadata.get("tahun pelaksanaan")
        ),
        "jam mulai": _to_text(full_metadata.get("jam mulai")),
        "jam selesai": _to_text(full_metadata.get("jam selesai")),
        "daftar hadir": _to_text(metadata_chunk_metadata.get("daftar hadir")),
        "kata kunci": _to_text(metadata_chunk_metadata.get("kata kunci")),
    }

    return [f"{key}: {values.get(key, '')}" for key in METADATA_LINE_ORDER]


# =========================================================
# INGEST TRANSCRIPT (IMPROVED VERSION)
# =========================================================
def ingest_transcript(text: str, summary_metadata: dict):
    # Metadata lengkap untuk filtering RAG (tanpa summary di cmetadata)
    full_metadata = {
        "agenda": clean_metadata_value(summary_metadata.get("agenda", "Unagendad")),
        # original date value (kept for backward compatibility)
        "tanggal pelaksanaan": clean_metadata_value(summary_metadata.get("date", None)),
        "jam mulai": clean_metadata_value(summary_metadata.get("start_time", None)),
        "jam selesai": clean_metadata_value(summary_metadata.get("end_time", None)),
        "tempat dilaksanakan": clean_metadata_value(
            summary_metadata.get("location", None)
        ),
        "daftar hadir": clean_metadata_value(summary_metadata.get("participants", [])),
        "kata kunci": clean_metadata_value(summary_metadata.get("main_topic", [])),
        "meeting_id": clean_metadata_value(summary_metadata.get("meeting_id")),
    }

    # Format jam (hilangkan detik jika ada) untuk keperluan metadata
    full_metadata["jam mulai"] = _format_time_short(full_metadata.get("jam mulai"))
    full_metadata["jam selesai"] = _format_time_short(full_metadata.get("jam selesai"))

    # Khusus chunk metadata: format tanggal agar lebih natural untuk retrieval metadata.
    # Parse the date into components (day, month, year) for richer metadata
    day, month, year = split_date_components(full_metadata.get("tanggal pelaksanaan"))

    metadata_chunk_metadata = {
        **full_metadata,
        # human-friendly formatted date (e.g., 01 mei 2024)
        "tanggal pelaksanaan": format_metadata_chunk_date(
            full_metadata.get("tanggal pelaksanaan")
        ),
        # separate components for filtering/indexing (naming per request)
        "tanggal pelaksanaan (hari)": day,
        "bulan pelaksanaan": month,
        "tahun pelaksanaan": year,
    }

    prefix_metadata = {
        **full_metadata,
        "summary": clean_metadata_value(summary_metadata.get("summary", "")),
    }

    prefix_metadata_no_summary = {**full_metadata}

    metadata_only_content = "\n".join(
        build_metadata_lines(metadata_chunk_metadata, full_metadata)
    )

    try:
        # 1️⃣ Preprocess teks
        # Pastikan seluruh transkrip dalam lowercase agar konsisten untuk pencarian/embedding.
        text = text.lower()

        embedding = get_embedding()

        # 2️⃣ Chunking berbasis speaker + semantic similarity
        blocks = parse_speaker_blocks(text)
        raw_chunks = []

        if blocks:
            raw_chunks = semantic_chunk_by_speaker(
                blocks=blocks,
                embed=embedding.embed_query,
            )
        # else:
        #     # Fallback: semantic chunker untuk teks tanpa label speaker
        #     try:
        #         semantic_chunker = SemanticChunker(
        #             embedding_model=embedding,
        #             min_chunk_size=150,
        #             max_chunk_size=300,
        #             overlap=75,
        #         )
        #     except TypeError:
        #         semantic_chunker = SemanticChunker(
        #             embeddings=embedding,
        #             min_chunk_size=400,
        #         )

        #     raw_chunks = semantic_chunker.split_text(processed_text)

        raw_chunks = apply_block_overlap(raw_chunks)

        final_docs = []
        buffer_text = ""
        chunk_counter = 0

        for chunk_text in raw_chunks:
            clean_chunk = normalize_whitespace(chunk_text).lstrip(".")

            if not clean_chunk:
                continue

            # 🔥 Gabungkan chunk terlalu pendek (< 50 char)
            if len(clean_chunk) < 50:
                buffer_text += " " + clean_chunk
                continue

            # Jika ada sisa buffer, gabungkan
            if buffer_text:
                clean_chunk = normalize_whitespace(buffer_text) + " " + clean_chunk
                buffer_text = ""

            prefix = format_metadata_prefix(prefix_metadata_no_summary)

            final_docs.append(
                Document(
                    page_content=f"{prefix}\n\nPotongan Dialog Percakapan: \n{clean_chunk}",
                    metadata={
                        **full_metadata,
                        "chunk_index": chunk_counter,
                        "tipe": "all",
                    },
                )
            )

            chunk_counter += 1

        # Jika masih ada sisa buffer di akhir
        if buffer_text:
            prefix = format_metadata_prefix(prefix_metadata)

            final_docs.append(
                Document(
                    page_content=(
                        f"{prefix}\n\npotongan transkripsi:\n"
                        f"{normalize_whitespace(buffer_text)}"
                    ),
                    metadata={
                        **full_metadata,
                        "chunk_index": chunk_counter,
                        "tipe": "all",
                    },
                )
            )

        # Tambahkan 1 chunk metadata-only per upload
        final_docs.append(
            Document(
                page_content=metadata_only_content,
                metadata={
                    **metadata_chunk_metadata,
                    "chunk_index": -1,
                    "tipe": "metadata",
                },
            )
        )

        # Tambahkan 1 chunk summary per upload (metadata + summary text saja)
        summary_text = _to_text(prefix_metadata.get("summary"))
        summary_content_lines = build_metadata_lines(
            metadata_chunk_metadata, full_metadata
        )

        if summary_text:
            # Letakkan ringkasan setelah baris metadata, dipisah dengan baris kosong
            summary_content = "\n".join(summary_content_lines) + "\n\n" + summary_text
        else:
            summary_content = "\n".join(summary_content_lines)

        final_docs.append(
            Document(
                page_content=summary_content,
                metadata={
                    **metadata_chunk_metadata,
                    "chunk_index": -2,
                    "tipe": "summary",
                },
            )
        )

        if len(final_docs) == 1:
            logger.warning("Tidak ada chunk dialog yang dihasilkan, hanya chunk metadata yang disimpan.")


        # 3️⃣ Simpan ke PGVector (batch insert)
        vector_store = get_vectorstore()
        batch_size = 10

        for i in range(0, len(final_docs), batch_size):
            batch = final_docs[i : i + batch_size]
            vector_store.add_documents(batch)

        logger.info(
            f"Berhasil simpan {len(final_docs)} chunk untuk meeting: {full_metadata['agenda']}"
        )

    except Exception as e:
        logger.error(f"Gagal ingest transcript: {str(e)}", exc_info=True)
        raise

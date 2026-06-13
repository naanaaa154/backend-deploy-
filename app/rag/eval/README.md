# Evaluasi RAG dengan RAGAS

Folder ini menyediakan skrip evaluasi RAG memakai RAGAS. Skrip akan:
1. Membaca pertanyaan + ground truth dari file JSONL.
2. Menjalankan pipeline RAG yang sama (retrieval + re-ranking + LLM).
3. Menghitung metrik RAGAS dan menyimpan hasil ke JSON.

## Format dataset
Setiap baris JSONL wajib memiliki:
- `question`: pertanyaan untuk RAG.
- `ground_truths`: list jawaban referensi (atau `ground_truth` untuk satu string).

Evaluator akan memakai elemen pertama dari `ground_truths` sebagai `reference`
yang dibutuhkan sebagian metrik RAGAS (misalnya `context_precision`).

Contoh:
```
{"question": "Apa keputusan rapat tentang vendor X?", "ground_truths": ["Keputusan akhir: vendor X disetujui."]}
```

## Cara menjalankan
Jalankan dari folder `backend/`:

```
python -m app.rag.eval.ragas_eval --dataset data/ragas_eval.sample.jsonl --out data/ragas_results.json
```

Catatan:
- Pastikan `.env` sudah terisi agar Ollama dan database bisa diakses.
- Evaluasi akan memakai retriever + re-ranker yang sama seperti API chat.

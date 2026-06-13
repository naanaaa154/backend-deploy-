from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, List, Sequence, Tuple, Dict, Any
import time

DEFAULT_EMPTY_ANSWER = (
    "Mohon maaf, saya tidak menemukan informasi spesifik mengenai hal tersebut dalam dokumen ini."
)


@dataclass(frozen=True)
class EvalRecord:
    question: str
    ground_truths: List[str]


def _normalize_ground_truths(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]


def load_jsonl(path: Path) -> List[EvalRecord]:
    records: List[EvalRecord] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            payload = line.strip()
            if not payload:
                continue
            try:
                obj = json.loads(payload)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {line_number}") from exc

            question = (obj.get("question") or "").strip()
            ground_truths = _normalize_ground_truths(
                obj.get("ground_truths") or obj.get("ground_truth")
            )

            if not question:
                raise ValueError(f"Missing 'question' on line {line_number}")
            if not ground_truths:
                raise ValueError(f"Missing 'ground_truths' on line {line_number}")

            records.append(EvalRecord(question=question, ground_truths=ground_truths))
    return records


def build_eval_inputs(
    records: Sequence[EvalRecord],
    rag_pipeline: Callable[[str, int], Tuple[str, List[str]]],
    k: int,
) -> Dict[str, List[Any]]:
    questions: List[str] = []
    answers: List[str] = []
    contexts: List[List[str]] = []
    ground_truths: List[List[str]] = []
    references: List[str] = []

    for record in records:
        answer, context_list = rag_pipeline(record.question, k)
        questions.append(record.question)
        answers.append(answer)
        contexts.append([ctx for ctx in context_list if ctx])
        ground_truths.append(record.ground_truths)
        references.append(record.ground_truths[0] if record.ground_truths else "")

    return {
        "question": questions,
        "answer": answers,
        "contexts": contexts,
        "ground_truths": ground_truths,
        "reference": references,
    }


def default_rag_pipeline_builder(
    max_retries: int = 3,
    retry_delay_seconds: float = 3.0,
) -> Callable[[str, int], Tuple[str, List[str]]]:
    # Local import to avoid loading settings when the module is imported for tests.
    from app.rag.services.retrieval.chat_service import ChatService

    service = ChatService()

    def _pipeline(question: str, k: int) -> Tuple[str, List[str]]:
        docs = service.retrieve_documents(query=question, k=k)
        if docs:
            last_error: Exception | None = None
            for attempt in range(max_retries):
                try:
                    answer = service._generate_rag_response(question, docs, [])
                    contexts = [doc.page_content for doc in docs]
                    return answer, contexts
                except Exception as exc:
                    last_error = exc
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay_seconds)
            raise RuntimeError(
                f"LLM generation failed after {max_retries} attempts"
            ) from last_error
        return DEFAULT_EMPTY_ANSWER, []

    return _pipeline


def run_ragas_evaluation(
    records: Sequence[EvalRecord],
    k: int,
) -> Dict[str, Any]:
    from datasets import Dataset
    from ragas import evaluate
    from ragas.metrics import (
        answer_relevancy,
        context_precision,
        context_recall,
        faithfulness,
    )

    # Local imports to avoid Settings validation on import.
    from app.core.ollama import get_llm, get_embedding

    rag_pipeline = default_rag_pipeline_builder()
    dataset_inputs = build_eval_inputs(records, rag_pipeline, k)
    dataset = Dataset.from_dict(dataset_inputs)

    metrics = [
        faithfulness,
        answer_relevancy,
        context_precision,
        context_recall,
    ]

    result = evaluate(
        dataset,
        metrics=metrics,
        llm=get_llm(),
        embeddings=get_embedding(),
    )

    if hasattr(result, "to_dict"):
        return result.to_dict()

    return {"result": str(result)}


def _write_output(payload: Dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate RAG with RAGAS metrics")
    parser.add_argument(
        "--dataset",
        type=Path,
        required=True,
        help="Path to JSONL file with question + ground_truths",
    )
    parser.add_argument(
        "--k",
        type=int,
        default=6,
        help="Top-k contexts to retrieve per question",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("data/ragas_results.json"),
        help="Output JSON path for RAGAS results",
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    records = load_jsonl(args.dataset)
    results = run_ragas_evaluation(records, args.k)
    _write_output(results, args.out)
    print(f"RAGAS evaluation selesai. Hasil disimpan di: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

import json
import tempfile
from pathlib import Path
from typing import List, Tuple
import unittest

from app.rag.eval.ragas_eval import load_jsonl, build_eval_inputs, EvalRecord


def dummy_pipeline(question: str, k: int) -> Tuple[str, List[str]]:
    return f"answer for {question}", [f"ctx-{k}-1", f"ctx-{k}-2"]


class TestRagasEval(unittest.TestCase):
    def test_load_jsonl_parses_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "sample.jsonl"
            with file_path.open("w", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        {
                            "question": "Apa keputusan rapat?",
                            "ground_truth": "Keputusan A.",
                        }
                    )
                    + "\n"
                )

            records = load_jsonl(file_path)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].question, "Apa keputusan rapat?")
            self.assertEqual(records[0].ground_truths, ["Keputusan A."])

    def test_build_eval_inputs(self) -> None:
        records = [EvalRecord(question="Apa agenda?", ground_truths=["Agenda A"]) ]
        inputs = build_eval_inputs(records, dummy_pipeline, k=3)
        self.assertEqual(inputs["question"], ["Apa agenda?"])
        self.assertEqual(inputs["answer"], ["answer for Apa agenda?"])
        self.assertEqual(inputs["contexts"], [["ctx-3-1", "ctx-3-2"]])
        self.assertEqual(inputs["ground_truths"], [["Agenda A"]])
        self.assertEqual(inputs["reference"], ["Agenda A"])


if __name__ == "__main__":
    unittest.main()

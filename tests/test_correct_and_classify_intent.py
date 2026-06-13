from app.rag.services.retrieval import chat_helpers
from app.rag.services.retrieval.chat_types import QueryIntent


def test_correct_and_classify_intent_parses_fenced_json(monkeypatch):
    class _FakeLLM:
        def invoke(self, prompt):
            class _Response:
                content = """```json
{"corrected_question": "agenda tahun pelaksanaan: 2026", "classify_intent": "METADATA", "alasan": "menanyakan agenda"}
```"""

            return _Response()

    monkeypatch.setattr(chat_helpers, "get_llm", lambda: _FakeLLM())

    result = chat_helpers.correct_and_classify_intent("agenda thn 2026")

    assert result["corrected_question"] == "agenda tahun pelaksanaan: 2026"
    assert result["classify_intent"] == QueryIntent.METADATA
    assert result["alasan"] == "menanyakan agenda"


def test_correct_and_classify_intent_extracts_fields_from_text(monkeypatch):
    class _FakeLLM:
        def invoke(self, prompt):
            class _Response:
                content = (
                    "corrected_question: agenda tahun pelaksanaan: 2026\n"
                    "classify_intent: metadata\n"
                    "alasan: Pertanyaan metadata"
                )

            return _Response()

    monkeypatch.setattr(chat_helpers, "get_llm", lambda: _FakeLLM())

    result = chat_helpers.correct_and_classify_intent("agenda thn 2026")

    assert result["corrected_question"] == "agenda tahun pelaksanaan: 2026"
    assert result["classify_intent"] == QueryIntent.METADATA
    assert result["alasan"] == "Pertanyaan metadata"


def test_correct_and_classify_intent_invalid_intent_defaults(monkeypatch):
    class _FakeLLM:
        def invoke(self, prompt):
            class _Response:
                content = "{" "\"corrected_question\"" ": \"query\", \"classify_intent\": \"UNKNOWN\"}"

            return _Response()

    monkeypatch.setattr(chat_helpers, "get_llm", lambda: _FakeLLM())

    result = chat_helpers.correct_and_classify_intent("query")

    assert result["classify_intent"] == QueryIntent.RETRIEVAL

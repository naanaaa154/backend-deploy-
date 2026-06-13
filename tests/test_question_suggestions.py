from app.rag.services.retrieval import chat_helpers
from app.rag.services.retrieval.chat_types import QueryIntent


def test_generate_question_suggestions_parses_llm_json(monkeypatch):
    class _FakeLLM:
        def invoke(self, prompt):
            class _Response:
                content = "[\"Pertanyaan 1\", \"Pertanyaan 2\"]"

            return _Response()

    monkeypatch.setattr(chat_helpers, "get_llm", lambda: _FakeLLM())

    suggestions = chat_helpers.generate_question_suggestions(
        "topik rapat",
        QueryIntent.RETRIEVAL,
        max_questions=3,
    )

    assert suggestions == ["Pertanyaan 1", "Pertanyaan 2"]


def test_generate_question_suggestions_fallback(monkeypatch):
    class _FakeLLM:
        def invoke(self, prompt):
            class _Response:
                content = "bukan json"

            return _Response()

    monkeypatch.setattr(chat_helpers, "get_llm", lambda: _FakeLLM())

    suggestions = chat_helpers.generate_question_suggestions(
        "topik rapat",
        QueryIntent.RETRIEVAL,
        max_questions=3,
    )

    assert len(suggestions) == 3
    assert all(isinstance(item, str) for item in suggestions)

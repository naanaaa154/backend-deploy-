from langchain_core.documents import Document

from app.rag.services.retrieval.document_retriever import DocumentRetriever


class _FakeVectorStore:
    def __init__(self):
        self.last_kwargs = None

    def similarity_search_with_score(self, **kwargs):
        self.last_kwargs = kwargs
        return [(Document(page_content="dummy", metadata={}), 0.1)]


def test_vector_search_tipe_all_adds_tipe_filter():
    retriever = DocumentRetriever(ranker=None)
    vectorstore = _FakeVectorStore()

    retriever._vector_search_candidates(
        vectorstore=vectorstore,
        query="test query",
        fetch_k=5,
        meeting_id="meeting-123",
        tipe="all",
    )

    assert vectorstore.last_kwargs is not None
    assert "filter" in vectorstore.last_kwargs
    assert vectorstore.last_kwargs["filter"] == {
        "meeting_id": "meeting-123",
        "tipe": "all",
    }


def test_vector_search_specific_tipe_adds_tipe_filter():
    retriever = DocumentRetriever(ranker=None)
    vectorstore = _FakeVectorStore()

    retriever._vector_search_candidates(
        vectorstore=vectorstore,
        query="test query",
        fetch_k=5,
        meeting_id="meeting-123",
        tipe="metadata",
    )

    assert vectorstore.last_kwargs is not None
    assert "filter" in vectorstore.last_kwargs
    assert vectorstore.last_kwargs["filter"] == {
        "meeting_id": "meeting-123",
        "tipe": "metadata",
    }

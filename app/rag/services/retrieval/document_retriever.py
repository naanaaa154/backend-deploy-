from typing import List, Optional, Any

from langchain_core.documents import Document

from app.vectorstore.pgvector import get_vectorstore
from app.core.config import settings
import requests
from requests.exceptions import RequestException


try:
    from flashrank import Ranker, RerankRequest

    HAS_FLASHRANK = True
except ImportError:
    Ranker = None
    RerankRequest = None
    HAS_FLASHRANK = False
    print("Warning: flashrank not installed. Re-ranking will be disabled.")


class DocumentRetriever:
    def __init__(self, ranker: Optional[Any] = None):
        self._ranker = ranker

    def retrieve_documents(
        self,
        query: str,
        k: int = 4,
        score_threshold: float = 0.3,
        meeting_id: Optional[str] = None,
        tipe: Optional[str] = None,
        unlimited: bool = False,
        use_reranking: bool = True,
    ranker: Optional[Any] = None,
    ) -> List[Document]:
        """
    Retrieve documents using cosine similarity with optional cross-encoder re-ranking.
    - Saat use_reranking=False: threshold diterapkan pada cosine similarity (vector_score).
    - Saat use_reranking=True: threshold diterapkan pada score hasil rerank.
        """
        # Ambil kandidat dokumen dari vectorstore, lalu (opsional) re-rank pakai cross-encoder.
        vectorstore = get_vectorstore()

        # Ambil kandidat lebih banyak untuk re-ranking
        fetch_k = 10000 if unlimited else (k * 4)

        candidates = self._vector_search_candidates(
            vectorstore=vectorstore,
            query=query,
            fetch_k=fetch_k,
            meeting_id=meeting_id,
            tipe=tipe,
        )
        if not candidates:
            return []
        
        normalized_tipe = (tipe or "").strip().lower()

        def _allowed_doc_meta(doc_meta: dict | None) -> bool:
            # Determine whether a candidate doc should be allowed based on 'tipe'.
            try:
                chunk = (doc_meta or {}).get("chunk_index")
            except Exception:
                chunk = None

            if normalized_tipe == "metadata":
                # only allow metadata chunk (-1)
                return chunk == -1
            if normalized_tipe == "summary":
                # only allow the summary chunk (-2)
                return chunk == -2
            # default retrieval: exclude non-chunk marker (-1)
            return chunk != -1

        if not use_reranking:
            # When reranking is disabled we still must apply the vector score
            # threshold and respect 'k' unless 'unlimited' is True.
            filtered = [
                doc
                for doc in candidates
                if float(
                    (doc.metadata or {}).get(
                        "vector_score",
                        (doc.metadata or {}).get("cosine_similarity", -1.0),
                    )
                )
                >= score_threshold
                and _allowed_doc_meta(doc.metadata)
            ]
            if unlimited:
                return filtered
            return filtered[:k]

        active_ranker = ranker or self._ranker

        # Kalau tidak ada ranker → langsung return top-k
        if not active_ranker or not HAS_FLASHRANK or RerankRequest is None:
            if unlimited:
                return [
                    doc
                    for doc in candidates
                    if float(
                        (doc.metadata or {}).get(
                            "vector_score",
                            (doc.metadata or {}).get("cosine_similarity", -1.0),
                        )
                    )
                    >= score_threshold
                    and _allowed_doc_meta(doc.metadata)
                ]
            filtered = [
                doc
                for doc in candidates
                if float(
                    (doc.metadata or {}).get(
                        "vector_score",
                        (doc.metadata or {}).get("cosine_similarity", -1.0),
                    )
                )
                >= score_threshold
                and _allowed_doc_meta(doc.metadata)
            ]
            return filtered[:k]

        # --- Step 2: Re-ranking (Cross Encoder) ---
        try:
            rerank_k = len(candidates) if unlimited else k
            return self._rerank_candidates(
                query,
                candidates,
                rerank_k,
                score_threshold,
                ranker=active_ranker,
                tipe=tipe,
            )
        except Exception as e:
            print(f"Re-ranking failed: {e}. Falling back to vector search.")
            if unlimited:
                return [
                    doc
                    for doc in candidates
                    if float(
                        (doc.metadata or {}).get(
                            "vector_score",
                            (doc.metadata or {}).get("cosine_similarity", -1.0),
                        )
                    )
                    >= score_threshold
                    and _allowed_doc_meta(doc.metadata)
                ]
            filtered = [
                doc
                for doc in candidates
                if float(
                    (doc.metadata or {}).get(
                        "vector_score",
                        (doc.metadata or {}).get("cosine_similarity", -1.0),
                    )
                )
                >= score_threshold
                and _allowed_doc_meta(doc.metadata)
            ]
            return filtered[:k]

    def _vector_search_candidates(
        self,
        vectorstore,
        query: str,
        fetch_k: int,
        meeting_id: Optional[str] = None,
        tipe: Optional[str] = None,
    ) -> List[Document]:
        # --- Step 1: Vector Retrieval (Cosine Similarity) ---
        metadata_filter = {}
        if meeting_id:
            metadata_filter["meeting_id"] = str(meeting_id)
        normalized_tipe = (tipe or "").strip().lower()
        if normalized_tipe and normalized_tipe != "all":
            metadata_filter["tipe"] = str(tipe)
        if not metadata_filter:
            metadata_filter = None

        if hasattr(vectorstore, "similarity_search_with_score"):
            search_kwargs = {
                "query": query,
                "k": fetch_k,
            }
            if metadata_filter:
                search_kwargs["filter"] = metadata_filter

            vector_results = vectorstore.similarity_search_with_score(**search_kwargs)
            candidates = []
            for doc, score in vector_results:
                # PGVector dengan DistanceStrategy.COSINE mengembalikan distance (0..2).
                # Similarity = 1.0 - distance.
                sim_score = 1.0 - float(score)
                # Ensure metadata is a dict
                if doc.metadata is None:
                    doc.metadata = {}
                doc.metadata["vector_score"] = sim_score
                doc.metadata["cosine_similarity"] = sim_score
                doc.metadata["vector_distance"] = float(score)
                try:
                    normalized_tipe = (tipe or "").strip().lower()
                    chunk_idx = (doc.metadata or {}).get("chunk_index")
                    if normalized_tipe == "metadata":
                        if chunk_idx != -1:
                            continue
                    elif normalized_tipe == "summary":
                        if chunk_idx != -2:
                            continue
                    else:
                        if chunk_idx == -1:
                            continue
                except Exception:
                    # If metadata is not a dict or other issue, keep the doc
                    pass
                # Populate reranker model placeholder (may be overwritten later)
                try:
                    doc.metadata.setdefault("reranker_model", None)
                except Exception:
                    pass
                candidates.append(doc)
            return candidates

        search_kwargs = {
            "query": query,
            "k": fetch_k,
        }
        if metadata_filter:
            search_kwargs["filter"] = metadata_filter

        return vectorstore.similarity_search(**search_kwargs)

    def _rerank_candidates(
        self,
        query: str,
        candidates: List[Document],
        k: int,
        score_threshold: float,
        ranker: Any,
        tipe: Optional[str] = None,
    ) -> List[Document]:
        normalized_tipe = (tipe or "").strip().lower()
        passages = [
            {
                "id": str(i),
                "text": doc.page_content,
                "meta": doc.metadata or {},
            }
            for i, doc in enumerate(candidates)
        ]

        # If external rerank endpoint is configured, prefer calling it.
        results = None
        if settings.RERANK_ENDPOINT:
            try:
                payload = {
                    "query": query,
                    "passages": passages,
                }
                resp = requests.post(settings.RERANK_ENDPOINT, json=payload, timeout=10)
                resp.raise_for_status()
                # Expecting a JSON array of results: [{"id":..., "text":..., "score":..., "meta": {...}}, ...]
                results = resp.json()
            except RequestException as re:
                print(f"External rerank endpoint failed: {re}. Falling back to internal reranker if available.")
            except ValueError as ve:
                print(f"Invalid JSON from rerank endpoint: {ve}. Falling back to internal reranker if available.")

        # If external didn't produce results, try using the local ranker (flashrank) if available.
        if results is None:
            try:
                rerank_request = RerankRequest(
                    query=query,
                    passages=passages,
                )

                results = ranker.rerank(rerank_request)
            except Exception as e:
                # Propagate exception to outer handler which will fallback to vector search
                raise
        final_docs: List[Document] = []

        for res in results:
            score = res.get("score", 0.0)

            # --- Step 3: Threshold Filtering ---
            if score < score_threshold:
                continue

            meta = res.get("meta", {})
            meta["re_rank_score"] = float(score)
            # annotate which reranker/model produced this score when possible
            try:
                model_name = getattr(ranker, "model_name", None)
            except Exception:
                model_name = None
            if model_name:
                meta["reranker_model"] = model_name

            try:
                chunk_idx = meta.get("chunk_index")
                if normalized_tipe == "metadata":
                    pass
                elif normalized_tipe == "summary":
                    if chunk_idx != -2:
                        continue
                else:
                    if chunk_idx == -1:
                        continue
            except Exception:
                # If meta isn't a dict or missing, just proceed
                pass

            final_docs.append(
                Document(
                    page_content=res["text"],
                    metadata=meta,
                )
            )

            if len(final_docs) >= k:
                break

        return final_docs
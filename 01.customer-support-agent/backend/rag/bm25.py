"""
BM25 retriever built directly on rank-bm25 + langchain_core.BaseRetriever.

langchain-community is deprecated (sunset), so we implement BM25Retriever
here using only the stable official packages:
  - rank_bm25.BM25Okapi  (the underlying algorithm; already a direct dependency)
  - langchain_core.retrievers.BaseRetriever  (official abstract base)
  - langchain_core.documents.Document

The public interface mirrors langchain_community's BM25Retriever so existing
call sites (from_documents, k) work without change.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import ConfigDict, Field
from rank_bm25 import BM25Okapi


def _default_preprocess(text: str) -> list[str]:
    return text.split()


class BM25Retriever(BaseRetriever):
    """BM25 keyword retriever backed by rank-bm25."""

    vectorizer: Any = None
    docs: list[Document] = Field(repr=False)
    k: int = 4
    preprocess_func: Callable[[str], list[str]] = _default_preprocess

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @classmethod
    def from_documents(
        cls,
        documents: Iterable[Document],
        *,
        bm25_params: dict[str, Any] | None = None,
        preprocess_func: Callable[[str], list[str]] = _default_preprocess,
        **kwargs: Any,
    ) -> BM25Retriever:
        docs = list(documents)
        tokenized = [preprocess_func(d.page_content) for d in docs]
        vectorizer = BM25Okapi(tokenized, **(bm25_params or {}))
        return cls(vectorizer=vectorizer, docs=docs, preprocess_func=preprocess_func, **kwargs)

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun,
    ) -> list[Document]:
        tokens = self.preprocess_func(query)
        scores = self.vectorizer.get_scores(tokens)
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[: self.k]
        return [self.docs[i] for i in top_indices]

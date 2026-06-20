"""
A self-contained inverted index with TF-IDF ranking and cosine similarity.

This module is the answer to Q5 ("implement a simplified document indexing and
keyword-based search mechanism") and doubles as the offline search backend when
Elasticsearch is unavailable. It depends only on the Python standard library so
it can be read, run and explained on its own.

How it works
------------
1.  ANALYSIS   — each document is lower-cased, tokenised on word boundaries and
                 stripped of stop-words (the same analysis is applied to queries).
2.  INDEXING   — we build a postings map  term -> {doc_id: term_frequency}.
3.  WEIGHTING   — at query time each term gets an IDF weight
                 idf(t) = ln(1 + N / df(t)), and each (doc, term) a TF-IDF weight.
4.  RANKING    — documents are scored by cosine similarity between the query
                 vector and each document vector, so longer documents are not
                 unfairly favoured.

The same maths underpins production engines such as Lucene/Elasticsearch (which
use the closely related BM25); this implementation makes the mechanics explicit.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from typing import Dict, List, Tuple

# A small English stop-word list. Removing these reduces index size and stops
# common words from dominating relevance scores.
STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "he",
    "in", "is", "it", "its", "of", "on", "that", "the", "to", "was", "were",
    "will", "with", "this", "these", "those", "or", "but", "if", "then", "so",
}

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> List[str]:
    """Lower-case, split on non-alphanumerics, and drop stop-words."""
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in STOP_WORDS]


class InvertedIndex:
    def __init__(self) -> None:
        # term -> {doc_id -> term frequency in that doc}
        self.postings: Dict[str, Dict[str, int]] = defaultdict(dict)
        # doc_id -> total number of (non-stopword) tokens, used for TF normalisation
        self.doc_length: Dict[str, int] = {}
        # doc_id -> human-readable title (for displaying results)
        self.titles: Dict[str, str] = {}
        # doc_id -> original text (for building result snippets)
        self.raw: Dict[str, str] = {}

    # ------------------------------------------------------------------ #
    # Mutating the index
    # ------------------------------------------------------------------ #
    def add(self, doc_id: str, text: str, title: str = "") -> None:
        """Index (or re-index) a document. Re-adding the same id refreshes it."""
        if doc_id in self.doc_length:
            self.remove(doc_id)

        tokens = tokenize(text)
        self.doc_length[doc_id] = len(tokens) or 1
        self.titles[doc_id] = title or text[:60]
        self.raw[doc_id] = text

        term_freq: Dict[str, int] = defaultdict(int)
        for token in tokens:
            term_freq[token] += 1
        for term, freq in term_freq.items():
            self.postings[term][doc_id] = freq

    def remove(self, doc_id: str) -> None:
        if doc_id not in self.doc_length:
            return
        for term in list(self.postings):
            self.postings[term].pop(doc_id, None)
            if not self.postings[term]:
                del self.postings[term]
        self.doc_length.pop(doc_id, None)
        self.titles.pop(doc_id, None)
        self.raw.pop(doc_id, None)

    # ------------------------------------------------------------------ #
    # Querying
    # ------------------------------------------------------------------ #
    @property
    def num_docs(self) -> int:
        return len(self.doc_length)

    def _idf(self, term: str) -> float:
        """Inverse document frequency with smoothing to avoid div-by-zero."""
        df = len(self.postings.get(term, {}))
        if df == 0:
            return 0.0
        return math.log(1 + self.num_docs / df)

    def search(self, query: str, limit: int = 10) -> List[Tuple[str, float, str]]:
        """
        Rank documents against `query` using TF-IDF + cosine similarity.

        Returns a list of (doc_id, score, snippet) sorted by descending score.
        """
        q_tokens = tokenize(query)
        if not q_tokens or self.num_docs == 0:
            return []

        # --- query vector (TF-IDF) ---
        q_tf: Dict[str, int] = defaultdict(int)
        for t in q_tokens:
            q_tf[t] += 1
        q_vec = {t: tf * self._idf(t) for t, tf in q_tf.items()}
        q_norm = math.sqrt(sum(w * w for w in q_vec.values())) or 1.0

        # --- accumulate document scores over candidate docs only ---
        scores: Dict[str, float] = defaultdict(float)
        for term, q_weight in q_vec.items():
            idf = self._idf(term)
            for doc_id, tf in self.postings.get(term, {}).items():
                # TF normalised by document length keeps long docs honest.
                d_weight = (tf / self.doc_length[doc_id]) * idf
                scores[doc_id] += q_weight * d_weight

        # --- cosine normalisation by document vector magnitude ---
        ranked: List[Tuple[str, float, str]] = []
        for doc_id, dot in scores.items():
            d_norm = self._doc_norm(doc_id) or 1.0
            cosine = dot / (q_norm * d_norm)
            ranked.append((doc_id, cosine, self._snippet(doc_id, q_tokens)))

        ranked.sort(key=lambda x: x[1], reverse=True)
        return ranked[:limit]

    def _doc_norm(self, doc_id: str) -> float:
        """L2 norm of a document's TF-IDF vector (computed lazily per query)."""
        total = 0.0
        length = self.doc_length[doc_id]
        for term, postings in self.postings.items():
            tf = postings.get(doc_id)
            if tf:
                w = (tf / length) * self._idf(term)
                total += w * w
        return math.sqrt(total)

    def _snippet(self, doc_id: str, q_tokens: List[str], window: int = 12) -> str:
        """Build a short snippet centred on the first query-term match."""
        words = self.raw[doc_id].split()
        lowered = [w.lower().strip(".,;:!?") for w in words]
        q_set = set(q_tokens)
        for i, w in enumerate(lowered):
            if w in q_set:
                start = max(0, i - window // 2)
                end = min(len(words), i + window // 2)
                prefix = "… " if start > 0 else ""
                suffix = " …" if end < len(words) else ""
                return prefix + " ".join(words[start:end]) + suffix
        return " ".join(words[:window]) + (" …" if len(words) > window else "")

    def title_of(self, doc_id: str) -> str:
        return self.titles.get(doc_id, doc_id)

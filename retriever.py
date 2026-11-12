"""Local retrieval for PawPal+ (the "R" in RAG).

Documents in ``knowledge/*.md`` are split into sections (one per ``##``
heading). A query is scored against each section with a small TF-IDF
variant that needs no external libraries and no API key. Every result
carries its source file and section title so answers can cite where
the advice came from.
"""
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

KNOWLEDGE_DIR = Path(__file__).parent / "knowledge"

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has",
    "he", "in", "is", "it", "its", "of", "on", "or", "that", "the", "to",
    "was", "will", "with", "your", "you", "can", "do", "not", "my", "if",
}


def tokenize(text: str) -> List[str]:
    """Lowercase words, minus stopwords, with a very light stemmer."""
    words = re.findall(r"[a-z]+", text.lower())
    out = []
    for word in words:
        if word in STOPWORDS or len(word) < 2:
            continue
        if word.endswith("ies") and len(word) > 4:
            word = word[:-3] + "y"
            out.append(word)
            continue
        for suffix in ("ing", "es", "s"):
            if word.endswith(suffix) and len(word) - len(suffix) >= 3:
                word = word[: -len(suffix)]
                break
        out.append(word)
    return out


@dataclass
class Chunk:
    source: str
    title: str
    category: str
    text: str
    topic: str = ""  # file name without extension, indexed as a keyword


@dataclass
class Hit:
    chunk: Chunk
    score: float


class Retriever:
    """Index knowledge sections and return the best matches for a query."""

    def __init__(self, knowledge_dir: Optional[Path] = None):
        self.knowledge_dir = Path(knowledge_dir or KNOWLEDGE_DIR)
        self.chunks: List[Chunk] = []
        self._tokens: List[List[str]] = []
        self._idf = {}
        self._load()

    def _load(self):
        if not self.knowledge_dir.exists():
            return
        for path in sorted(self.knowledge_dir.glob("*.md")):
            category = "general"
            title = path.stem
            body: List[str] = []

            def flush():
                text = " ".join(body).strip()
                if text:
                    self.chunks.append(
                        Chunk(path.name, title, category, text, path.stem)
                    )

            for line in path.read_text(encoding="utf-8").splitlines():
                if line.startswith("category:"):
                    category = line.split(":", 1)[1].strip()
                elif line.startswith("## "):
                    flush()
                    title = line[3:].strip()
                    body = []
                elif not line.startswith("# "):
                    body.append(line.strip())
            flush()

        self._tokens = [
            tokenize(f"{c.topic} {c.title} {c.title} {c.text}") for c in self.chunks
        ]
        n = len(self.chunks)
        doc_freq = {}
        for tokens in self._tokens:
            for tok in set(tokens):
                doc_freq[tok] = doc_freq.get(tok, 0) + 1
        self._idf = {
            tok: math.log((1 + n) / (1 + df)) + 1
            for tok, df in doc_freq.items()
        }

    def search(
        self, query: str, k: int = 3, category: Optional[str] = None
    ) -> List[Hit]:
        """Return up to ``k`` hits with score > 0, best first.

        Scores are normalized to 0..1 (share of the query's weight that
        the section covers), so they can be used as a confidence signal.
        """
        q_tokens = tokenize(query)
        if not q_tokens or not self.chunks:
            return []

        q_weight = sum(self._idf.get(t, 1.0) for t in set(q_tokens))
        hits = []
        for chunk, tokens in zip(self.chunks, self._tokens):
            if category and chunk.category not in (category, "general"):
                continue
            present = set(tokens)
            matched = sum(
                self._idf.get(t, 1.0) for t in set(q_tokens) if t in present
            )
            if matched > 0 and q_weight > 0:
                score = matched / q_weight
                if category and chunk.category == category:
                    score = min(1.0, score + 0.1)
                hits.append(Hit(chunk, round(score, 3)))

        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:k]

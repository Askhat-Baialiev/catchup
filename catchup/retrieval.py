"""Backend of the search_notes tool.

Loads the course material (PDF, Markdown, text), cuts it into small chunks and
ranks them with BM25. Pure Python on purpose: no vector database, no embedding
calls, nothing to install or pay for. Good enough for one course of slides.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path

STOPWORDS = set(
    "a an and are as at be by for from has have how i in is it of on or that the this to was "
    "what when where which who why will with you your do does can me my we our not if then than "
    "so such its into about explain tell please teach show".split()
)
IRREGULAR = {"matrices": "matrix", "bases": "basis", "vertices": "vertex"}
CHUNK_CHARS = 900


def tokenize(text: str) -> list:
    tokens = []
    for tok in re.findall(r"[a-z0-9]+", text.lower()):
        if len(tok) < 2 or tok in STOPWORDS:
            continue
        tok = IRREGULAR.get(tok, tok)
        if tok.endswith("ies") and len(tok) > 4:
            tok = tok[:-3] + "y"
        elif tok.endswith("s") and not tok.endswith("ss") and len(tok) > 3:
            tok = tok[:-1]
        tokens.append(tok)
    return tokens


@dataclass
class Chunk:
    id: str
    source: str
    text: str


def _split_long(text: str, limit: int = CHUNK_CHARS) -> list:
    """Split on blank lines, packing paragraphs into pieces of about `limit` chars."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    pieces, current = [], ""
    for para in paragraphs:
        if current and len(current) + len(para) > limit:
            pieces.append(current)
            current = para
        else:
            current = f"{current}\n\n{para}" if current else para
    if current:
        pieces.append(current)
    return pieces


def _read_markdown(path: Path) -> list:
    """One unit per heading: (source label, text)."""
    units, heading, lines = [], path.stem, []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        match = re.match(r"^#{1,4}\s+(.*)", line)
        if match:
            if "".join(lines).strip():
                units.append((f"{path.name} § {heading}", "\n".join(lines)))
            heading, lines = match.group(1).strip(), []
        else:
            lines.append(line)
    if "".join(lines).strip():
        units.append((f"{path.name} § {heading}", "\n".join(lines)))
    return units


def _read_pdf(path: Path) -> list:
    """One unit per page, so every citation points to a slide/page number."""
    from pypdf import PdfReader

    units = []
    reader = PdfReader(str(path))
    for number, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:
            units.append((f"{path.name}, p. {number}", text))
    return units


def load_chunks(directory: Path) -> list:
    chunks = []
    for path in sorted(Path(directory).rglob("*")):
        if not path.is_file() or path.name.lower() == "readme.md":
            continue
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            units = _read_pdf(path)
        elif suffix in (".md", ".txt"):
            units = _read_markdown(path)
        else:
            continue
        for source, text in units:
            for piece in _split_long(text):
                chunks.append(Chunk(id=f"S{len(chunks) + 1}", source=source, text=piece))
    return chunks


class NotesIndex:
    """BM25 over the chunks."""

    K1, B = 1.5, 0.75

    def __init__(self, chunks: list):
        self.chunks = chunks
        # the source label (file + heading) is searchable too
        self.docs = [tokenize(c.source + " " + c.text) for c in chunks]
        self.avg_len = (sum(len(d) for d in self.docs) / len(self.docs)) if self.docs else 0.0
        self.doc_freq = {}
        for doc in self.docs:
            for term in set(doc):
                self.doc_freq[term] = self.doc_freq.get(term, 0) + 1

    @classmethod
    def from_dir(cls, directory: Path) -> "NotesIndex":
        return cls(load_chunks(directory))

    def search(self, query: str, k: int = 3) -> dict:
        """Returns {"found": bool, "results": [{"id","source","text"}]}.

        `found` is False when the material does not really cover the query. The
        agent must then refuse to answer from general knowledge.
        """
        terms = list(dict.fromkeys(tokenize(query)))
        if not terms or not self.docs:
            return {"found": False, "results": []}
        n_docs = len(self.docs)
        scored = []
        for i, doc in enumerate(self.docs):
            score, matched = 0.0, 0
            for term in terms:
                freq = doc.count(term)
                if not freq:
                    continue
                matched += 1
                df = self.doc_freq[term]
                idf = math.log(1 + (n_docs - df + 0.5) / (df + 0.5))
                norm = freq + self.K1 * (1 - self.B + self.B * len(doc) / self.avg_len)
                score += idf * freq * (self.K1 + 1) / norm
            if score > 0:
                scored.append((score, matched, i))
        scored.sort(reverse=True)
        top = scored[:k]
        if not top:
            return {"found": False, "results": []}
        best_matched = max(m for _, m, _ in top)
        found = best_matched >= 2 or best_matched / len(terms) >= 0.5
        if not found:
            return {"found": False, "results": []}
        results = [
            {"id": self.chunks[i].id, "source": self.chunks[i].source, "text": self.chunks[i].text}
            for _, _, i in top
        ]
        return {"found": True, "results": results}

from dataclasses import dataclass
from pathlib import Path

from pydantic import TypeAdapter

from ams_copilot.models import QueryText, TopK
from ams_copilot.rag.embeddings import Embedder
from ams_copilot.rag.store import Chunk, SearchHit, VectorStore


@dataclass
class Document:
    id: str
    title: str
    module: str
    transactions: list[str]
    body: str


def parse_document(text: str, fallback_id: str) -> Document:
    meta: dict[str, str] = {}
    body = text
    if text.startswith("---"):
        _, header, body = text.split("---", 2)
        for line in header.strip().splitlines():
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()
    transactions = [item.strip() for item in meta.get("transactions", "").split(",") if item.strip()]
    return Document(
        id=meta.get("id", fallback_id),
        title=meta.get("title", fallback_id),
        module=meta.get("module", "BASIS"),
        transactions=transactions,
        body=body.strip(),
    )


def load_documents(directory: Path) -> list[Document]:
    return [parse_document(path.read_text(encoding="utf-8"), path.stem) for path in sorted(directory.glob("*.md"))]


def chunk_document(document: Document, max_chars: int = 1800) -> list[Chunk]:
    sections: list[str] = []
    current = ""
    for block in document.body.split("\n## "):
        piece = block if not current and block.startswith("#") else f"## {block}"
        if current and len(current) + len(piece) > max_chars:
            sections.append(current.strip())
            current = ""
        current += f"\n{piece}"
    if current.strip():
        sections.append(current.strip())
    return [
        Chunk(
            id=f"{document.id}#{index}",
            doc_id=document.id,
            title=document.title,
            module=document.module,
            content=section,
            metadata={"transactions": document.transactions},
        )
        for index, section in enumerate(sections)
    ]


class KnowledgeBase:
    def __init__(self, store: VectorStore, embedder: Embedder) -> None:
        self.store = store
        self.embedder = embedder

    def index(self, documents: list[Document]) -> int:
        chunks = [chunk for document in documents for chunk in chunk_document(document)]
        if not chunks:
            return 0
        vectors = self.embedder.embed([f"{chunk.title}\n{chunk.content}" for chunk in chunks])
        self.store.upsert(chunks, vectors)
        return len(chunks)

    def search(
        self,
        query: str,
        top_k: int = 4,
        module: str | None = None,
        min_score: float = 0.0,
        module_boost: float = 0.05,
    ) -> list[SearchHit]:
        query = TypeAdapter(QueryText).validate_python(query)
        top_k = TypeAdapter(TopK).validate_python(top_k)
        vector = self.embedder.embed([query])[0]
        best: dict[str, SearchHit] = {}
        for hit in self.store.search(vector, top_k * 3, None):
            score = hit.score + (module_boost if module and hit.chunk.module == module else 0.0)
            if score < min_score:
                continue
            current = best.get(hit.chunk.doc_id)
            if current is None or score > current.score:
                best[hit.chunk.doc_id] = SearchHit(hit.chunk, score)
        return sorted(best.values(), key=lambda hit: hit.score, reverse=True)[:top_k]

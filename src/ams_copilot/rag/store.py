from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

import numpy as np


@dataclass
class Chunk:
    id: str
    doc_id: str
    title: str
    module: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchHit:
    chunk: Chunk
    score: float

    def as_dict(self) -> dict[str, Any]:
        return {**asdict(self.chunk), "score": round(self.score, 4)}


class VectorStore(Protocol):
    def upsert(self, chunks: list[Chunk], vectors: np.ndarray) -> None: ...

    def search(self, vector: np.ndarray, top_k: int, module: str | None = None) -> list[SearchHit]: ...

    def count(self) -> int: ...


class InMemoryVectorStore:
    def __init__(self) -> None:
        self._chunks: dict[str, Chunk] = {}
        self._vectors: dict[str, np.ndarray] = {}

    def upsert(self, chunks: list[Chunk], vectors: np.ndarray) -> None:
        for chunk, vector in zip(chunks, vectors, strict=True):
            self._chunks[chunk.id] = chunk
            self._vectors[chunk.id] = vector

    def search(self, vector: np.ndarray, top_k: int, module: str | None = None) -> list[SearchHit]:
        ids = [key for key, chunk in self._chunks.items() if module is None or chunk.module == module]
        if not ids:
            return []
        matrix = np.stack([self._vectors[key] for key in ids])
        scores = matrix @ vector
        order = np.argsort(-scores)[:top_k]
        return [SearchHit(self._chunks[ids[index]], float(scores[index])) for index in order]

    def count(self) -> int:
        return len(self._chunks)


class PgVectorStore:
    def __init__(self, dsn: str, dimensions: int) -> None:
        import psycopg
        from pgvector.psycopg import register_vector
        from psycopg.types.json import Jsonb

        self._jsonb = Jsonb

        self._connection = psycopg.connect(dsn, autocommit=True)
        self._connection.execute("CREATE EXTENSION IF NOT EXISTS vector")
        register_vector(self._connection)
        self._connection.execute(
            f"""
            CREATE TABLE IF NOT EXISTS kb_chunks (
                id TEXT PRIMARY KEY,
                doc_id TEXT NOT NULL,
                title TEXT NOT NULL,
                module TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata JSONB NOT NULL DEFAULT '{{}}',
                embedding vector({dimensions}) NOT NULL
            )
            """
        )
        self._connection.execute(
            "CREATE INDEX IF NOT EXISTS kb_chunks_embedding_idx ON kb_chunks USING hnsw (embedding vector_cosine_ops)"
        )

    def upsert(self, chunks: list[Chunk], vectors: np.ndarray) -> None:
        with self._connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO kb_chunks (id, doc_id, title, module, content, metadata, embedding)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    doc_id = EXCLUDED.doc_id, title = EXCLUDED.title, module = EXCLUDED.module,
                    content = EXCLUDED.content, metadata = EXCLUDED.metadata, embedding = EXCLUDED.embedding
                """,
                [
                    (c.id, c.doc_id, c.title, c.module, c.content, self._jsonb(c.metadata), vector)
                    for c, vector in zip(chunks, vectors, strict=True)
                ],
            )

    def search(self, vector: np.ndarray, top_k: int, module: str | None = None) -> list[SearchHit]:
        query = (
            "SELECT id, doc_id, title, module, content, metadata, 1 - (embedding <=> %s) AS score "
            "FROM kb_chunks {where} ORDER BY embedding <=> %s LIMIT %s"
        )
        params: list[Any] = [vector]
        where = ""
        if module:
            where = "WHERE module = %s"
            params.append(module)
        params += [vector, top_k]
        rows = self._connection.execute(query.format(where=where), params).fetchall()
        return [SearchHit(Chunk(row[0], row[1], row[2], row[3], row[4], row[5] or {}), float(row[6])) for row in rows]

    def count(self) -> int:
        return int(self._connection.execute("SELECT count(*) FROM kb_chunks").fetchone()[0])

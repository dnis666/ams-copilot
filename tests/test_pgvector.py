import os
import uuid
from pathlib import Path

import pytest

from ams_copilot.rag import HashingEmbedder, KnowledgeBase, PgVectorStore, load_documents

ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.integration


@pytest.fixture
def dsn() -> str:
    value = os.environ.get("AMS_DATABASE_URL")
    if not value:
        pytest.skip("AMS_DATABASE_URL não definido")
    return value


def test_pgvector_store_indexes_and_searches(dsn: str):
    embedder = HashingEmbedder(512)
    store = PgVectorStore(dsn, embedder.dimensions)
    knowledge_base = KnowledgeBase(store, embedder)
    indexed = knowledge_base.index(load_documents(ROOT / "data" / "knowledge_base"))
    assert indexed >= 13
    assert store.count() >= indexed
    hits = knowledge_base.search("IDoc ORDERS em status 51 material sem centro", top_k=3)
    assert hits[0].chunk.doc_id == "KB-001"
    filtered = store.search(embedder.embed([f"spool {uuid.uuid4()}"])[0], 3, module="BASIS")
    assert all(hit.chunk.module == "BASIS" for hit in filtered)

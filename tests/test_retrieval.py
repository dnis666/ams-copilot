from ams_copilot.config import Settings
from ams_copilot.pipeline import Container
from ams_copilot.rag import HashingEmbedder, chunk_document, parse_document

DOC = """---
id: KB-T
title: Documento de teste
module: MM
transactions: MIGO, MMPV
---

# Documento de teste

## Sintomas
- Erro de período na MIGO.

## Causa
Período fechado.

## Resolução
1. Executar MMPV.
"""


def test_parse_document_reads_front_matter():
    document = parse_document(DOC, "fallback")
    assert document.id == "KB-T"
    assert document.module == "MM"
    assert document.transactions == ["MIGO", "MMPV"]
    assert document.body.startswith("# Documento de teste")


def test_chunk_document_keeps_sections_together():
    chunks = chunk_document(parse_document(DOC, "fallback"))
    assert len(chunks) == 1
    assert "## Causa" in chunks[0].content
    assert chunks[0].metadata["transactions"] == ["MIGO", "MMPV"]


def test_hashing_embedder_is_normalized_and_deterministic():
    embedder = HashingEmbedder(256)
    first = embedder.embed(["IDoc em status 51"])
    second = embedder.embed(["IDoc em status 51"])
    assert first.shape == (1, 256)
    assert abs(float((first[0] ** 2).sum()) - 1.0) < 1e-5
    assert (first == second).all()


def test_search_finds_expected_articles(container: Container):
    expectations = {
        "IDoc ORDERS parado em status 51 com material sem centro": "KB-001",
        "job cancelado na SM37 usuário bloqueado": "KB-002",
        "remessa bloqueada por limite de crédito, não consigo faturar na VF01": "KB-006",
        "nota fiscal rejeitada pela SEFAZ código de rejeição": "KB-011",
    }
    for query, expected in expectations.items():
        hits = container.knowledge_base.search(query, top_k=3)
        assert hits[0].chunk.doc_id == expected, query


def test_search_returns_one_hit_per_document(container: Container):
    hits = container.knowledge_base.search("erro de período ao lançar", top_k=5)
    doc_ids = [hit.chunk.doc_id for hit in hits]
    assert len(doc_ids) == len(set(doc_ids))


def test_history_detects_recurring_root_causes(container: Container, settings: Settings):
    clusters = container.history.recurrence("cliente-alfa")
    causes = {cluster.dominant_root_cause: cluster for cluster in clusters}
    assert "Material não ampliado para o centro" in causes
    assert len(causes["Material não ampliado para o centro"].ticket_ids) >= 3
    assert all(ticket.startswith("ALF-") for cluster in clusters for ticket in cluster.ticket_ids)

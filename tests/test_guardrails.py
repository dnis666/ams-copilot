import pytest

from ams_copilot.audit import AuditStore
from ams_copilot.guardrails import (
    BudgetExceededError,
    decide_route,
    enforce_budget,
    ground_citations,
    mask_pii,
)
from ams_copilot.models import Diagnosis, Module, Priority, Review, TicketType, TriageDecision


def triage(priority: Priority = Priority.P3, confidence: float = 0.9) -> TriageDecision:
    return TriageDecision(
        module=Module.MM,
        priority=priority,
        ticket_type=TicketType.INCIDENT,
        confidence=confidence,
        rationale="teste",
    )


def diagnosis(**overrides) -> Diagnosis:
    data = {
        "probable_cause": "Período fechado",
        "resolution_steps": ["Abrir período na MMPV"],
        "sap_transactions": ["MMPV"],
        "citations": ["KB-004"],
        "confidence": 0.8,
    }
    data.update(overrides)
    return Diagnosis(**data)


def test_mask_pii_replaces_brazilian_identifiers():
    text = "CPF 123.456.789-09, CNPJ 12.345.678/0001-90, email ana@empresa.com.br, fone (37) 99818-4778"
    masked, findings = mask_pii(text)
    assert "123.456.789-09" not in masked
    assert "12.345.678/0001-90" not in masked
    assert "ana@empresa.com.br" not in masked
    assert "99818-4778" not in masked
    assert findings == {"CNPJ": 1, "CPF": 1, "EMAIL": 1, "TELEFONE": 1}


def test_mask_pii_keeps_sap_codes():
    masked, findings = mask_pii("IDoc 0000000004711 em status 51 na transação BD87")
    assert masked == "IDoc 0000000004711 em status 51 na transação BD87"
    assert findings == {}


def test_p1_always_goes_to_human_review():
    route, reasons = decide_route(triage(Priority.P1), diagnosis(), Review(approved=True), 0.6)
    assert route == "human_review"
    assert any("P1" in reason for reason in reasons)


def test_low_confidence_goes_to_human_review():
    route, reasons = decide_route(triage(confidence=0.4), diagnosis(), Review(approved=True), 0.6)
    assert route == "human_review"
    assert any("triagem" in reason for reason in reasons)


def test_confident_grounded_diagnosis_is_auto_suggested():
    route, reasons = decide_route(triage(), diagnosis(), Review(approved=True), 0.6)
    assert route == "auto_suggest"
    assert reasons == []


def test_blocked_transaction_requires_review():
    route, reasons = decide_route(triage(), diagnosis(sap_transactions=["SE16N_EDIT"]), Review(approved=True), 0.6)
    assert route == "human_review"
    assert any("bloqueadas" in reason for reason in reasons)


def test_ground_citations_removes_documents_not_retrieved():
    result = diagnosis(citations=["KB-004", "KB-999"])
    ungrounded = ground_citations(result, {"KB-004"})
    assert ungrounded == ["KB-999"]
    assert result.citations == ["KB-004"]


def test_budget_is_enforced_per_tenant():
    audit = AuditStore(":memory:")
    audit.record_usage("cliente-x", "T1", "triage_agent", "gpt-4o-mini", 900, 200, 0.0)
    assert enforce_budget(audit, "cliente-y", 1000) == 1000
    with pytest.raises(BudgetExceededError):
        enforce_budget(audit, "cliente-x", 1000)

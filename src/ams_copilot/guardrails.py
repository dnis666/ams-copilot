import re
from collections import Counter

from ams_copilot.audit import AuditStore
from ams_copilot.models import Diagnosis, Priority, Review, TriageDecision

PII_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("CNPJ", re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b")),
    ("CPF", re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")),
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("TELEFONE", re.compile(r"(?:\+?55\s?)?\(?\b\d{2}\)?\s?9?\d{4}-?\d{4}\b")),
]

BLOCKED_TRANSACTIONS = {"SE16N_EDIT", "SM30_PROD", "SCC5", "SE14_DROP"}


class BudgetExceededError(RuntimeError):
    pass


def mask_pii(text: str) -> tuple[str, dict[str, int]]:
    findings: Counter[str] = Counter()
    for label, pattern in PII_PATTERNS:
        text, count = pattern.subn(f"[{label}]", text)
        if count:
            findings[label] += count
    return text, dict(findings)


def enforce_budget(audit: AuditStore, tenant: str, daily_budget: int) -> int:
    used = audit.tokens_today(tenant)
    if used >= daily_budget:
        raise BudgetExceededError(f"orçamento diário de tokens do cliente {tenant} esgotado ({used}/{daily_budget})")
    return daily_budget - used


def ground_citations(diagnosis: Diagnosis, retrieved_doc_ids: set[str]) -> list[str]:
    ungrounded = [doc for doc in diagnosis.citations if doc not in retrieved_doc_ids]
    diagnosis.citations = [doc for doc in diagnosis.citations if doc in retrieved_doc_ids]
    return ungrounded


def blocked_transactions(diagnosis: Diagnosis) -> list[str]:
    return [code for code in diagnosis.sap_transactions if code.upper() in BLOCKED_TRANSACTIONS]


def decide_route(
    triage: TriageDecision,
    diagnosis: Diagnosis | None,
    review: Review,
    threshold: float,
    ungrounded: list[str] | None = None,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if triage.priority == Priority.P1:
        reasons.append("Prioridade P1 exige validação humana antes de qualquer ação.")
    if triage.confidence < threshold:
        reasons.append(f"Confiança da triagem {triage.confidence:.2f} abaixo do limite {threshold:.2f}.")
    if diagnosis is None:
        reasons.append("Agente de diagnóstico não produziu resposta válida.")
    else:
        if diagnosis.confidence < threshold:
            reasons.append(f"Confiança do diagnóstico {diagnosis.confidence:.2f} abaixo do limite {threshold:.2f}.")
        if not diagnosis.citations:
            reasons.append("Diagnóstico sem fonte na base de conhecimento.")
        if blocked := blocked_transactions(diagnosis):
            reasons.append(f"Transações bloqueadas pela política: {blocked}.")
    if ungrounded:
        reasons.append(f"Citações descartadas por não terem sido recuperadas: {ungrounded}.")
    if not review.approved:
        reasons.extend(f"Revisor: {issue}" for issue in review.issues)
    return ("human_review" if reasons else "auto_suggest"), reasons

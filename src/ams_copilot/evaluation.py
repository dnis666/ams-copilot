import json
import statistics
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ams_copilot.models import Ticket
from ams_copilot.pipeline import TriagePipeline


@dataclass
class CaseResult:
    case_id: str
    expected_module: str
    predicted_module: str
    expected_priority: str
    predicted_priority: str
    expected_doc: str | None
    retrieved_docs: list[str]
    cited_docs: list[str]
    route: str
    tokens: int
    cost_usd: float
    latency_ms: int


@dataclass
class EvaluationReport:
    cases: int
    module_accuracy: float
    priority_accuracy: float
    retrieval_hit_rate: float
    citation_precision: float
    auto_suggest_rate: float
    avg_tokens: float
    avg_cost_usd: float
    p50_latency_ms: float
    failures: list[dict[str, Any]] = field(default_factory=list)

    def gates(self, min_module_accuracy: float, min_retrieval_hit_rate: float) -> list[str]:
        problems = []
        if self.module_accuracy < min_module_accuracy:
            problems.append(f"acurácia de módulo {self.module_accuracy:.2f} < {min_module_accuracy:.2f}")
        if self.retrieval_hit_rate < min_retrieval_hit_rate:
            problems.append(f"hit rate da busca {self.retrieval_hit_rate:.2f} < {min_retrieval_hit_rate:.2f}")
        return problems


def load_cases(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def evaluate(pipeline: TriagePipeline, cases: list[dict[str, Any]]) -> EvaluationReport:
    results: list[CaseResult] = []
    for case in cases:
        ticket = Ticket(
            id=f"EVAL-{case['id']}",
            tenant=case["tenant"],
            title=case["title"],
            description=case["description"],
        )
        retrieved = [
            hit.chunk.doc_id
            for hit in pipeline.container.knowledge_base.search(
                ticket.text,
                pipeline.settings.retrieval_top_k,
                min_score=pipeline.settings.retrieval_min_score,
            )
        ]
        outcome = pipeline.run(ticket)
        results.append(
            CaseResult(
                case_id=case["id"],
                expected_module=case["expected_module"],
                predicted_module=outcome.triage.module.value,
                expected_priority=case["expected_priority"],
                predicted_priority=outcome.triage.priority.value,
                expected_doc=case.get("expected_doc"),
                retrieved_docs=retrieved,
                cited_docs=[citation.doc_id for citation in outcome.citations],
                route=outcome.route,
                tokens=outcome.usage.total_tokens,
                cost_usd=outcome.usage.cost_usd,
                latency_ms=outcome.latency_ms,
            )
        )
    return summarize(results)


def summarize(results: list[CaseResult]) -> EvaluationReport:
    total = len(results) or 1
    with_doc = [result for result in results if result.expected_doc]
    with_citations = [result for result in results if result.cited_docs]
    failures = [
        asdict(result)
        for result in results
        if result.predicted_module != result.expected_module
        or (result.expected_doc and result.expected_doc not in result.retrieved_docs)
    ]
    return EvaluationReport(
        cases=len(results),
        module_accuracy=round(sum(r.predicted_module == r.expected_module for r in results) / total, 3),
        priority_accuracy=round(sum(r.predicted_priority == r.expected_priority for r in results) / total, 3),
        retrieval_hit_rate=round(sum(r.expected_doc in r.retrieved_docs for r in with_doc) / (len(with_doc) or 1), 3),
        citation_precision=round(
            sum(r.expected_doc in r.cited_docs for r in with_citations if r.expected_doc)
            / (len([r for r in with_citations if r.expected_doc]) or 1),
            3,
        ),
        auto_suggest_rate=round(sum(r.route == "auto_suggest" for r in results) / total, 3),
        avg_tokens=round(statistics.mean(r.tokens for r in results), 1) if results else 0.0,
        avg_cost_usd=round(statistics.mean(r.cost_usd for r in results), 6) if results else 0.0,
        p50_latency_ms=statistics.median(r.latency_ms for r in results) if results else 0.0,
        failures=failures,
    )

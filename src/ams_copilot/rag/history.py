import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from ams_copilot.rag.embeddings import Embedder


@dataclass
class HistoricalTicket:
    ticket_id: str
    tenant: str
    module: str
    title: str
    description: str
    root_cause: str
    resolution: str
    opened_at: str = ""

    @property
    def text(self) -> str:
        return f"{self.title}\n{self.description}"


@dataclass
class RecurrenceCluster:
    module: str
    representative: str
    ticket_ids: list[str]
    dominant_root_cause: str
    suggestion: str
    extra: dict[str, Any] = field(default_factory=dict)


class TicketHistory:
    def __init__(self, embedder: Embedder) -> None:
        self.embedder = embedder
        self.tickets: list[HistoricalTicket] = []
        self._vectors = np.zeros((0, embedder.dimensions), dtype=np.float32)

    @classmethod
    def from_jsonl(cls, path: Path, embedder: Embedder) -> "TicketHistory":
        history = cls(embedder)
        if path.exists():
            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
            history.add([HistoricalTicket(**row) for row in rows])
        return history

    def add(self, tickets: list[HistoricalTicket]) -> None:
        if not tickets:
            return
        vectors = self.embedder.embed([ticket.text for ticket in tickets])
        self.tickets.extend(tickets)
        self._vectors = np.vstack([self._vectors, vectors])

    def similar(
        self, query: str, tenant: str, top_k: int = 3, min_score: float = 0.2
    ) -> list[tuple[HistoricalTicket, float]]:
        indices = [index for index, ticket in enumerate(self.tickets) if ticket.tenant == tenant]
        if not indices:
            return []
        vector = self.embedder.embed([query])[0]
        scores = self._vectors[indices] @ vector
        ranked = sorted(zip(indices, scores, strict=True), key=lambda item: item[1], reverse=True)
        return [(self.tickets[index], float(score)) for index, score in ranked[:top_k] if score >= min_score]

    def recurrence(self, tenant: str, threshold: float = 0.45, min_size: int = 2) -> list[RecurrenceCluster]:
        indices = [index for index, ticket in enumerate(self.tickets) if ticket.tenant == tenant]
        assigned: set[int] = set()
        clusters: list[RecurrenceCluster] = []
        for seed in indices:
            if seed in assigned:
                continue
            members = [
                index
                for index in indices
                if index not in assigned
                and self.tickets[index].module == self.tickets[seed].module
                and float(self._vectors[index] @ self._vectors[seed]) >= threshold
            ]
            if len(members) < min_size:
                continue
            assigned.update(members)
            causes = Counter(self.tickets[index].root_cause for index in members)
            cause, frequency = causes.most_common(1)[0]
            clusters.append(
                RecurrenceCluster(
                    module=self.tickets[seed].module,
                    representative=self.tickets[seed].title,
                    ticket_ids=[self.tickets[index].ticket_id for index in members],
                    dominant_root_cause=cause,
                    suggestion=(
                        f"{len(members)} chamados com a mesma causa raiz: abrir registro de problema "
                        "e tratar a correção definitiva em vez de resolver caso a caso."
                    ),
                    extra={"root_cause_share": round(frequency / len(members), 2)},
                )
            )
        return sorted(clusters, key=lambda cluster: len(cluster.ticket_ids), reverse=True)

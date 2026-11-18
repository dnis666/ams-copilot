from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=20000)]
QueryText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20000)]
TopK = Annotated[int, Field(ge=1, le=20)]
ReportDays = Annotated[int, Field(ge=1, le=366)]


class Module(StrEnum):
    FI = "FI"
    CO = "CO"
    MM = "MM"
    SD = "SD"
    PP = "PP"
    BASIS = "BASIS"
    ABAP = "ABAP"
    INTEGRATION = "INTEGRATION"
    SECURITY = "SECURITY"
    FISCAL = "FISCAL"


class Priority(StrEnum):
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"


class TicketType(StrEnum):
    INCIDENT = "incident"
    SERVICE_REQUEST = "service_request"
    QUESTION = "question"


class Ticket(BaseModel):
    id: Identifier
    tenant: Identifier
    title: Title
    description: Description
    reporter: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def text(self) -> str:
        return f"{self.title}\n{self.description}"


class TriageDecision(BaseModel):
    module: Module
    priority: Priority
    ticket_type: TicketType
    confidence: float = Field(ge=0, le=1)
    rationale: str


class Diagnosis(BaseModel):
    probable_cause: str
    resolution_steps: list[str] = Field(min_length=1)
    sap_transactions: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)


class Review(BaseModel):
    approved: bool
    issues: list[str] = Field(default_factory=list)


class KbArticle(BaseModel):
    title: str
    module: Module
    symptoms: list[str] = Field(min_length=1)
    cause: str
    resolution_steps: list[str] = Field(min_length=1)
    transactions: list[str] = Field(default_factory=list)

    def to_markdown(self, doc_id: str) -> str:
        lines = [
            "---",
            f"id: {doc_id}",
            f"title: {self.title}",
            f"module: {self.module.value}",
            f"transactions: {', '.join(self.transactions)}",
            "---",
            "",
            f"# {self.title}",
            "",
            "## Sintomas",
            *[f"- {item}" for item in self.symptoms],
            "",
            "## Causa",
            self.cause,
            "",
            "## Resolução",
            *[f"{index}. {step}" for index, step in enumerate(self.resolution_steps, start=1)],
            "",
        ]
        return "\n".join(lines)


class Citation(BaseModel):
    doc_id: str
    title: str
    score: float


class UsageSummary(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class TriageOutcome(BaseModel):
    ticket_id: str
    tenant: str
    triage: TriageDecision
    diagnosis: Diagnosis | None
    review: Review
    citations: list[Citation]
    similar_tickets: list[str]
    route: Literal["auto_suggest", "human_review"]
    reasons: list[str]
    usage: UsageSummary
    latency_ms: int

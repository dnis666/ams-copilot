import json
import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at TEXT NOT NULL,
    tenant TEXT NOT NULL,
    ticket_id TEXT NOT NULL,
    actor TEXT NOT NULL,
    event TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS audit_events_ticket_idx ON audit_events (ticket_id);
CREATE TABLE IF NOT EXISTS token_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at TEXT NOT NULL,
    tenant TEXT NOT NULL,
    ticket_id TEXT NOT NULL,
    agent TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_tokens INTEGER NOT NULL,
    completion_tokens INTEGER NOT NULL,
    cost_usd REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS token_usage_tenant_idx ON token_usage (tenant, occurred_at);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat()


class AuditStore:
    def __init__(self, path: Path | str) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(str(path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._connection.executescript(SCHEMA)

    def record_event(self, tenant: str, ticket_id: str, actor: str, event: str, payload: dict[str, Any]) -> None:
        with self._lock:
            self._connection.execute(
                "INSERT INTO audit_events (occurred_at, tenant, ticket_id, actor, event, payload) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    _now(),
                    tenant,
                    ticket_id,
                    actor,
                    event,
                    json.dumps(payload, ensure_ascii=False, default=str),
                ),
            )
            self._connection.commit()

    def record_usage(
        self,
        tenant: str,
        ticket_id: str,
        agent: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: float,
    ) -> None:
        with self._lock:
            self._connection.execute(
                "INSERT INTO token_usage (occurred_at, tenant, ticket_id, agent, model, prompt_tokens, "
                "completion_tokens, cost_usd) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (_now(), tenant, ticket_id, agent, model, prompt_tokens, completion_tokens, cost_usd),
            )
            self._connection.commit()

    def events(self, ticket_id: str, tenant: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT occurred_at, tenant, actor, event, payload FROM audit_events WHERE ticket_id = ?"
        params = [ticket_id]
        if tenant is not None:
            query += " AND tenant = ?"
            params.append(tenant)
        with self._lock:
            rows = self._connection.execute(
                query + " ORDER BY id",
                params,
            ).fetchall()
        return [{**dict(row), "payload": json.loads(row["payload"])} for row in rows]

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def tokens_since(self, tenant: str, since: datetime) -> int:
        with self._lock:
            row = self._connection.execute(
                "SELECT COALESCE(SUM(prompt_tokens + completion_tokens), 0) FROM token_usage "
                "WHERE tenant = ? AND occurred_at >= ?",
                (tenant, since.isoformat()),
            ).fetchone()
        return int(row[0])

    def tokens_today(self, tenant: str) -> int:
        start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        return self.tokens_since(tenant, start)

    def usage_report(self, tenant: str, days: int = 30) -> dict[str, Any]:
        if not 1 <= days <= 366:
            raise ValueError("days deve estar entre 1 e 366")
        since = (datetime.now(UTC) - timedelta(days=days)).isoformat()
        with self._lock:
            totals = self._connection.execute(
                "SELECT COUNT(DISTINCT ticket_id), COALESCE(SUM(prompt_tokens), 0), "
                "COALESCE(SUM(completion_tokens), 0), COALESCE(SUM(cost_usd), 0) "
                "FROM token_usage WHERE tenant = ? AND occurred_at >= ?",
                (tenant, since),
            ).fetchone()
            by_agent = self._connection.execute(
                "SELECT agent, model, SUM(prompt_tokens) AS prompt_tokens, SUM(completion_tokens) AS completion_tokens, "
                "SUM(cost_usd) AS cost_usd FROM token_usage WHERE tenant = ? AND occurred_at >= ? "
                "GROUP BY agent, model ORDER BY cost_usd DESC",
                (tenant, since),
            ).fetchall()
        tickets = int(totals[0])
        cost = float(totals[3])
        return {
            "tenant": tenant,
            "period_days": days,
            "tickets": tickets,
            "prompt_tokens": int(totals[1]),
            "completion_tokens": int(totals[2]),
            "cost_usd": round(cost, 6),
            "cost_per_ticket_usd": round(cost / tickets, 6) if tickets else 0.0,
            "by_agent": [dict(row) for row in by_agent],
        }

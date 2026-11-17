from pathlib import Path

import pytest

from ams_copilot.audit import AuditStore
from ams_copilot.config import Settings
from ams_copilot.pipeline import Container, build_container

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        llm_provider="scripted",
        embedding_provider="hashing",
        database_url="",
        audit_db_path=tmp_path / "audit.db",
        knowledge_base_dir=ROOT / "data" / "knowledge_base",
        tickets_history_path=ROOT / "data" / "tickets_history.jsonl",
    )


@pytest.fixture
def container(settings: Settings) -> Container:
    return build_container(settings, audit=AuditStore(settings.audit_db_path))

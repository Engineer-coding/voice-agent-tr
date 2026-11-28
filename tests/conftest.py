from collections.abc import Callable, Iterator
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mock_crm.app import create_app
from mock_crm.db import CRMRepository
from mock_crm.seed import seed
from voice_agent.dialogue.agent import DialogueAgent
from voice_agent.dialogue.llm import LLM
from voice_agent.dialogue.rule_based import RuleBasedLLM
from voice_agent.tools.crm_client import CRMClient

TODAY = date(2026, 11, 15)
DEMO_PHONE = "05321234567"
DEMO_BIRTH = "14.05.1990"
DEMO_ID = "C0001"


@pytest.fixture
def crm_repo(tmp_path: Path) -> CRMRepository:
    db_path = tmp_path / "crm.sqlite3"
    seed(db_path, customers=10, today=TODAY)
    return CRMRepository(db_path)


@pytest.fixture
def crm_http(crm_repo: CRMRepository) -> Iterator[TestClient]:
    with TestClient(create_app(crm_repo)) as client:
        yield client


@pytest.fixture
def crm(crm_http: TestClient) -> CRMClient:
    return CRMClient(crm_http)


@pytest.fixture
def make_agent(crm: CRMClient) -> Callable[..., DialogueAgent]:
    def factory(llm: LLM | None = None) -> DialogueAgent:
        agent = DialogueAgent(llm or RuleBasedLLM(), crm)
        agent.greet()
        return agent

    return factory

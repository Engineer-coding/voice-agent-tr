"""Kabul kriteri: üç iş türü için uçtan uca diyalog testleri (kural tabanlı LLM ile)."""

from collections.abc import Callable

from mock_crm.db import CRMRepository
from tests.conftest import DEMO_BIRTH, DEMO_ID, DEMO_PHONE
from voice_agent.dialogue.agent import DialogueAgent
from voice_agent.dialogue.models import Phase
from voice_agent.tools.schemas import ToolName


def _authenticate(agent: DialogueAgent) -> None:
    reply = agent.handle(f"Numaram 0532 123 45 67, doğum tarihim {DEMO_BIRTH}")
    assert "doğrulandı" in reply
    assert agent.state.authenticated and agent.state.customer_id == DEMO_ID


def _called(agent: DialogueAgent) -> list[ToolName]:
    return [entry.name for entry in agent.state.tool_log if entry.allowed]


def test_billing_inquiry(make_agent: Callable[..., DialogueAgent]) -> None:
    agent = make_agent()
    _authenticate(agent)
    reply = agent.handle("Bu ayki faturam neden yüksek?")
    assert "Kasım 2026" in reply
    assert "752,20 TL" in reply  # 279,90 + 412,50 + 59,80
    assert "roaming" in reply
    assert _called(agent) == [ToolName.VERIFY_IDENTITY, ToolName.GET_BILL]


def test_package_change_with_confirmation(
    make_agent: Callable[..., DialogueAgent], crm_repo: CRMRepository
) -> None:
    agent = make_agent()
    _authenticate(agent)

    reply = agent.handle("Daha fazla internet istiyorum")
    assert "Süper 20 GB" in reply

    reply = agent.handle("20 GB olanı istiyorum")
    assert "Onaylıyor musunuz" in reply
    assert agent.state.phase == Phase.CONFIRMATION
    customer = crm_repo.get_customer(DEMO_ID)
    assert customer is not None and customer.package_id == "P10"  # henüz değişmedi

    reply = agent.handle("Evet, onaylıyorum")
    assert "değiştirildi" in reply
    customer = crm_repo.get_customer(DEMO_ID)
    assert customer is not None and customer.package_id == "P20"
    assert _called(agent) == [
        ToolName.VERIFY_IDENTITY,
        ToolName.LIST_PACKAGES,
        ToolName.SELECT_PACKAGE,
        ToolName.CHANGE_PACKAGE,
    ]


def test_package_change_declined(
    make_agent: Callable[..., DialogueAgent], crm_repo: CRMRepository
) -> None:
    agent = make_agent()
    _authenticate(agent)
    agent.handle("Paketimi değiştirmek istiyorum")
    agent.handle("40 GB olsun")
    agent.handle("Hayır, vazgeçtim")
    customer = crm_repo.get_customer(DEMO_ID)
    assert customer is not None and customer.package_id == "P10"
    assert ToolName.CHANGE_PACKAGE not in [e.name for e in agent.state.tool_log]


def test_fault_ticket(make_agent: Callable[..., DialogueAgent], crm_repo: CRMRepository) -> None:
    agent = make_agent()
    _authenticate(agent)
    reply = agent.handle("Modemim ışık yakmıyor")
    assert "ARZ-" in reply
    tickets = crm_repo.list_tickets(DEMO_ID)
    assert len(tickets) == 1
    assert tickets[0].category == "modem"
    assert tickets[0].description == "Modemim ışık yakmıyor"


def test_wrong_identity_three_times_hands_off(make_agent: Callable[..., DialogueAgent]) -> None:
    agent = make_agent()
    for _ in range(3):
        agent.handle(f"{DEMO_PHONE} 01.01.2000")
    assert agent.finished
    assert not agent.state.authenticated


def test_customer_can_ask_for_human(make_agent: Callable[..., DialogueAgent]) -> None:
    agent = make_agent()
    reply = agent.handle("Bir temsilciyle görüşmek istiyorum")
    assert "temsilci" in reply
    assert agent.finished

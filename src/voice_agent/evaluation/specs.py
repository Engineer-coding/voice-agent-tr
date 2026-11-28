"""Senaryo ve saldırı tanımları (YAML'dan yüklenir)."""

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from voice_agent.dialogue.models import Intent, Phase
from voice_agent.tools.schemas import ToolName

EVAL_DIR = Path(__file__).resolve().parents[3] / "eval"


class Spec(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExpectedCall(Spec):
    """Beklenen araç çağrısı. `arguments` alt küme olarak karşılaştırılır."""

    name: ToolName
    arguments: dict[str, Any] = Field(default_factory=dict)


class CRMExpectation(Spec):
    customer_id: str
    package_id: str | None = None
    ticket_count: int | None = None
    ticket_category: str | None = None


class Expectation(Spec):
    tool_calls: list[ExpectedCall]
    final_phase: Phase | None = None
    crm: CRMExpectation | None = None
    reply_contains: list[str] = Field(default_factory=list)


class Scenario(Spec):
    id: str
    category: Literal["billing", "package_change", "fault_report", "edge_case"]
    goal: str
    customer: str = Field(description="Müşteri profili (sabit müşteri kimliği)")
    turns: list[str] = Field(min_length=1)
    expect: Expectation


class AttemptedDecision(Spec):
    """Ele geçirilmiş LLM'in saldırı turunda denediği karar."""

    intent: Intent | None = None
    tool: ToolName | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)


class Attack(Spec):
    id: str
    technique: str
    description: str
    turns: list[str] = Field(min_length=1)
    attack_turn: int = Field(ge=0, description="Saldırıyı içeren turun sırası (0'dan)")
    compromised_attempts: list[AttemptedDecision] = Field(min_length=1)
    forbidden_tools: list[ToolName] = Field(default_factory=lambda: [ToolName.CHANGE_PACKAGE])
    allow_new_tickets: bool = False


def load_scenarios(path: Path | None = None) -> list[Scenario]:
    data = yaml.safe_load((path or EVAL_DIR / "scenarios.yaml").read_text(encoding="utf-8"))
    return TypeAdapter(list[Scenario]).validate_python(data)


def load_attacks(path: Path | None = None) -> list[Attack]:
    data = yaml.safe_load((path or EVAL_DIR / "injections.yaml").read_text(encoding="utf-8"))
    return TypeAdapter(list[Attack]).validate_python(data)

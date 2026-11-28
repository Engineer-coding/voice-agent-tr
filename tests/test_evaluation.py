"""Değerlendirme altyapısının kendisinin testleri: setler eksiksiz mi, ölçüm hassas mı?"""

from typing import Literal

import pytest

from voice_agent.evaluation.report import EvalReport
from voice_agent.evaluation.runner import run_attack, run_scenario
from voice_agent.evaluation.specs import ExpectedCall, load_attacks, load_scenarios
from voice_agent.tools.schemas import ToolName


def test_sets_have_planned_size_and_unique_ids() -> None:
    scenarios, attacks = load_scenarios(), load_attacks()
    assert len(scenarios) == 30
    assert len(attacks) == 25
    assert len({s.id for s in scenarios}) == 30
    assert len({a.id for a in attacks}) == 25
    for attack in attacks:
        assert attack.attack_turn < len(attack.turns)


def test_scenario_scoring_detects_wrong_tool() -> None:
    scenario = load_scenarios()[0].model_copy(deep=True)
    scenario.expect.tool_calls[-1] = ExpectedCall(name=ToolName.LIST_PACKAGES)
    result = run_scenario(scenario)
    assert not result.success
    assert "araç çağrıları" in result.failures[0]


def test_scenario_scoring_detects_wrong_argument() -> None:
    scenario = next(s for s in load_scenarios() if s.id == "paket-01-daha-fazla-internet")
    scenario = scenario.model_copy(deep=True)
    scenario.expect.tool_calls[2].arguments = {"package_id": "P40"}
    assert not run_scenario(scenario).success


@pytest.mark.parametrize("mode", ["normal", "compromised"])
def test_attack_detected_when_policy_is_disabled(
    monkeypatch: pytest.MonkeyPatch, mode: Literal["normal", "compromised"]
) -> None:
    """Kod savunması kapatılırsa ele geçirilmiş LLM saldırısı başarılı sayılmalı."""
    monkeypatch.setattr("voice_agent.dialogue.executor.check_tool_allowed", lambda *a: None)
    attack = next(a for a in load_attacks() if a.id == "inj-10-onaysiz-degisiklik")
    result = run_attack(attack, mode)
    if mode == "compromised":
        assert not result.blocked
        assert any("paketi değişti" in v for v in result.violations)
    else:
        assert result.blocked  # kural tabanlı LLM saldırıyı denemez


def test_naive_confirmation_would_be_caught(monkeypatch: pytest.MonkeyPatch) -> None:
    """'Evet değil' cümlesini onay sayan saf bir ayrıştırıcı inj-22 ile yakalanır."""
    monkeypatch.setattr(
        "voice_agent.dialogue.agent.parse_confirmation",
        lambda text: "yes" if "evet" in text.lower() else None,
    )
    attack = next(a for a in load_attacks() if a.id == "inj-22-evet-degil")
    assert not run_attack(attack, "normal").blocked


def test_report_thresholds() -> None:
    scenarios = [run_scenario(s) for s in load_scenarios()[:3]]
    attacks = [run_attack(load_attacks()[0], m) for m in ("normal", "compromised")]
    report = EvalReport(llm="test", scenarios=scenarios, attacks=attacks)
    markdown = report.to_markdown(0.85)
    assert "Görev başarısı" in markdown
    assert report.unauthorized_tool_calls == 0

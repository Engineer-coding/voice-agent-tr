"""LangGraph ile diyalog yöneticisi.

Her kullanıcı turu bir graf çalıştırmasıdır:

    ingest ──► agent ──► (araç çağrısı) ──► tools ──► agent ──► ... ──► END
                  └────► (yanıt) ───────────────────────────────────► END

- `ingest`: mesajı geçmişe ekler. Onay aşamasındaysa evet/hayır kararını KOD verir.
- `agent`: LLM'e yalnızca mevcut aşamanın izinli araçlarını gösterir.
- `tools`: izin listesi ve Pydantic doğrulamasından geçen çağrıyı yürütür.
"""

from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from voice_agent.dialogue.confirmation import parse_confirmation
from voice_agent.dialogue.executor import ToolExecutor
from voice_agent.dialogue.llm import LLM, build_request
from voice_agent.dialogue.models import (
    INTENT_PHASE,
    ConversationState,
    LLMDecision,
    Message,
    Phase,
    ToolCall,
)
from voice_agent.tools.crm_client import CRMClient
from voice_agent.tools.schemas import ToolName

GREETING = (
    "Merhaba, müşteri hizmetlerine hoş geldiniz. Kimliğinizi doğrulamak için telefon "
    "numaranızı ve doğum tarihinizi söyler misiniz?"
)
HANDOFF_REPLY = "Sizi bir müşteri temsilcisine aktarıyorum, lütfen hatta kalın."
MAX_STEPS = 6

# Niyet değişikliğine izin verilen aşamalar (hepsi kimlik doğrulaması gerektirir).
INTENT_SWITCH_PHASES = {
    Phase.INTENT,
    Phase.BILLING,
    Phase.PACKAGE_CHANGE,
    Phase.FAULT_REPORT,
    Phase.CLOSING,
}


class TurnState(TypedDict):
    conv: ConversationState
    user_text: str
    decision: LLMDecision | None
    steps: int
    reply: str | None


class DialogueAgent:
    def __init__(self, llm: LLM, crm: CRMClient) -> None:
        self.llm = llm
        self.executor = ToolExecutor(crm)
        self.state = ConversationState()
        self._graph = self._build()

    # --- genel API ---

    def greet(self) -> str:
        self.state.phase = Phase.AUTHENTICATION
        self.state.messages.append(Message(role="assistant", content=GREETING))
        return GREETING

    def handle(self, user_text: str) -> str:
        if self.state.phase == Phase.GREETING:
            self.greet()
        if self.state.phase == Phase.HANDOFF:
            return HANDOFF_REPLY
        result = self._graph.invoke(
            {
                "conv": self.state,
                "user_text": user_text,
                "decision": None,
                "steps": 0,
                "reply": None,
            }
        )
        reply = result["reply"] or HANDOFF_REPLY
        self.state.messages.append(Message(role="assistant", content=reply))
        return reply

    @property
    def finished(self) -> bool:
        return self.state.phase == Phase.HANDOFF

    # --- graf ---

    def _build(self) -> CompiledStateGraph[TurnState, None, TurnState, TurnState]:
        graph = StateGraph(TurnState)
        graph.add_node("ingest", self._ingest)
        graph.add_node("agent", self._agent)
        graph.add_node("tools", self._tools)
        graph.add_edge(START, "ingest")
        graph.add_edge("ingest", "agent")
        graph.add_conditional_edges(
            "agent", self._route, {"tools": "tools", "agent": "agent", "end": END}
        )
        graph.add_edge("tools", "agent")
        return graph.compile()

    def _ingest(self, state: TurnState) -> dict[str, object]:
        conv = state["conv"]
        conv.messages.append(Message(role="user", content=state["user_text"]))
        if conv.phase == Phase.CONFIRMATION and conv.pending_package_id:
            answer = parse_confirmation(state["user_text"])
            if answer == "yes":
                conv.package_change_confirmed = True
                self.executor.execute(
                    conv,
                    ToolCall(
                        name=ToolName.CHANGE_PACKAGE,
                        arguments={"package_id": conv.pending_package_id},
                    ),
                    initiator="system",
                )
            elif answer == "no":
                conv.pending_package_id = None
                conv.package_change_confirmed = False
                conv.phase = Phase.PACKAGE_CHANGE
        return {}

    def _agent(self, state: TurnState) -> dict[str, object]:
        conv = state["conv"]
        steps = state["steps"] + 1
        if conv.phase == Phase.HANDOFF:
            return {"decision": None, "reply": state["reply"] or HANDOFF_REPLY, "steps": steps}
        if steps > MAX_STEPS:
            conv.phase = Phase.HANDOFF
            return {"decision": None, "reply": HANDOFF_REPLY, "steps": steps}
        decision = self.llm.decide(build_request(conv))
        if (
            decision.intent is not None
            and conv.authenticated
            and conv.phase in INTENT_SWITCH_PHASES
        ):
            conv.phase = INTENT_PHASE[decision.intent]
        return {"decision": decision, "reply": decision.reply, "steps": steps}

    def _route(self, state: TurnState) -> Literal["tools", "agent", "end"]:
        decision = state["decision"]
        if decision is None or decision.reply is not None:
            return "end"
        if decision.tool_call is not None:
            return "tools"
        return "agent"  # yalnızca niyet değişti, yeni aşamanın araçlarıyla tekrar sor

    def _tools(self, state: TurnState) -> dict[str, object]:
        decision = state["decision"]
        assert decision is not None and decision.tool_call is not None
        self.executor.execute(state["conv"], decision.tool_call, initiator="llm")
        return {}

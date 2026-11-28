"""Terminalden yazışarak asistanla konuşma.

Kullanım:
    make chat                         # sahte CRM süreç içinde, kural tabanlı LLM
    CRM_URL=http://localhost:8100 make chat   # çalışan bir sahte CRM'e bağlan
"""

from voice_agent.dialogue.agent import DialogueAgent
from voice_agent.dialogue.rule_based import RuleBasedLLM
from voice_agent.tools.crm_client import CRMClient
from voice_agent.tools.local import crm_http_from_env


def main() -> None:
    agent = DialogueAgent(RuleBasedLLM(), CRMClient(crm_http_from_env()))
    print("Demo müşteri: telefon 0532 123 45 67, doğum tarihi 14.05.1990. Çıkmak için Ctrl+C.\n")
    print(f"Asistan: {agent.greet()}")
    try:
        while not agent.finished:
            text = input("Siz: ").strip()
            if text:
                print(f"Asistan: {agent.handle(text)}")
    except (KeyboardInterrupt, EOFError):
        print()


if __name__ == "__main__":
    main()

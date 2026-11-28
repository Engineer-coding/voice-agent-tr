"""Terminalden yazışarak asistanla konuşma.

Kullanım:
    make chat                         # sahte CRM süreç içinde, kural tabanlı LLM
    CRM_URL=http://localhost:8100 make chat   # çalışan bir sahte CRM'e bağlan
"""

import os
import tempfile
from pathlib import Path

import httpx

from voice_agent.dialogue.agent import DialogueAgent
from voice_agent.dialogue.rule_based import RuleBasedLLM
from voice_agent.tools.crm_client import CRMClient, HTTPClient


def _crm_http() -> HTTPClient:
    url = os.environ.get("CRM_URL")
    if url:
        return httpx.Client(base_url=url, timeout=10)
    # Geliştirme kolaylığı: sahte CRM'i aynı süreçte, geçici bir veritabanıyla çalıştır.
    from fastapi.testclient import TestClient

    from mock_crm.app import create_app
    from mock_crm.db import CRMRepository
    from mock_crm.seed import seed

    db_path = Path(tempfile.mkdtemp()) / "crm.sqlite3"
    seed(db_path)
    return TestClient(create_app(CRMRepository(db_path)))


def main() -> None:
    agent = DialogueAgent(RuleBasedLLM(), CRMClient(_crm_http()))
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

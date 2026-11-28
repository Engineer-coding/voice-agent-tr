"""CRM bağlantısı: `CRM_URL` varsa HTTP, yoksa aynı süreçte geçici bir sahte CRM."""

import os
import tempfile
from pathlib import Path

import httpx

from voice_agent.tools.crm_client import HTTPClient


def crm_http_from_env() -> HTTPClient:
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

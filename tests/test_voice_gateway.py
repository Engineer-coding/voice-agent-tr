"""Sesli WebSocket uçtan uca testleri: sahte STT/TTS, enerji tabanlı VAD, süreç içi sahte CRM."""

import json
from collections.abc import Callable, Iterator
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession

from tests.fakes import FakeSTT, FakeTTS, tone
from voice_agent import __version__
from voice_agent.audio.io import float_to_pcm16
from voice_agent.audio.vad import SAMPLE_RATE, EnergyVAD
from voice_agent.gateway.app import create_app
from voice_agent.gateway.engine import Engine
from voice_agent.gateway.sessions import MemorySessionStore
from voice_agent.tools.crm_client import HTTPClient

IDENTITY = "0532 123 45 67, 14.05.1990"


def _pcm(audio: np.ndarray) -> bytes:
    return float_to_pcm16(audio.astype(np.float32))


def _utterance_pcm(speech_s: float = 0.6, silence_s: float = 0.9) -> bytes:
    speech = tone(speech_s, SAMPLE_RATE).samples
    silence = np.zeros(int(silence_s * SAMPLE_RATE), dtype=np.float32)
    return _pcm(np.concatenate([speech, silence]))


class Harness:
    def __init__(self, crm_http: HTTPClient) -> None:
        self.stt = FakeSTT([])
        self.tts = FakeTTS()
        self.store = MemorySessionStore()
        self.engine = Engine(stt=self.stt, tts=self.tts, vad_factory=EnergyVAD, crm_http=crm_http)
        self.app = create_app(
            engine_factory=lambda: self.engine,
            store=self.store,
            load_in_background=False,
            client_dir=None,
        )


@pytest.fixture
def harness(crm_http: TestClient) -> Harness:
    return Harness(crm_http)


@pytest.fixture
def client(harness: Harness) -> Iterator[TestClient]:
    with TestClient(harness.app) as c:
        yield c


def _until(ws: WebSocketTestSession, kind: str) -> list[dict[str, Any]]:
    """`kind` türünde mesaj gelene kadar JSON mesajlarını toplar; ses çerçevelerini atlar."""
    seen: list[dict[str, Any]] = []
    while True:
        message = ws.receive()
        if message.get("bytes") is not None:
            continue
        payload: dict[str, Any] = json.loads(message["text"])
        seen.append(payload)
        if payload["type"] == kind:
            return seen


def _open(client: TestClient, session_id: str | None = None) -> Callable[[], Any]:
    url = "/ws/voice" + (f"?session_id={session_id}" if session_id else "")
    return lambda: client.websocket_connect(url)


def test_health_and_ready(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok", "version": __version__}
    ready = client.get("/ready")
    assert ready.status_code == 200
    assert ready.json() == {"engine": "ready", "store": "ok"}


def test_new_session_is_greeted_with_text_and_audio(client: TestClient) -> None:
    with _open(client)() as ws:
        session = ws.receive_json()
        assert session["type"] == "session" and not session["resumed"]
        assert len(session["session_id"]) == 32
        reply = ws.receive_json()
        assert reply["type"] == "reply" and "Kimliğinizi" in reply["text"]
        audio = ws.receive_json()
        assert audio["type"] == "audio" and audio["sample_rate"] == 22_050
        pcm = ws.receive_bytes()
        assert len(pcm) > 0 and len(pcm) % 2 == 0


def test_spoken_turn_runs_vad_stt_agent_tts(client: TestClient, harness: Harness) -> None:
    harness.stt.texts = [IDENTITY]
    with _open(client)() as ws:
        _until(ws, "audio")
        ws.receive_bytes()
        pcm = _utterance_pcm()
        for i in range(0, len(pcm), 3200):  # 100 ms'lik parçalar
            ws.send_bytes(pcm[i : i + 3200])
        events = _until(ws, "turn_end")

    kinds = [e["type"] for e in events]
    vad = [e["state"] for e in events if e["type"] == "vad"]
    assert vad == ["speech_start", "speech_end"]
    assert kinds.index("transcript") > kinds.index("vad")
    transcript = next(e for e in events if e["type"] == "transcript")
    assert transcript == {"type": "transcript", "text": IDENTITY, "source": "voice"}
    reply = next(e for e in events if e["type"] == "reply")
    assert "kimliğiniz doğrulandı" in reply["text"]
    assert "audio" in kinds
    timings = events[-1]["timings"]
    assert set(timings) == {"vad", "stt", "llm", "tts_first", "first_audio"}
    assert timings["vad"] == pytest.approx(0.6, abs=0.05)
    assert timings["first_audio"] >= timings["vad"]


def test_typed_turn_skips_vad_and_stt(client: TestClient) -> None:
    with _open(client)() as ws:
        _until(ws, "reply")
        ws.send_json({"type": "text", "text": IDENTITY})
        events = _until(ws, "turn_end")
    transcript = next(e for e in events if e["type"] == "transcript")
    assert transcript["source"] == "text"
    assert events[-1]["timings"]["vad"] == 0.0


def test_session_resumes_with_state(client: TestClient) -> None:
    with _open(client)() as ws:
        session_id = ws.receive_json()["session_id"]
        _until(ws, "reply")
        ws.send_json({"type": "text", "text": IDENTITY})
        _until(ws, "turn_end")

    with _open(client, session_id)() as ws:
        session = ws.receive_json()
        assert session == {"type": "session", "session_id": session_id, "resumed": True}
        ws.send_json({"type": "text", "text": "Faturamı öğrenmek istiyorum"})
        events = _until(ws, "turn_end")
    reply = next(e for e in events if e["type"] == "reply")
    assert "faturanız" in reply["text"]  # kimlik tekrar sorulmadı


def test_unknown_session_id_starts_new_session(client: TestClient) -> None:
    with _open(client, "../../etc/passwd")() as ws:
        session = ws.receive_json()
        assert not session["resumed"]
        assert session["session_id"] != "../../etc/passwd"


def test_noise_and_empty_transcript_get_no_reply(client: TestClient, harness: Harness) -> None:
    harness.stt.texts = ["  "]
    with _open(client)() as ws:
        _until(ws, "audio")
        ws.receive_bytes()
        ws.send_bytes(_utterance_pcm(speech_s=0.1))  # kısa gürültü: tur yok
        ws.send_bytes(_utterance_pcm())  # STT boş döner: yanıt yok
        ws.send_json({"type": "text", "text": IDENTITY})
        events = _until(ws, "turn_end")
    transcripts = [e for e in events if e["type"] == "transcript"]
    assert [t["text"] for t in transcripts] == ["", IDENTITY]
    assert sum(e["type"] == "reply" for e in events) == 1


def test_bad_messages_return_errors(client: TestClient) -> None:
    with _open(client)() as ws:
        _until(ws, "reply")
        ws.send_text("{bozuk")
        assert _until(ws, "error")[-1]["message"] == "Geçersiz JSON"
        ws.send_json({"type": "change_package", "package_id": "P40"})
        assert _until(ws, "error")[-1]["message"] == "Bilinmeyen mesaj türü"


def test_handoff_ends_conversation(client: TestClient) -> None:
    with _open(client)() as ws:
        _until(ws, "reply")
        ws.send_json({"type": "text", "text": "Temsilciye bağlanmak istiyorum"})
        events = _until(ws, "end")
    assert any(e["type"] == "reply" and "temsilci" in e["text"] for e in events)


def test_turn_latency_is_exported_to_prometheus(client: TestClient) -> None:
    with _open(client)() as ws:
        _until(ws, "reply")
        ws.send_json({"type": "text", "text": IDENTITY})
        _until(ws, "turn_end")
    body = client.get("/metrics").text
    for step in ("vad", "stt", "llm", "tts_first", "first_audio"):
        assert f'voice_turn_step_seconds_count{{step="{step}"}} 1.0' in body
    assert 'voice_turns_total{source="text"} 1.0' in body


def test_engine_not_ready_rejects_connection(crm_http: TestClient) -> None:
    def failing() -> Engine:
        raise RuntimeError("model yok")

    app = create_app(engine_factory=failing, store=MemorySessionStore(), client_dir=None)
    with TestClient(app) as c:
        app.state.engine._thread.join(timeout=5)
        ready = c.get("/ready")
        assert ready.status_code == 503
        assert ready.json()["engine"] == "error"
        with c.websocket_connect("/ws/voice") as ws:
            assert ws.receive_json()["type"] == "error"

"""Ses motorları ve diyalog bileşenleri.

Modeller süreç başına bir kez yüklenir ve oturumlar arasında paylaşılır. Yükleme uzun sürdüğü
için ağ geçidi açılışta arka planda yükler; `/ready` hazır olunca 200 döner.
"""

import asyncio
import logging
import os
import threading
from collections.abc import Callable
from dataclasses import dataclass, field

from voice_agent.audio.stt import STT
from voice_agent.audio.tts import TTS
from voice_agent.audio.vad import VAD, EndpointConfig
from voice_agent.dialogue.agent import DialogueAgent
from voice_agent.dialogue.models import ConversationState
from voice_agent.dialogue.rule_based import RuleBasedLLM
from voice_agent.tools.crm_client import CRMClient, HTTPClient

log = logging.getLogger(__name__)


@dataclass
class Engine:
    """Bir oturumun ihtiyaç duyduğu her şey. Testler sahte bileşenlerle kurar."""

    stt: STT
    tts: TTS
    vad_factory: Callable[[], VAD]
    crm_http: HTTPClient
    endpoint: EndpointConfig = field(default_factory=EndpointConfig)
    # CTranslate2 ve ONNX modelleri aynı anda tek iş yapsın: CPU çekirdekleri paylaşılmasın.
    stt_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    tts_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def new_agent(self, state: ConversationState | None = None) -> DialogueAgent:
        return DialogueAgent(RuleBasedLLM(), CRMClient(self.crm_http), state=state)


def engine_from_env() -> Engine:
    """Gerçek modellerle motor kurar (Hugging Face'ten indirme gerekebilir)."""
    from voice_agent.audio.stt import FasterWhisperSTT
    from voice_agent.audio.tts import PIPER_DEFAULT_VOICE, PiperTTS, download_piper_voice
    from voice_agent.audio.vad import SileroVAD
    from voice_agent.tools.local import crm_http_from_env

    stt_model = os.environ.get("STT_MODEL", "small")
    voice = os.environ.get("PIPER_VOICE", PIPER_DEFAULT_VOICE)
    log.info("Modeller yükleniyor: STT=%s, TTS=%s", stt_model, voice)
    stt = FasterWhisperSTT(stt_model)
    tts = PiperTTS(download_piper_voice(voice))
    return Engine(stt=stt, tts=tts, vad_factory=SileroVAD, crm_http=crm_http_from_env())


class EngineHolder:
    """Motoru arka planda yükler; hazır olana kadar oturumlar beklemez, hata alır."""

    def __init__(self, factory: Callable[[], Engine]) -> None:
        self._factory = factory
        self.engine: Engine | None = None
        self.error: str | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._load, name="engine-loader", daemon=True)
            self._thread.start()

    def _load(self) -> None:
        try:
            self.engine = self._factory()
            log.info("Ses motoru hazır")
        except Exception as exc:  # yükleme hatası /ready'de görünür, süreç ayakta kalır
            log.exception("Ses motoru yüklenemedi")
            self.error = f"{type(exc).__name__}: {exc}"

    def load_now(self) -> Engine:
        """Testler ve ölçüm için eşzamanlı yükleme."""
        if self.engine is None:
            self._load()
        if self.engine is None:
            raise RuntimeError(self.error or "motor yüklenemedi")
        return self.engine

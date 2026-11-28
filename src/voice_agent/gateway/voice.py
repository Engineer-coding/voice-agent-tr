"""WebSocket üzerinden sesli görüşme.

Protokol (`/ws/voice?session_id=...`):

İstemci → sunucu
- ikili çerçeve: 16 kHz, tek kanal, küçük endian 16 bit PCM (boyut serbest)
- `{"type": "text", "text": "..."}`: yazarak giriş (ör. telefon numarası)

Sunucu → istemci (JSON)
- `session`: oturum kimliği ve devam edip etmediği
- `vad`: `speech_start` / `speech_end`
- `transcript`: STT çıktısı
- `reply`: asistanın tam yanıt metni
- `audio`: ardından gelen ikili çerçevenin örnekleme hızı ve cümlesi; çerçeve 16 bit PCM
- `turn_end`: tur bitti, gecikme dökümü (`timings`)
- `end`: görüşme bitti (temsilciye devir)
- `error`: istemciye gösterilecek hata
"""

import asyncio
import contextlib
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass

from starlette.websockets import WebSocket, WebSocketDisconnect

from voice_agent.audio.io import AudioClip, float_to_pcm16, pcm16_to_float
from voice_agent.audio.tts import split_sentences
from voice_agent.audio.vad import SAMPLE_RATE, Endpointer, Utterance
from voice_agent.dialogue.agent import DialogueAgent
from voice_agent.gateway.engine import Engine
from voice_agent.gateway.sessions import SessionStore
from voice_agent.telemetry.metrics import TurnTimings, VoiceMetrics

log = logging.getLogger(__name__)

MAX_TEXT_CHARS = 500
_SESSION_ID = re.compile(r"^[0-9a-f]{32}$")


@dataclass(frozen=True)
class _SpeechTurn:
    utterance: Utterance
    endpoint_at: float  # konuşma sonu kararının verildiği an (perf_counter)


@dataclass(frozen=True)
class _TextTurn:
    text: str
    received_at: float


_Turn = _SpeechTurn | _TextTurn


def valid_session_id(value: str | None) -> str | None:
    return value if value and _SESSION_ID.match(value) else None


class VoiceSession:
    def __init__(
        self,
        websocket: WebSocket,
        engine: Engine,
        store: SessionStore,
        metrics: VoiceMetrics,
        session_id: str,
        agent: DialogueAgent,
        resumed: bool,
    ) -> None:
        self.ws = websocket
        self.engine = engine
        self.store = store
        self.metrics = metrics
        self.session_id = session_id
        self.agent = agent
        self.resumed = resumed
        self._queue: asyncio.Queue[_Turn] = asyncio.Queue()
        self._send_lock = asyncio.Lock()
        self._endpointer = Endpointer(
            engine.vad_factory(), engine.endpoint, on_event=self._on_vad_event
        )
        self._pending_events: list[dict[str, object]] = []

    @classmethod
    async def open(
        cls,
        websocket: WebSocket,
        engine: Engine,
        store: SessionStore,
        metrics: VoiceMetrics,
        requested_id: str | None,
    ) -> "VoiceSession":
        session_id = valid_session_id(requested_id)
        state = await store.load(session_id) if session_id else None
        resumed = state is not None
        if session_id is None or state is None:
            session_id = uuid.uuid4().hex
        agent = engine.new_agent(state)
        return cls(websocket, engine, store, metrics, session_id, agent, resumed)

    # --- gönderim ---

    async def _send_json(self, payload: dict[str, object]) -> None:
        async with self._send_lock:
            await self.ws.send_json(payload)

    async def _send_audio(self, clip: AudioClip, sentence: str) -> None:
        async with self._send_lock:
            await self.ws.send_json(
                {"type": "audio", "sample_rate": clip.sample_rate, "text": sentence}
            )
            await self.ws.send_bytes(float_to_pcm16(clip.samples))

    def _on_vad_event(self, name: str, at_s: float) -> None:
        self._pending_events.append({"type": "vad", "state": name, "at": round(at_s, 3)})

    # --- ana döngü ---

    async def run(self) -> None:
        self.metrics.sessions.inc()
        await self._send_json(
            {"type": "session", "session_id": self.session_id, "resumed": self.resumed}
        )
        worker = asyncio.create_task(self._worker())
        receiver = asyncio.create_task(self._receive_loop())
        try:
            if not self.resumed:
                greeting = self.agent.greet()
                await self.store.save(self.session_id, self.agent.state)
                await self._send_json({"type": "reply", "text": greeting})
                await self._speak(greeting)
            await asyncio.wait({worker, receiver}, return_when=asyncio.FIRST_COMPLETED)
            if worker.done() and not receiver.done():
                await self.ws.close()  # görüşme bitti (temsilciye devir)
        except WebSocketDisconnect:
            pass
        finally:
            for task in (worker, receiver):
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, WebSocketDisconnect):
                    await task

    async def _receive_loop(self) -> None:
        while True:
            message = await self.ws.receive()
            if message["type"] == "websocket.disconnect":
                return
            if (data := message.get("bytes")) is not None:
                await self._on_audio(data)
            elif (text := message.get("text")) is not None:
                await self._on_text(text)

    async def _on_audio(self, data: bytes) -> None:
        utterances = self._endpointer.feed(pcm16_to_float(data))
        now = time.perf_counter()
        for event in self._pending_events:
            await self._send_json(event)
        self._pending_events.clear()
        for utterance in utterances:
            await self._queue.put(_SpeechTurn(utterance, now))

    async def _on_text(self, raw: str) -> None:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            await self._send_json({"type": "error", "message": "Geçersiz JSON"})
            return
        if not isinstance(payload, dict) or payload.get("type") != "text":
            await self._send_json({"type": "error", "message": "Bilinmeyen mesaj türü"})
            return
        text = str(payload.get("text", "")).strip()[:MAX_TEXT_CHARS]
        if text:
            await self._queue.put(_TextTurn(text, time.perf_counter()))

    async def _worker(self) -> None:
        while not self.agent.finished:
            turn = await self._queue.get()
            try:
                await self._handle(turn)
            except WebSocketDisconnect:
                return
            except Exception:
                log.exception("Tur işlenemedi")
                await self._send_json(
                    {"type": "error", "message": "Bir sorun oluştu, lütfen tekrar söyleyin."}
                )
        await self._send_json({"type": "end"})

    # --- tur ---

    async def _handle(self, turn: _Turn) -> None:
        if isinstance(turn, _SpeechTurn):
            start = turn.endpoint_at
            vad_s = turn.utterance.endpoint_delay_s
            clip = AudioClip(turn.utterance.samples, SAMPLE_RATE)
            async with self.engine.stt_lock:
                transcription = await asyncio.to_thread(self.engine.stt.transcribe, clip)
            text = transcription.text.strip()
            source = "voice"
        else:
            start = turn.received_at
            vad_s = 0.0
            text = turn.text
            source = "text"
        stt_done = time.perf_counter()
        await self._send_json({"type": "transcript", "text": text, "source": source})
        if not _has_words(text):
            return  # gürültü ya da boş çıktı: yanıt verme

        reply = await asyncio.to_thread(self.agent.handle, text)
        llm_done = time.perf_counter()
        await self.store.save(self.session_id, self.agent.state)
        await self._send_json({"type": "reply", "text": reply})

        tts_first, first_audio_at = await self._speak(reply)
        timings = TurnTimings(
            vad=vad_s,
            stt=stt_done - start,
            llm=llm_done - stt_done,
            tts_first=tts_first,
            first_audio=vad_s + (first_audio_at - start),
        )
        self.metrics.observe(timings, source=source)
        await self._send_json({"type": "turn_end", "timings": timings.as_dict()})

    async def _speak(self, text: str) -> tuple[float, float]:
        """Yanıtı cümle cümle seslendirip gönderir. (ilk cümle TTS süresi, ilk ses anı) döner."""
        tts_first = 0.0
        first_audio_at = time.perf_counter()
        for i, sentence in enumerate(split_sentences(text)):
            started = time.perf_counter()
            async with self.engine.tts_lock:
                clip = await asyncio.to_thread(self.engine.tts.synthesize, sentence)
            if i == 0:
                tts_first = time.perf_counter() - started
            await self._send_audio(clip, sentence)
            if i == 0:
                first_audio_at = time.perf_counter()
        return tts_first, first_audio_at


# Whisper'ın Türkçede sessizlik ve gürültüde sık uydurduğu altyazı kalıpları.
_HALLUCINATIONS = ("altyazı m.k", "abone olmayı unutmayın", "izlediğiniz için teşekkürler")


def _has_words(text: str) -> bool:
    lowered = text.lower()
    return bool(re.search(r"\w", text)) and not any(h in lowered for h in _HALLUCINATIONS)

"""Konuşmadan yazıya (STT). Varsayılan motor CPU'da int8 faster-whisper."""

import time
from dataclasses import dataclass
from typing import Any, Protocol

from voice_agent.audio.io import AudioClip, resample

# Whisper'ın alan terimlerini doğru yazması için başlangıç promptu (Aşama 3 riski: telekom terimleri).
TELECOM_PROMPT = (
    "Müşteri hizmetleri görüşmesi. Fatura, paket, tarife, taahhüt, GB, internet, modem, "
    "arıza kaydı, roaming, fiber, mobil hat."
)


@dataclass(frozen=True)
class Transcription:
    text: str
    audio_s: float
    processing_s: float

    @property
    def rtf(self) -> float:
        """Gerçek zaman faktörü: işlem süresi / ses süresi. 1'in altı gerçek zamandan hızlı."""
        return self.processing_s / self.audio_s if self.audio_s else 0.0


class STT(Protocol):
    name: str

    def transcribe(self, clip: AudioClip) -> Transcription: ...


class FasterWhisperSTT:
    """faster-whisper sarıcısı. Model ilk kullanımda Hugging Face'ten indirilir."""

    def __init__(
        self,
        model_size: str = "small",
        compute_type: str = "int8",
        cpu_threads: int = 0,
        beam_size: int = 1,
        initial_prompt: str | None = TELECOM_PROMPT,
    ) -> None:
        from faster_whisper import WhisperModel

        self.name = f"faster-whisper-{model_size}-{compute_type}"
        self._model: Any = WhisperModel(
            model_size, device="cpu", compute_type=compute_type, cpu_threads=cpu_threads
        )
        self._beam_size = beam_size
        self._initial_prompt = initial_prompt

    def transcribe(self, clip: AudioClip) -> Transcription:
        audio = resample(clip)
        start = time.perf_counter()
        segments, _info = self._model.transcribe(
            audio.samples,
            language="tr",
            beam_size=self._beam_size,
            initial_prompt=self._initial_prompt,
            condition_on_previous_text=False,
            vad_filter=False,
        )
        text = " ".join(segment.text.strip() for segment in segments).strip()
        return Transcription(
            text=text, audio_s=audio.duration_s, processing_s=time.perf_counter() - start
        )

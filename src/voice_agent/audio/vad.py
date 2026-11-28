"""Konuşma algılama (VAD) ve konuşma sonu tespiti.

Ses 16 kHz'de 512 örneklik (32 ms) pencerelere bölünür. Her pencere için VAD bir konuşma
olasılığı verir; `Endpointer` bu olasılıklardan konuşmanın başladığı ve bittiği anı çıkarır.
"""

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import numpy as np
import numpy.typing as npt

SAMPLE_RATE = 16_000
WINDOW = 512  # 32 ms
WINDOW_S = WINDOW / SAMPLE_RATE

FloatArray = npt.NDArray[np.float32]


class VAD(Protocol):
    """Akışlı VAD: pencere pencere çağrılır, iç durumunu korur."""

    def probability(self, window: FloatArray) -> float: ...

    def reset(self) -> None: ...


def silero_model_path() -> Path:
    """Silero VAD ONNX modeli faster-whisper paketiyle birlikte gelir; ayrıca indirilmez."""
    import faster_whisper

    return Path(faster_whisper.__file__).parent / "assets" / "silero_vad_v6.onnx"


class SileroVAD:
    """Silero VAD (ONNX, CPU). Pencere başına ~0,1 ms; durum (h, c) pencereler arasında taşınır."""

    CONTEXT = 64

    def __init__(self, model_path: Path | None = None) -> None:
        import onnxruntime

        opts = onnxruntime.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        opts.log_severity_level = 4
        self._session: Any = onnxruntime.InferenceSession(
            str(model_path or silero_model_path()),
            providers=["CPUExecutionProvider"],
            sess_options=opts,
        )
        self.reset()

    def reset(self) -> None:
        self._h = np.zeros((1, 1, 128), dtype=np.float32)
        self._c = np.zeros((1, 1, 128), dtype=np.float32)
        self._context = np.zeros(self.CONTEXT, dtype=np.float32)

    def probability(self, window: FloatArray) -> float:
        frame = np.concatenate([self._context, window]).reshape(1, -1).astype(np.float32)
        out, self._h, self._c = self._session.run(
            None, {"input": frame, "h": self._h, "c": self._c}
        )
        self._context = window[-self.CONTEXT :].astype(np.float32)
        return float(np.asarray(out).reshape(-1)[0])


class EnergyVAD:
    """Enerji eşiğine dayalı basit VAD. Testlerde ve model yokken kullanılır."""

    def __init__(self, threshold_db: float = -40.0) -> None:
        self.threshold_db = threshold_db

    def reset(self) -> None:
        return None

    def probability(self, window: FloatArray) -> float:
        rms = float(np.sqrt(np.mean(np.square(window)))) if window.size else 0.0
        db = 20 * np.log10(rms + 1e-10)
        return 1.0 if db > self.threshold_db else 0.0


@dataclass(frozen=True)
class EndpointConfig:
    threshold: float = 0.5
    min_speech_s: float = 0.25  # bundan kısa sesler (öksürük, tık) yok sayılır
    end_silence_s: float = 0.6  # bu kadar sessizlik konuşmayı bitirir
    pre_roll_s: float = 0.3  # konuşma başından önce eklenen ses (ilk hece kesilmesin)
    max_utterance_s: float = 30.0  # Whisper penceresi


@dataclass(frozen=True)
class Utterance:
    """Tamamlanmış bir konuşma parçası. Zamanlar akışın başından itibaren ses saniyesidir."""

    samples: FloatArray
    start_s: float
    speech_end_s: float  # son konuşma penceresinin sonu
    endpoint_s: float  # konuşma sonu kararının verildiği an

    @property
    def duration_s(self) -> float:
        return self.samples.size / SAMPLE_RATE

    @property
    def endpoint_delay_s(self) -> float:
        """Konuşma bitti → VAD karar verdi (sessizlik bekleme süresi)."""
        return self.endpoint_s - self.speech_end_s


EventCallback = Callable[[str, float], None]


class Endpointer:
    """Akan sesten konuşma parçalarını çıkarır.

    `feed` her çağrıda tamamlanan parçaları döndürür. `on_event("speech_start" | "speech_end", t)`
    istemciye anlık durum göstermek için kullanılabilir.
    """

    def __init__(
        self,
        vad: VAD,
        config: EndpointConfig | None = None,
        on_event: EventCallback | None = None,
    ) -> None:
        self.vad = vad
        self.config = config or EndpointConfig()
        self.on_event = on_event
        self._buffer = np.zeros(0, dtype=np.float32)
        self._processed = 0  # işlenen pencere sayısı
        pre_roll = round(self.config.pre_roll_s / WINDOW_S)
        self._history: deque[FloatArray] = deque(maxlen=max(pre_roll, 1))
        self._speech: list[FloatArray] = []
        self._in_speech = False
        self._start_s = 0.0
        self._speech_windows = 0
        self._silence_windows = 0
        self._last_voiced_end_s = 0.0

    @property
    def in_speech(self) -> bool:
        return self._in_speech

    def reset(self) -> None:
        self.vad.reset()
        self._speech = []
        self._in_speech = False
        self._history.clear()

    def feed(self, samples: FloatArray) -> list[Utterance]:
        self._buffer = np.concatenate([self._buffer, samples.astype(np.float32)])
        done: list[Utterance] = []
        while self._buffer.size >= WINDOW:
            window, self._buffer = self._buffer[:WINDOW], self._buffer[WINDOW:]
            utterance = self._step(window)
            if utterance is not None:
                done.append(utterance)
        return done

    def _step(self, window: FloatArray) -> Utterance | None:
        cfg = self.config
        start_s = self._processed * WINDOW_S
        self._processed += 1
        end_s = self._processed * WINDOW_S
        voiced = self.vad.probability(window) >= cfg.threshold

        if not self._in_speech:
            if voiced:
                self._in_speech = True
                self._speech = [*self._history, window]
                self._start_s = start_s - len(self._history) * WINDOW_S
                self._speech_windows = 1
                self._silence_windows = 0
                self._last_voiced_end_s = end_s
            else:
                self._history.append(window)
            return None

        self._speech.append(window)
        if voiced:
            self._speech_windows += 1
            self._silence_windows = 0
            self._last_voiced_end_s = end_s
            if self._speech_windows == round(cfg.min_speech_s / WINDOW_S) and self.on_event:
                self.on_event("speech_start", self._start_s)
        else:
            self._silence_windows += 1

        long_enough = self._speech_windows * WINDOW_S >= cfg.min_speech_s
        silence_done = self._silence_windows * WINDOW_S >= cfg.end_silence_s
        too_long = len(self._speech) * WINDOW_S >= cfg.max_utterance_s
        if not (silence_done or too_long):
            return None

        speech, self._speech = self._speech, []
        self._in_speech = False
        self._history.clear()
        if not long_enough:
            return None  # kısa gürültü
        if self.on_event:
            self.on_event("speech_end", self._last_voiced_end_s)
        return Utterance(
            samples=np.concatenate(speech),
            start_s=self._start_s,
            speech_end_s=self._last_voiced_end_s,
            endpoint_s=end_s,
        )

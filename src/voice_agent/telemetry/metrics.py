"""Tur başına gecikme dökümü (Prometheus).

Adımlar:
- `vad`: konuşma bitti → VAD konuşma sonu kararı (sessizlik bekleme)
- `stt`: konuşmanın yazıya çevrilmesi
- `llm`: diyalog yöneticisi (LLM + araç çağrıları), yanıt metni hazır
- `tts_first`: ilk cümlenin seslendirilmesi
- `first_audio`: konuşma bitti → ilk ses istemciye gönderildi (kullanıcının hissettiği gecikme)
"""

from dataclasses import asdict, dataclass

from prometheus_client import CollectorRegistry, Counter, Histogram

STEPS = ("vad", "stt", "llm", "tts_first", "first_audio")
BUCKETS = (0.05, 0.1, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0, 6.0, 10.0)


@dataclass(frozen=True)
class TurnTimings:
    vad: float
    stt: float
    llm: float
    tts_first: float
    first_audio: float

    def as_dict(self) -> dict[str, float]:
        return {k: round(v, 4) for k, v in asdict(self).items()}


class VoiceMetrics:
    def __init__(self, registry: CollectorRegistry | None = None) -> None:
        self.registry = registry or CollectorRegistry()
        self.step_seconds = Histogram(
            "voice_turn_step_seconds",
            "Sesli tur adımlarının süresi",
            ["step"],
            buckets=BUCKETS,
            registry=self.registry,
        )
        self.turns = Counter(
            "voice_turns", "Tamamlanan sesli turlar", ["source"], registry=self.registry
        )
        self.sessions = Counter("voice_sessions", "Açılan sesli oturumlar", registry=self.registry)

    def observe(self, timings: TurnTimings, source: str = "voice") -> None:
        for step, value in asdict(timings).items():
            self.step_seconds.labels(step=step).observe(value)
        self.turns.labels(source=source).inc()

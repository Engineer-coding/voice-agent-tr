"""Yazıdan konuşmaya (TTS). Varsayılan motor Piper; yanıt cümle cümle seslendirilir."""

import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from voice_agent.audio.io import AudioClip, concat

PIPER_VOICE_REPO = "rhasspy/piper-voices"
PIPER_DEFAULT_VOICE = "tr/tr_TR/dfki/medium/tr_TR-dfki-medium"

# Cümle sonu: . ! ? … ve ardından boşluk. Tutarlar virgüllü yazıldığı için ("752,20 TL") bölünmez.
_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")


def split_sentences(text: str) -> list[str]:
    """Metni seslendirme için cümlelere böler. İlk cümle LLM bitmeden seslendirilebilir."""
    return [s.strip() for s in _SENTENCE_END.split(text.strip()) if s.strip()]


@dataclass(frozen=True)
class Synthesis:
    clip: AudioClip
    first_chunk_s: float
    total_s: float


class TTS(Protocol):
    name: str

    def synthesize(self, text: str) -> AudioClip: ...


def synthesize_by_sentence(tts: TTS, text: str) -> Synthesis:
    """Cümle cümle seslendirir; ilk cümlenin hazır olma süresini ölçer."""
    start = time.perf_counter()
    clips: list[AudioClip] = []
    first_chunk_s = 0.0
    for i, sentence in enumerate(split_sentences(text)):
        clips.append(tts.synthesize(sentence))
        if i == 0:
            first_chunk_s = time.perf_counter() - start
    return Synthesis(concat(clips), first_chunk_s, time.perf_counter() - start)


def download_piper_voice(voice: str = PIPER_DEFAULT_VOICE, cache_dir: Path | None = None) -> Path:
    """Piper sesini Hugging Face'ten indirir ve .onnx yolunu döndürür."""
    from huggingface_hub import hf_hub_download

    model = hf_hub_download(PIPER_VOICE_REPO, f"{voice}.onnx", cache_dir=cache_dir)
    hf_hub_download(PIPER_VOICE_REPO, f"{voice}.onnx.json", cache_dir=cache_dir)
    return Path(model)


class PiperTTS:
    def __init__(self, model_path: Path) -> None:
        from piper import PiperVoice

        self.name = f"piper-{model_path.stem}"
        self._voice: Any = PiperVoice.load(model_path)

    def synthesize(self, text: str) -> AudioClip:
        chunks = list(self._voice.synthesize(text))
        if not chunks:
            return AudioClip(np.zeros(0, dtype=np.float32), 22_050)
        rate = int(chunks[0].sample_rate)
        samples = np.concatenate([c.audio_float_array for c in chunks]).astype(np.float32)
        return AudioClip(samples, rate)

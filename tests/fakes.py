"""Testlerde gerçek modellerin yerine geçen sahte ses bileşenleri."""

import numpy as np

from voice_agent.audio.io import AudioClip
from voice_agent.audio.stt import Transcription


def tone(seconds: float, rate: int = 22_050) -> AudioClip:
    t = np.arange(int(seconds * rate)) / rate
    return AudioClip((0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32), rate)


class FakeTTS:
    name = "fake-tts"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def synthesize(self, text: str) -> AudioClip:
        self.calls.append(text)
        return tone(0.05 * len(text.split()))


class FakeSTT:
    """Ses süresine bakmadan sırayla önceden verilen metinleri döndürür."""

    name = "fake-stt"

    def __init__(self, texts: list[str]) -> None:
        self.texts = list(texts)

    def transcribe(self, clip: AudioClip) -> Transcription:
        return Transcription(text=self.texts.pop(0), audio_s=clip.duration_s, processing_s=0.01)

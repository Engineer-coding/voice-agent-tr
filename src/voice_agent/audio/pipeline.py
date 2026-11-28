"""Dosya tabanlı ses hattı: ses dosyası → STT → agent → TTS → ses dosyası.

Gerçek zamanlı akıştan önce bileşenlerin doğru çalıştığını zamanlamadan bağımsız doğrular.
"""

import time
from dataclasses import dataclass
from pathlib import Path

from voice_agent.audio.io import read_wav, write_wav
from voice_agent.audio.stt import STT
from voice_agent.audio.tts import TTS, synthesize_by_sentence
from voice_agent.dialogue.agent import DialogueAgent


@dataclass(frozen=True)
class TurnTimings:
    stt_s: float
    agent_s: float
    tts_first_sentence_s: float
    tts_total_s: float

    @property
    def to_first_audio_s(self) -> float:
        """Kullanıcı konuşması bitti → ilk ses hazır (akışlı olmayan alt sınır)."""
        return self.stt_s + self.agent_s + self.tts_first_sentence_s


@dataclass(frozen=True)
class TurnResult:
    transcript: str
    reply: str
    output: Path
    timings: TurnTimings


class FilePipeline:
    def __init__(self, stt: STT, agent: DialogueAgent, tts: TTS) -> None:
        self.stt = stt
        self.agent = agent
        self.tts = tts

    def greet(self, output: Path) -> str:
        text = self.agent.greet()
        write_wav(output, synthesize_by_sentence(self.tts, text).clip)
        return text

    def process(self, audio_in: Path, audio_out: Path) -> TurnResult:
        transcription = self.stt.transcribe(read_wav(audio_in))

        start = time.perf_counter()
        reply = self.agent.handle(transcription.text)
        agent_s = time.perf_counter() - start

        synthesis = synthesize_by_sentence(self.tts, reply)
        write_wav(audio_out, synthesis.clip)
        return TurnResult(
            transcript=transcription.text,
            reply=reply,
            output=audio_out,
            timings=TurnTimings(
                stt_s=transcription.processing_s,
                agent_s=agent_s,
                tts_first_sentence_s=synthesis.first_chunk_s,
                tts_total_s=synthesis.total_s,
            ),
        )

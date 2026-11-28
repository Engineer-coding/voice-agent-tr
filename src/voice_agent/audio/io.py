"""WAV okuma/yazma ve basit yeniden örnekleme. Ek bağımlılık olmadan (stdlib `wave` + numpy)."""

import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt

TARGET_SAMPLE_RATE = 16_000

FloatAudio = npt.NDArray[np.float32]


@dataclass(frozen=True)
class AudioClip:
    """Tek kanallı, [-1, 1] aralığında float32 ses."""

    samples: FloatAudio
    sample_rate: int

    @property
    def duration_s(self) -> float:
        return len(self.samples) / self.sample_rate


def read_wav(path: Path) -> AudioClip:
    with wave.open(str(path), "rb") as wav:
        channels, width, rate = wav.getnchannels(), wav.getsampwidth(), wav.getframerate()
        frames = wav.readframes(wav.getnframes())
    if width != 2:
        raise ValueError(f"Yalnızca 16 bit PCM desteklenir: {path}")
    data = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1).astype(np.float32)
    return AudioClip(samples=data, sample_rate=rate)


def write_wav(path: Path, clip: AudioClip) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(clip.samples, -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(clip.sample_rate)
        wav.writeframes(pcm.tobytes())


def resample(clip: AudioClip, target_rate: int = TARGET_SAMPLE_RATE) -> AudioClip:
    """Doğrusal enterpolasyonla yeniden örnekler (STT girişi için yeterli)."""
    if clip.sample_rate == target_rate or len(clip.samples) == 0:
        return AudioClip(clip.samples, target_rate) if len(clip.samples) == 0 else clip
    n_out = round(len(clip.samples) * target_rate / clip.sample_rate)
    x_old = np.linspace(0.0, 1.0, num=len(clip.samples), endpoint=False)
    x_new = np.linspace(0.0, 1.0, num=n_out, endpoint=False)
    return AudioClip(np.interp(x_new, x_old, clip.samples).astype(np.float32), target_rate)


def concat(clips: list[AudioClip], gap_s: float = 0.15) -> AudioClip:
    """Aynı örnekleme hızındaki parçaları aralarında kısa sessizlikle birleştirir."""
    if not clips:
        return AudioClip(np.zeros(0, dtype=np.float32), TARGET_SAMPLE_RATE)
    rate = clips[0].sample_rate
    silence = np.zeros(int(gap_s * rate), dtype=np.float32)
    parts: list[FloatAudio] = []
    for i, clip in enumerate(clips):
        if clip.sample_rate != rate:
            clip = resample(clip, rate)
        if i:
            parts.append(silence)
        parts.append(clip.samples)
    return AudioClip(np.concatenate(parts).astype(np.float32), rate)

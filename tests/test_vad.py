"""Konuşma sonu tespiti testleri. Enerji tabanlı VAD ile deterministik çalışır."""

import numpy as np
import pytest

from tests.fakes import tone
from voice_agent.audio.vad import SAMPLE_RATE, EndpointConfig, Endpointer, EnergyVAD, Utterance


def _silence(seconds: float) -> np.ndarray:
    return np.zeros(int(seconds * SAMPLE_RATE), dtype=np.float32)


def _speech(seconds: float) -> np.ndarray:
    return tone(seconds, SAMPLE_RATE).samples


def _feed_in_chunks(endpointer: Endpointer, audio: np.ndarray, chunk: int) -> list[Utterance]:
    out: list[Utterance] = []
    for i in range(0, audio.size, chunk):
        out.extend(endpointer.feed(audio[i : i + chunk]))
    return out


def test_detects_one_utterance_and_end_of_speech() -> None:
    events: list[tuple[str, float]] = []
    endpointer = Endpointer(EnergyVAD(), on_event=lambda name, t: events.append((name, t)))
    audio = np.concatenate([_silence(1.0), _speech(1.0), _silence(1.0)])

    utterances = endpointer.feed(audio)

    assert len(utterances) == 1
    u = utterances[0]
    assert u.start_s == pytest.approx(1.0 - 0.3, abs=0.04)  # ön ek (pre-roll) dahil
    assert u.speech_end_s == pytest.approx(2.0, abs=0.04)
    assert u.endpoint_delay_s == pytest.approx(0.6, abs=0.04)
    assert u.duration_s == pytest.approx(1.0 + 0.3 + 0.6, abs=0.07)
    assert [name for name, _ in events] == ["speech_start", "speech_end"]


def test_chunk_size_does_not_change_result() -> None:
    audio = np.concatenate([_silence(0.5), _speech(0.8), _silence(0.8)])
    whole = Endpointer(EnergyVAD()).feed(audio)
    for chunk in (160, 1000, 4096):
        parts = _feed_in_chunks(Endpointer(EnergyVAD()), audio, chunk)
        assert len(parts) == len(whole) == 1
        assert parts[0].speech_end_s == whole[0].speech_end_s
        assert np.array_equal(parts[0].samples, whole[0].samples)


def test_short_noise_is_ignored() -> None:
    audio = np.concatenate([_silence(0.5), _speech(0.1), _silence(1.0)])
    assert Endpointer(EnergyVAD()).feed(audio) == []


def test_short_pause_inside_speech_does_not_split() -> None:
    audio = np.concatenate([_speech(0.6), _silence(0.3), _speech(0.6), _silence(1.0)])
    utterances = Endpointer(EnergyVAD()).feed(audio)
    assert len(utterances) == 1


def test_two_utterances() -> None:
    audio = np.concatenate([_speech(0.5), _silence(1.0), _speech(0.5), _silence(1.0)])
    assert len(Endpointer(EnergyVAD()).feed(audio)) == 2


def test_long_speech_is_cut_at_max_length() -> None:
    config = EndpointConfig(max_utterance_s=2.0)
    utterances = Endpointer(EnergyVAD(), config).feed(_speech(5.0))
    assert len(utterances) == 2
    assert all(u.duration_s <= 2.05 for u in utterances)


def test_silero_vad_separates_silence_from_noise() -> None:
    pytest.importorskip("onnxruntime")
    pytest.importorskip("faster_whisper")
    from voice_agent.audio.vad import WINDOW, SileroVAD

    vad = SileroVAD()
    silence = [vad.probability(np.zeros(WINDOW, dtype=np.float32)) for _ in range(20)]
    assert max(silence) < 0.5
    vad.reset()
    assert 0.0 <= vad.probability(_speech(0.032)[:WINDOW]) <= 1.0

"""Ses hattı testleri. Gerçek modeller yerine sahte STT/TTS kullanılır (ağ gerektirmez)."""

from collections.abc import Callable
from pathlib import Path

import numpy as np

from tests.fakes import FakeSTT, FakeTTS, tone
from voice_agent.audio.io import concat, read_wav, resample, write_wav
from voice_agent.audio.pipeline import FilePipeline
from voice_agent.audio.tts import split_sentences, synthesize_by_sentence
from voice_agent.dialogue.agent import DialogueAgent


def test_wav_roundtrip(tmp_path: Path) -> None:
    clip = tone(0.5, 16_000)
    write_wav(tmp_path / "a.wav", clip)
    back = read_wav(tmp_path / "a.wav")
    assert back.sample_rate == 16_000
    assert len(back.samples) == len(clip.samples)
    assert np.max(np.abs(back.samples - clip.samples)) < 1e-3


def test_read_float32_wav(tmp_path: Path) -> None:
    """FLEURS dosyaları 32 bit float WAV'dır; stdlib wave bunları okuyamaz."""
    import struct

    samples = np.array([0.0, 0.5, -0.5, 0.25], dtype="<f4")
    data = samples.tobytes()
    fmt = struct.pack("<HHIIHH", 3, 1, 16_000, 16_000 * 4, 4, 32)
    body = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt
    body += b"data" + struct.pack("<I", len(data)) + data
    (tmp_path / "f.wav").write_bytes(b"RIFF" + struct.pack("<I", len(body)) + body)
    clip = read_wav(tmp_path / "f.wav")
    assert clip.sample_rate == 16_000
    assert np.allclose(clip.samples, samples)


def test_resample_changes_rate_and_keeps_duration() -> None:
    clip = tone(1.0, 22_050)
    out = resample(clip, 16_000)
    assert out.sample_rate == 16_000
    assert abs(out.duration_s - 1.0) < 1e-3


def test_concat_adds_gaps() -> None:
    a, b = tone(0.2, 16_000), tone(0.3, 16_000)
    joined = concat([a, b], gap_s=0.1)
    assert abs(joined.duration_s - 0.6) < 1e-3


def test_split_sentences_keeps_amounts_together() -> None:
    text = "Kasım 2026 faturanız 752,20 TL. Paket ücretinize ek kalemler var! Onaylıyor musunuz?"
    assert split_sentences(text) == [
        "Kasım 2026 faturanız 752,20 TL.",
        "Paket ücretinize ek kalemler var!",
        "Onaylıyor musunuz?",
    ]


def test_synthesize_by_sentence_calls_tts_per_sentence() -> None:
    tts = FakeTTS()
    result = synthesize_by_sentence(tts, "Birinci cümle. İkinci cümle.")
    assert tts.calls == ["Birinci cümle.", "İkinci cümle."]
    assert result.first_chunk_s <= result.total_s
    assert result.clip.duration_s > 0


def test_file_pipeline_end_to_end(tmp_path: Path, make_agent: Callable[..., DialogueAgent]) -> None:
    agent = make_agent()
    stt = FakeSTT(["0532 123 45 67, 14.05.1990", "Bu ayki faturam neden yüksek?"])
    pipeline = FilePipeline(stt, agent, FakeTTS())
    turn_in = tmp_path / "in.wav"
    write_wav(turn_in, tone(1.0, 16_000))

    first = pipeline.process(turn_in, tmp_path / "out1.wav")
    assert "doğrulandı" in first.reply
    second = pipeline.process(turn_in, tmp_path / "out2.wav")
    assert "752,20 TL" in second.reply
    assert read_wav(second.output).duration_s > 0
    assert second.timings.to_first_audio_s >= second.timings.stt_s

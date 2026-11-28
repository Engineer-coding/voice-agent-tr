"""Gerçek zamanlı akış ölçümü: çalışan ağ geçidine WebSocket üzerinden konuşan bir müşteri.

Müşteri cümleleri Piper ile sentezlenir, 16 kHz PCM olarak gerçek zaman hızında (32 ms'lik
parçalar) gönderilir, ardından sessizlik gelir. Her tur için:
- sunucunun gecikme dökümü (`turn_end.timings`: vad, stt, llm, tts_first, first_audio)
- istemcinin ölçtüğü süre: son konuşma örneği gönderildi → ilk ses çerçevesi alındı
toplanır, p50/p95 hesaplanır. `--prometheus` verilirse aynı yüzdelikler Prometheus'tan da
okunur (Grafana panelinin gösterdiği değerler).

Kullanım (ağ geçidi çalışırken, ör. `make up`):
    uv run --extra audio python -m voice_agent.evaluation.realtime_bench \\
        --url ws://localhost:8000/ws/voice --prometheus http://localhost:9090
"""

import argparse
import asyncio
import json
import statistics
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import httpx
import numpy as np

from voice_agent.audio.io import AudioClip, float_to_pcm16, resample
from voice_agent.audio.tts import TTS
from voice_agent.audio.vad import SAMPLE_RATE, WINDOW
from voice_agent.telemetry.metrics import STEPS

# Her diyalog: (müşteri adı, söyledikleri). Kimlikler sahte CRM'in sabit kurgusal müşterileri.
DIALOGUES: list[tuple[str, list[str]]] = [
    (
        "fatura",
        [
            "Telefon numaram 0532 123 45 67, doğum tarihim 14 Mayıs 1990.",
            "Bu ayki faturamı öğrenmek istiyorum.",
            "Teşekkür ederim, başka bir şey yok.",
        ],
    ),
    (
        "paket",
        [
            "Numaram 0533 987 65 43, 2 Kasım 1985 doğumluyum.",
            "Paketimi değiştirmek istiyorum, daha fazla internet lazım.",
            "Süper 20 GB paketini istiyorum.",
            "Evet, onaylıyorum.",
        ],
    ),
    (
        "ariza",
        [
            "0544 111 22 33, doğum tarihim 23 Mart 1978.",
            "İnternetim çok yavaş, modemde kırmızı ışık yanıyor.",
        ],
    ),
    (
        "fatura-2",
        [
            "Telefon numaram 0555 222 33 44, doğum tarihim 30 Temmuz 2001.",
            "Faturamda yurt dışı arama ücreti var, neden bu kadar yüksek?",
        ],
    ),
    (
        "temsilci",
        [
            "Numaram 0506 333 44 55, doğum tarihim 9 Aralık 1995.",
            "Bir temsilciyle görüşmek istiyorum.",
        ],
    ),
]
TRAILING_SILENCE_S = 1.2
TURN_TIMEOUT_S = 60.0


@dataclass
class TurnRecord:
    dialogue: str
    said: str
    heard: str = ""
    reply: str = ""
    timings: dict[str, float] = field(default_factory=dict)
    client_first_audio_s: float | None = None


def _percentile(values: list[float], q: float) -> float:
    return float(np.percentile(values, q)) if values else float("nan")


async def _read_turn(ws: Any, record: TurnRecord, done: asyncio.Event) -> float | None:
    """Turun olaylarını okur; ilk ses çerçevesinin alındığı anı döndürür."""
    first_audio: float | None = None
    while True:
        raw = await asyncio.wait_for(ws.recv(), TURN_TIMEOUT_S)
        if isinstance(raw, bytes):
            if first_audio is None:
                first_audio = time.perf_counter()
            continue
        payload = json.loads(raw)
        kind = payload["type"]
        if kind == "transcript":
            record.heard = payload["text"]
            if not payload["text"].strip():
                break
        elif kind == "reply":
            record.reply = payload["text"]
        elif kind == "turn_end":
            record.timings = payload["timings"]
            break
        elif kind in ("end", "error"):
            break
    done.set()
    return first_audio


async def _turn(ws: Any, name: str, said: str, clip: AudioClip) -> TurnRecord:
    record = TurnRecord(dialogue=name, said=said)
    pcm16 = float_to_pcm16(clip.samples)
    speech_bytes = (clip.samples.size - int(TRAILING_SILENCE_S * SAMPLE_RATE)) * 2
    chunk = WINDOW * 2
    done = asyncio.Event()
    reader = asyncio.create_task(_read_turn(ws, record, done))
    start = time.perf_counter()
    last_speech_sent = start
    for i in range(0, len(pcm16), chunk):
        await ws.send(pcm16[i : i + chunk])
        if i < speech_bytes:
            last_speech_sent = time.perf_counter()
        # Gerçek zaman hızı: parça süresi kadar bekle.
        target = start + (i + chunk) / 2 / SAMPLE_RATE
        await asyncio.sleep(max(0.0, target - time.perf_counter()))
        if done.is_set():
            break
    try:
        first_audio = await asyncio.wait_for(reader, TURN_TIMEOUT_S)
    except TimeoutError:
        return record  # sunucu yanıt vermedi (ör. konuşma algılanmadı): ölçüm dışı
    if first_audio is not None:
        record.client_first_audio_s = first_audio - last_speech_sent
    return record


async def _run_dialogue(
    url: str, name: str, clips: list[tuple[str, AudioClip]]
) -> list[TurnRecord]:
    from websockets.asyncio.client import connect

    records: list[TurnRecord] = []
    async with connect(url, max_size=2**24) as ws:

        async def next_json(kind: str) -> dict[str, Any]:
            while True:
                raw = await asyncio.wait_for(ws.recv(), TURN_TIMEOUT_S)
                if isinstance(raw, bytes):
                    continue
                payload: dict[str, Any] = json.loads(raw)
                if payload["type"] == kind:
                    return payload

        await next_json("session")
        # Karşılamanın tüm ses çerçeveleri gelene kadar bekle: sonraki turla karışmasın.
        await next_json("reply")
        while True:
            try:
                await asyncio.wait_for(ws.recv(), 0.5)
            except TimeoutError:
                break

        for said, clip in clips:
            record = await _turn(ws, name, said, clip)
            records.append(record)
            # Asistanın sesi çalınırken müşteri susar (yarı çift yönlü, Aşama 5'e kadar).
            await asyncio.sleep(0.5)
            if not record.timings or "temsilci" in record.reply:
                break
    return records


def synthesize_dialogues(tts: TTS) -> list[tuple[str, list[tuple[str, AudioClip]]]]:
    silence = np.zeros(int(TRAILING_SILENCE_S * SAMPLE_RATE), dtype=np.float32)
    out = []
    for name, lines in DIALOGUES:
        clips = []
        for line in lines:
            speech = resample(tts.synthesize(line), SAMPLE_RATE)
            clips.append((line, AudioClip(np.concatenate([speech.samples, silence]), SAMPLE_RATE)))
        out.append((name, clips))
    return out


def prometheus_quantiles(base_url: str, window: str) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    with httpx.Client(base_url=base_url, timeout=10) as client:
        for q in (0.5, 0.95):
            query = (
                f"histogram_quantile({q}, sum by (le, step) "
                f"(increase(voice_turn_step_seconds_bucket[{window}])))"
            )
            data = client.get("/api/v1/query", params={"query": query}).json()
            for series in data["data"]["result"]:
                step = series["metric"]["step"]
                result.setdefault(step, {})[f"p{int(q * 100)}"] = float(series["value"][1])
    return result


def to_markdown(records: list[TurnRecord], prom: dict[str, dict[str, float]] | None) -> str:
    measured = [r for r in records if r.timings]
    lines = [
        "## Gerçek zamanlı akış: tur gecikmesi",
        "",
        f"{len(measured)} tur, {len({r.dialogue for r in records})} diyalog. "
        "Süreler saniye; `first_audio` konuşma sonu → ilk sesin gönderilmesi.",
        "",
        "| Adım | p50 | p95 | En kötü |" + (" Prometheus p50 | Prometheus p95 |" if prom else ""),
        "| --- | --- | --- | --- |" + (" --- | --- |" if prom else ""),
    ]
    for step in STEPS:
        values = [r.timings[step] for r in measured]
        row = (
            f"| {step} | {_percentile(values, 50):.3f} | {_percentile(values, 95):.3f} "
            f"| {max(values, default=float('nan')):.3f} |"
        )
        if prom:
            p = prom.get(step, {})
            row += f" {p.get('p50', float('nan')):.3f} | {p.get('p95', float('nan')):.3f} |"
        lines.append(row)
    client = [r.client_first_audio_s for r in measured if r.client_first_audio_s is not None]
    if client:
        lines.append(
            f"| istemci: son ses → ilk ses | {_percentile(client, 50):.3f} "
            f"| {_percentile(client, 95):.3f} | {max(client):.3f} |" + (" | |" if prom else "")
        )
    if prom:
        lines += [
            "",
            "Prometheus sütunları histogram kovalarından hesaplanır (Grafana panelinin gösterdiği "
            "değer); kova sınırları nedeniyle doğrudan ölçümden biraz farklıdır.",
        ]
    lines += [
        "",
        "### Turlar",
        "",
        "| Diyalog | Söylenen | Duyulan (STT) | Asistan | İlk ses (sn) |",
        "| --- | --- | --- | --- | --- |",
    ]
    for r in records:
        first = f"{r.timings['first_audio']:.2f}" if r.timings else "-"
        reply = r.reply.replace("|", "/")
        lines.append(f"| {r.dialogue} | {r.said} | {r.heard} | {reply} | {first} |")
    return "\n".join(lines) + "\n"


async def run(
    url: str, dialogues: list[tuple[str, list[tuple[str, AudioClip]]]], repeat: int
) -> list[TurnRecord]:
    records: list[TurnRecord] = []
    for _ in range(repeat):
        for name, clips in dialogues:
            records.extend(await _run_dialogue(url, name, clips))
    return records


def main() -> None:
    from voice_agent.audio.tts import PiperTTS, download_piper_voice

    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--url", default="ws://localhost:8000/ws/voice")
    parser.add_argument("--repeat", type=int, default=2)
    parser.add_argument("--prometheus", default=None)
    parser.add_argument("--out", type=Path, default=Path("eval/reports/realtime"))
    args = parser.parse_args()

    tts = PiperTTS(download_piper_voice())
    dialogues = synthesize_dialogues(tts)
    started = time.time()
    records = asyncio.run(run(args.url, dialogues, args.repeat))
    prom = None
    if args.prometheus:
        time.sleep(12)  # son kazıma (5 sn aralık) tamamlansın
        window = f"{int(time.time() - started) + 60}s"
        prom = prometheus_quantiles(args.prometheus, window)

    markdown = to_markdown(records, prom)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "realtime.md").write_text(markdown, encoding="utf-8")
    (args.out / "results.json").write_text(
        json.dumps(
            {"turns": [asdict(r) for r in records], "prometheus": prom},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(markdown)
    first_audio = [r.timings["first_audio"] for r in records if r.timings]
    if first_audio:
        print(f"first_audio p95 = {statistics.quantiles(first_audio, n=20)[-1]:.3f} sn")


if __name__ == "__main__":
    main()

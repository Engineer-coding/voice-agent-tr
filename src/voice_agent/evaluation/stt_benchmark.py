"""STT model karşılaştırması ve dosya tabanlı uçtan uca hat ölçümü.

Ölçülenler:
1. FLEURS Türkçe test setinin ilk N cümlesinde her Whisper boyutu için WER ve gerçek zaman faktörü.
2. Telekom terimleri içeren 30 cümle: Piper ile sentezlenip her modelle yazıya çevrilir
   (sentetik ses; alan terimlerindeki hatayı gösterir, gerçek konuşmacı doğruluğunu değil).
3. Seçilen modelle dosya tabanlı uçtan uca hat: STT → agent → TTS adım süreleri.

Modeller ve veri Hugging Face'ten indirilir; ağ erişimi gerekir.

Kullanım:
    uv run --extra audio python -m voice_agent.evaluation.stt_benchmark --samples 100 \\
        --models tiny base small medium large-v3-turbo --out eval/reports/bench
"""

import argparse
import csv
import json
import platform
import statistics
import tarfile
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from voice_agent.audio.io import AudioClip, read_wav, write_wav
from voice_agent.audio.stt import STT, FasterWhisperSTT
from voice_agent.audio.tts import TTS, PiperTTS, download_piper_voice, synthesize_by_sentence
from voice_agent.evaluation.specs import EVAL_DIR, load_scenarios
from voice_agent.evaluation.wer import corpus_wer, normalize_tr

FLEURS_REPO = "google/fleurs"


@dataclass(frozen=True)
class Utterance:
    id: str
    reference: str
    clip: AudioClip


@dataclass(frozen=True)
class ModelResult:
    model: str
    fleurs_wer: float
    fleurs_rtf_mean: float
    fleurs_rtf_p95: float
    telecom_wer: float
    load_s: float
    samples: int
    worst_examples: list[tuple[str, str]]


def load_fleurs(samples: int) -> list[Utterance]:
    from huggingface_hub import hf_hub_download

    tsv = hf_hub_download(FLEURS_REPO, "data/tr_tr/test.tsv", repo_type="dataset")
    with Path(tsv).open(encoding="utf-8") as fh:
        rows = list(csv.reader(fh, delimiter="	", quoting=csv.QUOTE_NONE))
    rows = sorted(rows, key=lambda r: r[1])[:samples]
    wanted = {r[1]: r for r in rows}
    archive = hf_hub_download(FLEURS_REPO, "data/tr_tr/audio/test.tar.gz", repo_type="dataset")
    utterances: list[Utterance] = []
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar:
            name = Path(member.name).name
            if name in wanted and member.isfile():
                data = tar.extractfile(member)
                assert data is not None
                with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
                    tmp.write(data.read())
                    tmp.flush()
                    clip = read_wav(Path(tmp.name))
                row = wanted[name]
                utterances.append(Utterance(id=row[0], reference=row[2], clip=clip))
    return sorted(utterances, key=lambda u: u.id)


def telecom_set(tts: TTS) -> list[Utterance]:
    sentences = (EVAL_DIR / "telecom_sentences.txt").read_text(encoding="utf-8").splitlines()
    return [
        Utterance(id=f"telekom-{i:02d}", reference=s, clip=tts.synthesize(s))
        for i, s in enumerate((s for s in sentences if s.strip()), start=1)
    ]


def _p95(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(0.95 * (len(ordered) - 1)))]


def evaluate_model(size: str, fleurs: list[Utterance], telecom: list[Utterance]) -> ModelResult:
    start = time.perf_counter()
    stt = FasterWhisperSTT(size)
    load_s = time.perf_counter() - start
    pairs: list[tuple[str, str]] = []
    rtfs: list[float] = []
    for utt in fleurs:
        result = stt.transcribe(utt.clip)
        pairs.append((utt.reference, result.text))
        rtfs.append(result.rtf)
    telecom_pairs = [(u.reference, stt.transcribe(u.clip).text) for u in telecom]
    worst = sorted(
        telecom_pairs + pairs,
        key=lambda p: corpus_wer([p]),
        reverse=True,
    )[:3]
    return ModelResult(
        model=size,
        fleurs_wer=corpus_wer(pairs),
        fleurs_rtf_mean=statistics.fmean(rtfs),
        fleurs_rtf_p95=_p95(rtfs),
        telecom_wer=corpus_wer(telecom_pairs),
        load_s=load_s,
        samples=len(fleurs),
        worst_examples=[(normalize_tr(r), normalize_tr(h)) for r, h in worst],
    )


def end_to_end(stt: STT, tts: TTS, out_dir: Path) -> list[dict[str, object]]:
    """Fatura senaryosunun müşteri cümlelerini sentezleyip dosya hattından geçirir."""
    from fastapi.testclient import TestClient

    from mock_crm.app import create_app
    from mock_crm.db import CRMRepository
    from mock_crm.seed import seed
    from voice_agent.audio.pipeline import FilePipeline
    from voice_agent.dialogue.agent import DialogueAgent
    from voice_agent.dialogue.rule_based import RuleBasedLLM
    from voice_agent.evaluation.runner import EVAL_TODAY
    from voice_agent.tools.crm_client import CRMClient

    scenario = next(s for s in load_scenarios() if s.id == "paket-01-daha-fazla-internet")
    rows: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "crm.sqlite3"
        seed(db, customers=10, today=EVAL_TODAY)
        with TestClient(create_app(CRMRepository(db))) as http:
            agent = DialogueAgent(RuleBasedLLM(), CRMClient(http))
            pipeline = FilePipeline(stt, agent, tts)
            pipeline.greet(out_dir / "00-asistan.wav")
            for i, text in enumerate(scenario.turns, start=1):
                user_wav = out_dir / f"{i:02d}-musteri.wav"
                write_wav(user_wav, synthesize_by_sentence(tts, text).clip)
                result = pipeline.process(user_wav, out_dir / f"{i:02d}-asistan.wav")
                rows.append(
                    {
                        "musteri": text,
                        "stt": result.transcript,
                        "asistan": result.reply,
                        **{k: round(v, 3) for k, v in asdict(result.timings).items()},
                        "ilk_ses_s": round(result.timings.to_first_audio_s, 3),
                    }
                )
    return rows


def to_markdown(results: list[ModelResult], e2e: list[dict[str, object]], e2e_model: str) -> str:
    lines = [
        "## STT model karşılaştırması",
        "",
        f"Makine: {platform.processor() or platform.machine()}, CPU, int8, beam_size=1, "
        f"FLEURS Türkçe test setinin ilk {results[0].samples} cümlesi.",
        "",
        "| Model | FLEURS WER | Telekom WER (sentetik) | RTF ort. | RTF p95 | Yükleme (sn) |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for r in results:
        lines.append(
            f"| {r.model} | {r.fleurs_wer:.1%} | {r.telecom_wer:.1%} | {r.fleurs_rtf_mean:.3f} | "
            f"{r.fleurs_rtf_p95:.3f} | {r.load_s:.1f} |"
        )
    lines += [
        "",
        "RTF (gerçek zaman faktörü) = işlem süresi / ses süresi; 1'in altı gerçek zamandan hızlı.",
        "Telekom WER, Piper ile sentezlenmiş 30 alan cümlesi üzerindedir; gerçek konuşmacı",
        "doğruluğunu değil, alan terimlerindeki hatayı gösterir.",
        "",
        f"## Dosya tabanlı uçtan uca hat ({e2e_model})",
        "",
        "| Müşteri | STT çıktısı | STT (sn) | Agent (sn) | TTS ilk cümle (sn) | İlk ses (sn) |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in e2e:
        lines.append(
            f"| {row['musteri']} | {row['stt']} | {row['stt_s']} | {row['agent_s']} | "
            f"{row['tts_first_sentence_s']} | {row['ilk_ses_s']} |"
        )
    lines += [
        "",
        "İlk ses süresi akışsız bir alt sınırdır: STT konuşma bitince başlar ve LLM yerine kural",
        "tabanlı agent kullanılır. Akışlı STT ve gerçek LLM Aşama 4'te ölçülecek.",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=100)
    parser.add_argument("--models", nargs="+", default=["tiny", "base", "small", "medium"])
    parser.add_argument("--e2e-model", default="small")
    parser.add_argument("--out", type=Path, default=Path("eval/reports/bench"))
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)

    tts = PiperTTS(download_piper_voice())
    fleurs = load_fleurs(args.samples)
    telecom = telecom_set(tts)
    print(f"FLEURS: {len(fleurs)} cümle, telekom: {len(telecom)} cümle", flush=True)

    results: list[ModelResult] = []
    for size in args.models:
        print(f"Model ölçülüyor: {size}", flush=True)
        results.append(evaluate_model(size, fleurs, telecom))
        print(json.dumps(asdict(results[-1]), ensure_ascii=False), flush=True)

    e2e = end_to_end(FasterWhisperSTT(args.e2e_model), tts, args.out / "e2e")
    markdown = to_markdown(results, e2e, args.e2e_model)
    (args.out / "benchmarks.md").write_text(markdown, encoding="utf-8")
    (args.out / "results.json").write_text(
        json.dumps(
            {"models": [asdict(r) for r in results], "end_to_end": e2e},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(markdown)


if __name__ == "__main__":
    main()

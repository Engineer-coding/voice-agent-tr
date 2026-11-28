# voice-agent-tr

Telekom müşteri hizmetleri için Türkçe, gerçek zamanlı, araya girilebilen ve araç kullanan sesli asistan.

> Durum: Aşama 3 (dosya tabanlı ses hattı ve STT ölçümü). Ayrıntılı plan ve kurallar için [CLAUDE.md](CLAUDE.md).

## Hızlı başlangıç

Gereksinimler: [uv](https://docs.astral.sh/uv/), Docker.

```bash
make install      # bağımlılıklar
make check        # lint + tip denetimi + testler
make chat         # terminalden asistanla yazış (API anahtarı gerekmez)
make up           # Docker Compose ile ağ geçidi + sahte CRM + Redis
curl localhost:8000/health
```

Demo müşteri (kurgusal): telefon `0532 123 45 67`, doğum tarihi `14.05.1990`.

## Diyalog yöneticisi

LangGraph üzerinde bir durum makinesi: karşılama → kimlik doğrulama → niyet →
fatura / paket değişikliği → onay / arıza kaydı → kapanış veya temsilciye devir.

- Her aşamada LLM yalnızca o aşamaya izinli araçları görür; izin kontrolü kodda yapılır
  ([ADR 0002](docs/adr/0002-durum-makinesi-ve-arac-izinleri.md)).
- Paket değişikliğini LLM değil sistem yapar ve yalnızca müşterinin açık "evet" cevabından sonra.
- Testler betikli sahte bir LLM ile kötü niyetli araç çağrılarının engellendiğini kanıtlar.

Geliştirme için pre-commit kancalarını kurun:

```bash
uv run pre-commit install
```

## Hedef ölçütler

| Ölçüt | Hedef (CPU) |
| --- | --- |
| Yanıt gecikmesi (konuşma sonu → ilk ses) | p95 < 2,5 sn |
| Görev başarısı (30 senaryo) | ≥ %85 |
| Araya girme tepkisi | < 300 ms |
| Injection direnci (25 saldırı) | %100 engellenir |
| STT hatası (WER, FLEURS Türkçe) | `small`: %17,3 ([ölçümler](docs/benchmarks.md)) |

## Değerlendirme

`make eval` 30 diyalog senaryosunu ve 25 prompt injection saldırısını çalıştırır, raporu
`eval/reports/` altına yazar ve CI'da her PR'da çalışır
([ADR 0003](docs/adr/0003-degerlendirme-ve-ele-gecirilmis-llm.md)).

Saldırılar iki kipte denenir: agent'ın kendi LLM'iyle ve saldırgana tamamen itaat eden
"ele geçirilmiş" bir LLM'le. İkinci kip, korumanın modelden bağımsız olarak kodda olduğunu ölçer.

Güncel sonuçlar (kural tabanlı LLM, henüz gerçek model bağlı değil):

| Ölçüt | Sonuç |
| --- | --- |
| Görev başarısı | 30/30 |
| Injection direnci (normal / ele geçirilmiş LLM) | 25/25 / 25/25 |
| Yetkisiz araç çağrısı | 0 |

## Ses hattı

Dosya tabanlı hat: WAV → faster-whisper (CPU, int8) → diyalog yöneticisi → Piper TTS (cümle cümle).
Varsayılan STT modeli `small`; `large-v3-turbo` daha doğru ama kısa bir yanıtta 4 çekirdekte
~6 sn sürüyor ([ADR 0004](docs/adr/0004-stt-modeli-secimi.md), [ölçümler](docs/benchmarks.md)).

```bash
uv sync --extra audio   # faster-whisper, Piper
make bench-stt          # model karşılaştırması + uçtan uca hat (uzun sürer; CI'da da çalışır)
```

## KVKK notu

Ses izi biyometrik veridir ve KVKK'da özel nitelikli kişisel veri sayılır. Bu projede gerçek müşteri
verisi kullanılmaz; konuşmacı doğrulama için yalnızca açık rızayla kaydedilmiş sesler kullanılır.

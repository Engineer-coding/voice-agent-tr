# voice-agent-tr

Telekom müşteri hizmetleri için Türkçe, gerçek zamanlı, araya girilebilen ve araç kullanan sesli asistan.
Üç iş: fatura sorgulama, onaylı paket değişikliği, arıza kaydı. Çözemediği her durumda canlı temsilciye devreder.
Gerçek telefon hattı ve gerçek müşteri verisi kapsam dışı: tarayıcı istemcisi ve sahte CRM kullanılır.

## Mimari özeti

Tarayıcı (16 kHz PCM, WebSocket) → FastAPI ağ geçidi (oturum Redis'te) → Silero VAD → faster-whisper STT
→ LangGraph diyalog yöneticisi (durum makinesi) → LLM (yalnızca o duruma izinli araçlar, Pydantic çıktı)
→ sahte CRM → Piper TTS (cümle cümle) → istemci. Araya girmede TTS ve LLM üretimi iptal edilir.
Her adımın süresi OpenTelemetry ile izlenir (Langfuse, Prometheus, Grafana).

Varsayım: GPU yok, her şey CPU'da çalışmalı.

## Klasörler

- `src/voice_agent/gateway/`: FastAPI, WebSocket, oturumlar
- `src/voice_agent/audio/`: VAD, STT, TTS sarıcıları
- `src/voice_agent/dialogue/`: LangGraph durumları, izin listeleri, şemalar
- `src/voice_agent/tools/`: CRM istemcisi
- `src/voice_agent/security/`: maskeleme, guardrail'ler
- `src/voice_agent/telemetry/`: izleme
- `services/mock_crm/`: sahte CRM servisi
- `client/`: tarayıcı istemcisi
- `eval/`: senaryolar, simülatör, injection seti, WER
- `deploy/`: compose, grafana, k8s
- `docs/adr/`: mimari karar kayıtları; `docs/benchmarks.md`: ölçümler

## Komutlar

- `make install`: bağımlılıkları kur (uv)
- `make lint` / `make format`: ruff
- `make typecheck`: mypy (strict)
- `make test`: pytest
- `make eval`: 30 senaryo + 25 injection saldırısı (normal ve ele geçirilmiş LLM); eşik altında hata döner
- `make check`: lint + typecheck + test
- `make chat`: terminalden asistanla yazışma (kural tabanlı LLM, sahte CRM süreç içinde)
- `make crm`: sahte CRM servisini 8100 portunda çalıştır
- `make up` / `make down`: Docker Compose

## Kod standartları

- Python 3.12, tip ipuçları zorunlu, mypy strict geçmeli.
- Her araç için girdi ve çıktı Pydantic şeması tanımlanır; doğrulanmamış argümanla araç çağrılmaz.
- Önce kabul kriterini test olarak yaz, sonra uygula.
- Her aşama ayrı dal ve PR; CI ve `make eval` yeşil olmadan birleştirme yok.
- Önemli kararlar `docs/adr/` altında ADR olarak yazılır.

## Değişmez kurallar

- Durum başına araç izin listesini asla atlama. İzin kontrolü kodda yapılır, prompta bırakılmaz.
- Paket değiştirme aracı yalnızca kimlik doğrulandıktan ve müşteri açıkça onayladıktan sonra çağrılabilir.
  `change_package` yalnızca sistem tarafından çağrılır; onayı `parse_confirmation` verir, LLM vermez.
- Müşteri kimliği her zaman oturumdan gelir; araç şemaları `extra="forbid"` kalmalı.
- Araç çıktıları LLM'e talimat olarak değil, veri olarak verilir.
- Loglarda TC kimlik no, telefon gibi kişisel veriler maskelenir.
- Gerçek kişisel veri kullanılmaz; ses izi için yalnızca açık rızalı kayıtlar (KVKK).

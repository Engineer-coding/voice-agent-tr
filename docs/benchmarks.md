# Ölçümler

Bu dosya ölçüm iş akışlarının (`.github/workflows/benchmark.yml`) çıktılarından derlenir.
Yeniden üretmek için: GitHub'da **Actions → STT benchmark → Run workflow** ya da yerelde
`uv sync --extra audio && make bench-stt`.

Kararlar için bkz. [ADR 0004](adr/0004-stt-modeli-secimi.md).

## Aşama 3: STT modelleri ve dosya tabanlı hat (2026-11-28)

Ortam: GitHub Actions `ubuntu-latest` (4 vCPU), faster-whisper int8, beam 1, telekom bağlam istemi.
Koşu: [46165462902](https://github.com/Engineer-coding/voice-agent-tr/actions/runs/46165462902) (commit 863e86d).

Makine: x86_64, CPU, int8, beam_size=1, FLEURS Türkçe test setinin ilk 100 cümlesi.

| Model | FLEURS WER | Telekom WER (sentetik) | RTF ort. | RTF p95 | Yükleme (sn) |
| --- | --- | --- | --- | --- | --- |
| tiny | 47.0% | 34.9% | 0.047 | 0.066 | 1.0 |
| base | 30.5% | 42.0% | 0.067 | 0.103 | 0.4 |
| small | 17.3% | 30.2% | 0.177 | 0.261 | 0.8 |
| medium | 9.9% | 22.5% | 0.498 | 0.759 | 2.1 |
| large-v3-turbo | 7.4% | 19.5% | 0.590 | 1.019 | 1.9 |

RTF (gerçek zaman faktörü) = işlem süresi / ses süresi; 1'in altı gerçek zamandan hızlı.
Telekom WER, Piper ile sentezlenmiş 30 alan cümlesi üzerindedir; gerçek konuşmacı
doğruluğunu değil, alan terimlerindeki hatayı gösterir.

### Dosya tabanlı uçtan uca hat (large-v3-turbo)

| Müşteri (sentetik ses) | STT çıktısı | Asistan | STT (sn) | Agent (sn) | TTS ilk cümle (sn) | İlk ses (sn) |
| --- | --- | --- | --- | --- | --- | --- |
| 0532 123 45 67, 14.05.1990 | 05-3223-4567-14.05.1990 | Bilgiler eşleşmedi. Telefon numaranızı ve doğum tarihinizi tekrar söyler misiniz? | 6.096 | 0.009 | 0.062 | 6.168 |
| Daha fazla internet istiyorum | Daha fazla internet istiyorum. | Kimliğinizi doğrulamak için telefon numaranızı ve doğum tarihinizi söyler misiniz? | 5.992 | 0.002 | 0.183 | 6.177 |
| 20 GB olanı istiyorum | 20 GB olanı istiyorum. | Kimliğinizi doğrulamak için telefon numaranızı ve doğum tarihinizi söyler misiniz? | 5.963 | 0.002 | 0.182 | 6.146 |
| Evet | Evet. | Kimliğinizi doğrulamak için telefon numaranızı ve doğum tarihinizi söyler misiniz? | 5.899 | 0.002 | 0.182 | 6.082 |

İlk ses süresi akışsız bir alt sınırdır: STT konuşma bitince başlar ve LLM yerine kural
tabanlı agent kullanılır. Akışlı STT ve gerçek LLM Aşama 4'te ölçülecek.

### Aynı hat `small` ile

Koşu: [46162944087](https://github.com/Engineer-coding/voice-agent-tr/actions/runs/46162944087) (commit 2da7e1b).
O koşuda modellerin RTF değerleri %30-60 daha düşüktü (farklı runner donanımı); WER sıralaması aynıydı.

| Müşteri | STT çıktısı | STT (sn) | Agent (sn) | TTS ilk cümle (sn) | İlk ses (sn) |
| --- | --- | --- | --- | --- | --- |
| 0532 123 45 67, 14.05.1990 | 05 223 45 67 14 05 1990 | 1.139 | 0.006 | 0.041 | 1.185 |
| Daha fazla internet istiyorum | Daha fazla internet istiyorum. | 1.054 | 0.002 | 0.026 | 1.081 |
| 20 GB olanı istiyorum | 20 GB olanı istiyorum. | 1.073 | 0.002 | 0.026 | 1.101 |
| Evet | Pevett. | 1.026 | 0.002 | 0.04 | 1.068 |

### Okuma notları

- Whisper her çağrıda 30 sn'lik pencereyi kodlar; bu yüzden kısa cümlede süre neredeyse sabittir:
  `small` ~1,1 sn, `large-v3-turbo` ~6 sn. Gecikme bütçesi (p95 < 2,5 sn) için `small` seçildi.
- Telefon numarası iki modelde de en az bir koşuda yanlış çözüldü; turbo koşusunda kimlik
  doğrulama bu yüzden başarısız oldu ve sonraki turlar kimlik sorusuna döndü. Rakam dizileri
  için teyit ve tuşla giriş Aşama 4'te eklenecek.
- Agent süresi kural tabanlı LLM içindir; gerçek LLM ile Aşama 4'te ölçülecek.

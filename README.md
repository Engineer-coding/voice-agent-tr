# voice-agent-tr

Telekom müşteri hizmetleri için Türkçe, gerçek zamanlı, araya girilebilen ve araç kullanan sesli asistan.

> Durum: Aşama 0 (proje iskeleti). Ayrıntılı plan ve kurallar için [CLAUDE.md](CLAUDE.md).

## Hızlı başlangıç

Gereksinimler: [uv](https://docs.astral.sh/uv/), Docker.

```bash
make install      # bağımlılıklar
make check        # lint + tip denetimi + testler
make up           # Docker Compose ile ağ geçidi + Redis
curl localhost:8000/health
```

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
| STT hatası (WER, FLEURS Türkçe) | Ölçülüp iyileştirilecek |

## KVKK notu

Ses izi biyometrik veridir ve KVKK'da özel nitelikli kişisel veri sayılır. Bu projede gerçek müşteri
verisi kullanılmaz; konuşmacı doğrulama için yalnızca açık rızayla kaydedilmiş sesler kullanılır.

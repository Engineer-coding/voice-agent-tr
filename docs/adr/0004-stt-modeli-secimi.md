# 0004: STT modeli seçimi (faster-whisper, CPU)

- Durum: Kabul edildi (Aşama 4'teki akışlı ölçümle yeniden değerlendirilecek)
- Tarih: 2026-11-28

## Bağlam

Asistan GPU'suz çalışmalı. Hedef: müşteri sustuktan sonra ilk ses için p95 < 2,5 sn.
Aşama 3 ölçümünde agent ve TTS'in ilk cümlesi birlikte 0,2 sn'nin altında kaldı; bütçeyi STT belirliyor.
Öte yandan yanlış anlaşılan bir telefon numarası kimlik doğrulamayı, yanlış anlaşılan "evet"
onayı bozar.

Ölçüm yöntemi ve tüm tablolar `docs/benchmarks.md` içinde (GitHub Actions 4 vCPU, int8, beam 1).

## Karar

1. Varsayılan model `small` (int8, beam 1, telekom bağlam istemiyle).
2. `large-v3-turbo` daha fazla çekirdekli makineler için yapılandırmayla seçilebilir kalır.
3. Kimlik bilgisi gibi rakam dizileri STT'ye tek başına bırakılmaz: Aşama 4'te telefon numarası
   müşteriye okunup teyit edilir ve tarayıcı istemcisinde tuşla girme seçeneği olur.

## Gerekçe ve alternatifler

| Model | FLEURS WER | Telekom WER | RTF ort. | Kısa cümlede STT süresi |
|---|---|---|---|---|
| tiny | 47,0% | 34,9% | 0,047 | ölçülmedi |
| base | 30,5% | 42,0% | 0,067 | ölçülmedi |
| small | 17,3% | 30,2% | 0,177 | ~1,1 sn |
| medium | 9,9% | 22,5% | 0,498 | ölçülmedi |
| large-v3-turbo | 7,4% | 19,5% | 0,590 | ~6,0 sn |

- Doğrulukta açık ara en iyisi `large-v3-turbo`. İlk taslakta bu yüzden onu seçmiştik.
- Ancak uçtan uca ölçüm gösterdi ki Whisper her çağrıda 30 sn'lik pencereyi kodluyor: "Evet"
  gibi bir saniyelik bir yanıt da turbo ile 4 vCPU'da ~6 sn sürüyor. Bu, 2,5 sn bütçesinin
  iki katından fazla. `medium` da aynı sorunu taşıyor.
- `small` aynı yanıtlarda ~1,1 sn, bütçe içinde ve akış, LLM ve ağ için pay bırakıyor.
- `tiny` ve `base` Türkçede kullanılamayacak kadar hatalı.
- Telefon numarasını iki model de en az bir koşuda yanlış yazdı (`small`: "05 223 45 67",
  turbo: "05-3223-4567"). Yani daha büyük model bu sorunu tek başına çözmüyor; çözüm teyit ve
  tuşla giriş (Karar 3).
- Aynı iş akışı iki koşuda farklı makinelere düştü ve RTF %30-60 oynadı. Göreli sıra
  güvenilir, mutlak değerler makineye bağlı.

Telekom WER'i olduğundan yüksek görünür: referanslar sayıları yazıyla, STT rakamla yazıyor ve
Piper bazı ekleri farklı telaffuz ediyor.

## Sonuçlar

- Olumlu: gecikme bütçesi içinde, model küçük (~480 MB) ve hızlı yükleniyor.
- Olumsuz: `small` "Evet"i bir koşuda "Pevett." yazdı. Onay ayrıştırıcısı bunu "evet" saymaz,
  güvenli tarafta kalır ama müşteriye soruyu tekrarlatır. Aşama 4'te onay için kısa
  ifadelere odaklı ek önlemler (bağlam istemi, tekrar sorma sınırı) ölçülecek.
- Akışlı çözümleme ve VAD ile cümle sonunun erken yakalanması Aşama 4'te ölçülüp bu ADR'yi günceller.

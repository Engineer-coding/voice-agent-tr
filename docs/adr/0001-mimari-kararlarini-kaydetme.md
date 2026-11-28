# 0001: Mimari kararlarını ADR ile kaydetme

- Durum: Kabul edildi
- Tarih: 2026-11-28

## Bağlam

Proje birçok teknoloji seçimi içeriyor (STT modeli, ses taşıma, diyalog yöneticisi). Bu seçimlerin
gerekçesi sonradan unutulursa değişiklikler rastgele yapılır.

## Karar

Önemli her karar `docs/adr/NNNN-baslik.md` biçiminde, `0000-sablon.md` şablonuyla yazılır.

## Gerekçe ve alternatifler

Alternatif olarak kararları README'de veya PR açıklamalarında tutmak düşünüldü. ADR'ler tek yerde,
numaralı ve değiştirilemez kayıt sağlar; bir karar değişirse yeni ADR eskisinin yerini alır.

## Sonuçlar

Her önemli PR'da küçük bir yazma maliyeti doğar. Karşılığında "neden bunu seçtik" sorusunun cevabı
her zaman repoda bulunur.

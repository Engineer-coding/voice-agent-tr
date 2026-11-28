# 0002: Diyalog için durum makinesi ve kodda zorunlu araç izinleri

- Durum: Kabul edildi
- Tarih: 2026-11-28

## Bağlam

Asistan müşteri adına geri alınamaz işlemler yapabiliyor (paket değişikliği). Serbest dolaşan bir
agent'ta hangi aracın ne zaman çağrılacağına LLM karar verir; prompt injection ile ele geçirilen
bir LLM yetkisiz işlem yapabilir.

## Karar

1. Diyalog LangGraph üzerinde açık aşamalardan oluşan bir durum makinesidir: karşılama →
   kimlik doğrulama → niyet → (fatura | paket değişikliği → onay | arıza) → kapanış veya devir.
2. Her aşamanın izinli araç listesi `dialogue/policy.py` içindedir. LLM'e yalnızca bu araçlar
   gösterilir ve başka bir çağrı kodda reddedilir.
3. `change_package` yalnızca sistem tarafından çağrılabilir. Müşterinin "evet" cevabı LLM'e değil
   kural tabanlı `parse_confirmation` fonksiyonuna sorulur.
4. Müşteri kimliği her zaman oturumdan alınır. Araç şemaları `extra="forbid"` olduğu için LLM
   `customer_id` gibi bir alan ekleyemez.
5. Araç sonuçları ve hataları geçmişe `tool` rolünde veri olarak eklenir, talimat olarak değil.
6. LLM bir arayüzün arkasındadır (`dialogue/llm.py`). Testler betikli bir sahte LLM ile, demo
   ise ağ gerektirmeyen kural tabanlı bir LLM ile çalışır.

## Gerekçe ve alternatifler

- Elle yazılmış durum makinesi de mümkündü; LangGraph aşamaları ve geçişleri açık bir graf
  olarak gösterir ve sonraki aşamalarda akış/iptal desteği sunar.
- Onayı LLM'e sınıflandırtmak daha esnek olurdu, ancak "müşteri onayladı" diyen bir saldırı
  metni LLM'i kandırabilir. Geri alınamaz işlemde esneklik yerine güvenlik seçildi.

## Sonuçlar

- Güvenlik kuralları birim testlerle kanıtlanabilir (aşama × araç izin matrisi testi).
- Kural tabanlı onay, "evet ama..." gibi karmaşık cevaplarda müşteriden tekrar onay ister.
- Yeni bir iş türü eklemek için yeni aşama, izin listesi ve geçiş tanımlamak gerekir.

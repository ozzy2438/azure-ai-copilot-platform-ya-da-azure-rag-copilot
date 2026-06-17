# RegDesk Azure RAG Copilot - Baştan Sona Anlatım

Bu doküman, projeyi hiç bilmeyen birine anlatmak için yazıldı.
Amacı sadece "hangi dosya ne yapıyor" demek değil; neden bu yola çıktık,
hangi Azure servislerini kullandık, nerelerde hata aldık ve sistemi nasıl
daha güvenli hale getirdik, bunları adım adım kafaya oturtmak.

## 1. Projeyi Bir Cümleyle Anlatırsak

Bu proje, bir finansal hizmetler şikayetini alır, kişisel bilgileri temizler,
şikayetin türünü basitçe sınıflandırır, ASIC RG 271 dokümanından ilgili
kuralları bulur, Azure OpenAI ile kaynaklı bir iç işlem notu üretir ve sonucu
Azure Functions üzerinden API olarak döner.

Daha basit anlatımla:

Bir müşteri "firma bana 3 haftadır cevap vermedi" dediğinde sistem şunu yapar:

1. E-posta, telefon gibi kişisel bilgileri gizler.
2. Bunun muhtemelen bir "service_delay" yani hizmet gecikmesi olduğunu anlar.
3. RG 271 dokümanında cevap süreleri ve gecikme bildirimiyle ilgili parçaları bulur.
4. Modelden, sadece bu bulunan kaynaklara dayanarak kısa bir iç not yazmasını ister.
5. Notta kullanılan kaynakları `rg271-XXXX` şeklinde gösterir.
6. İnsan incelemesi gerekiyorsa JSON içinde `needs_human_review: true` döner.
7. Audit kaydı tutar, ama şikayetin kendisini değil sadece hash'ini saklar.

## 2. Neden Bu Projeye Başladık?

Yola çıkış amacımız, Azure üzerinde çalışan küçük ama gerçekçi bir RAG copilot
platformu kurmaktı.

Buradaki "RAG" şu demek:

- Model her şeyi kafadan uydurmasın.
- Önce güvenilir dokümandan ilgili parçalar bulunsun.
- Sonra model sadece bu parçaları kullanarak cevap versin.
- Cevapta kaynak gösterilsin.

Bu projede güvenilir kaynak olarak ASIC Regulatory Guide 271 kullanıldı.
Bu rehber, finansal hizmetlerde iç uyuşmazlık çözümü ve şikayet yönetimi
kurallarını anlatıyor.

Bizim hedefimiz bir "genel sohbet botu" yapmak değildi. Daha dar, daha kontrollü,
daha açıklanabilir bir sistem yapmak istedik:

- Şikayet yönetimi alanına odaklı.
- RG 271 kaynaklı.
- Kişisel verileri mümkün olduğunca azaltan.
- Hukuki karar vermeyen.
- İnsan incelemesini gerektiğinde açıkça isteyen.
- Audit izi bırakan.

## 3. Çocuğa Anlatır Gibi Büyük Resim

Sistemi bir okul ödevi yardımcısı gibi düşünebiliriz.

Elimizde kalın bir kitap var: ASIC RG 271.

Bir çocuk gelip şöyle soruyor:

"Ben öğretmene üç hafta önce sordum ama hala cevap alamadım. Ne yapmalıyım?"

Akıllı yardımcımız doğrudan cevap uydurmuyor. Önce kitabın ilgili sayfalarını
buluyor. Sonra sadece o sayfalara bakarak şöyle diyor:

"Bu durumda önce hangi şikayet türü olduğunu ve başvuru tarihini doğrulamak
gerekir. Bazı şikayetlerde genel süre 30 takvim günü olabilir, ama bunu
şikayet türüne göre doğrulamak gerekir. İnsan incelemesi gerekir."

Yani sistemin ana prensibi şu:

Bilmediğin şeyi biliyormuş gibi söyleme. Önce kaynağa bak. Emin değilsen
insana gönder.

## 4. Azure Öncesi Dönem: Temeli Yerelde Kurduk

Azure'a gitmeden önce şu parçaları yerelde kurduk:

- PDF metnini çıkarma.
- Metni sayfalara ve bloklara bölme.
- Blokları daha küçük kaynak birimlerine ayırma.
- LLM yardımıyla anlamlı chunk'lar oluşturma.
- Bu chunk'ları JSON dosyası olarak hazırlama.
- Retrieval, generation ve test script'leriyle mantığı doğrulama.

Bu aşamada asıl sorumuz şuydu:

"RG 271 gibi uzun bir dokümanı modele tek seferde vermeden, ihtiyaç olduğunda
doğru parçasını nasıl buluruz?"

Bu yüzden ingestion pipeline'ı kuruldu.

## 5. Ingestion Nedir?

Ingestion, dokümanı sisteme yedirmek demektir.

Bu projede ingestion şu sırayla çalışır:

1. `ingestion/prepare_rg271.py`
   - `rg271.pdf` dosyasından metin çıkarır.
   - Her sayfayı `--- PAGE X ---` etiketiyle ayırır.
   - Sonucu `ingestion/data/rg271.txt` içine yazar.

2. `ingestion/prepare_source_blocks.py`
   - Sayfa işaretli metni okur.
   - Paragrafları temizler.
   - Her parçaya `B00001`, `B00002` gibi block ID verir.
   - Sonucu `rg271_source_blocks.json` olarak kaydeder.

3. `ingestion/agentic_chunking.py`
   - Büyük metni küçük, izlenebilir kaynak birimlerine böler.
   - Front matter yani kapak, içindekiler gibi sayfaları dışarıda bırakır.
   - Azure OpenAI ile bu küçük birimleri anlamlı chunk'lara gruplar.
   - Modelin kaynak metni yeniden yazmasına izin vermez.
   - Final chunk içeriğini Python, orijinal kaynak birimlerinden yeniden kurar.

4. `ingestion/chunk_and_index.py`
   - Hazırlanan chunk'ları embedding'e çevirir.
   - Azure AI Search index'ini oluşturur.
   - Chunk'ları Azure AI Search'e yükler.

## 6. Chunk Ne Demek?

Chunk, uzun dokümanın daha küçük ve anlamlı bir parçasıdır.

Örnek:

- "Acknowledgement of complaint" ayrı bir konu olabilir.
- "Maximum IDR response timeframes" ayrı bir konu olabilir.
- "IDR delay notification" ayrı bir konu olabilir.

Modelden cevap isterken bütün RG 271'i vermiyoruz. Sadece soruyla ilgili
chunk'ları veriyoruz.

Bu hem daha ucuz, hem daha hızlı, hem de daha güvenlidir.

## 7. İlk Stratejimiz ve Sonra Düzelttiğimiz Yerler

Başta daha basit bir chunking yaklaşımı vardı. Ama hızlıca şunu gördük:

Basit bölme bazen iyi çalışmıyor.

Çünkü mevzuat dokümanlarında:

- Başlıklar var.
- Notlar var.
- Tablolar var.
- RG 271.2 gibi madde numaraları var.
- Aynı sayfada birden fazla konu olabiliyor.

Bu yüzden agentic chunking stratejisine geçtik.

Yani modele dedik ki:

"Sen kaynak metni yazma. Sadece bu küçük kaynak birimlerini nasıl gruplayacağını
söyle. Her ID tam bir kez kullanılacak. Sıra bozulmayacak. Eksik olmayacak."

Sonra Python bu plana göre asıl chunk içeriğini orijinal metinden kurdu.

Bu çok önemli bir tasarım kararıydı:

Model chunk içeriğini üretmiyor. Model sadece gruplama kararı veriyor.

Böylece kaynak metin korunuyor.

## 8. Agentic Chunking Aşamasında Yaşanan Hatalar

Bu bölüm önemli, çünkü sistemin neden bugünkü hale geldiğini gösteriyor.

### 8.1 IndentationError

Bir aşamada `build_source_units()` içinde girinti bozuldu.

Hata:

```text
IndentationError: expected an indented block after 'for' statement
```

Sebep basitti:

`for page_block in page_blocks:` satırından sonraki kod bir seviye içeride
olmalıydı.

Düzeltince prepare-only akışı çalıştı.

### 8.2 Yanlış Madde Bölme

Başta `RG 271.\d+` gördüğümüz her yerde bölüyorduk. Bu bazen yanlış yerde
kesmeye neden olabiliyordu.

Sonra regex'i şuna yaklaştırdık:

```text
RG 271.2 Most financial firms...
RG 271.3 A modified regulatory regime...
```

Yani sadece gerçek madde başlangıçlarını ayırmaya çalıştık.

### 8.3 Çok Büyük Final Chunk

Bir model planı bazı kaynak birimlerini fazla büyük tek chunk altında topladı.

Hata:

```text
Agent created an oversized final chunk
```

Bunun üzerine `MAX_FINAL_CHUNK_CHARS` kuralı eklendi.

Sonra sadece hata vermek yerine, gerekirse büyük planlı chunk'ı bitişik kaynak
birimi gruplarına bölme mantığı eklendi.

### 8.4 Model Bazı Unit ID'leri Atladı

Bir noktada model `U00111` gibi bir source unit ID'yi atladı.

Hata:

```text
Agent plan failed source coverage validation.
Expected: [...]
Returned: [...]
```

Bunun üzerine retry/repair mekanizması eklendi.

Sistem artık modele şöyle diyor:

"Planın doğrulamadan geçmedi. Tüm ID'leri tam bir kez, aynı sırayla döndür."

Bu, agentic chunking'i daha güvenilir yaptı.

## 9. Azure AI Search Ne İşe Yarıyor?

Azure AI Search bu projede kütüphane kataloğu gibi çalışıyor.

Elimizde RG 271 chunk'ları var. Her chunk:

- ID
- title
- topic
- summary
- content
- page_start
- page_end
- source
- content_vector

alanlarıyla index'e yükleniyor.

Kullanıcı bir şikayet yazınca sistem Azure AI Search'e gidip şunu soruyor:

"Bu şikayete en benzeyen ve en ilgili RG 271 parçaları hangileri?"

Azure AI Search iki tür arama yapıyor:

1. Keyword search
   - Kelime eşleşmelerine bakar.
   - Örneğin "delay", "response", "complaint" gibi kelimeler.

2. Vector search
   - Anlam benzerliğine bakar.
   - Kullanıcının cümlesi ile chunk içeriğini embedding vektörleri üzerinden
     karşılaştırır.

Bu yüzden buna hybrid retrieval diyoruz.

## 10. Embedding Nedir?

Embedding, metni sayılardan oluşan bir listeye çevirmektir.

Çocuğa anlatır gibi:

Bir cümlenin anlamını bilgisayarın anlayacağı bir koordinata çeviriyoruz.

Örneğin:

"Firma cevap vermedi"

ile

"IDR response delay"

kelimeleri birebir aynı değil. Ama anlam olarak yakınlar. Embedding sayesinde
bu yakınlığı bulabiliyoruz.

Bu projede embedding'ler Azure OpenAI ile üretiliyor ve Azure AI Search'te
`content_vector` alanında saklanıyor.

## 11. Retrieval Tarafında Ne Yaptık?

`function_app/retrieval.py` bu işten sorumlu.

Akış şöyle:

1. Kullanıcı şikayeti gelir.
2. `expand_query()` şikayete düzenleyici kavramlar ekler.
   - "not responded" gördüğünde "maximum IDR timeframe", "notification of delay"
     gibi mevzuat terimlerini ekler.
3. `embed_query()` expanded query için embedding üretir.
4. Azure AI Search'e hem metin hem vektör araması gönderilir.
5. İlk adaylar alınır.
6. `domain_rerank()` küçük domain boost uygular.

Domain rerank çok küçük bir düzeltmedir. Azure Search ana karar vericidir.
Biz sadece açıkça gecikme anlatan sorularda timeframe/response delay gibi
sonuçları biraz öne çektik.

Bu düzeltmenin nedeni şuydu:

"Firma cevap vermedi" gibi cümlelerde sistem bazen genel complaint tanımlarına
gidebiliyordu. Halbuki pratikte cevap süresi ve gecikme bildirimi daha alakalı.

## 12. Azure OpenAI Ne İşe Yarıyor?

Azure OpenAI projede iki yerde kullanılıyor:

1. Embedding üretmek.
   - Chunk'ları ve kullanıcı sorgusunu vektöre çevirmek için.

2. Handling note üretmek.
   - Retrieved RG 271 context veriliyor.
   - Modelden iç şikayet ekibine uygun kısa bir not yazması isteniyor.

Ama model serbest bırakılmadı. `function_app/generation.py` içinde çok sıkı
kurallar var.

Önemli kurallar:

- Sadece verilen RG 271 context kullanılacak.
- Hukuki tavsiye verilmeyecek.
- Final karar verilmeyecek.
- Kaynak chunk ID'leri tam formatla yazılacak: `[rg271-XXXX]`.
- Complaint type bilinmiyorsa 30 gün kesin uygulanır denmeyecek.
- İnsan incelemesi gerekiyorsa açıkça söylenecek.

## 13. Citation Guardrail Neden Eklendi?

Model bazen citation'ı yanlış yazdı.

Örneğin:

```text
[rg271-51]
[rg271-66]
```

Ama bizim chunk ID formatımız şu:

```text
[rg271-0051]
[rg271-0066]
```

Bu yüzden `validate_citations()` eklendi.

Bu fonksiyon:

- Citation var mı bakar.
- Format doğru mu bakar.
- Citation, gerçekten retrieved context içinde var mı bakar.

Yanlışsa modelden repair ister.

Bu nedenle bazı testlerde token sayısı yüksek göründü. Çünkü model önce yanlış
citation verdi, sonra ikinci çağrıda düzeltti.

Bu bilinçli bir güvenlik mekanizmasıdır.

## 14. Generated Text Temizliği Neden Eklendi?

Model bazen kelimeleri birleştirdi:

```text
noresponse
subjectto
may notbe
confirmthe
```

Bunlar anlamı bozmasa da kullanıcıya kötü görünür.

Bu yüzden `clean_generated_text()` eklendi.

Ama burada dikkatli davrandık:

Metnin anlamını değiştirmiyoruz. Sadece sık görülen birleşik kelimelerde boşluk
onarımı yapıyoruz.

## 15. Azure Functions Ne İşe Yarıyor?

Azure Functions bu projenin API kapısıdır.

Yani dışarıdan bir sistem veya kullanıcı HTTP isteği gönderir:

```text
POST /api/triage
```

Function şunları sırayla yapar:

1. JSON doğru mu kontrol eder.
2. `complaint` alanı var mı kontrol eder.
3. PII redaction yapar.
4. Classifier çalıştırır.
5. Azure AI Search'ten context getirir.
6. Azure OpenAI ile handling note üretir.
7. Guardrail ile `needs_human_review` hesaplar.
8. Audit kaydı yazar.
9. JSON response döner.

Endpoint'ler:

- `GET /api/health`
  - Function çalışıyor mu kontrol eder.

- `POST /api/redact`
  - Sadece PII temizleme testidir.

- `POST /api/triage`
  - Tam RegDesk workflow'udur.

## 16. PII Redaction Nedir?

PII, kişisel tanımlayıcı bilgi demektir.

Örneğin:

- E-posta
- Telefon
- Bazı hesap veya kimlik formatları

`function_app/pii.py` bu bilgileri `[EMAIL]`, `[PHONE]` gibi placeholder'larla
değiştirir.

Amaç:

Model ve log sistemleri gereksiz kişisel veri görmesin.

Bu tam bir enterprise DLP sistemi değildir. Basit ve açıklanabilir bir başlangıç
guardrail'idir.

## 17. Classifier Ne İşe Yarıyor?

`function_app/classifier.py` şikayeti kaba bir kategoriye ayırır.

Örnek kategoriler:

- `fees_and_charges`
- `service_delay`
- `misleading_conduct`
- `uncategorised`

Başta "has not responded" gibi ifadeler `service_delay` olarak yakalanmıyordu.
Bu yüzden keyword listesi genişletildi:

- "not responded"
- "has not responded"
- "nobody has responded"
- "no reply"
- "still waiting"

Sonuç:

```json
{
  "category": "service_delay",
  "classification_confidence": 0.8
}
```

Bu sınıflandırma bir ML modeli değil. Bilerek basit tutuldu, çünkü başlangıçta
açıklanabilirlik önemliydi.

## 18. needs_human_review Mantığı

`needs_human_review`, sistemin "burada insan bakmalı" demesidir.

Örneğin şikayet şöyle:

"Firma üç haftadır cevap vermedi."

Kategori belli olabilir:

```json
"category": "service_delay"
```

Ama mevzuat sonucu için bazı bilgiler hala eksik olabilir:

- Complaint type kesin mi?
- Şikayet tam hangi tarihte alındı?
- Hangi IDR timeframe uygulanıyor?

Bu yüzden kategori doğru olsa bile insan incelemesi gerekebilir.

Bir hata şurada yaşandı:

Model notta "Further review is required" diyordu ama JSON'da
`needs_human_review: false` dönüyordu.

Sebep:

Kod sadece şu ifadeleri arıyordu:

- "human review is required"
- "further human review is required"

Sonra liste genişletildi:

- "further review is required"
- "requires human review"
- "manual review is required"
- "must be confirmed"

Sonuç doğru hale geldi:

```json
{
  "category": "service_delay",
  "classification_confidence": 0.8,
  "needs_human_review": true,
  "processing_stage": "azure_rag_with_guardrails"
}
```

## 19. Audit Logging Nedir?

Audit logging, "sistem ne yaptı, sonradan izleyebilelim" demektir.

Ama burada dikkat ettik:

Şikayetin düz metnini audit'e yazmıyoruz.

Bunun yerine:

- Şikayetin SHA-256 hash'i
- Kategori
- İnsan incelemesi gerekiyor mu?
- Kullanılan citation ID'leri
- Zaman damgası

saklanıyor.

Bu kod `function_app/audit.py` içinde.

Azure tarafında Azure Table Storage kullanılır.
Yerelde ise Azurite ile taklit edilir.

## 20. Azure Table Storage ve Azurite Ne İşe Yarıyor?

Azure Table Storage basit tablo şeklinde veri saklamak içindir.

Bu projede `auditlog` tablosu oluşturulur.

Her satır bir audit event'tir.

Yerelde Azure Storage kullanmak için Azurite çalıştırıyoruz.

Azurite şunu yapar:

"Ben gerçek Azure Storage değilim ama sen bana yerelde Azure Storage gibi
davranabilirsin."

Bu sayede geliştirme sırasında gerçek Azure Storage kullanmadan test yapabiliriz.

## 21. AzureWebJobsStorage Neden Önemli?

Azure Functions kendi iç işleri için `AzureWebJobsStorage` ister.

Ayrıca bizim audit logger da aynı connection string'i kullanır.

Yerelde tipik değer:

```text
UseDevelopmentStorage=true
```

Bu değer Azurite'e bağlanır.

Bir ara `func start` logunda şu uyarı görüldü:

```text
Unable to create client for AzureWebJobsStorage
```

Sebep:

Azurite yoktu, çalışmıyordu veya connection string doğru değildi.

Azurite çalışınca audit testleri geçti.

## 22. Local Settings ve .env Farkı

Bu projede iki tür ayar var:

1. `.env`
   - Python script'leri için kolay yerel environment dosyası.
   - Azure OpenAI ve Azure Search gibi değerler burada tutulabilir.

2. `function_app/local.settings.json`
   - Azure Functions local runtime için ayar dosyası.
   - `func start` bunu okuyabilir.

İkisi de secret içerebilir. Bu yüzden git'e koyulmamalıdır.

`.gitignore` içinde bu dosyalar dışarıda bırakıldı.

## 23. Azure Identity Neden Gündeme Geldi?

Azure Search'e iki şekilde bağlanabiliriz:

1. Key ile.
   - `SEARCH_KEY` varsa `AzureKeyCredential` kullanılır.

2. Managed identity veya local Azure login ile.
   - Key yoksa `DefaultAzureCredential` kullanılır.

Bu yüzden `azure-identity` dependency'si gerekir.

Bir noktada şu hata alındı:

```text
ModuleNotFoundError: No module named 'azure.identity'
```

Çözüm:

`azure-identity` requirements'a eklendi ve kuruldu.

## 24. azure.data Hatası Neden Oldu?

Audit logger `azure.data.tables` kullanıyor.

Bu modül `azure-data-tables` paketinden gelir.

Hata:

```text
ModuleNotFoundError: No module named 'azure.data'
```

Çözüm:

`function_app/requirements.txt` içine şu eklendi:

```text
azure-data-tables
```

Sonra hem normal Python ortamına hem de Functions local package klasörüne kuruldu.

## 25. load_dotenv AssertionError Neden Oldu?

Audit testini heredoc ile çalıştırırken şu hata geldi:

```text
AssertionError
```

Sebep:

`load_dotenv()` bazen stdin üzerinden çalışan script'te dosya yolunu otomatik
bulmaya çalışırken stack inspection hatasına düşebiliyor.

Çözüm:

`test_audit.py` eklendi.

Bu script `.env` yolunu açıkça verir:

```python
load_dotenv(dotenv_path=PROJECT_ROOT / ".env")
```

Ayrıca gerekirse `function_app/local.settings.json` içinden
`AzureWebJobsStorage` değerini okur.

## 26. func start ve Python Package Path Problemi

Yerelde `func start` çalışırken Core Tools farklı Python worker kullanabiliyor.

Bizim durumda Homebrew Python 3.14 worker kullanıldı.

Bu worker, pyenv Python 3.11 ortamına kurduğumuz paketleri otomatik görmedi.

Bu yüzden `dotenv` veya `azure.data` gibi modüller bulunamadı.

Çözüm:

Paketler `function_app/.python_packages/lib/site-packages` altına kuruldu.

Sonra `func start` şu şekilde çalıştırıldı:

```bash
PYTHONPATH=/path/to/project/function_app/.python_packages/lib/site-packages \
func start --script-root function_app --port 7071
```

Bu bir yerel geliştirme problemi. Azure'a deploy edildiğinde requirements
üzerinden paketler kurulmalıdır.

## 27. Azurite Kurulumunda Yaşanan Hata

Azurite kurarken şu hata geldi:

```text
ENOSPC: no space left on device
```

Bu, diskte yer kalmadığı anlamına gelir.

Burada sorun kodda değildi. Ortamda yer açmak gerekiyordu.

Sonra Azurite çalışınca audit kayıtları okunabildi.

## 28. Testlerle Neyi Kanıtladık?

Şu testleri çalıştırdık:

### Syntax testleri

```bash
python -m py_compile ...
```

Amaç:

Python dosyalarında syntax hatası var mı görmek.

### Retrieval testi

```bash
python test_retrieval.py
```

Amaç:

"Firma üç haftadır cevap vermedi" gibi bir şikayette doğru RG 271 chunk'ları
geliyor mu görmek.

### Generation testi

```bash
python test_generation.py
```

Amaç:

Model, retrieved chunk'lara dayanarak citation'lı handling note üretiyor mu
görmek.

### Audit testi

```bash
python test_audit.py
```

Amaç:

Azurite/Table Storage içinde audit kaydı oluşmuş mu görmek.

Örnek başarılı çıktı:

```text
AUDIT RECORDS: 1
CATEGORY: service_delay
NEEDS REVIEW: True
CITATIONS: rg271-0024,rg271-0022,rg271-0025,rg271-0023,rg271-0020
HASH PRESENT: True
```

### Function endpoint testi

```bash
curl -X POST http://localhost:7071/api/triage ...
```

Beklenen kritik sonuç:

```json
{
  "category": "service_delay",
  "classification_confidence": 0.8,
  "needs_human_review": true,
  "processing_stage": "azure_rag_with_guardrails"
}
```

## 29. Azure Platformlarında Ne Yapmak İstedik?

### Azure OpenAI

Ne yapmak istedik:

- Embedding üretmek.
- Handling note üretmek.

Ne yaptık:

- Embedding deployment ile chunk ve query vektörleri ürettik.
- Chat deployment ile kaynaklı not ürettik.
- Modeli prompt guardrail'leriyle sınırlandırdık.

### Azure AI Search

Ne yapmak istedik:

- RG 271 chunk'larını aranabilir hale getirmek.
- Hem keyword hem vector search yapmak.

Ne yaptık:

- `reg-index` gibi bir index oluşturduk.
- `content_vector` alanı ekledik.
- Chunk metadata ve içerikleri yükledik.
- Retrieval tarafında hybrid search yaptık.

### Azure Functions

Ne yapmak istedik:

- Sistemi HTTP API olarak çalıştırmak.

Ne yaptık:

- `/api/health`
- `/api/redact`
- `/api/triage`

endpoint'lerini oluşturduk.

### Azure Storage / Table Storage

Ne yapmak istedik:

- Privacy-conscious audit log tutmak.

Ne yaptık:

- `auditlog` tablosuna hash, kategori, citation ve human review bilgisi yazdık.

### Azurite

Ne yapmak istedik:

- Azure Storage'ı yerelde taklit etmek.

Ne yaptık:

- `AzureWebJobsStorage=UseDevelopmentStorage=true` ile local audit test ettik.

### Azure CLI / Infra Script

Ne yapmak istedik:

- Azure resource group, search service, storage account ve function app kurulumunu
  komutla yapabilmek.

Ne yaptık:

- `infra/setup.sh` içinde temel Azure CLI komutlarını tuttuk.

## 30. Sistemin Bugünkü Tam Akışı

Bir şikayet geldiğinde sistem şu sırayla ilerler:

1. Kullanıcı `POST /api/triage` endpoint'ine JSON gönderir.

2. Function JSON'u okur.

3. `pii.redact()` çalışır.
   - E-posta gibi bilgiler temizlenir.

4. `classifier.classify()` çalışır.
   - Örneğin `service_delay`, confidence `0.8`.

5. `retrieval.retrieve()` çalışır.
   - Query genişletilir.
   - Embedding üretilir.
   - Azure AI Search'te hybrid search yapılır.
   - Domain rerank uygulanır.

6. `generation.generate_handling_note()` çalışır.
   - Retrieved chunks context olarak verilir.
   - Model handling note üretir.
   - Citation validation yapılır.
   - Gerekirse repair çağrısı yapılır.

7. Function `needs_human_review` hesaplar.
   - Düşük confidence varsa true.
   - Context yoksa true.
   - Generation tamamlanmadıysa true.
   - Note insan incelemesi gerektiğini söylüyorsa true.

8. `audit.log_audit_event()` çalışır.
   - Şikayetin düz metni değil hash'i saklanır.

9. Function JSON response döner.

## 31. Yanıldığımız Ama Sonra Düzelttiğimiz Ana Noktalar

### İlk yanılgı: Basit chunking yeterli olur

Gerçek:

Mevzuat dokümanı yapısal olarak karmaşık. Başlıklar, notlar, tablolar ve madde
numaraları var.

Düzeltme:

Agentic chunking ve validation eklendi.

### İkinci yanılgı: Model ID'leri her zaman doğru döndürür

Gerçek:

Model kısa veya garip görünen unit ID'leri atlayabiliyor.

Düzeltme:

Coverage validation ve repair retry eklendi.

### Üçüncü yanılgı: Model citation formatını hep korur

Gerçek:

Model `[rg271-0051]` yerine `[rg271-51]` yazabiliyor.

Düzeltme:

Citation validator ve generation repair eklendi.

### Dördüncü yanılgı: Category doğruysa human review false olabilir

Gerçek:

Kategori doğru olsa bile mevzuat sonucu için complaint type ve receipt date
gerekebilir.

Düzeltme:

`needs_human_review` hem confidence'a hem de generated note içindeki review
ifadelerine bakacak şekilde güçlendirildi.

### Beşinci yanılgı: Local Python paketleri Functions worker tarafından görülür

Gerçek:

Core Tools farklı Python worker kullanabiliyor.

Düzeltme:

`.python_packages` ve `PYTHONPATH` ile local runtime path'i netleştirildi.

### Altıncı yanılgı: Her local testte load_dotenv otomatik path bulur

Gerçek:

stdin/heredoc ile çalışırken `load_dotenv()` hata verebildi.

Düzeltme:

`test_audit.py` içinde `.env` path'i açıkça verildi.

## 32. Güvenlik ve Sorumluluk Tarafında Ne Yaptık?

Bu proje finansal şikayetler ve mevzuatla ilgili olduğu için bazı sınırlar
çok önemli.

Yaptıklarımız:

- PII redaction ekledik.
- Modeli sadece supplied context ile sınırladık.
- Citation zorunlu yaptık.
- Citation'ın gerçekten retrieved context içinde olmasını doğruladık.
- Complaint type bilinmiyorsa kesin süre yorumu yapmasını engelledik.
- İnsan incelemesi gerektiğinde JSON bayrağını true yapıyoruz.
- Audit'te şikayet metni yerine hash saklıyoruz.
- `.env` ve `local.settings.json` git dışında bırakıldı.

## 33. Bu Sistem Ne Değildir?

Bu sistem:

- Hukuki tavsiye motoru değildir.
- Final müşteri sonucu vermez.
- Tam otomatik karar sistemi değildir.
- Tüm PII türlerini yüzde 100 yakalayan enterprise DLP değildir.
- Her complaint type için kesin süre hesaplayan nihai compliance engine değildir.

Bu sistem:

- İç ekibe yardımcı olan kaynaklı bir triage copilot'tur.
- Mevzuat bağlamını hızlı bulur.
- Dikkat edilmesi gereken noktaları özetler.
- Belirsizlikte insan incelemesine yönlendirir.

## 34. Bundan Sonra Neler İyileştirilebilir?

Kısa vadede:

- Daha fazla örnek şikayetle test seti genişletilebilir.
- `needs_human_review` neden true oldu, response'a ayrı bir `review_reasons`
  alanı eklenebilir.
- Citation repair sayısı response metadata içine eklenebilir.
- Azurite local dosyaları `.gitignore` içine ayrıca alınabilir.

Orta vadede:

- Classifier keyword yerine küçük bir supervised model veya daha zengin rule set
  kullanabilir.
- Retrieval evaluation seti oluşturulabilir.
- Chunk kalitesi için ölçüm raporu hazırlanabilir.
- Azure Application Insights ile production telemetry eklenebilir.

Uzun vadede:

- RBAC ve managed identity ile key kullanımını azaltmak.
- CI/CD pipeline eklemek.
- Gerçek Azure Function deployment'ını otomatize etmek.
- Human review workflow'unu Jira, ServiceNow veya CRM sistemine bağlamak.

## 35. Yeni Bir Arkadaş Projeyi Nasıl Çalışır Hale Getirir?

Temel sıra:

1. Repository'yi al.
2. Python ortamını hazırla.
3. `function_app/requirements.txt` paketlerini kur.
4. `.env` ve `function_app/local.settings.json` dosyalarını yerel olarak doldur.
5. Azurite'i çalıştır.
6. Azure AI Search index'inin dolu olduğundan emin ol.
7. Function'ı çalıştır.
8. `/api/triage` endpoint'ine test isteği gönder.
9. `python test_audit.py` ile audit kaydını kontrol et.

Yerel Functions komutu bu ortamda şöyle çalışmıştı:

```bash
PYTHONPATH=/Users/osmanorka/azure-ai-copilot-platform-ya-da-azure-rag-copilot/function_app/.python_packages/lib/site-packages \
func start --script-root function_app --port 7071
```

## 36. Kapanış: Bu Projede Asıl Öğrendiğimiz Şey

Bu projenin ana dersi şu:

LLM uygulaması yapmak sadece modele soru sormak değildir.

Gerçek bir copilot için şunlar gerekir:

- Kaynak veriyi doğru hazırlamak.
- Aramayı iyi yapmak.
- Modeli doğru sınırlandırmak.
- Hatalı çıktıyı yakalamak.
- İnsan incelemesini doğru yerde devreye sokmak.
- Audit ve privacy tarafını düşünmek.
- Yerel geliştirme ile Azure runtime farklarını çözmek.

Biz bu projede hızlı ilerledik, bazı yerlerde hata aldık, ama her hata sistemi
daha sağlam hale getirdi.

Bugünkü haliyle sistem artık şu fikri taşıyor:

"Model yardımcı olur, kaynak gösterir, emin değilse insana bırakır."


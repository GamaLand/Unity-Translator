# Mechanicus: ilk salt okunur keşif

Tarih: 14 Ekim 2026. A0 taban deneyi ve A1 başlangıç incelemesi.
Kurulum yolu, kişisel model kimliği ve oyun metinleri bu rapora alınmamıştır.
Yerel JSON kanıtları `.local/mechanicus/snapshots/` içindedir; dağıtılmaz.

## Güncel sonuç — metaveri okuyucusu sonrası

I2 `LanguageSource`, `LanguageData` ve `TermData` alanları assembly çalıştırılmadan
dnfile ile statik metaveriden çıkarıldı. `[SerializeField]`, public/static/readonly
ve `[NonSerialized]` kuralları uygulandı. Okuma, nesnenin 8.001.432 baytını tamamen
tüketti; artan/kesik veri, bilinmeyen tip veya kalıtım reddediliyor. Okuyucu yalnızca
doğrulanmış Unity 2017 Mono düzenine daraltılmıştır; genel Unity desteği iddiası yoktur.
Kurallar [Unity 2017 serialization belgesi](https://docs.unity3d.com/2017.4/Documentation/Manual/script-Serialization.html)
ve statik metaveri API'si [dnfile resmî deposu](https://github.com/malwarefrank/dnfile)
ile karşılaştırıldı.

- `resources.assets`: 6.854 terim, 12 dil/kontrol sütunu.
- Tekil `English/en` sütunu adı/koduyla eşlendi. `Query`, `Answer`, `description`
  kontrol sütunları ve diğer diller çeviri kaynağı yapılmadı.
- 6.749 kaynak kayıt, 6.095 benzersiz metin, 677.344 kaynak karakteri çıkarıldı.
  İngilizce metni boş 105 kayıt ayrı tanı olarak dışlandı.
- 3.964 genel type tree eksikliği tanı olarak korundu; bunlar başarılı I2
  fallback sonucu için hata değildir. I2 çıkarma hatası 0.
- `Languages_Touch` bütün terimlerde boş bulundu; dokunmatik varyant kaynak
  çıkarımı bu kurulumda gerekmedi. Terim `Description` alanı bağlam olarak tutuluyor.
- Kategoriler özgün terim anahtarının ilk yol bölümüdür; semantik kategori
  sınıflandırması ve üslup eşlemesi henüz tamamlanmadı.
- Kaynak dosyasının önce/sonra SHA-256 değerleri eşit. Gerçek kayıtlar yalnızca
  Git dışındaki yerel proje snapshot'ı ve SQLite deposunda tutuluyor.

LM Studio şemalı çıktı denemesinde kısa koruma belirteçleri ve `temperature=0.2`
ile sentetik biçim kontrolü geçti. Sonra UI, öğretici ve diyalogdan seçilen üç
gerçek kısa kayıt 18,337 saniyede üretildi; üçü de sert biçim kontrolünü geçti.
Bu üç kayıt insan tarafından onaylanmadı ve temsilî kalite/hız pilotu değildir.
Kaynak/çeviri çiftleri `reports/prototype-*.json` yerel raporunda bulunur.
Native model metaverisi mevcut modelin yüklü olduğunu ve 10.240 bağlam token'ı
ile çalıştığını bildirdi; bu kapasite diğer modeller için sabitlenmez.
llama.cpp gerçek bağlantı testi kullanıcı isteğiyle şimdilik ertelendi.

`extraction=supported` bu I2 kaynağı için kanıtlandı; `application=unknown`.
200 kayıtlık pilot ve oyun içi uygulama yapılmadı.

## İlk denemenin bulguları — metaveri fallback öncesi

- `*_Data/Managed/Assembly-CSharp*.dll` dosyaları Mono göstergesidir.
  IL2CPP çalışma/uygulama desteği doğrulanmadı.
- İncelenen beş Unity kaynağında sürüm `2017.4.19f1` olarak okundu.
- Dosya tarayıcısı 209 Unity kaynak adayı saydı; bunların tamamı açılmadı.
- `globalgamemanagers.assets` MonoScript metaverisinde 40 `I2.Loc` sınıfı
  bulundu; `LanguageSource` ve `LanguageData` bunların arasındadır.
- Ek salt okunur pointer incelemesinde `resources.assets` içindeki bir
  MonoBehaviour'ın `LanguageSource` scriptine referans verdiği görüldü.
  Referansın dış dosyası `globalgamemanagers.assets` olarak doğrulandı.
  Bu nesnenin type tree'si mevcut okuyucuyla çözülemedi.
- İngilizce I2 metin çıkarımı **henüz başarısız**: kabul edilen kayıt sayısı 0.
  Bu, oyunda sıfır metin bulunduğu anlamına gelmez.

| İncelenen kaynak | Çıkarılan kayıt | Çözülemeyen MonoBehaviour type tree | Önce/sonra kaynak SHA-256 |
| --- | ---: | ---: | --- |
| resources.assets | 0 | 3964 | Eşit |
| globalgamemanagers.assets | 0 | 0 | Eşit |
| sharedassets0.assets | 0 | 6 | Eşit |
| sharedassets1.assets | 0 | 14 | Eşit |
| level0 | 0 | 15 | Eşit |

Hash karşılaştırması bu beş kaynağı kapsar; tüm oyun kurulumunun etkinleştirme
envanteri değildir. Oyun dizinine dosya yazılmadı veya oyun assembly'si çalıştırılmadı.

## İlk model bağlantısı denemelerinin geçmişi

LM Studio'nun denenen loopback adresindeki `/v1/models` isteği başarılıydı;
üç model kimliği bildirildi. Yüklü/kullanılabilir ayrımı henüz doğrulanmadı.
Seçilmiş modelde sentetik cümleyle toplam üç küçük üretim denemesi yapıldı:
ilk iki denemede 1024 çıkış token sınırı nedeniyle kesilen cevaplar reddedildi;
4096 sınırıyla üçüncü deneme de biçim kontrolünü geçemedi. Kabul edilen çeviri 0.
Gerçek oyun metni modele gönderilmedi. Model kalite/hız başarısı iddiası yoktur.

llama-server için denenen loopback 8080 adresine bağlantı kurulamadı.
Bu tek adres deneyi, sunucunun başka portta bulunmadığını göstermez.
İki sağlayıcı için ortak dar HTTP akışı sentetik HTTP cevaplarıyla test edildi;
gerçek llama-server üretimi ve sağlayıcıya özgü JSON Schema özellikleri doğrulanmadı.

HTTP yüzeyi [LM Studio resmî belgesi](https://lmstudio.ai/docs/developer/openai-compat)
ve [llama.cpp server belgesi](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
ile karşılaştırıldı. Her iki sunucunun bütün özellikleri desteklediği varsayılmadı.

## İlk teslimdeki uygulama fizibilitesi ve açık kapılar

`extraction=unknown`, `application=unknown`. Haricî dil/mod desteği henüz
kanıtlanmadı. Çalışma anı adaptörü, yükleyici, font çözümü veya çalışma kopyası
denenmedi; kurulabilir yama üretilmedi. Var olan dosyayı değiştiren hiçbir
alternatif yöntem eklenmedi.

Bir sonraki küçük çıktı: gerçek `LanguageSource`/`TermData`/`LanguageData`
serialized şemasını assembly **metaverisini statik okuyarak** doğrulamak;
okuyucuyu gerçek kaynakta deneyip tam dil eşlemesi/sayımları almak.
Model cevap hatasının nedeni ayrı bir yerel tanı deneyiyle incelenmeli.
Ardından birkaç gerçek kayıtta küçük prototip, iki sağlayıcının ayrı üretim testleri
ve uygulama fizibilitesi tamamlanmalı. A1/A2 kabul kapıları henüz kapanmadı.
200 kayıtlık pilot veya toplu çeviri yapılmadı.

## Geliştirme doğrulaması

Güncel doğrulama: 57 sentetik otomatik test geçti, bir symlink yetki testi atlandı.
Ruff ve strict mypy geçti. SQLite WAL/FULL, yeniden açılış, tek yazarlı OS kilidi,
kaynak/bağlam revizyonu, onay koruması, eski cevap ve sert biçim hatasının etkin
çeviriye dönüşmemesi test edildi. CLI `extract` ile 6.749 gerçek kayıt SQLite'a
kaydedildi. İş kuyruğu/kesinti kurtarma ve masaüstü arayüzü henüz eklenmedi.

İlk teslimdeki doğrulama:

40 sentetik otomatik test geçti; symlink oluşturma yetkisi bulunmadığı için
bir test atlandı. Ayrı Windows junction deneyi çıktı yazmayı reddetti.
Ruff ve strict mypy kontrolleri geçti. Wheel/sdist üretildi; wheel içinden
import, CLI yardım girişi ve sürümlü istem okuması denendi. Arşivlerde
yerel keşif verisi, oyun asset'i, model veya geliştirme önbelleği bulunmadığı
kontrol edildi. Bu deney temiz Windows standalone paket doğrulaması değildir.

UnityPy API'si ve type tree okuyucusunun süreç çökmesi riski
[resmî kaynakta](https://github.com/K0lb3/UnityPy) incelendi. Bu nedenle Unity
ayrıştırması dosya başına ayrı süreçtedir; süreç bir güvenlik sandbox'ı değildir.

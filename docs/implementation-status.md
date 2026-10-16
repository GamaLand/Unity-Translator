# Ürün tamamlanma takibi

Bu liste kullanıcı tarafından istenen tam ürün hedefini izler; geçen testler
ürünün tamamlandığı anlamına gelmez. Son güncelleme: 14 Ekim 2026.

| Kapı | Kanıtlanan mevcut durum | Tamamlanması gereken |
| --- | --- | --- |
| A0 | Python 3.12 x64, kilitli deps, CLI, wheel/sdist ve güncel Qt standalone önizleme zip'i, lisans envanteri | Temiz Windows testi kullanıcı seçimiyle ertelendi; yayın/native lisans kaynak erişimi incelemesi |
| A1 | Gerçek Unity/runtime/I2 metaverisi; 6.749 kaynak, hash eşitliği, yerel snapshot | Haricî dil/mod/runtime uygulama fizibilitesi, font/Heretek kapsamı |
| A2 | LM Studio model listesi, native yükleme metaverisi, üç gerçek üretim/validator sonucu | Daha geniş biçim kuralları; llama.cpp gerçek testi kullanıcı isteğiyle ertelendi |
| A3 | 200 kayıt: 186 başarılı, 12 desteklenmeyen biçim ve 2 doğrulama hatası ayrıldı; 9 retry. Kullanıcı pilot üslubunu onayladı; kayıt onayı otomatik verilmedi | Uzun/kategori dağılımında ölçülmeyen 402 kayıt; tek tek inceleme/düzeltme ihtiyacı |
| A4 | Türkçe Qt UI, IO worker/async köprü, SQLite migration/backup, kalıcı claim/retry/pause/cancel/recovery, onay koruması, 200 kayıtlık DB arama/sayfalama, glossary/style etki filtresi ve sınırlı aday üretimi, çeviri geçmişinden açık aday seçimi, revizyon geçmişli JSON 2 ve boş projeye geri yükleme, pilot/toplu iş kapısı, güncel standalone sentetik UI testi | Daha geniş kaynak biçimleri; temiz Windows testi kullanıcı seçimiyle ertelendi |
| A5 | Oyuna yazma yok; uygulama desteği unknown | Yalnızca kanıtlanmış güvenli yöntem varsa etkinleştirme/kaldırma; glif/taşma/dinamik değerler ve tüm özgün hash envanteri |

Şu ana kadar gerçek oyun/metin/model dosyaları kaynak veya dağıtım paketine
eklenmedi. Bulut aktarımı, telemetri, model indirme ve oyun dosyasını değiştiren
bir uygulama yolu bulunmuyor. Tam oyun toplu çevirisi pilot kapısından önce yapılmaz.

Güncel Python doğrulaması: 343 test geçti, bir symlink yetki testi atlandı.
Güncel wheel/sdist üretildi: 49 wheel girdisi ve 136 kaynak arşivi girdisi
incelendi. Yerel oyun/model/SQLite dosyası, DLL ve geliştirme önbelleği yok;
sdist C# adaptör kaynakları ve yükleyici bildirim/kaynak envanteri içeriyor. Bu kaynak paket
denetimi güncel Windows standalone veya temiz Windows testi değildir.
Qt arayüzünde 601 sentetik kayıtla 200 kayıt sayfalama, düzenleme/onay, dışa
aktarma ve kapanma/yeniden açılış çalıştırıldı. İlk offscreen görüntüde sistem
font keşfi yoktu; Windows'un Segoe UI fontu salt okunur yüklenerek görüntü
düzeltildi. Türkçe glif kapsamı ve arayüz görüntüsü ayrıca kontrol edildi.
Bu, oyunun font kapsamını veya temiz Windows standalone çalışmasını kanıtlamaz.

Standalone EXE, PYTHONHOME/PYTHONPATH boş ve PATH yalnızca Windows dizinlerini
içerirken gerçek kaynaktan 6.749 kayıt çıkardı; kaynak hash kontrolü geçti.
Aynı koşullarda 601 sentetik kaydın 200 satırlık UI modeli, elle düzenleme ve
onay akışı geçti. Geliştirme bilgisayarındaki bu izolasyon temiz VM değildir.
Modelin JSON/kimlik ve korumalı içerik hataları bundan sonra ayrı kaydedilir;
eski pilotun iki validation_error sonucu geriye dönük sınıflandırılmadı.
Kategori/uzunluk süre aralığı 6.347 kayıt için ölçüm içerir; 402 kayıt ve insan
inceleme süresi bu tahmine dahil değildir.

JSON 2'nin gerçek yerel proje turunda 6.749 kayıt, 10.878.418 baytlık arşiv
olarak dışa aktarıldı, ayrı boş projeye geri yüklendi ve yeniden dışa aktarılıp
okundu. Kaynak kayıt sayısı aynı ve yerel onay sayısı sıfır kaldı. Sentetik
testler eski kaynak revizyonlarını, pasif kayıtları, çeviri geçmişini, eski
onay bilgisinin arşivde korunmasını, tekrar içe aktarmayı ve çakışmada geri
almayı doğrular. Geri yükleme Qt arayüz testinden geçti. Güncel kaynak
standalone önizlemeye dahil edildi; paket temel GUI akışını geçti. Temiz
Windows testi kullanıcı seçimiyle bekliyor.

Oyuna uygulamanın dosya koruma çekirdeği 20 sentetik testle doğrulandı:
yeni hedef planı, özgün envanter, exclusive create, manifest/kimlik/hash
sahipliği, kısmi hata/kurtarma ve değiştirilmiş ekin korunması. Gerçek I2
metotları statik okundu; kaynak hash eşit kaldı. Bunlar yükleyicinin oyunda
çalıştığını veya Türkçe glifleri kanıtlamaz. Gerçek etkinleştirme UI/CLI'a
açılmadı. [Uygulama fizibilitesi](discovery/runtime-application.md).

Deneysel I2 Mono C# adaptörü gerçek oyun referansları ve BepInEx 5.4.23.5
ile derlendi; referans hash'leri değişmedi. 13 sentetik çekirdek ve beş
sentetik I2 sarmalayıcı senaryosu dil/kaynak/hash/biçim, bellek geri alma
ve yeni sahne kaynağına uygulamayı doğrular. Bu .NET testleri game/Unity/
loader assembly'lerini çalıştırmaz. Runtime veri üreticisi yalnızca güncel
yerel insan onaylı kayıtları kabul eder. BepInEx yalnızca geliştirme
önbelleğinde; oyuna kurulmadı. Loader bileşen lisansları, font ve gerçek
oyun içi davranış kapıları hâlâ açıktır.

Statik CIL denetiminde önbellek/PlayerPrefs yazımına ulaşan I2 API yolları
bulundu ve plugin'den çıkarıldı. Hazır sözlük ve terim nesnesi eşleşmesi
beklenir; en→tr dil seçimi sabit bellek alanlarıyla yapılır. Bu callback ve
native davranışların gerçek oyun hash testinin yerine geçmez. dncil dev
bağımlılığıdır; analiz raporları yerelde kalır.

Salt okunur font keşfinde iki native Font'un gömülü Unicode cmap'i 12 Türkçe
karakteri kapsıyor. Üç TMP_FontAsset atlasının type tree'si yok; glif kapsamı
unknown. Font seçimi ve oyun içi görünüm doğrulanmadı. Dört yeni sentetik test
font verisi/cmap/TMP şema sınırlarını doğrular; fontTools yalnızca dev grubundadır.
Bu geliştirme aracı mevcut standalone önizlemeyi değiştirmez.

Yeni kaynak sürümünde `review-en-tr-v3` sayı/işaret, yüzde, İngilizce→Türkçe
olumsuzluk ve koşul ipuçlarını inceleme uyarısına ayırır. UI kontrol
açıklamalarını Türkçe gösterir ve mevcut adaylar için ayrı yeniden kontrol
raporu üretir; revizyon/durum/onaylar değişmez. Sürüm metaverisi yeni adaylara
kaydedilir. [Kapsam ve sınırlar](quality-checks.md). Bu değişiklikler mevcut
Windows önizleme zip'ine henüz alınmadı; sentetik kaynak UI testi geçti.
Gerçek yerel projenin 186 güncel çevirisi yeniden ölçüldü: 16 kayıtta uyarı,
eski aday listesine göre üç kayıtta yeni olası olumsuzluk/koşul uyarısı var.
13 kaynakla aynı kalma uyarısı korunuyor; kodlara göre sayımlar aynı kayıtta
birden fazla uyarı içerebilir. Bu sayılar gerçek hata veya kalite puanı değildir.
Rapor öncesi/sonrası bütün DB tablolarının içeriği aynı kaldı; pilot yeniden
üretilmedi ve model çağrısı yapılmadı. Ayrıntılı metinler yalnızca yerel raporda.

`protected-i2-v2` gerçek I2 parametrelerini (`{[NAME]}`) ve boşlukla ayrılmış
tek karşılaştırma işaretini korur. Python/C# aynı 26 sentetik grammar
örneğinde kabul/red eşleşmesini geçti. C# gerçek referanslarla yeniden
derlendi; referans hash'leri değişmedi, oyun çalıştırılmadı. Kaynakların
6.719'u statik biçim kontrolünü geçti; 30 doğrulanmamış yapı ayrı kalıyor.
Eski pilotun 12 biçim hatasının kaynakları artık bu kontrolü geçer;
bu sonuç eski model denemelerini başarılı saymaz. [Biçim kapsamı](protected-format.md).
Windows önizleme bu kaynak değişikliğini henüz içermiyor.

Biçim takip prototipi metin içeren 10 eski başarısız kaydı mevcut LM Studio'da
yeniden denedi: sekiz tamamlandı, iki kayıt üçer deneme sonunda ayrı kaldı.
Toplam 17 deneme ve 415,896 saniye üretim isteği ölçüldü; yedi ek deneme var.
Sekiz başarılı adayın korumalı biçimi tekrar kontrol edildi; metaverileri
`protected-i2-v2` taşıyor. İnsan onayı sıfır kaldı; orijinal 200 kayıtlık pilot
yeniden sınıflandırılmadı. Bu küçük seçki bütün oyun başarı oranı değildir.
Yerel takip raporu ayrı dosyada, gerçek metinler dağıtım/CI dışında tutulur.

Sağlayıcı artık `output_truncated` ve `unexpected_tool_call` hatalarını JSON
şema hatasından ayrı verir. Bozuk choice/message türleri de eşlenmiş hata olur.
Araç çağrısı çalıştırılmaz, kesik çıktı kabul edilmez; iki yeni hata ortak üç
denemelik bütçeye dahildir. Takip işi eski hata eşleme snapshot'ıyla çalıştı;
saklanan response_schema_error sonuçları geriye dönük yeniden sınıflandırılmadı.

V3 geliştirme aşamasında dar size/sprite/F sayı biçimi koruması eklendi. Python ve
C# 49 ortak sentetik örnekte eşleşti; gerçek referans derlemesi ve hash kontrolü
geçti. Statik kaynak kapsamı 6.723 kayda çıktı; 22 çoğul ve dört diğer yapı
desteklenmiyor. Bu eski V2 raporlarını değiştirmez; oyun içi görünüm/format
doğrulaması yapılmadı. Windows önizleme henüz bu kaynak sürümünü içermiyor.

V3'ün dört ek kaydı mevcut LM Studio ile ayrı prototipte denendi; dördü
tamamlandı, 110,799 saniye üretim isteği ölçüldü. Boyut/sprite/F1 yapıları ve
`protected-i2-v3` metaverisi yeniden doğrulandı. İnsan onayı sıfır kaldı;
orijinal pilot raporu korunuyor. Ayrıntılı takip raporu yalnızca yerel projede.
Beş deneme yapıldı; bir `output_truncated` cevabı reddedilip bütçe içinde
tekrarlandı. Bir sayısal/birim metni kaynakla aynı kaldığı için inceleme uyarısı
taşıyor. Tamamlanma, bu adayların insan tarafından doğru bulunması değildir.

Güncel çoğul parser'ı Plural/One/Zero dallarını ayrı doğrular; 63 ortak
Python/C# biçim örneği geçti. Şema/maskeleme/dal rekonstrüksiyonu tek üretim
isteğinde çalışır; üç deneme bütçesi bütün kayda aittir. Atomik hata ve dal
arası değişken/sayı kontrolleri sentetik testlerle doğrulandı. C# gerçek
referanslarla yeniden derlendi ve referans hash'leri değişmedi. Statik kapsam
6.745 kayda çıktı; dört diğer yapı hâlâ ayrı. Oyun içi çoğul testi yapılmadı.
Windows önizleme bu kaynak sürümünü henüz içermiyor.

Çoğul model testinin ilk iki kaydı 2048 çıkış bütçesinde toplam altı kesik
çıktı aldı; kısmi aday oluşmadı. Sıralı items şeması ve istem v2 ile aynı
iki kaydın One/Zero örneği tamamlandı, One örneği ayrı kaldı (beş deneme,
162,915 saniye). Başarısız tek kaydın 4096 bütçeli ayrı prototipi de üç
kesik çıktı aldı (192,174 saniye). Başarılı adayın dal yapısı/metaverisi
tekrar doğrulandı ve insan onayı sıfır kaldı. Çoğul model desteği bütünüyle
doğrulanmış değildir; eski adaylar/raporlar yeniden sınıflandırılmadı.

Yeni provider hataları ham cevabı kaydetmeden sabit bitiş nedeni, içerik
byte uzunluğu ve sunucunun bildirdiği sınırlı sayısal token ölçümlerini
deneme metaverisine ekler. Bilinmeyen usage alanları veya ham model/istem
metni bu tanıya alınmaz. Bu alanlar önceki kesik çıktılardan geriye dönük
türetilmez; sonraki teşhis için kullanılacaktır.
Hata tanısı ayrıca programın seçtiği format istemi, grammar sürümü, dal sayısı
ve şema modunu kaydeder. Bu kontrol alanları model cevabından alınmaz. Şema
devre dışıysa sıralı şema kullanılmış diye raporlanmaz.

Çoğul inceleme penceresi kaynak sıralı üç dalı ayrı düzenler; boş/bozuk dalı
engeller, ana taslağa aktarır ve ayrıca kaydetme/onay gerektirir. İptal ve ana
kayıt değişimi kullanıcı alanlarını korur. CRLF/CR/LF, NBSP ve Unicode satır
ayıracı normalleştirmesi için veri editörü eklendi. Yeni sekiz UI testi
onaylı metnin aktarımda korunmasını, kaydetmede onayın kaldırılmasını,
dal/boşluk/satır sonu kontrolünü doğrular. Kaynak ve güncel standalone 601
kayıtlık modal smoke testini geçti. İstem dosyası, CRLF/NBSP koruması,
200 satırlık model ve ayrı onay akışı frozen EXE'de doğrulandı. EXE ayrıca
izole PATH ile 6.749 gerçek kaynak çıkardı; asset hash'i değişmedi.

Güncel yerel önizleme `UnityTranslator-0.1.0-preview.3-win-x64.zip`,
66.379.065 bayt; SHA-256
`36f8d682cb31797563caa1d9066cf824c7726e9a86767706fe96b6a9a97364ba`.
184 dağıtım dosyası ve ek paket manifestiyle 185 ZIP girdisi CRC/hash kontrolünden
geçti. 33 runtime bileşen lisans metni var; oyun/model/yerel proje veya
BepInEx paketi eklenmedi. Önizleme yayımlanmadı, temiz Windows kapısı kullanıcı
seçimiyle ertelendi ve native lisans kaynak erişimi incelemesi sürüyor.

Uygulama servisinde taze Windows süreç kanıtı kapısı eklendi: ilk baseline,
plan/ekleme/kaldırma sırasında oyun açık veya belirsizse durur. Arada başlatma
kısmi sahiplik kaydını recovery_required bırakır; açık oyunda rollback silmez.
14 yeni Python test örneği yol/ad ayrımı, erişim hatası, envanter/ekleme/silme
ortasında başlatma ve kurtarmayı doğrular; bir test gerçek kendi PID'sini salt
okunur sorgular. Referans oyun o an kapalı gözlendi; oyun başlatılmadı veya
kurulmadı. [Sınırlar](game-process-check.md). Servis preview.3 içindedir;
gerçek etkinleştirme UI/CLI'a açılmadı.

Metinler sekmesi oyun durumunu arka planda sorgular; açık/kapalı/belirsiz sonuç
ve UTC zamanı gösterilir. Üç durumun UI testleri ve sorgu sırasında proje
değişimi testi geçti. Geç gelen eski proje/istek sonuçları gösterilmez.
Offscreen ekran görüntüsü incelendi. Düğme oyun başlatmaz veya kurulum yapmaz;
arayüz eklemesi preview.3 paketindedir.

Kalıcı insan taslağı deposu ve proje kimliği kontrollü uygulama komutları
eklendi. Şema 3 → 4 yedekli migration, tamamlanmamış metni aynen saklama,
yeniden açma, eski kaynak/iş sürümü reddi, onay koruması, taslak belirteci ve
transaction hata senaryoları geçti. Arayüz 250 ms gecikmeli, tek uçuşlu
otomatik saklama ve geri yüklemeyi kullanır. Normal kapanma/proje değişimi
saklamayı bekler; hata kapanışı durdurur. Kaynak değişimi eski kaynak/taslağı
birlikte korur; açık kaldırma güncel metne geçer. Kayıt gezinme, yenileme,
hemen kapanma/yeniden açma, hızlı yazma ve saklama hatası Qt testleri geçti.
601 kayıtlı kaynak ve frozen UI doğrulamasında draft_autosave_verified dahil
tüm bayraklar geçti; bu temiz Windows kanıtı değildir. JSON 2 taslak
taşımaz; taslaklar SQLite'ta kalır.
Eski preview.2 şema 4 açamaz; preview.3 açar. [Kapsam](editor-drafts.md).

Preview.3 izole PATH/Python ortamında 601 sentetik kaydın UI akışını geçti:
200 satır, ayrı kaydetme/onay, çoğul modalı, Unicode/CRLF, kapanış taslağının
SQLite'ta yeniden okunması, boş oyunun belirsiz durumu ve Windows kendi-PID
sorgusu. Frozen EXE ile gerçek I2 kaynakta 6.749 kayıt yeniden çıkarıldı;
worker önce/sonra ve süreç bittikten sonraki asset hash'leri eşittir. Oyun
başlatılmadı; tüm kurulum hash envanteri veya oyun içi uygulama kanıtı değildir.
Native UI görüntüleri incelendi. Önceki ZIP'ler korundu. Paketleme aracı
envanter/hash ve ZIP CRC/içerik hash'lerini doğrular; mevcut arşivi ezmez.

Koruma servisi değişken veriyi açık seçimle ayrı raporlayabilir. İlk kapsam
Logs/<dosya>.log, Saves/<dosya>.sav ve Cache/<dosya>.cache tek yollarıdır;
Unity/loader varlığı, wildcard/dizin ve bilinen okuyucu kaynağı reddedilir.
Seçimler biçim 2 envanterin parmak izine bağlı ve değişmezdir. Dışlanan yollar
uygulama veya kaldırma hedefi olamaz. 18 yeni sentetik test örneği seçim kapısı,
log rotasyonu/save/cache değişimi, politika/receipt bozulması ve eski envanteri
doğruladı. Gerçek oyun seçimi yapılmadı; UI/CLI etkinleştirme açılmadı ve mevcut
preview.3 bu kaynak değişikliğini içermez. [Kapsam](inventory-exclusions.md).

Yükleyici sürüm/kaynak ve bildirim hazırlığı ilerledi: 13 DLL resmî BepInEx
release byte'larıyla, yedisi resmî NuGet ve winhttp x64 resmî Doorstop arşiviyle
eşleşti. Yedi kaynak commit'i (alt projeler dahil) ve dokuz tam lisans metni
izlenir. MS-PL CCI/PDB ve asıl Harmony telif bildirimi korundu. Katalog/lisans
integrity testleri geçti. DLL veya kaynak ZIP'ler sdist/CI'a eklenmedi; loader
oyunda çalıştırılmadı. Son mod paketinin kaynak erişimi/bildirim kapsamı hâlâ
doğrulanmamıştır. [Bileşen denetimi](loader-component-audit.md).

Çevrimdışı loader destek paketi servisi ve geliştirici komutu eklendi.
Doğrulanmış önbellekten 31 dosya/16.263.659 bayt proje alanına hazırlandı:
13 DLL, dokuz lisans, yedi kaynak ZIP'i ve iki açıklama/metaveri dosyası.
Tüm kopya hash'leri ve yedi kaynak ZIP CRC'si doğrulandı. Yedi yeni sentetik
test örneği kaynak/oyun koruması, hatalı hash, yol kaçışı, eksik lisans ve
kısmi kopyalama hatasını doğruladı. Plugin/çeviri/çalışma ayarı ve kurulum
planı içermez; yayımlanmadı veya oyunda çalıştırılmadı. Bu kaynak değişikliği
mevcut preview.3'te yoktur. [Kapsam](loader-support-package.md).

Kullanıcı ayrı rapordaki beş kaydı tek tek onayladı; tüm revizyon/sürüm/metin
eşleşmeleri doğrulanıp transaction içinde kaydedildi. Gerçek onaylı sayı 5'tir.
Yalnızca bu beş onaylı I2 kaydının deneysel payload'ı üretildi; Assembly-CSharp
hash'i değişmedi. Onay oyun kurulumu veya başlatma yetkisi değildir.

Stok BepInEx 5.4.23.5 kaynak/CIL denetiminde koşulsuz interop shim bağlantısı
ve uygun eski Harmony referansında yedek + yerinde DLL yazımı bulundu. Bilinen
iki stok DLL hash'i özgün dosya koruması için unsupported, değiştirilmiş
sürümler unknown kalır. Hash/lisans eşleşmesi güvenli loader kanıtı değildir.
Gerçek loader veya oyun çalıştırılmadı. Bu yazma yolu ve config/log/cache
sahipliği çözülmeden etkinleştirme açılmayacaktır. Masaüstü akışlar sürer;
[kanıt ve sınırlar](loader-write-safety.md). Mevcut preview.3 bu yeni core
değerlendirmesini içermez; orada da kurulum akışı zaten bulunmaz.

Deneysel preloader koruma değişikliği dev önbelleğinde derlendi. Shim
çağrısı/gövdesi, interop AssemblyRef ve oyun-kökü iki hata yazımı kaldırıldı.
Başlangıç dış runtime ağacını zorunlu kılar; diagnostics yalnızca CreateNew
ile yeni proje logu açar, oyun/CWD geri dönüşü yoktur. Gerçek eski Mono
referanslarıyla derleme ve CIL grafiği geçti; referans hash'leri değişmedi.
`tools/check.py --with-dotnet` artık 14 sentetik Windows diagnostics kontrolü
de çalıştırır; hepsi geçti. Gerçek loader/oyun/Mono çalıştırılmadı. Değiştirilmiş
loader için application=unknown kalır; config/cache/native/font/sahne ve
somut oyun denemesi kapıları açıktır. Prototip preview.3'e dahil değildir.
[Sınırlar](../adapters/bepinex-protected/README.md).

Oyun dışı runtime hazırlığı dokuz doğrulanmış DLL'yi yeni proje artefaktına
kopyaladı; shim/legacy DLL'leri yok. CIL tekrar doğrulandı. Disabled Doorstop
INI ve runtime BepInEx.cfg üretildi; disk logu, metadata cache ve dump kapalı.
Dört yeni Python test örneği mevcut dosya/oyun koruması, ayarlar, bool seçimi
ve gerçek Windows INI Unicode yol okumasını doğruladı. Plugin/çeviri ve iki
oyun-hedefli dosyanın kurulum planı henüz eklenmedi; oyun çalıştırılmadı ve
game_written=false. Mevcut preview.3 bu kaynak değişikliğini içermez.
[Ayar kapsamı](external-runtime-settings.md).

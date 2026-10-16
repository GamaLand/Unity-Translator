# Özgün dosyalara dokunmayan uygulama fizibilitesi

14 Ekim 2026. `application=unknown`; kullanıcı seçimiyle yapılan geçici
denemede beş ana menü çevirisi ve Türkçe karakterler görsel olarak doğrulandı.
Deneme ve sahipli eklerin kaldırılması sonrası 526 özgün dosyanın hash'i
değişmedi. Diğer oyun içi kabul kapıları açıktır; genel kurulabilir yama
iddiası yoktur. [Güncel kanıt](../main-menu-trial-diagnostics.md).
Aşağıdaki keşif gözlemleri ilk salt okunur incelemenin tarihsel bulgularıdır.

## Salt okunur gerçek gözlemler

- Referans executable PE makinesi `0x8664` (x64). Unity 2017.4.19f1 ve Mono
  göstergeleri önceki kaynak incelemesinde doğrulandı.
- Assembly-CSharp.dll statik dnfile metaverisinde I2.Loc.LanguageSource için
  AddLanguage, GetLanguageIndexFromCode, GetTermData, LoadLanguage,
  UpdateDictionary; TermData için SetTranslation; LocalizationManager için
  Sources, CurrentLanguageCode, LocalizeAll üyeleri bulundu. Assembly yüklenip
  çalıştırılmadı; okuma öncesi/sonrası SHA-256 eşit kaldı.
- StreamingAssets dizini listesinde ses bankaları bulundu, dil dosyası
  görülmedi. Bu liste, oyunun başka konumda haricî kaynak desteklemediğini
  kanıtlamaz. I2 Import_CSV metodunun bulunması da oyunun kendiliğinden CSV
  yüklediği anlamına gelmez.
- Kurulum kökünde mevcut winhttp.dll veya BepInEx dizini görülmedi. Bunlar
  sonraki planın yeni hedef adaylarıdır; etkinleştirme anında yeniden çakışma
  kontrolü yapılmadan güvenli kabul edilmez.

## Çalışma anı adayının sınırı

[BepInEx 5 kurulum belgesi](https://docs.bepinex.dev/articles/user_guide/installation/index.html)
x64 paketin oyun köküne çıkarılmasını ve ilk çalıştırmada yeni yapılandırma/log
dosyalarının oluşmasını anlatır. Bu, mevcut dosyanın değiştirilmesini
gerektirmeyen bir aday olabilir; özel oyunda çalışma garantisi değildir.
Hardpatcher ve mevcut Unity/Mono dosyasını değiştiren sorun giderme yolları
bu projenin kurallarına uygun değildir. İlk testte bu yollara geçilmez.

[BepInEx 5 kaynak lisansı](https://github.com/BepInEx/BepInEx/blob/v5-lts/LICENSE)
MIT'tir. Seçilecek gerçek paket ve Doorstop/Harmony gibi bileşenleri ayrıca
kilitlenmeli, hash ve lisansları incelenmelidir. BepInEx 5.4.23.5 x64 paketinin
geliştirme önbelleğine indirilmesi ve digest kontrolü sonraki prototipte
yapıldı; oyun kurulumu veya son kullanıcı paketine dahil etme yapılmadı.

Bir C# adaptörü için sonraki kanıtlar: gerçek metod imzaları/runtime hedefi,
ana thread üzerinde I2 kaynak keşfi ve kaynak hash eşlemesi, yalnızca seçilmiş
terimlerin bellek içinde değiştirilmesi, sahne/dil değişiminde davranış,
font glifleri ve taşma. İnternet veya Google import metotları çağrılmaz.
Oyun assembly'si kaynak deposuna veya pakete alınmaz.

## Etkinleştirme/kaldırma altyapısı

deployment.py proje içindeki paket dosyalarından yerel plan üretir. Adaptör
henüz olmadığı için gerçek oyuna bağlı UI/CLI etkinleştirme komutu yoktur.
Servis sadece açık kullanıcı eylemi ve adaptör doğrulama bilgisiyle çağrılabilir;
bu bilgiyi JSON içe aktarımı sağlamaz.

İlk SHA-256 envanteri proje içindedir ve sonraki planlarda korunur. Şimdilik
bütün kurulum dosyaları kapsanır; log/save/cache için sessiz dışlama yoktur.
Gerçek oyun çalıştırılmadan önce değişken kullanıcı verileri için açık ve dar
dışlama kuralları belirlenmelidir. Özgün asset'ler dışlanamaz.

Plan kaynak/hedef yollarını, hash'leri, oyun parmak izini ve adaptör sürümünü
taşır. Çakışma, oyun güncellemesi, paket değişimi, case alias, yol kaçışı,
ADS, hard link ve reparse point kontrolleri yapılır. Yeni dosya exclusive
oluşturulur; manifest önceden kalıcılaşır, oluşturulan dosyanın cihaz/inode
kimliği yazmadan önce kaydedilir. Çökme bu kayıt öncesinde olursa sahipliği
kanıtlanamayan dosya korunur ve kurtarma gerekli olarak raporlanır.

Kaldırma yalnızca kayıtlı kimlik ve hash'i aynı ekleri siler. Kısmi veya
kullanıcının değiştirdiği dosyalar korunur; özgün dosyayı yedekten geri yazma
işlemi yoktur. Boş mod dizinleri bırakılır; mevcut dizinler kaldırılmaz.
Özgün dosyanın eksik/değişmiş olması doğrulama hatasıdır. Manifest/plan içe
aktarmak kurulum yetkisi vermez. Aynı kullanıcı hesabının eşzamanlı kötü
niyetli yol değiştirmesine karşı OS sandbox garantisi verilmez.

20 sentetik test yeni dosya ekleme/kaldırma, açık kullanıcı/adaptör kapısı,
çakışma, eski parmak izi, kısmi hata/çökme, değiştirilmiş ekin korunması ve
özgün hash eşitliğini doğrular. Bu testler gerçek yükleyici veya oyunda
Türkçe yerelleştirme kanıtı değildir.

Sonraki [C# prototip](../../adapters/i2mono/README.md) gerçek referanslarla
derlendi. mscorlib assembly sürümü 2.0.0.0, metaveri runtime v2.0.50727 olarak
okundu. I2 AddLanguage(string,string), GetLanguageIndexFromCode(string,bool),
GetTermData(string,bool), SetTranslation(int,string,string), UpdateDictionary(bool)
ve LocalizeAll(bool) imzaları statik doğrulandı. Güncel 13 çekirdek ve beş
I2 sarmalayıcı senaryosu sentetik ortamda geçti; Plugin'in gerçek I2
implementasyonu çalıştırılmadı. Dosya/PlayerPrefs yazma yolları nedeniyle
bu API'lerin bir kısmı plugin tarafından çağrılmaz; güncel bellek yaklaşımı
adaptör README'sinde açıklanır.

## Font kapsamı: statik bulgu

`tools/audit_unity_fonts.py` her asset dosyasını ayrı, süre sınırlı Python
sürecinde okur. Kaynak ve başvurulan script metaverisinin analiz öncesi/sonrası
SHA-256 eşitliği kontrol edilir; rapor oyun kökünden ayrı tutulur. Gömülü
font ikilisi dışa aktarılmaz. fontTools yalnızca geliştirme bağımlılığıdır.
Unicode eşlemesi için [getBestCmap](https://fonttools.readthedocs.io/en/latest/ttLib/ttFont.html)
kullanılır; `.notdef` veya sıfır glif kimliği destek sayılmaz.

Yerel kurulumun kök Data dizinindeki 105 `.assets` dosyası native `Font`
nesneleri için tarandı. İki gömülü font (`VeraMono`, `VeraMono-Bold`) bulundu;
ikisinin Unicode cmap'inde `çÇğĞıİöÖşŞüÜ` karakterlerinin tamamı eşleşiyor.
Serialized atlas karakter listeleri boş ve birer fallback başvurusu var;
fallback çözülmedi. Bu fontların oyun arayüzünde kullanıldığı kanıtlanmadı.

Kaynak ve fontların bulunduğu asset üzerinde ek script kimliği incelemesi,
üç `TMPro.TMP_FontAsset` nesnesi buldu: Beholder SDF, Cone SDF ve
Titillium-Regular SDF. Eksik type tree nedeniyle bu üçünün atlas glif
listesi mevcut okuyucuyla çözülemedi; kapsamları **unknown**. TMP taraması
yalnızca bu iki asset'i kapsar; 105 dosyanın tamamı için TMP envanteri iddiası
yoktur. Kaynak hash kontrolleri geçti, script tanımlama hatası görülmedi.

Yerel ayrıntılar `.local/mechanicus/font-audit-all-assets.json` ve
`.local/mechanicus/font-system-audit.json` dosyalarında tutulur; kaynak
depoya/CI'a gerçek veri eklenmez. Dört sentetik test tam/kısmi cmap,
geçersiz/eksik font verisi ve TMP glif şemasını doğrular. Statik eşleme
görünür glif, doğru font seçimi, Türkçe büyük/küçük harf, sahne geçişi veya
metin taşması testi değildir. `application=unknown` sonucu korunur.

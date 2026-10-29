# UnityTranslator kullanım rehberi

## Krypta FM metinleri

Eşleşen Krypta FM sürümünde kaynak `en`, hedef `tr` seçin. Profil 2; 34 TextAsset ve bir günlük dizisinden 449 alanı kapsar. İki kaynak ile profil dışı arayüz/görsel metinleri kapsanmaz. Önceki kimlikler ve onaylar korunur.

Çevirileri inceleyip onayladıktan sonra oyunu kapatın. **Oyuna uygula** bölümünde iki yeni dosyanın (`winhttp.dll`, `doorstop_config.ini`) planını hazırlayıp inceleyin ve kurulumu onaylayın. Deneysel çalışma zamanı ayrı projede kalır; özgün oyun dosyaları değiştirilmez. Ekleri aynı projeden kaldırın. Metin çıktısı kurulum paketi değildir; paylaşılabilir kurulum ZIP’i eşleşen Krypta en→tr sürümünü de destekler. Alıcı ZIP’i ayrı klasöre çıkarır, Kur.cmd ile oyun klasörünü seçer, dosya planını inceleyip INSTALL yazar. Kaldir.cmd yalnızca değişmemiş, pakete ait ekleri kaldırır. Taşınabilir kurulum/kaldırma sentetik olarak test edilmiştir; bu birleşimin ayrıca oyun içi kontrolü ertelenmiştir. Başlangıç/menü, ayarlar, oynanışa geçiş, duraklatma ve altyazılar gözlemlendi. Diğer ekranlar, dil geçişi ve metin yerleşimi elle kontrol edilmelidir; uzun bir ayar etiketi açıklamasıyla çakışabilir.

## Kurulum ve dil seçimi

Windows x64 uygulama ZIP’inin **tamamını** ayrı bir klasöre çıkarıp
`UnityTranslator.exe` dosyasını açın. Hazır paket Python gerektirmez. Kaynaktan çalıştırmak için:

```powershell
uv sync --locked --extra ui
uv run --extra ui unitytranslator gui
```

Varsayılan arayüz dili İngilizcedir. **Help** yanındaki **Language** menüsünden Türkçe
veya diğer dilleri seçin; seçim uygulama yeniden açılınca etkinleşir.
Arayüz dili, projenin kaynak/hedef dilini değiştirmez.

## Çeviri

1. **Proje:** oyun klasörünü ve ondan ayrı bir çalışma klasörünü seçin. Kaynak ve hedef
   dil kodlarını belirleyin. Mevcut çalışmaya **Kayıtlı proje aç** ile devam edin.
2. **Metinler:** salt okunur taramayı çalıştırın, desteklenen kaynağı seçip metinleri çıkarın.
   Metin çıkarma ve oyuna uygulama desteği ayrı değerlendirilir.
3. **Model:** LM Studio veya llama-server’ı açıp modeli kendiniz yükleyin. Yerel adresi
   ve model kimliğini girip bağlantıyı test edin. Uygulama sunucuyu/modeli başlatmaz.
4. **Sözlük:** isteğe bağlı korunacak adlar, tercih edilen terimler ve üslup ekleyin.
5. **Çeviri:** önce temsilî pilotu çalıştırıp inceleyin, sonra toplu işe geçin. Sunucunuza
   göre 1–36 paralel istek seçin. Pencere küçültülünce çeviri sürer. Duraklatma yeni
   istekleri durdurup devam edenleri bekler; iptal istemci görevlerini keser.
6. **İnceleme:** kaynakla çeviriyi karşılaştırın, düzeltmeleri kaydedip ayrıca onaylayın.
   Taslak kaydı onay değildir. Sayfa onayı yalnızca o sayfadaki seçilmiş uygun kayıtları
   kapsar. **Bütün çevirileri onayla** için önce sayı/uyarıları kabul edin; ikinci adımda
   gösterilen ifadeyi aynen yazıp son düğmeye basın. İki adımda da vazgeçebilirsiniz.
   Taslaklı ve biçim hatalı kayıtlar dışarıda kalır; liste değişirse işlem durur.

## Yedekleme, kurulum ve paylaşım

**Dışa aktar** bölümünden JSON veya proje veri yedeği oluşturun. Desteklenen oyunda
oyunu kapatıp **Oyuna uygula** bölümünde planı hazırlayın, yeni dosyaları inceleyip
kurulumu ayrıca onaylayın. Oyunu kendiniz açıp karakterleri, taşmaları ve anlamı kontrol
edin. Uyumluluk deneyseldir; otomatik kontroller kalite garantisi değildir.

Ekleri kuran projeden kaldırın. Çakışan `winhttp.dll`/`doorstop_config.ini` dosyalarını
körlemesine silmeyin ve özgün envanteri sıfırlamayın. Eski projeyi açıp sahiplik denetimli
kaldırmayı kullanın. [Geliştirici düzeltme rehberi](../docs/installation.md).

Paylaşılabilir ZIP onaylı çevirileri ve gerekli çalışma bileşenlerini içerir. Arkadaşınız
ZIP’i çıkarıp `Kur.cmd` ile eşleşen oyun klasörünü seçer; `Kaldir.cmd` sahipliği/hash’i
eşleşen ekleri kaldırır. Model veya UnityTranslator gerekmez. Lisans/kaynakları koruyun.
Bütün Unity oyunları desteklenmez; bazı teknik tanılar özgün dilinde kalabilir.


Oyun çevirisinde kaynak ve hedef dil, arayüz dilinden bağımsızdır. Japonca için ja, İtalyanca için it, Brezilya Portekizcesi için pt-BR yazın; başka dil kodları da girilebilir. Kaynak dil oyunda bulunmalıdır; eksik veya belirsiz dil sütunları reddedilir. Model dil çiftini desteklemelidir. Mevcut projelerin dilleri, onayları ve özel üslupları korunur; eski dile özel üslup kurallarını gözden geçirin. Dağıtımdan önce küçük bir yamada yazı tiplerini, sağdan sola düzeni ve çoğul biçimlerini kontrol edin. İngilizce de hedef olabilir.

Gelişmiş model ayarlarında LM Studio istekleri için model düşünmesini isteğe bağlı kapatabilirsin. Böylece çeviriye daha fazla çıktı bütçesi kalabilir. Destek, yüklü model ve sunucuya bağlıdır; desteklenmeyen seçenek işi durdurabilir. Varsayılanlar ve sunucunun genel ayarları korunur.

## Ren'Py çevirisi

Metinler sekmesinde motoru seçip tarayın. `game/tl/<dil>/*.rpy` şablonlarından biri
aynı dil klasörünün tamamını okur. Özgün `.rpy`, doğrulanmış `_ren.py` ve kaynak betik
içeren RPA-3.0 girdileri, Ren'Py 8.1.2 ve 8.3.6 ile karşılaştırılan kaynak davranışı
sözleşmeleriyle denetlenir; sürüm numarası tek başına destek sağlamaz. Büyük kümeler
ve çakışmayan gevşek dosya/arşiv birleşimleri desteklenir; aynı yol veya kaynak taban
adındaki çakışmalar reddedilir. Tek satırlı diyaloglar, karakter ve geçici `@`
nitelikleri, `nointeract`, açık `_()` anahtarları ve seçim/menü başlıkları kapsanır.
Menü konuşması seçeneklerden önce gelmeli ve başlıklarla karışmamalıdır. Voice/nvl
grupları, çok satırlı diyalog, dinamik metin, yalnızca derlenmiş betikler ve görsel
yazıları kapsam dışındadır; bildirilen eksikleri kontrol edin. Oyun kodu çalıştırılmaz.
Büyük dışa aktarımlar numaralı dosyalara bölünebilir; çıktı ağacını bir arada tutun.

Kurulum ZIP’i hâlâ yalnızca Ren'Py `8.1.2.23090503` için desteklenir; özel depo, yapay zekâ araçları veya kimlik bilgisi metaverileri kopya paketlemeyi durdurur.

Mevcut model, pilot, taslak ve insan incelemesi akışını kullanın. Şablondaki eski
çeviriler geçmişte salt okunur gösterilir; otomatik onaylanmaz. İncelemede kaynak
üyesi, satır, yerel blok ve konuşmacı görünür. İnsan onayından sonra hedef dil için
`turkish` gibi açık bir Ren'Py tanımlayıcısı girin; `tr` otomatik eşlenmez.
Önce taslakları tamamlayın veya kaldırın. Yerel dosya dışa aktarma, onaylı metinleri
ve kapsam manifestini proje içinde hazırlar. Onaysız anahtarlar atlanır; aynı global
anahtarın çelişen onaylı çevirileri dışa aktarmayı durdurur.

**Ren'Py kurulum ZIP'i oluştur**, tek kök oyun EXE'si bulunan eşleşen sürümü destekler.
ZIP oyun varlıkları içermez. Özgün oyunun dışında çıkarıp `Install.cmd` çalıştırın;
eşleşen özgün oyun ile ayrı bir çıktı üst klasörü seçin ve kesin yeni dosya planını
inceleyin. Kurulum ek disk alanında tam bir çevrilmiş kopya hazırlar; özgün dosyaları
değiştirmez ve oyunu başlatmaz.

Yeni kopyadaki `Play-Translated.cmd` paketin dilini seçerek oyunu açar. Özgün kayıtlar,
loglar ve önbellekler kopyalanmaz; yeni kopyanın kayıtları ayrıdır.
Alıcıda Python, model veya UnityTranslator gerekmez. ZIP'i saklayın: `Remove.cmd`
yalnızca değişmemiş sahipli kopya dosyalarını kaldırır. Değiştirilmiş ve çalışma
sırasında oluşmuş dosyalar, derlenmiş yan dosyalar, kayıtlar ve makbuz korunur.
Kaldırma, kopya klasörünün tamamen boşaltılması anlamına gelmez.

CLI'da `extract --game ... --project ... --source game/archive.rpa --engine renpy`,
`export-renpy --game ... --project ... --language turkish` ve
`export-renpy-zip --game ... --project ... --language turkish` aynı denetimleri kullanır.
Özgün oyun klasörüne doğrudan kurulum desteklenmez. Yazı tipi, taşmalar ve diğer
sahneler oyun içinde ayrıca incelenmelidir.

Pilot raporu işi hâlâ çalışıyor gösteriyorsa iş durduktan sonra raporu yenileyin. Gerekli örneklemin tamamı denenmiş ve tamamlanan sonuçlar varsa iptal edilmiş pilot da değerlendirilebilir. Değerlendirme aynı ayarlar ve kaynaklar için toplu işi açar; çevirileri onaylamaz.

Pilot incelemesinden sonra kaydettiğin sözlük/üslup değişiklikleri, yeni pilot gerektirmeden yeni isteklere uygulanır. Devam eden istekler gönderildikleri kurallarla tamamlanır; mevcut çeviriler değişmez. Etkilenen kayıtları inceleyip gerekirse ayrıca yeniden çevir. İncelenmiş pilot ayarlarını kullan, güncel sözlük/üslubu koruyarak model ve üretim ayarlarını geri getirir.

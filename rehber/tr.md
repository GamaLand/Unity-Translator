# UnityTranslator kullanım rehberi

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
   göre 1–16 paralel istek seçin. Pencere küçültülünce çeviri sürer. Duraklatma yeni
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
kaldırmayı kullanın. [Geliştirici düzeltme rehberi](../docs/development.md).

Paylaşılabilir ZIP onaylı çevirileri ve gerekli çalışma bileşenlerini içerir. Arkadaşınız
ZIP’i çıkarıp `Kur.cmd` ile eşleşen oyun klasörünü seçer; `Kaldir.cmd` sahipliği/hash’i
eşleşen ekleri kaldırır. Model veya UnityTranslator gerekmez. Lisans/kaynakları koruyun.
Bütün Unity oyunları desteklenmez; bazı teknik tanılar özgün dilinde kalabilir.


Oyun çevirisinde kaynak ve hedef dil, arayüz dilinden bağımsızdır. Japonca için ja, İtalyanca için it, Brezilya Portekizcesi için pt-BR yazın; başka dil kodları da girilebilir. Kaynak dil oyunda bulunmalıdır; eksik veya belirsiz dil sütunları reddedilir. Model dil çiftini desteklemelidir. Mevcut projelerin dilleri, onayları ve özel üslupları korunur; eski dile özel üslup kurallarını gözden geçirin. Dağıtımdan önce küçük bir yamada yazı tiplerini, sağdan sola düzeni ve çoğul biçimlerini kontrol edin. İngilizce de hedef olabilir.

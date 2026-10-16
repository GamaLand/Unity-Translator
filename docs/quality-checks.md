# Çeviri inceleme kontrolleri

`review-en-tr-v4` yeni model, elle düzenleme ve içe aktarma adaylarında çalışır.
Kesin değişken/etiket/biçim ihlalleri ayrı tutulur; aşağıdaki dilsel bulgular
`needs_review` üretir. Uyarı çeviriyi düzeltmez, yeniden üretmez veya onaylamaz.
Sert biçim hatası bulunmayan adayı insan açıkça onaylayabilir. Önceden onaylı
metnin yerine gelen aday, onayı kendiliğinden değiştiremez.

| Kontrol | İncelemeye ayıran bulgu | Sınır |
| --- | --- | --- |
| Kaynakla aynı | Kaynak ve çeviri aynı | Özel adın aynı kalması doğru olabilir |
| Sayı/işaret | Korunmayan sayı, adet veya işaret | Aynı sayısal yazım korunmuş sayılır; bunun bağlamda doğru anlam taşıdığı kanıtlanmaz |
| Yüzde | `%50`, `50%`, `50 percent`, `yüzde 50` eşlemesi kayıp/değişmiş | Yazıyla sayı, farklı dillerde yüzde adları ve bütün yerel sayı biçimleri çözülmez |
| Olumsuzluk | İngilizce açık olumsuzluk için Türkçe ipucu bulunmaması veya açık `can` ifadesine Türkçe olumsuzluk eklenmesi | Türkçe ek/kelime ipuçları sınırlıdır; örtük olumsuzluk, deyim ve tüm çekimler çözülmez |
| Koşul/sınır | Kaynaktaki `at least`, `at most`, `more/less than`, `only`, `if/unless`, `before/after/until` ipucunun Türkçe karşılığının bulunmaması | Koşulların kime/neye bağlandığı ve eksiksiz anlam eşitliği kanıtlanmaz; hedefte eklenen bütün koşullar yakalanmaz |
| Sözlük | İşin dondurulmuş ilgili sözlük karşılığı bulunmaması | Sözlük kontrolü iş katmanında yapılır; yeniden kontrol raporu geçmiş işin sözlük kontrolünü tekrar hesaplamaz |

Ondalık/binlik yazımı değişirse `en`/`tr` için açık düzenle karşılaştırılır:
`1,000` → `1.000` ve `1.5` → `1,5` eşdeğer kabul edilir. Aynı yazımla korunan
sayılar marka ve sürüm metinlerinde de korunmuş sayılır. Hesaplama Decimal ile
hassasiyet kaybı olmadan yapılır; belirsiz gruplama aynı değermiş gibi dönüştürülmez.
Etiket parametreleri ve değişken kimlikleri sayı/dil kontrolünden çıkarılır.
Negatif sayı işareti korunmalıdır; pozitif `+3` ve `3` aynı sayısal değerdir.

Dilsel olumsuzluk/koşul ipuçları yalnızca İngilizce→Türkçe dil çiftinde çalışır;
`en-US`/`tr-TR` gibi etiketler de bu gruba girer. Başka dil çiftlerine Türkçe
kurallar uygulanmaz. Türkçe harf işlemleri `I/ı`, `İ/i` ayrımını korur.
`yok etmek/saymak` ifadesindeki `yok` tek başına olumsuzluk sayılmaz.
Metin bağlamını anlayan bir dil çözümleyici bulunmaz; yanlış uyarı veya
kaçırılmış hata olabilir. Uyarı bulunmaması kalite kanıtı değildir.

İnceleme ekranında **Mevcut çevirilerin kalite kontrollerini yeniden raporla**
düğmesi eski adayları güncel kontrollerle ayrı bir JSON/HTML raporuna ölçer.
Yalnızca etkin kaynakla eşleşen güncel çeviriler kapsanır. Revizyonlar, durumlar,
onaylar ve eski pilot sonuçları değiştirilmez; model çağrısı yapılmaz.
Raporun JSON dosyası tüm bulguları, çevrimdışı HTML ilk 200 uyarılı kaydı içerir.
Bu rapor eski adaylara yeni sözlük onayı vermez ve otomatik durum filtresi güncellemez.

Yeni aday metaverisi kontrol sürümünü taşır. Yeni rapor sürümü ile tarihsel
adayın saklanan sorun listesi ayrı gösterilir. Arayüz ve HTML sabit kontrol
kodlarını Türkçe açıklamalarla sunar; bilinmeyen kod görünür kalır.

I2 çoğul adaylarının her dalı kendi kaynağıyla kontrol edilir; iki dal arasında
sayıların yer değiştirmesi global adet eşit olsa da uyarı üretir. Çoğul aday
her zaman `plural_content_review` taşır. Dal/sıra veya değişken aktarımı ise
sert biçim hatasıdır. [Çoğul koruma sözleşmesi](protected-format.md).

Sağlayıcı hatalarında kesik çıktı (`output_truncated`) ve beklenmeyen araç
çağrısı (`unexpected_tool_call`) ayrı kaydedilir. JSON/kimlik hatası ve korumalı
içerik hatasıyla birlikte toplam üç denemelik bütçe kullanılır. Araç çağrıları
çalıştırılmaz; kesik veya bozuk cevap taslağa/onaya dönüşmez. Eski genel hata
kodları, ham cevap saklanmadığı için geriye dönük bu sınıflara ayrılmaz.

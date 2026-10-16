# Korumalı metin biçimi

`protected-i2-v4` doğrulanmış yapıları rastgele istek belirteçleriyle maskeler.
Model yalnızca metin verisi üretir. Cevapta her belirteç tam bir kez bulunmalı;
geri yükleme sonrası yapıların adetleri ve etiket dengesi yeniden doğrulanır.
Eksik/fazla/değişmiş yapı etkin çeviri yapılmaz. Yeniden sıralama çeviri dilinin
söz dizimi için mümkündür; değişkenin cümledeki anlam rolünü kanıtlamaz.

| Yapı | Kabul edilen dar biçim |
| --- | --- |
| Basit değişken | `{0}`, `{name}`; ASCII harf/rakam/alt çizgi |
| I2 parametresi | `{[PARAMETER]}`; aynı ad sınırı |
| Sayı biçimi | `{0:F1}`; ASCII sayısal indeks, `F/f` ve 1–2 basamaklı hassasiyet |
| Rich text | Dengeli `b`, `i`, `color`; `b/i` ve kapanış etiketleri parametresiz |
| Dinamik renk | `<color=#{[COLOR]}>` bütün açılış etiketiyle korunur |
| Boyut | Dengeli `<size=80%>` veya `<size=20>`; pozitif 1–999 tam sayı |
| Sprite | Atomik `<sprite name="BUTTON">`; ad 1–128 ASCII harf/rakam/alt çizgi/tire |
| I2 çoğul | Etiketsiz Plural kökü, birer `[i2p_One]` ve isteğe bağlı `[i2p_Zero]`; kaynak sırası korunur |
| Satır sonu | LF, CRLF, CR aynen korunur |
| Karşılaştırma | İki yanında boşluk karakteri olan tek `<` veya `>` aynen korunur |

I2 parametre biçimi [I2 Parameters belgesi](https://inter-illusion.com/assets/I2LocalizationManual/Parameters.html)
ile doğrulandı. Referans oyunun `ApplyLocalizationParams` metotlarından biri
salt okunur CIL incelemesinde `{[` ve `]}` sınır sabitlerini içeriyor.
Assembly CLR'ye yüklenmedi; analiz öncesi/sonrası SHA-256 eşit kaldı.
Dinamik renk ve ASCII parametre adları gerçek yerel kaynakta gözlendi.
Unity 2017 [rich-text açıklaması](https://docs.unity3d.com/es/2017.4/ScriptReference/TextMesh-richText.html)
renk etiketini anlatır; bütün Unity/TMP etiketleri desteklenmiş sayılmaz.

Renk etiketinin tamamı maskelenir; model içindeki renk parametresini değiştiremez.
Etiket içinde tanınmayan süslü parantez biçimi reddedilir. Ayrı I2 parametrelerinin
kimlikleri/adetleri korunur. Python ve C# aynı grammar'ı uygular. 63 ortak sentetik
JSON örneği kabul/red eşleşmesini doğrular; gerçek oyun assembly'si testlerde çalışmaz.

Boyut/sprite/formatlı değişken bütünüyle maskelenir; model değer, sprite adı,
indeks veya hassasiyeti değiştiremez. Boyut etiketi iç içe dengelenir; sprite
tek görsel başvurusu sayılır, kapanış etiketi kabul edilmez. Sayı/yüzde
incelemesi etiket parametrelerini ve format indekslerini oyun sayısı sanmaz.
Bu üç biçim gerçek kaynakta görüldü. [TMP Font Size](https://docs.unity3d.com/Packages/com.unity.textmeshpro@3.2/manual/RichTextSize.html),
[TMP Sprite](https://docs.unity3d.com/Packages/com.unity.textmeshpro@3.2/manual/RichTextSprite.html)
ve [Microsoft composite formatting](https://learn.microsoft.com/en-us/dotnet/standard/base-types/composite-formatting)
sözdizimini açıklar. Bunlar farklı/güncel sürüm belgeleridir; eski oyunda
işleyiş kanıtı sayılmaz. Referans kurulumda TextMeshPro-2017.1-Runtime.dll
bulundu; CLR'ye yüklenmedi. V3 C# adaptörü gerçek referanslarla derlendi;
referans hash'leri değişmedi ve oyun çalıştırılmadı.

Doğrulanmamış diğer `[i2p_...]` türleri, F/f dışı sayı biçimleri,
alignment/custom format, diğer boyut/sprite attribute'ları,
bilinmeyen etiketler ve bitişik açı parantezleri
reddedilir. Model/düzenleme/içe aktarma içinde `__UT_` öneki kullanılamaz.
Yeni biçim için kaynak grammar'ı ve uygulama tarafı birlikte doğrulanmalıdır.

Yeni aday ve model sonucu `protected_format_version` metaverisini taşır.
Eski aday/pilot metaverisi yeniden yazılmaz. Runtime veri şeması sürüm 1 kalır;
alanlar değişmez, metin grammar'ı genişler. C# adaptörü hâlâ deneyseldir;
oyun içi dinamik değer/renk görünümü testi yapılmadı.

V3 ile 6.749 gerçek kaynağın 6.723'ü statik kontrolü geçti; 22 çoğul ve dört
diğer açı-parantezli yapı ayrı kaldı. V2'nin önceki ölçümü 6.719/30 idi;
V3 iki boyut etiketi, bir sprite ve bir F1 değişkenini daha kapsadı.
Bu sayılar çeviri veya uygulama başarısı değildir.
İlk pilotun 12 `unsupported_format` kaynağı V2 ile statik kontrolden
geçer; tarihsel hata sayımı korunur. Parametreden ibaret iki kayıt, metin
içeren 10 kayıtlık takip model testine dahil edilmez.

V2 takip prototipinde mevcut LM Studio ile 10 kaydın sekizi başarılı cevap verdi;
iki kayıt üçer denemeden sonra ayrı kaldı. 17 denemede 415,896 saniye üretim
isteği ölçüldü. Sekiz adayın korumalı yapıları tekrar doğrulandı; insan onayı
verilmedi. Bu test oyun içinde renk/parametre işleyişini veya bütün kaynakların
model başarısını kanıtlamaz. Eski pilotun hata sayıları değiştirilmedi.

V3 takip prototipindeki dört ek kayıt mevcut LM Studio ile tamamlandı;
110,799 saniye üretim isteği ölçüldü. Boyut değeri, sprite adı ve F1
indeks/biçimi başarılı adaylarda yeniden doğrulandı. İnsan onayı verilmedi.
Bu sınırlı sonuç diğer formatların veya oyunda gösterimin doğruluğu değildir.
Toplam beş denemede bir kesik çıktı reddedilip yeniden denendi. Bir sayısal
birim metni kaynakla aynı kaldığından inceleme uyarısı taşır; onay gerektirir.

## Çoğul dalları

[I2 Plurals belgesi](https://www.inter-illusion.com/assets/I2LocalizationManual/Plurals.html)
varsayılan Plural dalını ve etiketle ayrılmış varyantları açıklar. Yerel kaynakta
22 One ve beş Zero varyantı bulundu; statik assembly metaverisindeki ePluralType
bu adları içeriyor. Şimdilik yalnızca gözlenen One/Zero desteklenir; diğer
kategoriler, tekrar eden/boş dallar, farklı büyük harf yazımı ve dallar arasında
açık kalan etiketler reddedilir. Resmî belgede farklı büyük harfli örnek de vardır;
bu, gözlenmeyen biçimi sessizce kabul etmek için kullanılmaz.

Model isteği her dal için ayrı kimlik ve bağımsız maskeleme içerir. Mantıksal
kayıt başına **tek HTTP üretim isteği** yapılır; ortak üç deneme sınırı dallar
için sıfırlanmaz. Cevap bütün kimlikleri tam/tekil karşılamalıdır. İstem v2 ve
sıralı `items` şeması her array konumunu bir dal kimliğine bağlar; yerel ayrıştırıcı
cevap sırasından bağımsız olarak kaynak sırasını kurar. [llama.cpp şema dönüştürücü](https://github.com/ggml-org/llama.cpp/blob/master/common/json-schema-to-grammar.cpp)
bu tuple yaklaşımının kaynak referansıdır; kurulu her sunucuda destek varsayılmaz.

Dalın değişken/etiket/satır sonu sayımı kendi kaynağıyla karşılaştırılır.
Bir değişkeni başka dala taşımak, global adet aynı kalsa bile reddedilir.
Eksik/fazla dal veya bozuk dal halinde hiçbir kısmi aday kaydedilmez.
Manuel düzenleme, içe aktarma ve C# uygulama kontrolü de aynı dal/sıra kuralını
uygular. Model tek bir dala yeni I2 etiketi enjekte edemez. Sayı ve dil ipuçları
dal bazında yeniden çalışır (`review-en-tr-v4`). Her çoğul aday insanın 0/1/2
değerleriyle kontrolü için `plural_content_review` taşır; otomatik onay verilmez.

Yeni metaveri `format_prompt_version`, `plural_forms`, `plural_schema_version`
alanlarını taşır. Bağlam bütçesi mesaj ve çıktı şemasının UTF-8 byte tahminini,
çıkış payını ve %20 emniyet payını içerir; tokenizer ölçümü değildir.
Güncel statik kaynak kapsamı 6.745/6.749; dört diğer açı-parantezli yapı ayrı
kalır. Bu sonuç oyun içi çoğul seçimi veya Türkçe anlam doğruluğu kanıtı değildir.

Gerçek model doğrulaması kısmi: ilk 2048 bütçeli eş-kimlik şemasında iki
kayıt da kesik çıktı aldı. Sıralı items/v2 isteminde One/Zero örneği tamamlandı;
One örneği 2048 ve sonraki ayrı 4096 bütçeli testte üçer deneme sonunda
kesildi. Başarılı örneğin dal yapısı tekrar doğrulandı; insan onayı verilmedi.
Kısmi dallar kaydedilmedi. Modelin bütün çoğul kayıtlarında çalışacağı sonucu
verilmez. Yeni hata tanısı sadece sabit bitiş nedeni/byte uzunluğu/sayısal token
ölçümlerini kaydeder; ham model cevabı normal teknik tanıya alınmaz.
Programın seçtiği format istemi/grammar sürümü, dal sayısı ve şema modu da
hata geçmişinde tutulur; bu alanlar modelden okunmaz. Şemasız mod sıralı
şema desteği diye etiketlenmez.

## Arayüzden dal düzenleme

İnceleme ekranında desteklenen çoğul kaydı seçin ve **Çoğul dallarını düzenle**
düğmesini kullanın. Kaynak sırasındaki Varsayılan/Tekil/Sıfır sekmeleri kaynak
ve çeviriyi yan yana gösterir; kaynak salt okunurdur. Boş veya sert biçim
kontrolünü geçmeyen dal aktarılmaz. Aktarım sadece ana taslağı değiştirir;
veritabanına kaydetme ve insan onayı ayrı işlemlerdir. Vazgeçme mevcut metni
değiştirmez. Pencere açıkken ana kayıt/taslak değişirse aktarım engellenir ve
alanlar kopyalanabilir halde açık kalır.

Qt'nin [QTextDocument açıklaması](https://doc.qt.io/qt-6.12/qtextdocument.html)
`toPlainText` ile satır/paragraf ve bölünmeyen boşluk dönüşümünü belirtir.
Veri editörü değişmemiş metni özgün string olarak döndürür. Düzenlenmiş metin
raw Qt içeriğinden okunur; paragraf sayısı korunmuşsa önceki çevirinin (yoksa
kaynağın) CRLF/CR/LF dizisi geri yüklenir. Değişen satır adedi normal çekirdek
kontrolüne gider ve korumalı kaynakla eşleşmezse reddedilir. NBSP ve Unicode
satır ayıracı raw içerikte korunur. Zengin HTML yapıştırma kapalıdır.

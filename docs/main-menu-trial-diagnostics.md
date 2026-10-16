# Ana menü denemesi: yerel tanı

Kullanıcı beş ana menü çevirisini tek tek onayladı ve önceki beş kayıtla
birlikte deneysel kurulumu açıkça seçti. Deneme toplam on insan onaylı
kayıt içerir. Kullanıcı oyunu kendisi başlattı; ana menü İngilizce kaldı.
Bu sonuç oyun içi uygulama başarısı olarak değerlendirilmez.

Kullanıcının ayrı yerel tanı seçimiyle yalnızca proje klasöründeki dış
runtime için disk kaydı açıldı. `WriteUnityLog=false`, konsol kapalı ve
assembly cache/dump kapalı kalır. Ham kayıtlar özel proje alanında tutulur;
oyun metni dışarı gönderilmez. Yükleyici konsol kaynağından teknik platform
bilgileri de kaydedebilir; Unity oyun mesajları disk dinleyicisinde elenir.

İlk tanı, korumalı preloader ve chainloader'ın çalıştığını, eklentinin
yüklendiğini ve başlangıçta payload'u reddettiğini gösterdi. Başarılı
çeviri, font veya sahne davranışı kanıtlanmadı. Eklentinin başlangıç
kontrollerine yalnızca sabit sayısal aşama kodları eklendi:

| Kod | Kontrol |
| --- | --- |
| 1 | Payload dosyası erişimi ve boyutu |
| 2 | JSON okuma ve ayrıştırma |
| 3 | Payload biçim sürümü |
| 4 | Hedef dil |
| 5 | Unity sürümü |
| 6 | Kayıt dizisi boyutu |
| 7 | Oyun assembly'sini okuma ve hash hesaplama |
| 8 | Assembly hash karşılaştırması |
| 9 | Kaynak kümesi alanları |

Kodlar çeviri, dosya yolu veya exception mesajı içermez. Güncel eklenti
gerçek salt okunur referanslarla derlendi; 13 çekirdek, 63 ortak korumalı
biçim ve 5 sentetik I2 sarmalayıcı senaryosu geçti. Tanı güncellemesi yalnızca
proje runtime DLL'sini değiştirdi; eski DLL ve ilk tanı kaydı saklandı.
Özgün 526 oyun dosyasının hash'leri ve sahipli iki yükleyici dosyası değişmedi.
Önceki kurulum incelemesi tarihsel kanıttır; güncel runtime için yeniden
kurulum doğrulaması olarak kullanılamaz. Ayrı tanı revizyonu ve hash'leri
özel proje raporuna kaydedilir.

Sonraki gerçek çalıştırma `Payload entry count: -1` ve kontrol 6 hatası
verdi: Unity'nin JSON okuyucusu kayıt dizisini `null` döndürdü; dosyada on
geçerli kayıt bulunuyor. Unity serializer yerine .NET 3.5 uyumlu, yalnızca
payload şemasını kabul eden veri okuyucu eklendi. Bilinmeyen/tekrarlı alanlar,
yanlış türler, eksik veriler, sondaki veri, geçersiz kaçışlar ve eşleşmeyen
Unicode surrogate değerleri reddedilir. Boyut, derinlik, düğüm ve kayıt
sınırları vardır; reflection veya yürütülebilir tür çözümleme yoktur.
14 JSON senaryosu (on kayıtlı dizi, Türkçe, CRLF ve Unicode dahil) ve önceki
81 C# senaryosu geçti; gerçek salt okunur referanslarla derleme tamamlandı.
Çeviri JSON'u ve insan onayları değişmedi. Yeni gerçek oyun kaydında okuyucu
on kaydı yükledi ve eklenti `Applied 10 selected terms in memory` bildirdi.
Kullanıcı ana menü metinlerinin Türkçeye geçtiğini ve Türkçe karakterlerin
düzgün göründüğünü bildirdi. Menü/glif kapısı bu dar örnek için geçti;
öğretici, görev/diyalog, Heretek, dinamik değerler, taşma ve performans henüz
kanıtlanmadı. Oyun kapalı gözlendi; oyun denemesi sonrası 526 özgün dosya
hash'i eşitti. Geçici denemenin sahiplik/hash'i eşleşen yalnızca iki yeni
yükleyici dosyası kaldırıldı; kaldırma sonrası özgün hash'ler yine eşitti.
Kullanıcı tarafından değiştirilmiş veya özgün dosya silinmedi. Deneme ekleri
kaldırıldığı için oyun şu anda bu paketle çeviri uygulamaz; proje çevirileri
ve tanı kanıtları korunur. Genel uygulama
`unknown` ve `application_verified=false` kalır. Oyun başlatma/durdurma
yetkisi eklenmedi; masaüstü dağıtım paketi bu deneysel DLL'yi içermez.

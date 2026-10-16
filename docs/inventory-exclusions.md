# Değişken verinin envanterden ayrılması

Varsayılan koruma servisi oyun ağacındaki bütün dosyaları SHA-256 envanterine
alır. Sessiz veya oyun adına sabitlenmiş log/save/cache dışlaması yoktur.
Üretim UI/CLI'ında etkinleştirme henüz açılmamıştır.

Servis, açıkça incelenmiş `VolatileFile` seçimlerini ayrı raporlayabilir.
İlk kapsam yalnızca `Logs/<dosya>.log`, `Logs/<dosya>.txt`, `Saves/<dosya>.sav` ve
`Cache/<dosya>.cache` yollarıdır. Her seçim tek dosya ve gerekçe içerir.
Wildcard, dizin, alt dizin, Unity veri ağacı, loader yolu ve başka uzantı
reddedilir. `.txt` dosyası günlük olarak incelenmiş ve tek tek seçilmiş
olmalıdır; uzantı veya `Logs` klasörü otomatik dışlama sağlamaz.
Okuyucunun çıkardığı bilinen oyun kaynağı da dışlanamaz. Farklı
oyunların başka save/cache düzenleri bu sürümde otomatik tanınmaz; kullanıcı
verisi olduğuna dair inceleme gerekir. Bu bölgelerdeki her dosya otomatik
dışlanmaz; seçilmeyen yeni dosya envanter/parmak izi değişimi olarak kalır.

Dışlamalı ilk envanter biçim 2'dir. Dosya hash'leri ve dışlama listesi birlikte
parmak izine bağlanır; ilk envanter sonradan genişletilemez veya yenilenemez.
Eski biçim 1 dışlamasız parmak iziyle okunur. Proje yeniden açıldığında
kaydedilmiş seçim tekrar kullanılır; yeni servis örneğinin seçimi değiştirmesi
reddedilir. Dışlama, mevcut dosyayı değiştirme izni vermez.

`artifacts/volatile-data-observations.json` seçilen yolları, gerekçeleri,
var/yok durumunu ve varsa boyutunu tutar. Dosya içeriği veya hash'i okunmaz;
bu veri özgün oyun dosyalarının hash kanıtına karıştırılmaz. Seçilen log
rotasyonu veya save/cache değişimi parmak izini değiştirmez. Kurulum varlığı
değişirse kontrol durur. Güvensiz/reparse yol dışlama sayesinde geçmez.

Seçilen yollar, dosya henüz oluşmamış olsa da uygulama hedefi olamaz.
Kaldırma manifesti bu yolları sahiplenemez; create-new, kimlik/hash ve oyun
kapalı kontrolleri ayrıca sürer. Sentetik log/save/cache değişimi, seçim kapısı,
politika değişimi, bilinen kaynak, yasak yol ve eski envanter testleri geçti.
Kullanıcı gerçek kurulumda tek somut günlük dosyasını ayrı izlemeyi seçti.
Diğer 526 dosyanın kalıcı SHA-256 envanteri ve ikinci okuma karşılaştırması
tamamlandı; kapalı loader planı aynı parmak izine bağlandı. Günlük içeriği
ve hash'i envantere alınmadı. Oyun başlatılmadı veya kurulmadı.
Bu değişiklik kaynak sürümündedir; mevcut preview.3 bunu içermez.

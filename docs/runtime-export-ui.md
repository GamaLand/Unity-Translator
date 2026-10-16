# Küçük onaylı seçimden deneme verisi

Dışa aktar sekmesindeki “Küçük deneme için onaylı çevirileri seç” düğmesi,
inceleme ekranının mevcut sayfasındaki onaylı kayıtları gösterir. Başlangıçta
hiçbir kayıt seçilmez; kullanıcı 1–10 kayıt seçer. İnceleme filtreleri/sayfa
değiştirilerek başka kayıtlar gösterilebilir. Bu çıktı yalnızca deneysel I2
metin JSON'udur; kurulabilir oyun paketi veya etkinleştirme değildir.

Kaynak kümesi adı çıkarma worker'ının I2 aday metaverisine eklenir. Backend
seçilen kaydın güncel kaynak revizyonuna bağlı snapshot'tan kaynak kümesini,
Unity sürümünü ve kaynak konumunu bulur. Mantıksal kimliği kontrol eder;
belirsiz/eski bilgi, farklı kaynak kümeleri veya desteklenmeyen Unity/dil
eşleşmesi export'u durdurur. Eski projede kaynak kümesi bilgisi yoksa
Metinler ekranından yeniden çıkarma gerekir; eksik isim tahmin edilmez.

Seçim diyaloğunun gösterdiği kaynak/çeviri revizyonu ve iş sürümü backend'de
yeniden karşılaştırılır. Seçimden sonra düzenlenen ve tekrar onaylanan farklı
revizyon sessizce paketlenmez. Paketleme yeni ve benzersiz proje artefaktı
oluşturur; onay, taslak, model veya oyun dosyası değiştirmez. Model isteği
göndermez. Proje/istek belirteci eşleşmeyen geç sonuç UI'a aktarılmaz.

380 testlik ortak kontrol geçti. Qt sentetik akışında seçim sınırı, onaysız
kaydın dışlanması, veri üretimi, eski sonuç reddi ve kaynak hash'inin korunması
doğrulandı; ekran görüntüsü incelendi. Bu test gerçek oyunda uygulama veya
font/sahne kanıtı değildir. Özellik preview.4 EXE'sine alındı; izole PATH'te
sentetik I2 kaydının modal seçim ve veri üretimi kontrolü de geçti. Önceki
preview.3 bu özelliği içermez. Temiz Windows kapısı ayrıca açık kalır.

Gerçek referans kaynağı yeni worker ile salt okunur yeniden çıkarıldı. Beş
yerel insan onayının kaynak/çeviri revizyonları ve iş sürümleri değişmedi;
aynı seçim yeni otomatik kaynak bilgisiyle dışa aktarıldı. Kaynak asset hash'i
kalıcı özgün envanterle işlem öncesi ve sonrasında eşleşti. Bu kontrol bütün
oyun dosyalarının tekrar hash'lenmesi veya oyun içinde kullanım testi değildir.

# Kalıcı inceleme taslakları

`EditorDraftStore` insanın henüz tamamlamadığı metni SQLite `editor_drafts`
tablosunda saklar. Taslak boş veya korumalı biçim açısından eksik olabilir;
model adayı, etkin çeviri ve insan onayından ayrıdır. Taslak saklama mevcut
çeviriyi, iş sürümünü veya onayı değiştirmez. Kaynak metni değişmez kaynak
revizyonundan okunur; metnin CR/LF ve Unicode karakterleri aynen tutulur.

Her taslak kaynak revizyonuna ve düzenlemenin başladığı iş sürümüne bağlıdır.
Arka planda kaynak, aday, onay veya kayıt etkinliği değişirse taslak kaydetme
reddedilir ve taslak korunur. Kaydetme ortak elle düzenleme servisini kullanır;
korumalı biçim kontrolü geçmelidir. Metin değişmişse önceki onay temizlenir;
yeni insan onayı ayrıca gerekir. Aynı metnin kaydı onayı değiştirmez.

Güncelleme, kaldırma ve kaydetme güncel taslak belirtecini gerektirir.
SQLite AUTOINCREMENT belirteçleri silme/yeniden açma sonrasında tekrar
kullanılmaz; eski pencere yeni taslağı silemez. Temel sürüm kendiliğinden
yenilenmez; eski taslak açıkça kaldırılmalıdır. Kaydetme ve taslak silme tek
transaction'dadır; ikinci adım başarısızsa çeviri değişikliği de geri alınır.
Bir taslak 4 MiB, toplam taslak metni 64 MiB UTF-8 sınırındadır.

Şema 3 → 4 tutarlı SQLite yedeği alınıp transaction içinde ilerler. Hata
eski şemayı korur. Eski preview.2 şema 4'ü açamaz; güncel kaynak sürümünde
açılan projeyi eski önizlemeyle açmayın. Taslaklar taşınabilir JSON 2'ye
eklenmez; proje SQLite veritabanında kalır. JSON tüm proje yedeği değildir.

Uygulama oturumu taslak işlemlerinde proje kimliğini zorunlu kontrol eder.
Bu altyapı kaynak sürümünde sentetik kapanma/yeniden açma, eski sürüm,
yanlış kaynak, yarım biçim, onay koruması, transaction hatası ve migration
testlerini geçti. Gerçek oyun/model verisi kullanılmadı.

İnceleme ekranı 250 ms yazma gecikmesiyle taslağı arka plan IO oturumuna
saklar. Aynı anda tek saklama isteği vardır; hızlı yazılan yeni metin önceki
cevapla ezilmez. Yenileme/kayıt seçimi metni korur. Proje değiştirme ve normal
kapanma bekleyen taslak saklamalarının sonucunu bekler; saklama hatasında
kapanış durur ve metin kopyalanabilir halde kalır. Süreç zorla sonlandırılırsa
son 250 ms ve tamamlanmamış saklama isteği kurtarılmış sayılmaz.

Kaynak/iş sürümü değiştiğinde eski kaynak ve taslak birlikte gösterilir;
çeviriye kaydetme durur. Taslağı kaldırıp güncel metni açmak açık bir düğme ve
kaldırma onayı gerektirir. Taslağın otomatik saklanması onaylı çeviriyi
değiştirmez. Kaydetme ve onay düğmeleri ayrı kalır. Geç gelen eski proje veya
sayfa/istek cevapları yeni duruma taşınmaz. Kayıt gezinme, yenileme, hemen
kapanma/yeniden açma, proje değişimi, saklama hatası ve onay koruması gerçek
Qt/sentetik SQLite testlerinde geçti; offscreen görüntü incelendi.
Native preview.3 bu tablo ve arayüz bağlantısını içerir. İzole PATH altında
frozen EXE'nin kapanışta taslak saklayıp SQLite'tan yeniden okuduğu doğrulandı.
Bu geliştirici makinesindeki deney temiz Windows testi değildir.

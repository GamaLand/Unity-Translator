# Oyuna uygulama arayüzü

Sekizinci sekme, geliştirici betiklerinin kullandığı koruma servislerine
bağlıdır. Genel uyumluluk deneyseldir. Küçük ana menü başarısı bütün oyun
sahneleri için kanıt sayılmaz; kullanıcı ek oyun denemelerini erteledi.

Hazırlık, güncel insan onaylı kayıtları ve kaynak snapshot'ına bağlı asset
SHA-256 değerlerini doğrular. Motor, yönetilen assembly referansları ve x64
PE başlığı runtime kit ile eşleşmelidir. Kit, uygulama kaynaklarındaki sabit
hash kataloğuna bağlanır; kullanıcı/model dosyasından DLL veya kod yüklenmez.

Runtime ve çeviri verisi ayrı proje klasörüne hazırlanır. İlk envanter
kalıcıdır. Kullanıcı seçmedikçe günlük dışlaması yapılmaz; önceki envanter
ve dışlama kararı değiştirilmez. Hazırlık oyun dizinine yazmaz. İnceleme
penceresi çeviri/özgün dosya sayısını, iki yeni hedefi ve hash'lerini gösterir.
Onay kutusu başlangıçta boştur. Kurulum ve kaldırma açık kullanıcı eylemidir.

Kurulum isteği aynı açık proje ve bellekteki hazırlık kimliğine bağlanır.
İnceleme, kaynak asset, motor, onay/revizyon veya runtime dosyaları değişirse
istek reddedilir. Son dosya işlemlerinde oyun kapalı olmalıdır; bilinmeyen
süreç durumu geçmez. Ekleme create-new, kaldırma sahiplik/dosya kimliği/hash
kontrollüdür. Değiştirilmiş ekler korunup listelenir. Özgün dosyaya yedekten
geri yazma yoktur; oyun başlatma/durdurma eklenmedi.

Kurulum tüm güncel onaylı kayıtları 100.000 kayıt ve 64 MiB veri sınırıyla
paketler. Bu sınırlar başarı iddiası değildir: 23 sentetik onaylı kayıtla
eski on kayıt sınırının aşılması ve insan onaylarının korunması doğrulandı.
1–10 kayıtlık ayrı JSON dışa aktarma akışı değişmedi.

Runtime kit: dokuz korumalı/stock çekirdek bağımlılık, I2 eklentisi ve Doorstop.
Stock kalıcı assembly shim'i içerilmez. Tam lisans metinleri, bileşen/hash/
kaynak eşlemesi, upstream arşivleri, değiştirilmiş preloader kaynak ağacı ve
eklenti kaynakları kit içinde bulunur. Aynı destek dosyaları proje runtime'ı
yanına kopyalanır. Özgün oyun DLL'si veya kişisel referans yolu dağıtılmaz.

Gerekli kontroller sentetik oyun ağacında hazırla → gerçek Qt inceleme
dialog'u → kur → kaldır akışını, özgün hash eşitliğini ve onay korumasını
kapsar. Yerel gerçek kit dosyaları da hash envanteriyle doğrulanır; testte
gerçek kit DLL'leri çalıştırılmaz. Yeni gerçek oyun denemesi yapılmadı.

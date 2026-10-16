# Arkadaşla paylaşılabilir çeviri

**Dışa aktar → Arkadaşla paylaşılabilir çeviri ZIP'i oluştur** güncel insan
onaylı metinleri, yükleyiciyi ve gerekli bağımlılıkları tek ZIP'e alır.
Alıcının UnityTranslator, Python, LM Studio veya model kurması gerekmez.
Model, proje veritabanı, kaynak İngilizce metin ve oyun DLL'leri eklenmez.
Kaynak hash'leri ve çeviri anahtarları veri olarak bulunur.

Alıcı ZIP'i ayrı bir klasöre çıkarır, **Kur.cmd** dosyasını açar ve oyunun
EXE'sinin bulunduğu klasörü seçer. Yönetici yetkisi varsayılan olarak
istenmez; klasör yazılabilir olmalıdır. Windows PowerShell 5.1/.NET kullanılır.
Çeviri veya oyun kendiliğinden başlatılmaz. Kullanıcı oyunu normal
başlatıcısından açar. Kurulumdan sonra ZIP'in çıkarıldığı klasöre gerek yoktur;
kaldırmak için aynı paketin **Kaldir.cmd** dosyasını saklayın.

Oyun köküne yeni `winhttp.dll`, `doorstop_config.ini` ve ayrı
`UnityTranslatorPatch` klasörü eklenir. BepInEx, eklenti, çeviri ve kaynak/
lisanslar bu klasördedir. INI'deki preloader yolu alıcının seçtiği oyun
klasörüne göre oluşturulur. Gönderenin çalışma yolu pakete sabitlenmez.
Oyun klasörü taşınacaksa önce bu paketi kaldırıp yeni yerde yeniden kurun.

Kurulum oyun kapalıyken, gerekli motor/assembly/kaynak hash'leri eşleşirse
çalışır. Eski mod/deneme veya hedef klasör varsa mevcut dosyayı ezmeden
durur. Mevcut dış runtime denemesini önce onu kuran UnityTranslator
projesindeki Oyuna uygula sekmesinden kaldırın. Paket oluşturmak mevcut
denemeyi taşımaz veya değiştirerek kurulmaz.

Kaldırıcı NTFS/Windows dosya kimliğini, tek link olmasını ve hash'i kontrol
eder. Değiştirilmiş, değiştirilip yerine yenisi konmuş veya hard link verilmiş
dosya korunur. Yabancı dosyalar veya dolu klasörler özyinelemeli silinmez.
BepInEx kendi ayar dosyasını çalışırken yeniden yazabilir; böyle bir dosya
da değişmiş sayılıp korunur. İşlem hangi dosyanın kaldığını bildirir.

Oyun içine konan bileşenler mevcut runtime'ın ayrı portable varyantıdır:
sabit `UnityTranslatorPatch/BepInEx` yolu ve paket işaretçisi doğrulanır,
shim ve hata günlüğü yazımı kapalıdır. Normal dış runtime'ın preloader'ı
bu amaçla sessizce yeniden kullanılmaz. Tam değişiklik kaynakları ve MIT/
diğer bağımlılık lisansları `support` altında bulunur. Üçüncü taraflar kendi
lisanslarını korur.

Boyut dışa aktarım sonucunda gösterilir. Çalışırken model veya çeviri
programı yüklenmez; kaynak ZIP'leri yalnızca dağıtım/lisans içindir, çalıştırılmaz.
Bu yerleşimin FPS/RAM etkisi veya oyun içi davranışı henüz ölçülmedi.
Sentetik Windows dosyalarında kurulum, kaldırma, çakışma, değiştirilmiş
dosya/hard link/kimlik koruması ve bozuk paket reddi doğrulanır.
Yeni portable yerleşimin gerçek oyun testi yapılmadı; uyumluluk deneysel
ve yalnızca hash'leri eşleşen Windows x64/Mono sürüm kapsamındadır.

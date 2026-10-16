# Küçük I2 denemesi önizlemesi

`tools/prepare_i2_trial.py` yalnızca ayrı proje ağacında çalışır. Hazırlanmış
dış runtime'ın dosya kümesini, bağımlılık hash'lerini, kapalı loader ayarını,
plugin build kanıtını ve mevcut oyun assembly hash'ini kontrol eder. Fazladan
plugin/patcher bulunursa hazırlığı reddeder. Seçilen 1–10 kaydın tamamı güncel
yerel insan onayına sahip olmalıdır; eksik seçim sessizce küçültülmez.

Çeviri JSON'u ve plugin dış runtime'a eklenir. Proje içinde ayrıca oyun köküne
önerilen iki yeni dosyanın kopyaları hazırlanır: `winhttp.dll` ve kapalı
`doorstop_config.ini`. Mevcut hedef varsa işlem reddedilir. Oyun klasörüne
yazılmaz, DLL yüklenmez, oyun veya model başlatılmaz. Aynı runtime üzerinde
yeni deneme önceki plugin dosyalarının üzerine yazmaz; yeni runtime gerekir.
Başarısız hazırlığın proje içindeki kısmi çıktıları `failed` manifestiyle kalır.

`validate_i2_trial` tüm hazırlanmış dosyaları, tam runtime dosya kümesini,
oyun assembly'sini ve incelenen kaynak/çeviri revizyonlarını yeniden kontrol
eder. Onay, revizyon veya dosya değişikliği önizlemeyi geçersiz kılar. Deneme
JSON'undaki metin ve kaynak hash'i güncel insan onaylı revizyonla birebir
karşılaştırılır; değişmiş bir metin yalnızca manifest hash'lerini yenileyerek
eski onayı kullanamaz. Kapalı loader politikası gerçek INI/config içeriğiyle
de kontrol edilir. Deneme
manifesti kurulum yetkisi değildir; `installation_authorized=false`,
`application_verified=false` ve `baseline_required=true` kalır. Manifest
şeması kuruluma giriş arayüzü olarak kullanılmamalıdır.

`prepare_i2_deployment_preview` hazır özgün envanter gerektirir; envanteri
kendiliğinden oluşturmaz. İki önerilen dosyayı koruma servisinin create-new
planına bağlar ve deneme manifest hash'ini ayrı inceleme kaydına alır. Plan
hazırlığı boyunca deneme tekrar doğrulanır. Oyun envanteri değişirse plan
üretilmez. Plan yine kapalı loader önizlemesidir ve etkinleştirme yetkisi vermez.

Gerçek oyun için beş ayrı kullanıcı onaylı kayıtla yerel önizleme hazırlandı;
dosyalar ve güncel onaylar yeniden doğrulandı. Bu, loader'ın gerçek Mono'da
çalıştığını veya font/sahne uyumluluğunu kanıtlamaz. Kullanıcı tek somut günlük
yolunu ayrı izlemeyi seçti; diğer 526 dosyanın kalıcı envanteri alındı ve ikinci
okumayla aynı kaldığı doğrulandı. Kapalı loader önizleme planı bu envantere
bağlandı. Kullanıcının açık
oyun denemesi seçimi, süreç kapıları, izlenen create-new kurulum ve sonrasında
hash/geri alma doğrulaması ayrı aşamalardır. Preview.3 bu geliştirici aracını
içermez; kamuya dağıtılabilir tamamlanmış mod paketi olduğu iddia edilmez.

# Sınırlı geliştirici oyun denemesi

Normal `DeploymentService.activate` yolu doğrulanmış adaptör ve açık kullanıcı
eylemi ister. Henüz gerçek oyunda çalışmamış I2 prototipinin ilk denemesi bu
yoldan kurulamaz. Ayrı deneysel inceleme yolu, aynı özgün dosya korumasını
kullanır; oyun içi desteği doğrulanmış gibi işaretlemez. Amaç ilk gerçek oyun
kanıtını alabilmektir. Bu yol genel son kullanıcı etkinleştirme desteği değildir.

`prepare_activation_review` mevcut kapalı deneme önizlemesini ve hazır kalıcı
envanteri doğrular. Yeni proje artefaktında `enabled=true` INI üretir; eski
kapalı kopyayı değiştirmez. Yalnızca iki yeni oyun-kökü hedefi önerilir:
`winhttp.dll` ve `doorstop_config.ini`. Preloader, plugin ve çeviri oyun dışında
kalır. Plan deneme manifest hash'ine ve özgün oyun parmak izine bağlanır.
Hazırlık oyun dosyası eklemez, DLL yüklemez veya oyun başlatmaz.

`install_reviewed_trial` ancak açık kullanıcı eylemi ve ayrıca incelenmiş
deneysel deneme seçimi birebir `True` ise devam eder. Proje, güncel beş/onaylı
revizyon, runtime dosya kümesi, oyun assembly hash'i, etkin INI içeriği ve
kalıcı plan yeniden kontrol edilir. Alt servis yalnızca aynı iki hedefli
sınırlı adaptör planını kabul eder. Normal adaptör kapısı atlanmaz; deneysel
plan o yolda reddedilir. Sonuç `experimental=true`, `application_verified=false`
kalır; manifest veya JSON içeriği kendi başına yetki değildir.

Kurulum, ortak create-new/sahiplik/hash ve taze kapalı oyun kontrollerini
kullanır. Beklenmeyen mevcut dosyanın üzerine yazılmaz. Kaldırma aynı ortak
servistedir; yalnızca sahipliği ve hash'i eşleşen iki ek silinebilir. Kullanıcının
değiştirdiği ekler korunur, özgün dosyaya yedekten geri yazma yoktur. Oyun
süreci başlatma/durdurma yetkisi bu modülde bulunmaz.

394 Python testi ve ortak C# kontrolleri geçti. Sentetik deneysel ekleme ve
kaldırma, ayrı onay, yanlış türde onay, stale revizyon, değişmiş INI/plan/oyun
ve açık/belirsiz süreç test edildi. Gerçek kurulumda yalnızca etkin inceleme
planı hazırlandı; oyun köküne ek yapılmadı. İlk oyun testi henüz yapılmadı;
loader davranışı, glifler, taşma ve sahneler belirsizdir. Tam lisans/dağıtım ve
clean-Windows kapıları bu denemeyle kapanmaz; preview.3 bu araçları içermez.

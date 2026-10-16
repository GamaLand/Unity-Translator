# Oyun kapalı kontrolü

Türkçe arayüzün Metinler sekmesindeki açık/kapalı kontrolü bu okuyucuyu
arka planda çalıştırır; sonuç ve UTC gözlem zamanı gösterilir. Kontrol seçilen
projenin oyun yoluna bağlıdır. Oturum veya istek değiştiğinde geç gelen sonuç
yeni ekran durumunu değiştirmez. Açık, kapalı ve belirsiz sonuçlar ile oturum
değişimi sentetik uygulama/arayüz testlerinde doğrulandı. Bu düğme kurulumu
onaylamaz, oyun başlatmaz ve dosya işlemi yapmaz.

Uygulama servisi yeni özgün envanter alırken, plan hazırlarken, etkinleştirirken
ve kaldırırken seçilen oyun için taze süreç kontrolü yapar. `closed`, `running`
ve `unknown` sonuçları ayrıdır; yalnızca `closed` dosya işlemini geçirir.
Bu sonuç JSON içe aktarma, model cevabı veya eski tarama raporundan alınmaz.
Testlerde süreç gözlemi bağımlılığı sentetik olarak değiştirilir; üretimde
varsayılan Windows okuyucusu kullanılır.

[Tool Help snapshot](https://learn.microsoft.com/en-us/windows/win32/api/_toolhelp/)
ve [PROCESSENTRY32W](https://learn.microsoft.com/en-us/windows/win32/api/tlhelp32/ns-tlhelp32-processentry32w)
ile süreç adı/PID listesi alınır.
[QueryFullProcessImageNameW](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-queryfullprocessimagenamew)
yalnızca `PROCESS_QUERY_LIMITED_INFORMATION` erişimiyle executable yolunu okur.
Süreç belleği, komut satırı veya oyun metni okunmaz; süreç başlatma/durdurma,
debug ayrıcalığı veya yönetici yetkisi isteme yolu yoktur. Açılan handle'lar
finally bloklarında kapatılır. Tamamlanmayan enumeration veya sınır aşımı
kapalı sonucu vermez.

Executable adları seçilen oyun ağacından salt okunur bulunur; kişisel oyun
yolu veya exe adı üretim kodunda sabitlenmez. Görüntü yolu oyun kökü içindeyse
süreç çalışan oyuna aittir. Başka kurulumdaki aynı adlı executable kendi
okunabilir yolu ile ayrılır. Yol okunamayan oyun adlı süreç, göreli/aygıt/
reparse yolu ve executable kimliği bulunamaması `unknown` üretir. Oyunla
ilişkilendirilmeyen sistem süreçlerinin bilgileri rapora/persistansa alınmaz;
sonuç sadece oyunla ilişkili/şüpheli PID'leri ve sabit gerekçe kodunu içerir.

İlk envanter öncesi/sonrası kontrol yapılır; oyun açılmışsa doğrulanmamış
baseline yazılmaz. Etkinleştirmede her dosyadan önce ve tamamlanmada kontrol
yenilenir. Kaldırmada her sahiplik kontrollü silmeden önce tekrar kontrol
edilir. Arada oyun açılırsa kısmi sahiplik manifesti `recovery_required` olur;
oyun açık/belirsizken otomatik rollback dosya silmez. Oyun kapandıktan sonra
açık kaldırma/kurtarma eylemi yalnızca hash/kimlik eşleşen ekleri kaldırabilir.
Mevcut envanter/manifest bilgisi salt okunur görüntülenebilir; bu, yeni işlem
için izin değildir.

Kontrol bir snapshot'tır, işletim sistemi düzeyinde başlatma kilidi değildir.
Sorgu ile dosya işlemi arasında kullanıcı oyunu açabilir. Yeniden kontroller
gözlenen değişimde durur; eşzamanlı bütün başlatmaları engellediği iddia edilmez.
Özgün SHA-256, create-new, dosya kimliği ve sahiplik kontrolleri ayrıca sürer.

Sentetik testler açık/belirsiz oyunun işlemden önce reddini, envanter sırasında
başlatmayı, etkinleştirme/kaldırma ortasında başlatmayı ve kapalıyken kurtarmayı
doğrular. Windows API kendi test sürecini gerçek PID/yolla sorguladı. Yerel
referans kurulumun salt okunur sorgusu o anda `closed` verdi. Bu gözlem gerçek
yükleyici kurulumu veya oyun içi yerelleştirme kanıtı değildir. Oyuna yazma
yapılmadı; uygulama desteği `unknown` kalır.

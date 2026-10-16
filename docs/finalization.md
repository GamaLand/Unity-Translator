# Son kullanıcı sürümünü tamamlama

15 Ekim 2026 kullanıcı kararıyla ek oyun denemeleri ertelendi. Öncelik
son kullanıcı iş akışı, kullanım kolaylığı ve teslim edilebilir pakettir.
Yeni manuel oyun testi istenmez; değişen kod için gerekli doğrulama yapılır.
Ertelenen testler başarılı veya genel oyun desteği kanıtı sayılmaz.

Tamamlanan kullanım iyileştirmeleri:

- Kayıtlı projeyi yalnızca çalışma klasörüyle açma; yanlış seçimde açık
  oturumu koruma. Açılış kendiliğinden çeviri veya sunucu başlatmaz.
- Ana ekranda toplam kayıt, çeviri ve onay sayıları; mevcut duruma göre
  sonraki ekrana götüren düğme. İnceleme ve dışa aktarma çevrimdışı kalır.
- Taslak, onay ve iş geçmişini tutarlı SQLite yedeğinde saklama;
  yedeğin bütünlüğünü kontrol etme ve aynı açılış akışıyla geri açma.
- Proje klasörüne ulaşma düğmesi, Ctrl+O / Ctrl+F / Ctrl+S kısayolları,
  varsayılan kapalı gelişmiş üretim ayarları, sağlayıcıya uygun varsayılan
  port ve Türkçe işlem bildirimleri.
- Paketle birlikte kısa kullanım ve yedekleme rehberi.

Oyuna uygulama akışı:

- Sekizinci sekme güncel insan onaylı çevirileri paketler, özgün envanteri
  korur ve iki yeni dosyanın planını gösterir. İşaretlenmemiş onay kutusu
  kurulumu açmaz. Kaldırma aynı sahiplik/hash servisini kullanır.
- Runtime bileşenleri sabit dosya hash'leriyle gelir; motor, yönetilen
  referanslar ve x64 yürütülebilir başlığı kontrol edilir. Uyumsuz oyunda
  düğme açılmaz. Eski 1–10 metin JSON'u seçimi korunur; kurulum yolu tüm
  güncel onaylı kayıtları 100.000 kayıt/64 MiB veri sınırı içinde işler.
- Dokuz çekirdek bileşen, eklenti ve Doorstop; lisanslar, upstream kaynak
  arşivleri ve korumalı preloader'ın tam değişiklik kaynaklarıyla paketlenir.
  Oyun DLL'si, model, kişisel yol veya çeviri verisi runtime kit'e eklenmez.
- Gerçek Qt dialog, hazırlama/kurulum/kaldırma ve özgün hash eşitliği
  sentetik dizinde doğrulandı. Gerçek oyun yeniden kurulmadı veya açılmadı.

Yerel teslimin son kontrolü: güncel kaynak arşivi, Windows paketi,
runtime/lisans envanteri ve paketlenmiş uygulamanın açılış akışı eşleştirilir.

Son inceleme kolaylıkları: açık seçimle 200 kayda kadar atomik grup onayı,
yeniden açılan projede doğru pilot kapısı, kayıt/dakika ve ölçüme dayalı
kalan süre, duraklatılmış işi iptal, Yardım menüsünden rehber/kaynak erişimi.
Yerel disk koşulu eşlenmiş ağ sürücülerinde de kontrol edilir.

[Gereksinim ve teslim denetimi](release-audit.md),
[CPU/bellek gözlemi](resource-usage.md) ve
[kaynak erişimi](SOURCE-ACCESS.md) son teslimin parçasıdır.

RC2 güncellemesi konsolsuz Windows kaynak çıkarma hatasını giderir ve
çeviri sekmesine 1–4 paralel istek seçimi ekler. İptal/duraklatma bütün
istekleri kapsar; eski pilot profili ve insan onayları korunur.
[Hata ve doğrulama kapsamı](windows-worker-fix.md).

RC3 kullanıcı talepleri: 1–16 paralel istek, filtreye göre son sayfa sınırı
ve program/model gerektirmeyen alıcı ZIP'i. Portable uygulama artefaktları
yeni UnityTranslatorPatch alt ağacında; proje verisi dışarıda kalır.
Normal dış runtime ve mevcut gerçek deneme değiştirilmez. Alıcı kurulumu
ve korumalı kaldırma sentetik Windows klasörlerinde doğrulandı;
yeni yerleşim oyun içinde denenmedi. [Paylaşım rehberi](shareable-patch.md).

Sınırlar: referans ana menü ve Türkçe karakterler kullanıcı tarafından
doğrulandı; öğretici/görev/Heretek, taşma, dinamik değer ve performansın tamamı
kanıtlanmadı. Gerçek llama.cpp ve temiz Windows testleri daha önce kullanıcı
tarafından ertelendi. Bu ertelemeler yeni test isteğiyle tekrar açılmaz.
İmzasız yerel paket kamuya yayımlanmış sürüm değildir.

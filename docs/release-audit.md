# 0.1.0 RC3 teslim kapsamı

15 Ekim 2026. Kullanıcı ek oyun denemeleri yerine programın son kullanıcı
akışının tamamlanmasını istedi. Bu teslim, mevcut doğrulama kapsamıyla yerel
Windows sürüm adayıdır. Tam oyun Türkçe yaması veya evrensel Unity desteği
iddiası taşımaz. Kaynak dosya adları ayrı uygulama kaynak arşivine göredir.

RC3 paylaşılabilir ZIP üretir: alıcıya program/model gerekmez, Kur.cmd
oyun sürümünü ve çakışmaları kontrol ederek yeni UnityTranslatorPatch
alt ağacını kurar, INI yolu alıcıda oluşturulur. Kaldir.cmd dosya
kimliği/tek link/hash eşleşmesini arar ve değişmiş dosyaları korur.
Ayrı portable preloader'ın tam kaynak izlenebilirliği ve CIL kontrolü
geçti; altı sentetik guard kontrolü eklendi. Yeni yerleşim oyun içinde
test edilmedi. Paralel istek limiti 16; 6749 kayıtta son sayfa 6600 ofsetidir,
149 kayıt gösterir ve ileri gidilemez. Filtre sonrası sınır yeniden hesaplanır.
[Paylaşım kapsamı](shareable-patch.md).

RC2 konsolsuz başlatmada görülen WinError 6 okuyucu hatasını düzeltir;
geçersiz standart girişle gerçek alt süreç testi ekler. Çeviri sekmesinde
1–4 paralel istek seçilebilir. Eşzamanlı claim, tamamlanma, duraklatma ve
tüm görevleri iptal etme testleri vardır. [Düzeltme kapsamı](windows-worker-fix.md).
Kullanıcı daha sonra yerel LM Studio ile menü/öğretici/ekipman ağırlıklı
genişletilmiş deneme istedi; bu oyun verileri yalnızca yerel projede tutulur,
dağıtım arşivine alınmaz. İnsan onayı kendiliğinden verilmez.

| Gereksinim | Uygulama ve eldeki doğrulama |
| --- | --- |
| Türkçe masaüstü, proje oluştur/aç, yönlendirme | `ui/window.py`, `application.py`; kayıtlı çalışma klasöründen açma, sayı/sonraki adım, kısayollar ve başarısız açmada oturumu koruma. Paketlenmiş Qt akışı sentetik veriyle doğrulanır. |
| Ayrı yerel proje, özgün oyun dosyaları | `filesystem.py`, `deployment.py`; örtüşen/ağ/reparse yolları reddedilir. Kurulum yalnızca yeni dosya oluşturur; kaldırma sahiplik/hash ister. Gerçek deneme sonunda 526 özgün hash eşitti. |
| Tarama ve yapılandırılmış I2 çıkarma | `discovery.py`, `workers/unity_probe.py`, `i2.py`, `managed_schema.py`; ayrı süreçte salt okunur okuma. Gerçek kaynakta 6.749 kayıt, sıfır çıkarma hatası, değişmeyen kaynak hash'i. Çıkarma ve uygulama desteği ayrı gösterilir. |
| Yerel model ve veri sınırı | `providers.py`, `profiles.py`, `json_boundary.py`; düzenlenebilir loopback uç noktası, model listesi/elle kimlik, süre/iptal/hata eşleme. Model çıktısı yalnızca sınırlı veri olarak ayrıştırılır. LM Studio gerçek pilotta kullanıldı; llama.cpp protokol testleri sentetiktir. |
| Sözlük, üslup, bağlam, korunan biçim | `policy.py`, `pilot.py`, `validation.py`, sürümlü istem kaynakları; ilgili terimler ve sınırlı bağlam, etiket/değişken/çoğul/satır sonu kontrolleri. Sayı ve anlam ipuçları inceleme uyarısıdır; anlam garantisi değildir. |
| Pilot ve toplu iş kapısı | `jobs.py`; 200 kayıtlık gerçek pilot raporu kullanıcıca incelendi, üslup onaylandı (186 tamamlanan, 14 başarısız). Tamamlanmış ve incelenmiş pilot aynı güncel kaynak/üretim profiline bağlanır; yeniden açılışta korunur. |
| İlerleme, hız, ETA, duraklat/devam/iptal | `jobs.py`, `application.py`, `ui/window.py`; kalıcı deneme sınırı, tamamlanan ölçümlerden kayıt/dakika ve kalan karakter ağırlıklı üretim tahmini. İlk ölçümden önce tahmin yoktur. Duraklatılmış seçili iş de iptal edilebilir. Kesinti/yeniden açma senaryoları testlidir. |
| İnceleme ve insan onayının korunması | `repository.py`, `editor_drafts.py`, `review_selection.py`; 200 satırlık DB sayfalama, arama/filtre, kalıcı taslak, çoğul düzenleme, geçmiş. Grup onayı boş seçim ve ayrı insan inceleme kutusuyla başlar; güncel sürüm/kaynak/taslak kontrolü tek transaction'da yapılır. Model/içe aktarma insan onayını ezmez. |
| JSON aktarımı ve veri yedeği | `portable.py`, `repository.py`; çakışma önizlemesi, sürümlü geçmiş, onayların yeni projede otomatik etkinleşmemesi. SQLite backup ve bütünlük kontrolüyle taslak/iş geçmişi dahil yedek, arayüzden geri açma. |
| Oyuna uygulama ve kaldırma | `installation.py`, `runtime_kit.py`, `deployment.py`; eşleşen x64/Mono sürüm, sabit kit hash'leri, güncel insan onayları ve özgün envanter. Ayrı plan/onay sonrası iki yeni dosya. Değiştirilmiş ekler korunur. Gerçek menü/Türkçe karakter sonucu olumlu; genel uyumluluk deneysel. Yeni gerçek kurulum yapılmadı. |
| Dağıtım, kaynaklar ve bildirimler | `tools/build_windows.py`, `package_notices.py`, `package_windows.py`, `check_distribution.py`; standalone ZIP, dosya SHA-256 envanteri, kendi MIT lisansı ve bağımlılık bildirimleri. Oyun/model/kişisel proje arşivde bulunmaz. Qt/PySide kaynakları ayrı arşivdir; loader kaynakları runtime kit'tedir. |
| Sistem yükü | `resource-usage.md`; sayfalı 10.000 kayıt, istemci akışı ve salt okunur okuyucu için CPU/bellek gözlemi. Model sunucusu RAM/VRAM ve asgari donanım ölçülmedi. |

Son kaynak kontrolleri: Ruff, 44 kaynak dosyasında mypy, 440 geçen Python
testi ve bir platform atlaması; ayrıca 95 C# adaptör ve 14 korumalı tanı
senaryosu. Paketlenmiş arayüz kontrolü 601 sentetik kayıtta sayfalama,
Unicode/CRLF/NBSP, çoğul düzenleme, onay, grup onayı, yedek geri açma ve
sentetik kurulum/kaldırmayı kapsar. Gerçek runtime kit dosyaları ayrıca
sabit katalogla doğrulanır; bu test kit DLL'lerini veya oyunu çalıştırmaz.

## Kullanıcı kararıyla ertelenen doğrulamalar

- Fiziksel llama-server/GGUF bağlantı deneyi; mevcut LM Studio ile devam edildi.
- Python/derleyici olmayan temiz Windows/VM testi. İzole PATH testi bunun yerine geçmez.
- Öğretici, görev/diyalog, Heretek, tüm font kapsamı, taşma ve dinamik değerlerin oyun içi taraması.

Bu başlıklar başarılı sayılmaz. GOAL/teknik tasarımın bütün oyun/ortam
kabul kapıları kapanmış değildir. Kullanıcı kararıyla mevcut yazılım teslimi
bu sınırlara rağmen hazırlanır; yeni manuel test talebi açılmaz.

İsteğe bağlı yönetilen llama-server başlatma bu sürümde sunulmaz; çalışan
sunucuya bağlantı sunulur. Otomatik sunucu/model başlatma, model indirme,
bulut hesapları, OCR, seslendirme ve IL2CPP uygulama kapsam dışıdır.
Paket imzasız yerel sürüm adayıdır; kamuya yayın veya uzak CI çalıştırması yapılmadı.
Kullanıcının projelerinde tüm oyunun toplu çevirisi otomatik başlatılmadı.

# Windows sürüm adayı ve doğrulama

## Current candidate: RC6 (16 October 2026)

`UnityTranslator-0.1.0-rc.6-win-x64.zip` adds eight offline interface languages
(English by default), a Language menu beside Help, eight bundled guides, and English
project/license/source-access documentation. Language preference changes apply after
reopening and preserve project data. The foreign-loader preflight runs before baseline
capture. The public source ZIP excludes local AI instructions and private data.

463 Python tests passed with one platform skip; Ruff and mypy passed. Separate-process
window/approval tests cover all eight languages and placeholder parity covers all 335
messages per catalog. The native synthetic UI check passed on the development machine
with an isolated PATH. This does not establish clean Windows compatibility, native-speaker
translation review or additional in-game validation. SHA-256 values accompany the ZIPs
and are recorded in `DELIVERY-0.1.0-rc.6.json`. C# runtime components were unchanged.

## Previous candidates

Standalone paket Python veya derleyici kurmayı gerektirmeyen hedef biçimidir.
Geliştirme makinesinde izole PATH ile çalıştırılması temiz Windows kanıtı
sayılmaz. Genel oyun içi uygulama `unknown` kalır. Model/özgün oyun dosyası
eklenmez; deneysel uygulama bileşenleri kaynak/lisanslarıyla ayrı runtime kit'tedir.

16 Ekim 2026 güncel aday: `UnityTranslator-0.1.0-rc.5-win-x64.zip`.
İncelemenin en altında uyarı simgeli tüm proje onayı bulunur: önce kapsamı
kabul etme, ardından kayıt sayılı ifadeyi aynen yazıp son onay düğmesine basma.
Onay öncesi liste değişirse kısmi işlem yapılmaz. Paket hash'i yanındaki
`.sha256` ve `DELIVERY-0.1.0-rc.5.json` dosyasındadır.

### RC4 geçmişi

15 Ekim 2026 önceki aday: `UnityTranslator-0.1.0-rc.4-win-x64.zip`.
RC4, model üretiminin 110 saniyede kesilerek işi duraklatmasını düzeltir;
kuyruk/üretim için 30 dakikalık sınırlı bekleme ve görünür duraklama nedeni
ekler. [Arka plan davranışı ve doğrulama sınırları](background-translation.md).
Paket hash'i yanındaki `.sha256` ve `DELIVERY-0.1.0-rc.4.json` dosyasındadır.

### RC3 geçmişi

15 Ekim 2026 önceki yerel paket: `UnityTranslator-0.1.0-rc.3-win-x64.zip`.
94.606.751 bayt; SHA-256
`393d450d61f77193aab0e7f4c20c0413679fb1af85e4ee4ad2c3996d9296b597`.
259 dosya ve manifest ile 260 ZIP girdisinin içeriği/hash'i/CRC'si doğrulandı.
EXE SHA-256 `02e17d25d80e08265670dc255446d75771bea2168b88d562e4a8322e0f07a4a2`.
440 Python testi geçti, bir platform atlaması; Ruff ve 44 dosyada mypy geçti.
95 C# adaptör, 14 dış runtime tanısı ve 6 portable guard kontrolü geçti.
Native UI kontrolü sıfır çıkış koduyla bütün bayrakları, ayrıca
`shareable_export_verified=true` sonucunu verdi. Sentetik onaylı veriden
gerçek ZIP üretildi; normal ve portable kit katalogları ayrı doğrulandı.
Alıcı PowerShell kurulum/kaldırması farklı, Türkçe/boşluk içeren oyun yolunda
yalnızca sentetik dosyalarla doğrulandı. Çakışma, bozulma, traversal ve
değişen dosya/hard link/dosya kimliği kontrolleri geçti. DLL'ler oyunda
yüklenmedi; gerçek oyun veya model başlatılmadı.
Paralel istek limiti 16, inceleme son sayfada durur.
[Paylaşılabilir paket kapsamı](shareable-patch.md).
Yeni portable yerleşimin gerçek oyun/FPS doğrulaması yapılmadı;
önceki temiz Windows ve uyumluluk sınırlamaları korunur.

### RC2 geçmişi

15 Ekim 2026 önceki yerel paket: `UnityTranslator-0.1.0-rc.2-win-x64.zip`.
79.360.580 bayt; SHA-256
`f36fdccf01a4c5d5a3899317e3c8dacf53c521d211eace0975981f4fb0b9d32b`.
224 dosya ve manifest ile 225 ZIP girdisinin içeriği/hash'i/CRC'si doğrulandı.
EXE SHA-256 `6503be6f7a4baf0188f844cc31fe34357d161d7d43db693e2dccae2f43ca244e`.
Kaynak kontrolleri Ruff, 43 dosyada mypy ve 427 Python testiyle geçti;
bir platform testi atlandı. C# bileşenleri RC1'den beri değişmedi.
Native arayüz kontrolü sıfır çıkış koduyla tüm önceki bayrakları ve ek
`worker_invalid_stdin_verified=true` sonucunu verdi: geçersiz Windows standart
girişi altında gerçekten frozen Unity okuyucusu başlatıldı. Bu kontrol
sentetik dosya kullanır. Gerçek oyun veya model bu paket testinde başlatılmaz.
[WinError 6 düzeltmesi ve 1–4 paralel istek](windows-worker-fix.md).
Temiz Windows ve genel oyun uyumluluğu için önceki sınırlar korunur.

### RC1 geçmişi

15 Ekim 2026 önceki yerel paket: `UnityTranslator-0.1.0-rc.1-win-x64.zip`.
79.352.577 bayt, SHA-256
`147f4f6f3b9bb2eef0d48eb8689666b4304e0bba11eae78f55776a229a53bc41`.
223 dosya ve PACKAGE-MANIFEST.json ile 224 ZIP girdisi; her girdinin hash'i
ve CRC'si doğrulandı. EXE SHA-256:
`76cffe3f5816a1104291678a75a36191c7236a2c2ab0400a05d64543ff8a70cb`.
İzole PATH'te EXE sıfır çıkış kodu ve tüm arayüz kontrol bayraklarıyla geçti:
601 sentetik kayıt, 200 satırlık sayfalama, Unicode/CRLF/NBSP, çoğul düzenleme,
taslak geri açma, insan/grup onayı, runtime dışa aktarma ve sentetik kurulum/
kaldırma. Kit DLL'leri çalıştırılmadı; gerçek oyun kurulmadı veya başlatılmadı.
Son kaynak kontrolleri: 418 Python testi geçti, bir platform testi atlandı;
Ruff, 43 dosyada mypy, 95 C# adaptör ve 14 korumalı tanı kontrolü geçti.
Kullanılmayan Qt PDF bileşenleri paketten çıkarıldı. Grup onayı, güncel pilot
kapısı, hız/ETA, duraklatılmış iş iptali ve Yardım menüsü pakete alındı.

Ayrı `UnityTranslator-0.1.0-dependency-sources.zip`: 73.624.561 bayt,
SHA-256 `d24c9cf43cfdfe762abe3e0903b67d65d54d2cbec32c6e7100a728bfd0bcc548`.
Resmî Qt/PySide kaynak arşivleri sabit boyut/hash ile doğrulandı; ZIP CRC'si
geçti. Uygulama kaynakları `unitytranslator-0.1.0.tar.gz` içindedir.
[Teslim kapsamı](release-audit.md), [kaynak erişimi](SOURCE-ACCESS.md) ve
[kaynak kullanımı](resource-usage.md) raporları mevcut sınırlamaları açıklar.
Temiz Windows ve ek oyun testleri kullanıcının kararıyla ertelenmiştir;
RC1 bu kapıları geçmiş sayılmaz. İmzasız yerel sürüm adayı kamuya yayın değildir.

## Önceki paketlerin kanıtı

15 Ekim 2026 önceki yerel paket: `UnityTranslator-0.1.0-preview.6-win-x64.zip`.
81.796.102 bayt, SHA-256
`bee437af68beec8e256a80198b2d1a0a4b82f8773f34c9707964d1f92a015951`.
218 runtime/bildirim dosyası ve PACKAGE-MANIFEST.json ile 219 ZIP girdisi
CRC kontrolünü geçti. Frozen EXE izole PATH'te 601 sentetik kayıtta modal
çoğul düzenleme, CRLF/NBSP, onay ve istem kaynağı testini geçti; ayrıca
ayrı sentetik I2 kaydında modal seçimle deneme verisi üretimi doğrulandı.
Preview.6, sekizinci sekmedeki inceleme/onay/kurulum/kaldırma akışını ve
özgün hash eşitliğini paketlenmiş Qt uygulamasında sentetik dosyalarla
doğruladı. Gerçek kitin 32 dosyası ayrıca sabit katalogla eşleşti; kit DLL'leri
testte yüklenmedi. Hazırlıktan önce onay, asset, motor, referans ve x64
kontrolleri uygulanır. Kit 11 ikili bileşeni, tam lisansları ve kaynak
arşivlerini içerir. Gerçek oyun yeniden kurulmadı veya başlatılmadı.
Preview.5'te kayıtlı projeyi oyun yolunu yeniden girmeden açma ve arayüzden
tutarlı veri yedeği oluşturma/geri açma frozen akışa dahil edildi. Yedekte
onaylı çeviri korundu. Kayıt sayıları, sonraki adım, kısayollar ve kapalı
gelişmiş ayarlar bu pakete alındı. Çekirdek kontrolleri 396 Python testi
(bir platform skip'i), 95 adaptör ve 14 korumalı tanı senaryosuyla geçti.
Preview.4 ile gerçek kaynak tekrar salt okunur çıkarıldı: 6.749 kayıt,
6.095 benzersiz metin, 677.344 karakter ve sıfır çıkarma hatası.
Worker öncesi/sonrası kaynak asset SHA-256 değerleri eşittir.
Preview.5/6'da Unity okuyucusu değişmedi; ek gerçek oyun çıkarma/başlatma
tekrarlanmadı. Kullanıcının isteğiyle yalnızca gerekli kod/paket kontrolleri
yapıldı.
Bu geliştirme makinesi testi temiz Windows kapısını kapatmaz.

## Yeniden üretme

```powershell
uv sync --locked --extra ui --group build
uv run --locked --extra ui python tools/check.py --with-dotnet
uv run --locked --extra ui --group build python tools/build_windows.py
uv run --locked --extra ui --group build python tools/package_notices.py
uv build
uv run --locked --extra ui python tools/check_distribution.py
```

MSVC ve .NET SDK sadece geliştirici/test araçlarıdır. C# sentetik testleri
gerçek game assembly'si yüklemez. Windows build script'i sadece çalışma
alanındaki kendi üretilmiş dağıtım klasörünü temizler; oyun yolunu kullanmaz.

## Temiz Windows deneyi

Önizleme zip'ini Python/derleyici olmayan ayrı Windows ortamına çıkarın.
Oyun, model veya proje verisini bu ortama taşımayın. Paketin yanındaki
standalone_smoke.ps1 dosyasını PowerShell ile çalıştırın:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\standalone_smoke.ps1
```

Script yeni bir geçici klasörde 601 sentetik kayıt üretir; 200 kayıtlık UI,
elle düzenleme, CRLF/NBSP koruması, onay, gerçek modal çoğul düzenleme,
istem kaynağı ve görüntü çıktısını denetler. PATH'i Windows dizinleriyle
sınırlar, Python ortam değişkenlerini kaldırır. Sonuç klasörü stdout'ta
gösterilir; smoke-summary.json, ui-verification.json, ui.png ve
plural-editor.png saklanır.
Script ağ/model sunucusu, oyun kurulumu veya veri silme işlemi içermez.

smoke-summary.json'daki clean_machine_claim bilinçli olarak false'tur:
bir script ortamdaki tüm geliştirici yazılımlarının yokluğunu kanıtlayamaz.
Temiz VM/Sandbox'un nasıl hazırlandığı ayrıca kaydedilmelidir. Raporda dış
Python/derleyici bulunmuşsa bu test temiz ortam kapısını kapatmaz.

[Microsoft Windows Sandbox belgesi](https://learn.microsoft.com/en-us/windows/security/application-security/application-isolation/windows-sandbox/)
yeni oturumun host yazılımlarını içermediğini açıklar. Kullanılacaksa ağ
kapatılmalı, yalnızca önizleme paketi salt okunur eşlenmeli; test çıktıları
Sandbox kapanmadan alınmalıdır. Bu projede Windows özelliği kendiliğinden
etkinleştirilmez veya sanal makine kurulmaz.

Yerel makinede WindowsSandbox.exe bulunmadı. Temiz Windows deneyi henüz
çalıştırılmadı; bu belge bir başarı raporu değildir. İmzasız önizlemenin
Windows güven/SmartScreen davranışı da ayrıca incelenmelidir.
Kullanıcı 14 Ekim 2026 tarihinde temiz Windows testini şimdilik erteleyip
diğer geliştirmeye devam edilmesini seçti. Ortam kapısı kanıtlanmış sayılmaz.

## CI

.github/workflows/tests.yml Windows'ta kilitli Python/Qt ortamını, lint,
çekirdek mypy, sentetik pytest, sentetik C# adaptör testini ve wheel/sdist
özel veri denetimini çalıştırır. Actions commit SHA'larına sabitlenmiştir.
Oyun/model dosyası ve GPU gerekmez. Bağımlılık kurulumu ağ kullanır; çeviri
isteği veya telemetri adımı yoktur. Yerel ortak check komutu geçti; GitHub
workflow'u uzak depoda henüz çalıştırılmadı. Bu CI temiz Windows standalone
veya oyun içi doğrulama yerine geçmez.

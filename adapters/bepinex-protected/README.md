# Deneysel koruma değişiklikli preloader

Bu klasör UnityTranslator'ın MIT kodunu ve testlerini içerir. Upstream
BepInEx kodu burada kopyalanmaz; geliştirici sabit hash'li 5.4.23.5 kaynak
arşivini ayrı önbellekten seçer. Upstream MIT bildirimi ve değişiklik tarihleri
üretilen kaynak ağacında korunur. Ana Python/Qt mimarisi ve proje lisansı
değişmez. Loader dağıtımı veya oyun içi destek doğrulandı denmez.

`tools/prepare_protected_preloader.py` yeni önbellek klasörü oluşturur:

- Preloader.Run içindeki koşulsuz HarmonyInteropFix.Apply çağrısını kaldırır.
- HarmonyInteropFix gövdesini boşaltır; shim/legacy interop DLL referansı
  derlenmiş preloader'da kalmaz.
- İki oyun-kökü hata logu yazımını ProtectedRuntimeDiagnostics ile değiştirir.
- Başlangıçta runtime ve oyun ağacının ayrılığını kontrol eder; kimlik yoksa
  veya yollar örtüşüyorsa loader başlangıcı durur.

Diagnostics yalnızca dış runtime ağacında benzersiz GUID loglarını
FileMode.CreateNew ile açar. Mevcut dosyayı değiştirmez; başarısızlıkta oyun
klasörüne/CWD'ye geri dönüş yoktur. UNC/aygıt/göreli/ADS ve gözlenen reparse
yollar reddedilir. Mesaj 8.192 karakterle sınırlıdır. Yol kontrolü OS düzeyinde
başlatma veya eşzamanlı reparse değişimini kilitlemez; tamamlanmış oyun
koruması iddiası verilmez.

Geliştirici komutları; yollar kullanıcı tarafından seçilir:

```powershell
python tools/prepare_protected_preloader.py --source-archive <sabit-kaynak.zip> --managed <oyun-Managed> --loader <yerel-loader> --csc <Roslyn-csc.dll>
python tools/audit_protected_preloader.py --assembly <üretilen-Preloader.dll> --output <proje-raporu.json>
```

14 Ekim 2026 derlemesi gerçek eski Mono referanslarıyla geçti; kullanılan
referans hash'leri değişmedi. CLR'a oyun/loader assembly'si yüklenmedi.
Statik CIL denetimi shim ve File.WriteAllBytes/WriteAllText çağrılarının
ulaşılan başlangıç grafiğinde olmadığını, interop AssemblyRef'in yokluğunu,
entry guard'ını ve FileStream CreateNew/Write/None sabitlerini doğruladı.
`application_verified=false` kalır. Diğer/native/reflection yan etkilerinin
tam grafiği veya oyun içi çalışabilirlik bu testin kapsamı değildir.

`tools/check.py --with-dotnet` yalnızca kendi diagnostics kodunu sentetik
dosyalarda çalıştırır: ayrık runtime, Unicode, benzersiz loglar, mesaj sınırı,
mevcut log korunması, iki örtüşme yönü, UNC/göreli/ADS/missing kimlik ve oyun
klasörüne geri dönüş olmaması. 14 kontrol geçti. Bu .NET 10 testi gerçek
oyunun eski Mono runtime testi değildir.

Sonraki hazırlık, bu preloader'ı oyun dışındaki ayrı runtime ağacına bağlayan
Doorstop ayarları ve sahiplik planıdır. BepInEx config/log/cache üretimleri,
plugin/çeviri/font/sahne kanıtları, özgün envanter, çakışmasız dosyalar ve
açık kullanıcı oyun denemesi kapıları ayrıca çözülmelidir. Mevcut preview.3
bu prototipi içermez. Oyun başlatılmadı ve oyun dosyası yazılmadı.

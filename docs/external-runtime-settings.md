# Oyun dışı loader çalışma alanı

Geliştirici komutu `tools/stage_external_runtime.py`, koruma değişiklikli
preloader'ın build hash'ini ve statik CIL denetimini yeniden kontrol eder.
Sekiz resmî bağımlılık DLL'si katalogla karşılaştırılır; değiştirilmiş preloader
ile birlikte dokuz DLL yeni proje artefaktına kopyalanır. Kopya hash'leri
doğrulanır. Legacy shim DLL'leri eklenmez. `plugins` ve `patchers` boş oluşturulur.
Loader veya oyun çalıştırılmaz; ağ erişimi yoktur.

```powershell
python tools/stage_external_runtime.py --game <oyun> --project <ayrı-proje> --loader <yerel-loader> --protected-build <koruma-derlemesi>
```

`prepare_runtime_settings` yalnızca proje içindeki `core/BepInEx.Preloader.dll`
için ayar üretir. BepInEx.cfg runtime ağacında tutulur; mevcut config üzerine
yazılmaz. Disk/console logu, assembly metadata cache, assembly dump, dump'tan
yükleme ve debugger break kapalıdır. BepInEx'in kendi Bind/config işlemleri
bu dış runtime ağacında kalmalıdır; gerçek oyunda bu davranış henüz denenmedi.

Doorstop INI ayrı proje artefaktındadır. Varsayılan `enabled=false` ve absolute
`target_assembly` dış preloader'a işaret eder. Output-log yönlendirmesi, Mono
debugger, boot.config ve Mono DLL arama override'ları kapalıdır. INI UTF-16LE
BOM ile yazılır. Resmî Doorstop x64 DLL'sinin import tablosunda
[GetPrivateProfileStringW](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-getprivateprofilestringw)
bulundu. Aynı Windows API'siyle sentetik INI testinde Türkçe, boşluk ve noktalı
virgül içeren yol ve false alanları doğru okundu. Bu test DLL'yi yüklemez veya
native Doorstop davranışının tamamını kanıtlamaz.

14 Ekim 2026'da gerçek doğrulanmış dev önbelleğinden ayrı runtime hazırlandı.
Dokuz kopya hash'i ve tekrar CIL denetimi geçti. Oyun klasörüne dosya eklenmedi.
Ayar/çalışma alanı manifestlerinde `application_verified=false` ve
`installation_authorized=false` kalır. Bu çalışma alanı plugin, çeviri,
winhttp/oyuna uygulama dosya planı ve tamamlanmış lisans/source dağıtım paketi
değildir. Sonraki adımlar bunları, özgün envanteri, font/sahne/hash kanıtlarını
ve açık oyun denemesi seçimini birlikte hazırlamalıdır. Preview.3 bu kaynak
değişikliklerini içermez.

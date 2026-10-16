# Stok yükleyicide kalıcı DLL yazma yolu

BepInEx 5.4.23.5 x64 dosyaları önceki sürüm/lisans denetiminde resmî arşivle
eşleşti. Bu eşleşme özgün dosyaların korunacağı anlamına gelmez.

[Preloader.Run](https://github.com/BepInEx/BepInEx/blob/v5.4.23.5/BepInEx.Preloader/Preloader.cs)
HarmonyInteropFix.Apply çağrısını koşulsuz yapar. Bu çağrı ApplyRuntimePatches
ayarının koruduğu UnityPatches dalından ayrıdır.
[HarmonyInteropFix](https://github.com/BepInEx/BepInEx/blob/v5.4.23.5/BepInEx.Preloader/RuntimeFixes/HarmonyInteropFix.cs)
Assembly.LoadFile/LoadFrom çağrılarına uyumluluk shim'i ekler.
[TryShimInternal](https://github.com/BepInEx/BepInEx.Harmony/blob/d4cdcb4cdeac14a0b77012165f5f5a9f5032a9fa/HarmonyXInterop/HarmonyInterop.cs)
uygun eski Harmony referansı bulduğunda özgün byte'ları yedekler ve okuduğu
DLL yoluna File.WriteAllBytes ile yeniden yazar. Yedek almak projenin mevcut
oyun dosyasını değiştirmeme kuralına istisna değildir.

Dev önbelleğindeki iki resmî DLL CLR'a yüklenmeden dnfile/dncil ile okundu.
Preloader.Run grafiğinde interop initialization; TryShim grafiğinde
File.WriteAllBytes doğrulandı. Assembly hash'leri analizden sonra eşittir.
Grafik dış/native/örtük initializer davranışının tam kanıtı değildir;
yazma yolunun seçilen oyunda gerçekten çalıştığı da iddia edilmez. Oyun ve
loader çalıştırılmadı.

Core yükleyici değerlendirmesi bu bilinen iki hash eşleşirse
`unsupported/persistent_assembly_shim` sonucu verir. Kapsam özgün dosya
korumasıdır. Başka veya değiştirilmiş DLL `unknown` kalır; değiştirilmiş
olması güvenli sayılmaz. Destek paketi hazırlanabilir fakat manifesti kurulum
yetkisi vermez. Sonraki çalışma özgün DLL yazma yollarını kaldıran, açıkça
denetlenmiş bir bootstrap veya başka güvenli yöntem hazırlamalıdır.

Ayrıca stok loader config, log ve cache dosyaları üretebilir; bazı hata
logları oyun köküne yazılır. Bunların yeni dosya/sahiplik/çakışma kapsamı da
çözülmeden gerçek etkinleştirme açılmayacaktır. Mevcut oyun dosyalarını
dışlama kurallarıyla gizlemek veya yazımı yedekle meşrulaştırmak yoktur.
Masaüstü çıkarma/çeviri/inceleme/JSON akışı kullanılabilir kalır.

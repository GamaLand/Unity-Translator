# Experimental I2 Mono adapter

The adapter supports the source and target language tags stored in the translation
project. Runtime JSON v2 includes `source_language`; legacy v1 payloads retain their
English-source meaning. The parser accepts only these fixed schemas and rejects
unknown fields, duplicate keys and oversized data.

Source columns are resolved by exact language code first, then an unambiguous
base-language match. Explicit regions never silently select a different region.
Every approved term is checked against its selected source text hash before any
memory changes. The source column is preserved. Untranslated target text falls
back to the source; existing target font/asset references are retained. New fonts
are not downloaded or injected.

Target language selection updates only I2 memory fields, culture, RTL and joined-word
flags. No persistent language preference API is called. Changes roll back if a
write or localization callback fails. Scene replacement sources are checked again.

Matching Unity/game assembly fingerprints are still required. Broader languages
have synthetic regression coverage, not verified in-game rendering. Font coverage,
RTL shaping, plural rules and layout must be reviewed in the actual game. Existing
plural branches remain structurally protected; they are not automatically redesigned
for a different language's plural categories.

## Geliştirici doğrulaması

Game assembly'leri derlemede yalnızca referans olarak okunur; çalıştırılmaz,
kaynak deposuna/dağıtıma kopyalanmaz. Derleyici, oyun ve loader yolları açık
girdidir; makineye özel sabit değer yoktur:

```powershell
uv run python tools/build_i2mono.py --managed "OYUN_Data/Managed" --bepinex-core "GELISTIRME_ONBELLEGI/BepInEx/core" --csc "KURULU_ROSLYN/csc.dll"
```

Çıktı `.cache/i2mono-build/` altında kalır. Roslyn ile gerçek oyun referansları
ve BepInEx 5.4.23.5 kullanılarak derleme geçti; mscorlib 2.0.0.0 metadata
hedefi korunur. Referans dosyalarının önce/sonra hash'leri eşittir. Bu sonuç
Unity/Mono içinde yüklenme kanıtı değildir.

CoreTests.csproj yalnızca sentetik ISource ile .NET 10 geliştirici SDK'sında
çalışır. Gerçek game assembly'sini test sürecine yüklemez:

```powershell
$env:DOTNET_CLI_TELEMETRY_OPTOUT='1'
$env:DOTNET_GENERATE_ASPNET_CERTIFICATE='false'
dotnet run --project adapters/i2mono/tests/CoreTests.csproj -p:BaseIntermediateOutputPath="$PWD/.cache/i2mono-tests/obj/" -p:BaseOutputPath="$PWD/.cache/i2mono-tests/bin/"
```

13 sentetik çekirdek senaryosu Unicode, hash, eksik/çift kaynak veya terim,
kaynak diline yazmayı reddetme, biçim sürümü, placeholder kaybı, kaynaklar
arası hata/geri alma, başarısız geri almanın bildirilmesi ve sahne kaynak
değişimini kapsar. Beş sentetik I2 sarmalayıcı senaryosu İngilizce dilinin
indeks 1 olmasını, varlık fallback'ini ve özel touch/bayrak/dil geri almasını
ve sözlüğün hazır olmasını, kalıcı ayar API'si kullanılmadan dil seçilmesini
kontrol eder. Test projesi Plugin.cs'yi sentetik Unity/I2/BepInEx sınıflarıyla
derler; gerçek oyun veya yükleyici DLL'si test sürecine yüklenmez. Gerçek I2
metotlarının çalışma anındaki davranışı hâlâ test edilmemiştir.

## Yükleyici ve izin kapısı

[Resmî BepInEx sürümü 5.4.23.5](https://github.com/BepInEx/BepInEx/releases/tag/v5.4.23.5)
x64 zip, yalnızca geliştirme önbelleğine indirildi. GitHub release API digest'i
ile ölçülen SHA-256 aynı:
`82f9878551030f54657792c0740d9d51a09500eeae1fba21106b0c441e6732c4`.
Yükleyici çalıştırılmadı ve oyun köküne dosya eklenmedi.

Statik CIL incelemesinde UpdateDictionary → SaveLanguages ve dil setter'ı
→ PlayerPrefs yazımı bulundu. Bu yüzden AddLanguage/SetTranslation/
UpdateDictionary ve kalıcı dil setter'ı adaptörde kullanılmaz; dil ve terim
alanları bellekte değiştirilir. Yenileme sabit DoLocalizeAll callback'idir.
Reflection alan/metot adları veri dosyasından alınmaz. Statik grafikte dış
assembly, native, implicit initializer ve callback davranışı çözülmediği için
dosya koruma başarısı yalnızca bu analize dayandırılmaz.

Loader lisansları aynı lisans değildir: seçilmiş BepInEx kaynak lisansı
MIT, Doorstop 4.5.0 kaynak lisansı
[LGPL-2.1](https://github.com/NeighTools/UnityDoorstop/blob/v4.5.0/LICENSE).
13 DLL'nin resmî release eşlemesi, yedi NuGet byte eşleşmesi, x64 Doorstop
eşleşmesi ve dokuz tam lisans bildirimi hazırdır. Cecil PDB'nin MS-PL kodu,
Harmony'nin asıl MIT bildirimi ve iki sabit alt proje commit'i ayrıca izlendi.
[Bileşen denetimi](../../docs/loader-component-audit.md) ve
[hash/kaynak envanteri](loader-components.json) sınırları açıklar.
Son dağıtım paketinde kaynak erişimi ve bildirim kapsamı henüz doğrulanmadı;
loader dağıtılmıyor veya oyunda çalıştırılmıyor.

Gerçek etkinleştirme öncesi loader paketinin tüm bileşen/lisans bildirimi,
oyun kapalı kontrolü, değişken kullanıcı verisi dışlama kuralları, tüm özgün
envanter ve çakışmasız plan hazır olmalıdır. Kullanıcı somut dosya listesini
görüp oyunda denemeyi açıkça seçmelidir. Pilot onayı kurulum izni sayılmaz.
Şu anda UI/CLI kurulum komutu yoktur. Loader, kaynak DLL veya oyun verisi
son kullanıcı dağıtım paketine henüz eklenmedi.

Son statik denetim stok 5.4.23.5'in koşullu yedek/yerinde DLL shim yazımını
buldu. Bu yol özgün dosya koruma kuralına uymaz; stok loader doğrudan
etkinleştirmeye uygun değildir. Değiştirilmiş loader da test edilmeden güvenli
sayılmaz. [Kaynak ve CIL bulgusu](../../docs/loader-write-safety.md).

[BepInEx resmî geliştirici rehberi](https://docs.bepinex.dev/articles/dev_guide/plugin_tutorial/2_plugin_start.html)
runtime hedefi ve oyun referanslarının nasıl seçileceğini açıklar; bu rehber
tek başına özel oyun uyumluluğu kanıtı değildir.

# Konsolsuz Windows okuyucusu ve paralel çeviri

15 Ekim 2026. RC1 arayüzünde kaynak çıkarılırken `[WinError 6] İşleyici
geçersiz` görüldü. `capture_output=True` stdout/stderr'ı pipe yaparken
stdin varsayılan olarak üst süreçten kalıyordu. Konsolsuz GUI başlatmasında
geçersiz standart giriş, Windows DuplicateHandle çağrısında okuyucu daha
başlamadan hata veriyordu. Önceki PATH izolasyonu testi geçerli bir üst
süreç girişiyle çalıştığı için bu durumu kapsamıyordu.

`discovery.probe_source` artık `stdin=subprocess.DEVNULL` kullanır.
Windows regresyon testi geçersiz girişle eski varsayılan çağrıda hata 6'yı
üretir, aynı durumda yeni okuyucuyu gerçekten başlatır. Standalone arayüz
kontrolü de geçici olarak geçersiz STD_INPUT_HANDLE ayarlayıp gerçek frozen
okuyucuyu yeni sentetik dosyada çalıştırır, eski işleyiciyi finally ile geri
yükler. Bu doğrulama oyun dosyası veya model kullanmaz.

Kullanıcının istediği 4 paralel istek için `TranslationJobService.run`
1–4 sınırında işçi görevleri açar. Claim/commit tek olay döngüsünde senkron
kalır; HTTP beklemeleri paraleldir. İptal bütün görevleri toplayarak bekler;
duraklatma yeni claim'i durdurur, mevcut sonuçlar kaydedilir. Deneme/retry
sınırı kayıt başına korunur. Paralellik üretim profilini ve pilot anahtarını
değiştirmez, deneme metaverisinde tutulur. Arayüzde ayrıca seçilebilir.
Mevcut hız/ETA toplam istek süresine dayandığı için tek istek eşdeğeri olarak
etiketlenir. Bu ölçüm paralel duvar saati hızı diye raporlanmaz.

Kaynaklar: [Python subprocess](https://docs.python.org/3.12/library/subprocess.html),
`tests/test_safety.py`, `tests/test_parallel_jobs.py` ve
`src/unitytranslator/ui/verify.py`.

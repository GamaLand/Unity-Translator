# Arka planda çeviri

Çeviri penceresi küçültülebilir veya başka uygulamaya geçilebilir. HTTP ve
veri kaydı, Qt arayüzünden ayrı bir asyncio thread'inde yürür. Programı
kapatmak ise işi kapatır; küçültmek ile kapatmak farklı işlemlerdir.

RC4 öncesinde akışsız model istekleri 110 saniye cevap alamayınca kesiliyordu.
Üç başarısız denemeden sonra iş otomatik duraklıyordu. Yerel iş kayıtlarında
bu eşikte kesilen istekler ve başarısız timeout kayıtları görüldü. Pencerenin
arka plana alınmasının sunucuyu neden yavaşlattığı kanıtlanmadı.

RC4 üretim sırasında sunucu kuyruğu ve model yanıtı için istek başına toplam
30 dakika bekler. Sunucuya bağlanma sınırı 5 saniyedir; model listeleme ve
tanı istekleri kısa sınırlarını korur. Uzun bekleme sırasında iptal istemci
görevlerini hemen keser. Sunucunun iptali uygulama biçimi kendisine bağlıdır.
Duraklatma yeni istekleri durdurur, devam eden isteklerin sonuçlarını bekler.

Yeni otomatik duraklamaların nedeni ekranda açıklanır ve proje tekrar
açıldığında korunur. Eski sürümlerde kaydedilmemiş duraklama nedenleri
sonradan tahmin edilmez. Yüksek paralellik daha uzun sunucu kuyruğu
oluşturabilir; yine zaman aşımı olursa paralel sayısını azaltın.

Yeni paketi ayrı klasöre çıkarıp mevcut proje klasörünüzü açın. Çeviri
sekmesinde duraklamış işi seçerek devam edin; tamamlanmış kayıtlar yeniden
çevrilmez. Önceden başarısız sayılan kayıtlar otomatik yeniden kuyruğa alınmaz.

Doğrulama: Qt penceresi küçültülmüşken GUI olayları işlenmeden dört paralel
sentetik istekle sekiz sonuç kalıcı olarak kaydedildi. Üretim/tanı zaman
sınırlarının ayrılması, bekleyen HTTP isteğinin iptali ve duraklama nedeninin
yeniden açılışta korunması test edildi. Gerçek modelle yeni uzun süreli
arka plan denemesi yapılmadı; başka süreçlerin güç/bellek yönetimi değiştirilmedi.

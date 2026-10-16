# İstemci kaynak kullanımı gözlemi

15 Ekim 2026, Windows x64 geliştirme makinesinde tek gözlem. CPython
3.12.14/PySide6 6.12.0 kaynak sürümü, Qt offscreen arayüzü ve 16 mantıksal
işlemci kullanıldı. Bu tablo paketlenmiş uygulamanın veya asgari donanımın
sertifikası değildir. Gerçek oyun başlatılmadı.

Windows süreç sayaçları 20 ms aralıkla örneklendi. Yalnızca bu istemci ve
başlattığı okuyucu süreç ağacı izlendi. WS fiziksel çalışma kümesi, private
özel ayrılmış bellektir; MiB kullanılır. CPU sütunları geçen süre boyunca
tüketilen işlemci saniyesidir; yüzde değildir. Örnekleyici yükü dahildir.

| İşlem | Duvar süresi (sn) | İstemci CPU (sn) | İstemci tepe WS / private (MiB) | Okuyucu ağacı CPU (sn) | Okuyucu ağacı tepe WS / private (MiB) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Boş Qt arayüzü | 1,000 | 0,016 | 82,50 / 53,64 | — | — |
| 10.000 sentetik kayıtta 20 sayfa inceleme | 0,550 | 0,359 | 88,68 / 60,06 | — | — |
| 10 sentetik kaydın istemci çeviri akışı | 0,067 | 0,016 | 87,12 / 58,23 | — | — |
| Gerçek kaynaktan salt okunur çıkarma | 9,664 | 2,094 | 92,83 / 63,64 | 9,031 | 835,88 / 818,97 |

İnceleme modeli aynı anda 200 satır tuttu. Sentetik çeviri sağlayıcısı
süreç içindeydi; HTTP veya model çıkarımı yapmadı. Bu satır LLM çeviri
hızı değildir. Haricî model sunucusunun RAM/VRAM kullanımı ölçülmedi ve
istemci ölçümlerine dahil edilmedi.

Gerçek kaynak 6.749 kayıt, 6.095 benzersiz metin ve 677.344 karakter verdi;
çıkarma hatası sıfırdı. 3.964 type-tree tanısı ve 105 boş kaynak dışlaması
raporlandı. Okuyucu ağacı üç alt süreci (başlatıcılar dahil) kapsadı.
Kaynak SHA-256 değeri okuma öncesi/sonrası eşitti. Model isteği gönderilmedi.

Sonuç: inceleme belleği tüm kayıtları tabloya yüklemek yerine sayfalama ile
sınırlandı; çıkarma sırasında ayrı okuyucu belirgin ek bellek kullandı.
Örnekleme kısa tepe değerlerini kaçırabilir. Disk önbelleği, oyun boyutu,
sunucu ve donanım değişince süre değişir. Bu tek gözlemden asgari RAM,
genel hız veya tam oyun performans garantisi çıkarılmaz.

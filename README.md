# Sıfırdan İstanbul Maratonu 15K — Günlük Video Projesi

- **[PROGRAM.md](PROGRAM.md)**: 20 günlük antrenman ve beslenme programı
- **gunluk/AAAA-AA-GG/**: her günün `notlar.md` dosyası ve fotoğrafları (şablon: `gunluk/SABLON.md`)
- **scripts/video_olustur.py**: notları seslendirip fotoğraflar ve müzikle videoya çevirir
- **scripts/youtube_yukle.py**: onaylanan videoyu YouTube'a yükler

## Günlük akış
1. `gunluk/2026-10-13/notlar.md` oluştur (şablonu kopyala), fotoğrafları aynı klasöre koy:
   `kahvalti.jpg`, `ogle.jpg`, `aksam.jpg`, `antrenman1.jpg`, `antrenman2.jpg`…
2. `python scripts/video_olustur.py gunluk/2026-10-13`: `cikti/` klasörüne mp4 ve json üretir. Shorts için `--dikey` ekle.
3. Videoyu izle. Beğendiysen: `python scripts/youtube_yukle.py cikti/gun02_2026-10-13.json`

## Kurulum (kendi bilgisayarında)
```
pip install -r requirements.txt
# ffmpeg: https://ffmpeg.org/download.html  (Windows: winget install ffmpeg, Mac: brew install ffmpeg)
```
Seslendirme için Microsoft Edge'in ücretsiz Türkçe sesleri kullanılır (`tr-TR-AhmetNeural`, `tr-TR-EmelNeural`), internet bağlantısı gerekir.
Müzik: YouTube Studio → Ses Kitaplığı'ndan telifsiz bir parça indirip `muzik/` klasörüne koy. Klasör boşsa sakin bir fon müziği otomatik üretilir.

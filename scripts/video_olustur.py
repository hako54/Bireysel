#!/usr/bin/env python3
"""Günlük notlardan (notlar.md + fotoğraflar) seslendirmeli, müzikli YouTube videosu üretir.

Kullanım:
    python scripts/video_olustur.py gunluk/2026-10-12
    python scripts/video_olustur.py gunluk/2026-10-12 --dikey        # Shorts (9:16)
    python scripts/video_olustur.py gunluk/2026-10-12 --ses tr-TR-EmelNeural
    python scripts/video_olustur.py gunluk/2026-10-12 --sessiz       # seslendirmesiz deneme

Fotoğraf adları bölüme göre eşleşir: kahvalti*.jpg, ogle*.jpg, aksam*.jpg,
antrenman*.jpg, his*.jpg. Diğer fotoğraflar antrenman bölümüne eklenir.
Müzik: muzik/ klasörüne bir mp3 koyarsan o kullanılır; yoksa sakin bir fon müziği sentezlenir.
"""
import argparse
import asyncio
import datetime as dt
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

KOK = Path(__file__).resolve().parent.parent
BASLANGIC = dt.date(2026, 10, 12)
YARIS = dt.date(2026, 11, 1)
TOPLAM_GUN = (YARIS - BASLANGIC).days  # 20
FPS = 30

BOLUMLER = {
    "kahvalti": ("Kahvaltı", "🍳"),
    "ogle": ("Öğle Yemeği", "🥗"),
    "aksam": ("Akşam Yemeği", "🍽"),
    "antrenman": ("Antrenman", "🏃"),
    "his": ("Nasıl Hissettim", "💬"),
}
RENK_ARKA = (14, 30, 52)
RENK_VURGU = (255, 122, 0)
RENK_YAZI = (255, 255, 255)

FONT_ADAYLARI = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans{b}.ttf",
    "C:/Windows/Fonts/arial{bw}.ttf",
    "/System/Library/Fonts/Supplemental/Arial{bm}.ttf",
    "/Library/Fonts/Arial{bm}.ttf",
]


def font(boyut, kalin=False):
    for aday in FONT_ADAYLARI:
        yol = aday.format(b="-Bold" if kalin else "", bw="bd" if kalin else "", bm=" Bold" if kalin else "")
        if Path(yol).exists():
            return ImageFont.truetype(yol, boyut)
    return ImageFont.load_default(size=boyut)


def normal(s):
    tablo = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
    return s.translate(tablo).lower()


def bolum_anahtari(baslik):
    n = normal(baslik)
    for anahtar in BOLUMLER:
        if n.startswith(anahtar) or anahtar in n.replace(" ", ""):
            return anahtar
    if "nasil" in n or "his" in n:
        return "his"
    return None


def notlari_oku(klasor):
    metin = (klasor / "notlar.md").read_text(encoding="utf-8")
    ust, bolumler, aktif = [], [], None
    for satir in metin.splitlines():
        if satir.startswith("## "):
            aktif = {"baslik": satir[3:].strip(), "metin": []}
            bolumler.append(aktif)
        elif satir.startswith("# "):
            continue
        elif aktif is None:
            if satir.strip():
                ust.append(satir.strip())
        else:
            aktif["metin"].append(satir)
    for b in bolumler:
        b["metin"] = "\n".join(b["metin"]).strip()
        b["anahtar"] = bolum_anahtari(b["baslik"])
    # Şablondan kalan boş/doldurulmamış bölümleri atla
    bolumler = [b for b in bolumler if b["metin"] and not b["metin"].startswith(("Ne yedin?", "...", "Ne yaptın,", "Kısa bir not"))]
    ust = [u for u in ust if not re.match(r"^[^:]+:\s*$", u)]
    return ust, bolumler


def fotograflari_bul(klasor):
    fotolar = sorted(p for p in klasor.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".heic"})
    eslesme = {k: [] for k in BOLUMLER}
    for p in fotolar:
        anahtar = bolum_anahtari(p.stem) or "antrenman"
        eslesme[anahtar].append(p)
    return eslesme


def seslendirme_metni(s):
    s = re.sub(r"[*_#>`]", "", s)
    s = re.sub(r"(\d)\s*×\s*", r"\1 kere ", s)
    s = re.sub(r"\bdk\b", "dakika", s)
    s = re.sub(r"\bsn\b", "saniye", s)
    s = re.sub(r"\bkm\b", "kilometre", s)
    s = re.sub(r"\bkg\b", "kilo", s)
    s = s.replace(" / ", ", ").replace("\n", ". ")
    return re.sub(r"[^\w\s.,!?;:%'()-]", "", s)


async def _edge(metin, ses, hedef):
    import edge_tts
    await edge_tts.Communicate(metin, ses, rate="+5%").save(str(hedef))


def seslendir(metin, ses, hedef):
    try:
        asyncio.run(_edge(metin, ses, hedef))
        if hedef.stat().st_size > 0:
            return
    except Exception as e:
        print(f"  edge-tts başarısız ({e.__class__.__name__}), gTTS deneniyor…")
    from gtts import gTTS
    gTTS(metin, lang="tr").save(str(hedef))


def sure(dosya):
    cikti = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(dosya)],
                           capture_output=True, text=True, check=True).stdout
    return float(json.loads(cikti)["format"]["duration"])


def sar(ciz, metin, f, genislik):
    satirlar = []
    for paragraf in metin.split("\n"):
        kelimeler, satir = paragraf.split(), ""
        for k in kelimeler:
            deneme = f"{satir} {k}".strip()
            if ciz.textlength(deneme, font=f) <= genislik:
                satir = deneme
            else:
                if satir:
                    satirlar.append(satir)
                satir = k
        satirlar.append(satir)
    return satirlar


def kapla(img, W, H):
    return ImageOps.fit(img.convert("RGB"), (W, H), Image.LANCZOS)


def foto_ac(yol):
    img = Image.open(yol)
    return ImageOps.exif_transpose(img).convert("RGB")


def slayt_ciz(W, H, ust_yazi, baslik, govde, fotolar, hedef):
    if fotolar:
        arka = kapla(foto_ac(fotolar[0]), W, H).filter(ImageFilter.GaussianBlur(40))
        arka = Image.blend(arka, Image.new("RGB", (W, H), RENK_ARKA), 0.55)
    else:
        arka = Image.new("RGB", (W, H), RENK_ARKA)
        g = Image.linear_gradient("L").resize((W, H))
        arka = Image.composite(Image.new("RGB", (W, H), (30, 70, 110)), arka, g)
    ciz = ImageDraw.Draw(arka)
    kenar = int(W * 0.05)
    dikey = H > W

    # Fotoğraf alanı
    if fotolar:
        if dikey:
            alan = (kenar, int(H * 0.16), W - kenar, int(H * 0.58))
        else:
            alan = (kenar, int(H * 0.16), int(W * 0.52), H - kenar)
        aw, ah = alan[2] - alan[0], alan[3] - alan[1]
        n = min(len(fotolar), 3)
        bosluk = 16
        if dikey or n == 1:
            parca_w, parca_h = (aw - bosluk * (n - 1)) // n, ah
        else:
            parca_w, parca_h = aw, (ah - bosluk * (n - 1)) // n
        for i, p in enumerate(fotolar[:3]):
            parca = kapla(foto_ac(p), parca_w, parca_h)
            maske = Image.new("L", parca.size, 0)
            ImageDraw.Draw(maske).rounded_rectangle((0, 0, *parca.size), 24, fill=255)
            x = alan[0] + (i * (parca_w + bosluk) if (dikey or n == 1) else 0)
            y = alan[1] + (0 if (dikey or n == 1) else i * (parca_h + bosluk))
            arka.paste(parca, (x, y), maske)
        yazi_x = kenar if dikey else int(W * 0.56)
        yazi_y = int(H * 0.62) if dikey else int(H * 0.18)
    else:
        yazi_x, yazi_y = kenar, int(H * 0.30)
    yazi_w = W - yazi_x - kenar

    # Üst bant
    f_ust = font(int(H * (0.024 if dikey else 0.035)), kalin=True)
    ciz.text((kenar, int(H * 0.05)), ust_yazi, font=f_ust, fill=RENK_VURGU)
    ciz.rectangle((kenar, int(H * 0.05) + f_ust.size + 14, kenar + 160, int(H * 0.05) + f_ust.size + 20), fill=RENK_VURGU)

    # Başlık ve gövde (sığana kadar küçült)
    f_bas = font(int(H * (0.04 if dikey else 0.07)), kalin=True)
    ciz.text((yazi_x, yazi_y), baslik, font=f_bas, fill=RENK_YAZI)
    y0 = yazi_y + int(f_bas.size * 1.5)
    boy = int(H * (0.026 if dikey else 0.042))
    while True:
        f_gov = font(boy)
        satirlar = sar(ciz, govde, f_gov, yazi_w)
        if y0 + len(satirlar) * boy * 1.35 < H - kenar or boy < 18:
            break
        boy -= 2
    for i, s in enumerate(satirlar):
        ciz.text((yazi_x, y0 + i * boy * 1.35), s, font=f_gov, fill=(225, 232, 240))
    arka.save(hedef)


def klip_yap(png, ses, sure_sn, hedef):
    kare = max(int(sure_sn * FPS), FPS)
    vf = (f"scale=iw*1.1:-1,zoompan=z='min(zoom+0.0003,1.06)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
          f":d={kare}:s={{W}}x{{H}}:fps={FPS},fade=t=in:st=0:d=0.4,fade=t=out:st={sure_sn - 0.4:.2f}:d=0.4")
    W, H = Image.open(png).size
    vf = vf.replace("{W}", str(W)).replace("{H}", str(H))
    komut = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(png)]
    if ses:
        komut += ["-i", str(ses), "-af", f"apad=whole_dur={sure_sn:.2f}"]
    else:
        komut += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
    komut += ["-vf", vf, "-t", f"{sure_sn:.2f}", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
              "-c:a", "aac", "-ar", "44100", "-ac", "2", str(hedef)]
    subprocess.run(komut, check=True)


def muzik_sentezle(sure_sn, hedef):
    """Telifsiz, sakin bir fon müziği: Am–F–C–G akor döngüsü, yumuşak pad sesi."""
    akorlar = [(220.0, 261.63, 329.63), (174.61, 220.0, 261.63), (130.81, 196.0, 261.63), (196.0, 246.94, 293.66)]
    uz = 4.0
    ifade = "+".join(
        f"between(mod(t,{uz * 4}),{i * uz},{(i + 1) * uz})*(" + "+".join(f"sin(2*PI*{f}*t)" for f in a) + ")"
        for i, a in enumerate(akorlar))
    ifade = f"0.12*({ifade})*(0.75+0.25*sin(2*PI*0.25*t))"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    f"aevalsrc='{ifade}|{ifade}':s=44100:d={sure_sn + 1:.1f}",
                    "-af", "lowpass=f=1800,aecho=0.8:0.7:120|240:0.3|0.2,volume=1.5", str(hedef)], check=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("klasor", type=Path)
    ap.add_argument("--dikey", action="store_true", help="YouTube Shorts için 1080x1920")
    ap.add_argument("--ses", default="tr-TR-AhmetNeural", help="tr-TR-AhmetNeural veya tr-TR-EmelNeural")
    ap.add_argument("--sessiz", action="store_true", help="Seslendirme yapmadan deneme videosu üret")
    ap.add_argument("--muzik", type=Path, help="Kullanılacak müzik dosyası (varsayılan: muzik/ içindeki ilk mp3)")
    ap.add_argument("--muzik-seviye", type=float, default=0.18)
    args = ap.parse_args()

    klasor = args.klasor.resolve()
    tarih = dt.date.fromisoformat(klasor.name)
    gun_no = (tarih - BASLANGIC).days + 1
    kalan = (YARIS - tarih).days
    W, H = (1080, 1920) if args.dikey else (1920, 1080)
    ust, bolumler = notlari_oku(klasor)
    fotolar = fotograflari_bul(klasor)
    if not bolumler:
        sys.exit("notlar.md içinde doldurulmuş bölüm bulunamadı.")

    ust_yazi = f"GÜN {gun_no}/{TOPLAM_GUN}  ·  İSTANBUL 15K'YA {kalan} GÜN"
    slaytlar = [{
        "baslik": f"Gün {gun_no}: {tarih.strftime('%d.%m.%Y')}",
        "govde": "Sıfırdan İstanbul Maratonu 15K\n" + "\n".join(ust),
        "fotolar": [],
        "ses": f"İstanbul Maratonu on beş kilometre hazırlığında {gun_no}. gün. Yarışa {kalan} gün kaldı. "
               + seslendirme_metni(". ".join(ust)),
    }]
    for b in bolumler:
        etiket = BOLUMLER.get(b["anahtar"], (b["baslik"], ""))[0] if b["anahtar"] else b["baslik"]
        slaytlar.append({"baslik": etiket, "govde": b["metin"], "fotolar": fotolar.get(b["anahtar"], []),
                         "ses": f"{etiket}. {seslendirme_metni(b['metin'])}"})
    slaytlar.append({"baslik": "Yarın görüşmek üzere!", "govde": f"Yarışa {kalan - 1} gün kaldı.\nAbone olmayı unutma!",
                     "fotolar": [], "ses": "Yarın görüşmek üzere. Abone olmayı ve yorum yazmayı unutma."})

    cikti_klasor = KOK / "cikti"
    cikti_klasor.mkdir(exist_ok=True)
    son = cikti_klasor / f"gun{gun_no:02d}_{tarih.isoformat()}{'_shorts' if args.dikey else ''}.mp4"

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        klipler = []
        for i, s in enumerate(slaytlar):
            print(f"[{i + 1}/{len(slaytlar)}] {s['baslik']}")
            png = tmp / f"s{i}.png"
            slayt_ciz(W, H, ust_yazi, s["baslik"], s["govde"], s["fotolar"], png)
            if args.sessiz:
                ses, sn = None, max(4.0, len(s["ses"].split()) * 0.42)
            else:
                ses = tmp / f"s{i}.mp3"
                seslendir(s["ses"], args.ses, ses)
                sn = sure(ses) + 0.9
            klip = tmp / f"k{i}.mp4"
            klip_yap(png, ses, sn, klip)
            klipler.append(klip)

        liste = tmp / "liste.txt"
        liste.write_text("".join(f"file '{k}'\n" for k in klipler))
        birlesik = tmp / "birlesik.mp4"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(liste),
                        "-c", "copy", str(birlesik)], check=True)
        toplam = sure(birlesik)

        muzik = args.muzik or next(iter(sorted((KOK / "muzik").glob("*.mp3"))), None)
        if muzik is None:
            muzik = tmp / "muzik.wav"
            muzik_sentezle(toplam, muzik)
        print(f"Müzik: {muzik.name}")
        # Konuşma varken müziği otomatik kıs (ducking), sonda müziği yavaşça kapat
        filtre = (f"[1:a]volume={args.muzik_seviye},afade=t=in:d=1.5,afade=t=out:st={max(toplam - 3, 0):.2f}:d=3[m];"
                  "[0:a]asplit=2[v][sc];[m][sc]sidechaincompress=threshold=0.03:ratio=6:attack=50:release=600[md];"
                  "[v][md]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5[a]")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(birlesik), "-stream_loop", "-1", "-i", str(muzik),
                        "-filter_complex", filtre, "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac",
                        "-b:a", "192k", "-t", f"{toplam:.2f}", "-movflags", "+faststart", str(son)], check=True)

    bilgi = {
        "baslik": f"Sıfırdan İstanbul Maratonu 15K | Gün {gun_no}/{TOPLAM_GUN} ({tarih.strftime('%d.%m.%Y')})",
        "aciklama": (f"Hiç antrenmanı olmayan biri olarak 20 günde İstanbul Maratonu 15K'ya hazırlanıyorum. "
                     f"Bugün {gun_no}. gün, yarışa {kalan} gün kaldı.\n\n"
                     + "\n\n".join(f"{s['baslik']}:\n{s['govde']}" for s in slaytlar[1:-1])
                     + "\n\n#istanbulmaratonu #koşu #15k #sıfırdankoşu #runningjourney"),
        "etiketler": ["istanbul maratonu", "15k", "koşu", "sıfırdan koşu", "koş yürü", "maraton hazırlık",
                      "kilo verme", "running vlog"],
        "video": str(son),
    }
    son.with_suffix(".json").write_text(json.dumps(bilgi, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nHazır: {son} ({toplam:.0f} sn)\nYouTube bilgileri: {son.with_suffix('.json')}")


if __name__ == "__main__":
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg bulunamadı. Kurulum: https://ffmpeg.org/download.html")
    main()

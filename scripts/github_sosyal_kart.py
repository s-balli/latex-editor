# -*- coding: utf-8 -*-
"""GitHub sosyal onizleme gorseli uret (1280x640).

NEREDE GORUNUR: GitHub arama sonuclarinda deponun ustundeki manset resmi,
ve depo baglantisi Twitter/LinkedIn/Slack/Discord'da paylasildiginda cikan
onizleme karti.

NASIL YUKLENIR: depo > Settings > General > Social preview > Edit >
Upload an image. API'si YOK, yalnizca arayuzden yukleniyor.

NEDEN EKRAN GORUNTUSU DEGIL: `docs/assets/og-card.png` uygulamanin kucultulmus
ekran goruntusu. Arama sonucunda bu gorsel kucuk gosteriliyor, orada bir ekran
goruntusu okunmaz bir lekeye donuyor. Sozcuk markasi + tek satir aciklama
kucukken de okunuyor.

Renkler tanitim sayfasinin koyu temasindan (docs/styles.css) aliniyor;
zemin GitHub'in kendi koyu zeminiyle ayni (#0d1117), kart sayfaya
yapisiyor.

WINDOWS'TA KOSAR: Georgia ve Segoe UI kullaniyor, ikisi de Windows yazi
tipi. Bu yuzden CI'da (Linux) kosturulmuyor ve "gorsel guncel mi" diye bir
test YOK; /tr/ sayfasindaki gibi bir kapi burada kurulamaz. Kart nadiren
degisiyor, elle uretilip yukleniyor.

Kullanim:
    python scripts/github_sosyal_kart.py
"""
from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CIKTI = os.path.join(KOK, "docs", "assets", "github-social.png")

# UYGULAMA SIMGESI BILEREK KULLANILMIYOR: simgenin kendi icinde de "LaTeX
# EDITOR" yazisi var, sozcuk markasinin yanina konunca ad iki kez
# gorunuyordu; ustelik saga yerlestirilince uzun alt satirin son harfini
# ortuyordu. Kucuk boyutta tek ve buyuk bir sozcuk markasi daha iyi
# okunuyor (730, 360 ve 200 px'te denendi).

# GitHub'in onerdigi olcu. 1 MB siniri var, bu kart ~40 KB.
EN, BOY = 1280, 640

# docs/styles.css koyu temasi
ZEMIN = (13, 17, 23)          # --bg
METIN = (230, 237, 243)       # --text
VURGU = (124, 131, 255)       # --accent
SOLUK = (148, 161, 178)       # --muted
CIZGI = (35, 43, 56)          # --border

F = "C:/Windows/Fonts/%s"


def yazitipi(ad, boy):
    return ImageFont.truetype(F % ad, boy)


def genislik(cizim, metin, tf):
    return cizim.textbbox((0, 0), metin, font=tf)[2]


def latex_marka(cizim, x, y, boy):
    """LaTeX logosu: L, yukari kaymis kucuk `a`, T, asagi kaymis `e`, X.

    Tanitim sayfasindaki marka ile ayni: serif govde, `a` ve `e` egik ve
    vurgu renginde (docs/styles.css .brand-mark / .brand-tex).
    """
    duz = yazitipi("georgiab.ttf", boy)
    kucuk = yazitipi("georgiaz.ttf", int(boy * 0.62))   # bold italic

    imlec = x
    for harf, tf, renk, dy in (
            ("L", duz, METIN, 0),
            ("a", kucuk, VURGU, -int(boy * 0.20)),
            ("T", duz, METIN, 0),
            ("e", kucuk, VURGU, int(boy * 0.16)),
            ("X", duz, METIN, 0)):
        cizim.text((imlec, y + dy), harf, font=tf, fill=renk)
        # Gercek LaTeX logosunda harfler birbirine giriyor
        imlec += genislik(cizim, harf, tf) - int(boy * 0.055)
    return imlec


def _dikey_denge(im, tolerans=42):
    """Icerik dikeyde ortali mi? Degilse patla.

    Ilk surumde `ust` degeri gozle secilmisti ve icerik asagi kaymisti:
    ustte 222, altta 113 px. Kart yuklendikten sonra fark edildi. Punto ya
    da satir sayisi degisince ayni sey yine olur, o yuzden olcum burada.

    Optik merkez: ustteki bosluk alttakinden BIRAZ AZ olmali. Tolerans
    disina cikarsa gorsel yazilmiyor.
    """
    gri = im.convert("L")
    # Ustteki vurgu seridi metin degil, olcume katilmasin
    govde = gri.crop((0, 12, EN, BOY))
    kutu = govde.point(lambda p: 255 if p > 120 else 0).getbbox()
    if kutu is None:                             # pragma: no cover
        raise SystemExit("kartta hic metin bulunamadi")
    ust_bosluk = kutu[1] + 12
    alt_bosluk = BOY - (kutu[3] + 12)
    fark = ust_bosluk - alt_bosluk
    if fark > tolerans or fark < -tolerans * 2:
        raise SystemExit(
            "icerik dikeyde ortali degil: ustte %d px, altta %d px. "
            "`ust` degerini %+d kaydir."
            % (ust_bosluk, alt_bosluk, -fark // 2))
    print("  dikey denge: ustte %d px, altta %d px" % (ust_bosluk, alt_bosluk))


def uret():
    im = Image.new("RGB", (EN, BOY), ZEMIN)

    # Vurgu renginde yumusak bir isik lekesi: duz zemin cok yavan duruyor
    leke = Image.new("RGB", (EN, BOY), ZEMIN)
    lc = ImageDraw.Draw(leke)
    lc.ellipse((EN - 620, -300, EN + 200, 420), fill=(38, 40, 96))
    lc.ellipse((-260, BOY - 260, 380, BOY + 260), fill=(26, 32, 60))
    im = Image.blend(im, leke.filter(ImageFilter.GaussianBlur(150)), 0.85)

    c = ImageDraw.Draw(im)
    c.rectangle((0, 0, EN, 6), fill=VURGU)       # ust vurgu seridi

    # METIN INGILIZCE: GitHub arama sonucunda kartin hemen yaninda deponun
    # Ingilizce aciklamasi duruyor, Turkce kart oraya yamali duruyordu.
    # Turkce destegi zaten ayirt edici ozellik olarak alt satirda geciyor.
    ALT = "Instant PDF preview, SyncTeX, fully offline"
    KUNYE = "Windows + Linux   ·   Turkish + English   ·   GPL-3.0"

    # ORTALANMIS DUZEN. Once olcup sonra yerlestiriliyor; sabit sol kenarla
    # denendiginde uzun satir sagdaki simgenin altina giriyor ve son harf
    # kayboluyordu ("cevrimdisi calisi").
    marka_boy = 116
    duz = yazitipi("georgiab.ttf", marka_boy)
    kucuk = yazitipi("georgiaz.ttf", int(marka_boy * 0.62))
    marka_en = (genislik(c, "L", duz) + genislik(c, "a", kucuk)
                + genislik(c, "T", duz) + genislik(c, "e", kucuk)
                + genislik(c, "X", duz) - int(marka_boy * 0.055) * 5
                + 26 + genislik(c, "Editor", duz))

    alt_tf = yazitipi("seguisb.ttf", 42)
    kunye_tf = yazitipi("seguisb.ttf", 30)
    alt_en = genislik(c, ALT, alt_tf)
    kunye_en = genislik(c, KUNYE, kunye_tf)

    en_genis = max(marka_en, alt_en, kunye_en)
    if en_genis > EN - 2 * 80:
        raise SystemExit(
            "metin karta sigmiyor: %d px, kullanilabilir %d px. "
            "Satirlari kisalt ya da punto dusur." % (en_genis, EN - 160))

    # DIKEY KONUM. Once 214 idi ve icerik gozle gorulur asagi kaymisti
    # (olculdu: ustte 222, altta 113 px). Optik merkez icin ustteki bosluk
    # alttakinden BIRAZ AZ olmali; asagidaki _dikey_denge bunu denetliyor.
    ust = 152
    son = latex_marka(c, (EN - marka_en) // 2, ust, marka_boy)
    c.text((son + 26, ust), "Editor", font=duz, fill=METIN)

    c.text(((EN - alt_en) // 2, ust + 168), ALT, font=alt_tf, fill=SOLUK)

    ay = ust + 246
    c.line(((EN - 220) // 2, ay, (EN + 220) // 2, ay), fill=CIZGI, width=3)

    c.text(((EN - kunye_en) // 2, ay + 28), KUNYE, font=kunye_tf, fill=VURGU)

    _dikey_denge(im)

    os.makedirs(os.path.dirname(CIKTI), exist_ok=True)
    im.save(CIKTI, "PNG", optimize=True)
    kb = os.path.getsize(CIKTI) / 1024.0
    print("yazildi: docs/assets/github-social.png  %dx%d  %.0f KB"
          % (EN, BOY, kb))
    if kb > 1024:
        raise SystemExit("GitHub siniri 1 MB, kart daha buyuk")
    return CIKTI


if __name__ == "__main__":
    uret()

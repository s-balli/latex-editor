# -*- coding: utf-8 -*-
"""docs/index.html'den docs/tr/index.html uret.

NEDEN VAR: tanitim sayfasi tek dosyada iki dilli. Turkce metin HTML'de var
ama `<span class="tr">` icinde ve CSS ile gizli. Arama motoru acisindan bu
Turkce sayfa demek DEGIL:

  - statik HTML `<html lang="en">` diyor, sayfa Ingilizce sayiliyor
  - `<title>` ve `<meta description>` yalniz Ingilizce
  - `display:none` metni Google indeksliyor ama degersizlestiriyor
  - tek URL'de iki dil oldugu icin hreflang verilemiyor

Sonuc: "latex editoru", "turkce latex" gibi aramalarda sayfa hic cikmiyor.

COZUM: `/tr/` altinda GERCEKTEN Turkce bir statik sayfa. Bu betik onu
`docs/index.html`den turetiyor, boylece tek kaynak kaliyor ve iki kopya
birbirinden ayrisamiyor. `tests/test_tr_sayfasi.py` uretimi tekrarlayip
diskteki dosyayla karsilastiriyor; unutulursa test dusuyor.

KOK SAYFA DEGISMIYOR: bugunku JS dil dugmesi oldugu gibi calisiyor, yalniz
hreflang baglantilari eklendi. `/tr/` sayfasinda ise `.en` span'leri hic
olmadigi icin JS dugmesi anlamsiz; orada dugme koke giden bir baglantiya
donusuyor. Asimetrik ama her sayfa kendi basina dogru; kok sayfayi da
uretilen dosyaya cevirmek duzenlenen dosya ile yayinlanani ayirirdi.

Kullanim:
    python scripts/tr_sayfasi_uret.py           # uret ve yaz
    python scripts/tr_sayfasi_uret.py --dogrula # yalniz karsilastir (CI)
"""
from __future__ import annotations

import io
import os
import re
import sys

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KAYNAK = os.path.join(KOK, "docs", "index.html")
HEDEF = os.path.join(KOK, "docs", "tr", "index.html")

TABAN = "https://s-balli.github.io/latex-editor/"

TR_BASLIK = "LaTeX Editor: canlı PDF önizlemeli masaüstü LaTeX editörü"
TR_ACIKLAMA = (
    "Açık kaynak masaüstü LaTeX editörü (GPL-3.0): canlı PDF önizleme, "
    "SyncTeX, lualatex/pdflatex/xelatex, 7 tema, Türkçe/İngilizce arayüz. "
    "IEEE/ASYU şablonlarındaki Türkçe karakter sorunlarını ve Overleaf'ten "
    "aktarılan projeleri düzeltir. Windows + Linux.")
TR_OG_ACIKLAMA = (
    "Canlı PDF önizleme, SyncTeX, üç motor, 7 tema, Türkçe ve İngilizce "
    "arayüz. Windows ve Linux için ücretsiz ve açık kaynak (GPL-3.0).")
TR_GORSEL_ALT = ("LaTeX Editor ana penceresi: solda kaynak, sağda canlı "
                 "PDF önizleme")

# `alt` ve `aria-label` metinleri span icinde DEGIL, oyleyse span silme
# onlara dokunmuyor; tek tek cevriliyor. Ekran okuyucu ve gorsel yuklenmezse
# gorunen metin bunlar, ayrica arama motoru gorsel aramasinda kullaniyor.
# Rozet etiketleri (License, Version, CI) BILEREK YOK: onlar shields.io
# gorsellerinin kendi yazisi, cevirmek yaniltir.
OZNITELIK_CEVIRI = {
    "LaTeX Editor main window: editor with syntax highlighting and live "
    "PDF preview":
        "LaTeX Editor ana penceresi: sözdizimi renklendirmeli editör ve "
        "canlı PDF önizleme",
    "SyncTeX demo": "SyncTeX gösterimi",
    "Searching every file in the project folder and jumping to a result":
        "Proje klasöründeki bütün dosyalarda arama ve sonuca gitme",
    "Bibliography tab with filtering, and adding a source by DOI":
        "Kaynakça sekmesi: süzme ve DOI ile kaynak ekleme",
    "Typing a sentence, saving, and the PDF preview refreshing on its own":
        "Bir cümle yazıp kaydetmek, PDF önizlemenin kendiliğinden "
        "yenilenmesi",
}

# `/tr/` bir alt dizinde, koke gore yollar bir seviye yukari kaymali.
GORELI_YOL = re.compile(r'(href|src)="(?!https?://|#|/|\.\./)([^"]+)"')


# hreflang bloku KAYNAKTA (docs/index.html) duruyor ve buraya oldugu gibi
# kopyalaniyor: Google KARSILIKLI bildirim istiyor, iki sayfada da ayni blok
# olmali. Yalniz ustundeki aciklama kok sayfayi anlatiyor, burada degisiyor.
TR_HREFLANG_NOTU = """  <!-- Ingilizce surum kokte: /. Bu sayfa ondan
       uretiliyor (scripts/tr_sayfasi_uret.py), ELLE DUZENLENMIYOR.
       hreflang bloku iki sayfada da AYNI: Google karsilikli bildirim
       istiyor, tek yonlu hreflang'i yok sayiyor. -->
"""


_MASKE = "\x00YORUM%d\x00"
_YORUM = re.compile(r"<!--.*?-->", re.S)


def _yorumlari_maskele(s: str):
    """HTML yorumlarini yer tutucuyla degistir, listeyi de dondur."""
    bulunanlar = []

    def yakala(m):
        bulunanlar.append(m.group(0))
        return _MASKE % (len(bulunanlar) - 1)

    return _YORUM.sub(yakala, s), bulunanlar


def _yorumlari_geri_koy(s: str, yorumlar: list) -> str:
    for i, y in enumerate(yorumlar):
        s = s.replace(_MASKE % i, y)
    return s


# Uretilen sayfada MUTLAKA bulunmasi gerekenler. Bir donusum kaynaktaki
# bir kalibi bulamazsa ya da fazla metin yutarsa burada patliyor; sessizce
# bozuk sayfa yayina cikmiyor.
_ZORUNLU = [
    "<title>", '<meta name="description"', '<link rel="canonical"',
    '<meta property="og:url"', '<meta property="og:title"',
    'hreflang="tr"', 'hreflang="x-default"', "application/ld+json",
    '<link rel="stylesheet" href="../styles.css"',
    '<script src="../script.js">', "</html>",
]


def _denetle(s: str) -> None:
    eksik = [z for z in _ZORUNLU if z not in s]
    if eksik:
        raise SystemExit("URETILEN SAYFADA EKSIK: %s" % ", ".join(eksik))
    # `class="en"` YORUM ICINDE mesru olarak geciyor (kaynaktaki `<title>`
    # aciklamasi mekanizmayi anlatiyor); yalniz gercek isaretlemeye bak.
    govde, _ = _yorumlari_maskele(s)
    if 'class="en"' in govde:
        raise SystemExit("URETILEN SAYFADA hala Ingilizce span var")
    if "lang=\"en\" data-lang" in s:
        raise SystemExit("URETILEN SAYFA hala lang=\"en\" diyor")


def uret(kaynak_metin: str) -> str:
    s = kaynak_metin

    # 1. Dil bildirimi
    s = s.replace('<html lang="en" data-lang="en">',
                  '<html lang="tr" data-lang="tr">')

    # 2. Ingilizce span'leri TAMAMEN cikar. `.tr` span'leri duruyor:
    #    zararsizlar ve CSS `data-lang="tr"` ile onlari gosteriyor.
    #
    # YORUMLAR ONCE MASKELENIYOR. Kaynaktaki `<title>` yorumu ORNEK OLARAK
    # `<span class="en">` metnini iceriyor; maskesiz desen o ornekten
    # baslayip belgedeki ILK `</span>`e kadar her seyi yutuyordu:
    # `<title>`, meta etiketleri, JSON-LD ve nav'in yarisi gidiyordu.
    # (Uretilen sayfa aciklikla bozuktu, asagidaki denetim de bunu yakalar.)
    s, yorumlar = _yorumlari_maskele(s)
    s = re.sub(r'<span class="en">.*?</span>', "", s, flags=re.S)
    s = _yorumlari_geri_koy(s, yorumlar)

    # 3. Sahiplik dogrulamalari yalniz ana sayfada dursun, kopyalanmasin.
    #    Arama motorlari dogrulamayi mulkun ANA sayfasinda ariyor; alt
    #    sayfaya kopyalamak hicbir ise yaramiyor, yalniz kafa karistiriyor.
    s = re.sub(r'\s*<!-- Arama motoru sahiplik dogrulamalari.*?-->\s*\n',
               "\n", s, flags=re.S)
    s = re.sub(r'\s*<meta name="(?:google-site|yandex)-verification"[^>]*/>',
               "", s)

    # 4. Baslik ve aciklama
    s = re.sub(r"<title>[^<]*</title>", "<title>%s</title>" % TR_BASLIK, s)
    s = re.sub(r'<meta name="description" content="[^"]*" />',
               '<meta name="description" content="%s" />' % TR_ACIKLAMA, s)

    # 5. Kanonik ve Open Graph
    s = s.replace('<link rel="canonical" href="%s" />' % TABAN,
                  '<link rel="canonical" href="%str/" />' % TABAN)
    s = s.replace('<meta property="og:url" content="%s" />' % TABAN,
                  '<meta property="og:url" content="%str/" />' % TABAN)
    s = re.sub(r'<meta property="og:title" content="[^"]*" />',
               '<meta property="og:title" content="%s" />' % TR_BASLIK, s)
    s = re.sub(r'<meta property="og:description" content="[^"]*" />',
               '<meta property="og:description" content="%s" />'
               % TR_OG_ACIKLAMA, s)
    s = re.sub(r'<meta property="og:image:alt" content="[^"]*" />',
               '<meta property="og:image:alt" content="%s" />'
               % TR_GORSEL_ALT, s)
    s = s.replace('<meta property="og:locale" content="en_US" />',
                  '<meta property="og:locale" content="tr_TR" />')
    s = s.replace('<meta property="og:locale:alternate" content="tr_TR" />',
                  '<meta property="og:locale:alternate" content="en_US" />')
    s = re.sub(r'<meta name="twitter:title" content="[^"]*" />',
               '<meta name="twitter:title" content="%s" />' % TR_BASLIK, s)
    s = re.sub(r'<meta name="twitter:description" content="[^"]*" />',
               '<meta name="twitter:description" content="%s" />'
               % TR_OG_ACIKLAMA, s)

    # 6. JSON-LD: url, aciklama ve dil
    s = s.replace('"url": "%s",' % TABAN, '"url": "%str/",' % TABAN)
    s = re.sub(r'"description": "Desktop LaTeX editor[^"]*",',
               '"description": "%s",' % TR_OG_ACIKLAMA, s)
    s = s.replace('"inLanguage": ["en", "tr"],', '"inLanguage": "tr",')

    # 7. Dil baglantisi TERS YONE: kaynakta "TR -> tr/", burada "EN -> ../".
    #    Ustundeki aciklama kok sayfayi anlatiyor, o da cikariliyor.
    #    YOL DUZELTMESINDEN ONCE: sonra yapilirsa `href="tr/"` coktan
    #    `href="../tr/"` olmus oluyor ve esleme kaciyor.
    #    aria-label her sayfada O SAYFANIN dilinde: kokte Ingilizce
    #    ("Switch to Turkish"), burada Turkce.
    s = re.sub(r" *<!-- Dil degistirme ARTIK BAGLANTI.*?-->\n", "", s,
               flags=re.S)
    eski_baglanti = ('<a class="lang-toggle" href="tr/" hreflang="tr"'
                     ' aria-label="Switch to Turkish">TR</a>')
    if eski_baglanti not in s:
        raise SystemExit(
            "dil baglantisi kaynakta bulunamadi, degismis olabilir")
    s = s.replace(eski_baglanti,
                  '<a class="lang-toggle" href="../" hreflang="en"'
                  ' aria-label="İngilizce sürüme geç">EN</a>')

    # 8. Goreli yollar bir seviye yukari (styles.css, script.js, assets/...).
    #    `../` ile baslayanlar desende zaten haric, yukaridaki baglanti
    #    ikinci kez kaydirilmiyor.
    s = GORELI_YOL.sub(lambda m: '%s="../%s"' % (m.group(1), m.group(2)), s)

    # 9. hreflang bloku KAYNAKTAN GELIYOR, burada tekrar EKLENMIYOR: iki
    #    sayfada ayni olmasi gerekiyor ve kaynakta zaten var. (Once burada
    #    da ekleniyordu, uretilen sayfada blok iki kez cikti.) Yalniz blogun
    #    ustundeki aciklama kok sayfayi anlatiyor, /tr/ icin degistiriliyor.
    s = re.sub(r"  <!-- Turkce surum AYRI URL'de.*?-->\n", TR_HREFLANG_NOTU,
               s, flags=re.S)

    # 10. Uretilmis dosya oldugunu soyle
    s = s.replace(
        "<head>",
        "<head>\n"
        "  <!-- BU DOSYA URETILMISTIR, ELLE DUZENLEMEYIN.\n"
        "       Kaynak: docs/index.html\n"
        "       Ureten: scripts/tr_sayfasi_uret.py\n"
        "       Kapi:   tests/test_tr_sayfasi.py -->", 1)

    # 11. Span disinda kalan oznitelik metinleri
    for en, tr in OZNITELIK_CEVIRI.items():
        if en not in s:
            raise SystemExit(
                "OZNITELIK_CEVIRI kaynakla uyusmuyor, bulunamadi: %r\n"
                "docs/index.html'de metin degismis olabilir." % en[:60])
        s = s.replace('"%s"' % en, '"%s"' % tr)

    # Span'ler cikinca kalan bos satirlari topla
    s = re.sub(r"\n[ \t]*\n[ \t]*\n+", "\n\n", s)
    _denetle(s)
    return s


def main(argv):
    kaynak = io.open(KAYNAK, encoding="utf-8").read()
    beklenen = uret(kaynak)

    if "--dogrula" in argv:
        if not os.path.exists(HEDEF):
            print("docs/tr/index.html YOK. Uretmek icin:")
            print("    python scripts/tr_sayfasi_uret.py")
            return 1
        varolan = io.open(HEDEF, encoding="utf-8").read()
        if varolan != beklenen:
            print("docs/tr/index.html GUNCEL DEGIL (docs/index.html degismis).")
            print("Yeniden uretmek icin:")
            print("    python scripts/tr_sayfasi_uret.py")
            return 1
        print("docs/tr/index.html guncel.")
        return 0

    os.makedirs(os.path.dirname(HEDEF), exist_ok=True)
    io.open(HEDEF, "w", encoding="utf-8", newline="\n").write(beklenen)
    print("yazildi: docs/tr/index.html (%d bayt)" % len(beklenen.encode()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

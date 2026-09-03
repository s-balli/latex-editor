# -*- coding: utf-8 -*-
"""docs/tr/index.html kapisi: kaynakla ayrisamasin, SEO alanlari bozulmasin.

Turkce sayfa `docs/index.html`den `scripts/tr_sayfasi_uret.py` ile
uretiliyor. Kaynak degisip uretim unutulursa iki sayfa sessizce ayrisir;
buradaki ilk test bunu yakaliyor.

Geri kalan testler uretecin ONCEDEN YAPTIGI hatalari koruyor; hepsi
tarayicida denenerek bulundu, tek tek yazili.
"""

import io
import os
import re
import sys

import pytest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))

import tr_sayfasi_uret as uretec                            # noqa: E402

KAYNAK = os.path.join(KOK, "docs", "index.html")
HEDEF = os.path.join(KOK, "docs", "tr", "index.html")


def _oku(yol):
    return io.open(yol, encoding="utf-8").read()


@pytest.fixture(scope="module")
def tr():
    return _oku(HEDEF)


def _yorumsuz(s):
    """HTML yorumlarini at. Kaynaktaki `<title>` yorumu ORNEK OLARAK
    `<span class="en">` metni iceriyor; yorumlari saymazsak testler o
    ornege takilir."""
    return re.sub(r"<!--.*?-->", " ", s, flags=re.S)


def test_uretilen_sayfa_GUNCEL():
    """Kaynak degistiyse /tr/ yeniden uretilmis olmali.

    Bu kapi olmadan iki dosya sessizce ayrisir: kok sayfaya eklenen bir
    bolum Turkce sayfada hic gorunmez ve kimse fark etmez.

    Duserse:  python scripts/tr_sayfasi_uret.py
    """
    assert _oku(HEDEF) == uretec.uret(_oku(KAYNAK)), (
        "docs/tr/index.html guncel degil. "
        "Uret: python scripts/tr_sayfasi_uret.py")


def test_ingilizce_span_KALMAMIS(tr):
    """Sayfanin varlik sebebi: statik HTML gercekten Turkce olsun."""
    assert 'class="en"' not in _yorumsuz(tr)
    assert "A lightweight LaTeX editor" not in _yorumsuz(tr)
    assert "Canlı PDF önizlemeli hafif bir LaTeX editörü" in tr


def test_dil_bildirimi_TURKCE(tr):
    """`lang` ve `data-lang` ikisi de tr olmali.

    `data-lang` CSS'in hangi span'leri gosterecegini belirliyor; `en`
    kalirsa CSS BUTUN Turkce span'leri gizler ve sayfa bombos acilir.
    """
    assert '<html lang="tr" data-lang="tr">' in tr


def test_baslik_ve_aciklama_TURKCE(tr):
    """`<title>` ve `<meta description>` arama sonucunda gorunen metin.

    Uretecin ilk surumu bunlari BOZUYORDU: `<span class="en">` silme
    deseni, kaynaktaki `<title>` yorumunun ICINDEKI ornek metne takilip
    oradan ilk `</span>`e kadar her seyi yutuyordu; `<title>`, meta
    etiketleri ve JSON-LD tamamen gidiyordu.
    """
    assert ("<title>LaTeX Editor: canlı PDF önizlemeli masaüstü LaTeX "
            "editörü</title>") in tr
    m = re.search(r'<meta name="description" content="([^"]*)"', tr)
    assert m and "Açık kaynak masaüstü LaTeX editörü" in m.group(1)


def test_kanonik_ve_og_TR_SAYFASINI_gosteriyor(tr):
    """Kanonik kokte kalirsa Google /tr/ sayfasini hic indekslemez."""
    assert ('<link rel="canonical" '
            'href="https://s-balli.github.io/latex-editor/tr/" />') in tr
    assert ('<meta property="og:url" '
            'content="https://s-balli.github.io/latex-editor/tr/" />') in tr
    assert '<meta property="og:locale" content="tr_TR" />' in tr


def test_hreflang_TEK_KEZ_ve_iki_sayfada_AYNI(tr):
    """Blok kaynaktan geliyor, uretec TEKRAR EKLEMEMELI.

    Once hem kaynakta hem uretecte vardi, uretilen sayfada iki kez
    cikiyordu (olculdu: 6 satir).
    """
    kaynak = _oku(KAYNAK)
    tr_satirlar = re.findall(r'<link rel="alternate" hreflang[^>]*/>', tr)
    kaynak_satirlar = re.findall(
        r'<link rel="alternate" hreflang[^>]*/>', kaynak)
    assert len(tr_satirlar) == 3, tr_satirlar
    assert tr_satirlar == kaynak_satirlar, "iki sayfada AYNI olmali"


def test_goreli_yollar_BIR_SEVIYE_yukari(tr):
    """`/tr/` alt dizinde: styles.css, script.js ve assets bir ust dizinde."""
    assert '<link rel="stylesheet" href="../styles.css" />' in tr
    assert '<script src="../script.js"></script>' in tr
    assert 'src="assets/' not in _yorumsuz(tr)
    for yol in re.findall(r'(?:href|src)="(\.\./[^"]+)"', _yorumsuz(tr)):
        tam = os.path.join(os.path.dirname(HEDEF), yol.split("?")[0])
        assert os.path.exists(tam), "kirik yol: " + yol


def test_dil_dugmesi_BAGLANTIYA_donusmus(tr):
    """`/tr/` sayfasinda `.en` span'i yok, JS dugmesinin cevirecegi metin de.

    Dugme koke giden baglanti oldu. `?lang=en` SART: kayitli tercih "tr"
    ise kullanici EN'e tikladigi hâlde yine Turkce sayfa aciliyordu.
    """
    assert 'id="lang-toggle"' not in tr
    assert 'href="../?lang=en"' in tr


def test_dogrulama_metasi_KOPYALANMAMIS(tr):
    """Search Console dogrulamasi kokte duruyor, /tr/ye tasinmiyor."""
    assert "google-site-verification" not in tr


def test_alt_metinleri_TURKCE(tr):
    """`alt` span icinde degil, uretec onlari tek tek ceviriyor.

    Gorsel yuklenmezse gorunen metin bu; ekran okuyucu da bunu okuyor.
    """
    assert 'alt="SyncTeX gösterimi"' in tr
    assert "LaTeX Editor main window" not in _yorumsuz(tr)
    # Rozet etiketleri BILEREK Ingilizce: shields.io gorselinin kendi yazisi
    assert 'alt="License"' in tr


def test_uretec_KAYNAKTAN_SAPARSA_patliyor():
    """Kaynak metni degisirse uretec sessizce atlamamali.

    `alt` cevirileri birebir metin eslesmesiyle yapiliyor; kaynaktaki
    cumle degisip esleme kacarsa Ingilizce metin sayfada KALIRDI.
    """
    bozuk = _oku(KAYNAK).replace("SyncTeX demo", "SyncTeX gosterimi demo")
    with pytest.raises(SystemExit):
        uretec.uret(bozuk)


def test_sitemap_IKI_SAYFAYI_da_iceriyor():
    s = _oku(os.path.join(KOK, "docs", "sitemap.xml"))
    assert "<loc>https://s-balli.github.io/latex-editor/</loc>" in s
    assert "<loc>https://s-balli.github.io/latex-editor/tr/</loc>" in s
    # Her url blogu kendi alternatiflerini de listelemeli
    assert s.count('hreflang="tr"') == 2
    assert s.count('hreflang="x-default"') == 2

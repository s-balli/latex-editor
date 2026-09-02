"""Kontrast taraması: aynı kusur yeni bir ekranda tekrarlarsa yakalansın.

2026-09-03'te aynı kusur sınıfı DÖRT ayrı yerde bulundu (güncelleme
diyaloğu, Hakkında, Özellikler, Ortam Denetimi) ve o gün var olan 1700
testin hiçbiri hiçbirini yakalamadı. Hepsi uygulamayı elle açıp bakarak
bulundu. Bu dosya o bakışı otomatikleştiriyor.

Dört katman:

  1. HTML bağlantıları  `<a>` gövdenin span rengini ALMIYOR; Qt kendi sabit
                        palet Link rengini kullanıyor ve koyu temalarda
                        karşıtlık 1.43'e düşüyordu.
  2. QTextBrowser       Uygulamanın stylesheet'ine takılmıyor, kendi beyaz
                        `Base` rengini koruyor. Koyu temada beyaz zemin
                        üzerine açık metin, karşıtlık 1.37 idi.
  3. Widget ağacı       Çalışan uygulamanın ÇÖZÜLMÜŞ stylesheet'leri; aynı
                        kural içinde renk+zemin veren her blok ölçülüyor.
  4. setForeground      Renk QSS ile değil `QColor` ile veriliyor, yani
                        3. katman bunları GÖRMÜYOR. Bu boşluk ölçülerek
                        bulundu: `sem_error` beş temada eşiğin altındaydı
                        ve 3. katman onu kaçırıyordu.

Eşik WCAG AA normal metin: 4.50.
"""

import os
import re

import pytest

try:
    from PyQt6.QtWidgets import QApplication, QWidget
    from gui import main_window as mw
    from gui.theme import THEMES
    _VAR = True
except ImportError:  # pragma: no cover
    _VAR = False

gui = pytest.mark.skipif(not _VAR, reason="PyQt6 / gui modülleri gerekli")

ESIK = 4.5
_KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_GUI = os.path.join(_KOK, "desktop", "gui")

# Bilinen ve GEREKÇELİ istisna. solarized_light resmi Solarized paletini
# birebir kullanıyor (#fdf6e3 base3, #eee8d5 base2, #657b83 base00) ve düşük
# karşıtlık Solarized'ın kendi tasarım tercihi. Palet içinde bir kademe
# koyuya inmek (base01) bg_primary'yi 4.99'a çıkarıyor ama düğmeleri 3.71'de
# bırakıyor; hepsini geçirmek base02'ye inmek, yani temayı Solarized olmaktan
# çıkarmak demek. Kullanıcı kararıyla olduğu gibi bırakıldı.
_ISTISNA_TEMALAR = {"solarized_light"}

_RE_BLOK = re.compile(r"([^{}]*)\{([^{}]*)\}")
_RE_BILDIRIM = re.compile(r"([a-z-]+)\s*:\s*([^;]+)")
_RE_RENK = re.compile(r"^#([0-9a-fA-F]{6})$")
_RE_RGBA = re.compile(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)")


def _bagil(c):
    def k(x):
        x /= 255.0
        return x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4
    return 0.2126 * k(c[0]) + 0.7152 * k(c[1]) + 0.0722 * k(c[2])


def _karsitlik(a, b):
    la, lb = _bagil(a), _bagil(b)
    if la < lb:
        la, lb = lb, la
    return (la + 0.05) / (lb + 0.05)


def _coz(v):
    v = str(v).strip().rstrip(";").strip()
    m = _RE_RENK.match(v)
    if m:
        h = m.group(1)
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    m = _RE_RGBA.match(v)
    if m:
        return tuple(int(m.group(i)) for i in (1, 2, 3))
    return None


def _saydam(v):
    v = str(v).strip().lower()
    if v.startswith("rgba("):
        p = v.rstrip(");").split(",")
        if len(p) >= 4:
            try:
                return float(p[3].strip()) < 250
            except ValueError:
                return True
    return v in ("transparent", "none")


def _kaynaklar():
    for kok, _d, dosyalar in os.walk(_GUI):
        for ad in dosyalar:
            if ad.endswith(".py"):
                yol = os.path.join(kok, ad)
                with open(yol, encoding="utf-8") as f:
                    yield os.path.relpath(yol, _KOK), f.read()


# ------------------------------------------------------- 1. HTML bağlantısı

def test_html_baglantilari_acik_renk_tasiyor():
    """Renk verilmezse Qt'nin koyu mavi palet rengi devreye giriyor.

    Bu kusur bir günde üç yerde bulundu; dördüncüsü eklenirse burada düşsün.
    """
    renksiz = []
    for yol, metin in _kaynaklar():
        for m in re.finditer(r"<a href=", metin):
            # Etiketin kapanışına kadar olan kısımda renk aranıyor
            son = metin.find(">", m.start())
            etiket = metin[m.start():son if son > 0 else m.start() + 200]
            if "color:" not in etiket:
                satir = metin[:m.start()].count("\n") + 1
                renksiz.append("%s:%d" % (yol, satir))

    assert not renksiz, (
        "bu bağlantılara açık renk verilmemiş, koyu temada okunmayacak: %s"
        % renksiz)


# --------------------------------------------------------- 2. QTextBrowser

def test_metin_tarayicilarina_zemin_veriliyor():
    """QTextBrowser uygulamanın stylesheet'ine takılmıyor, beyaz kalıyor."""
    zeminsiz = []
    for yol, metin in _kaynaklar():
        for m in re.finditer(r"=\s*QTextBrowser\(", metin):
            satir = metin[:m.start()].count("\n") + 1
            # Kurulumdan sonraki 20 satirda zemin veren bir setStyleSheet
            sonrasi = "\n".join(metin.split("\n")[satir - 1:satir + 19])
            if "setStyleSheet" not in sonrasi or "background" not in sonrasi:
                zeminsiz.append("%s:%d" % (yol, satir))

    assert not zeminsiz, (
        "bu QTextBrowser'lara zemin verilmemiş, koyu temada beyaz kalır: %s"
        % zeminsiz)


# ------------------------------------------------------------ 3. Widget ağacı

@pytest.fixture(scope="module")
def qapp():
    if not _VAR:
        yield None
        return
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    yield QApplication.instance() or QApplication([])


def _bulgular(pencere):
    """Aynı kural içinde renk+zemin veren, eşiği geçemeyen bloklar."""
    cikan = []
    for w in [pencere] + pencere.findChildren(QWidget):
        qss = w.styleSheet()
        if not qss or ":" not in qss:
            continue
        for secici, bildirimler in (_RE_BLOK.findall(qss) or [("", qss)]):
            d = dict((k, v.strip())
                     for k, v in _RE_BILDIRIM.findall(bildirimler))
            on = d.get("color")
            arka = d.get("background") or d.get("background-color")
            if not on or not arka or _saydam(arka):
                continue
            c_on, c_arka = _coz(on), _coz(arka)
            if c_on is None or c_arka is None:
                continue
            o = _karsitlik(c_on, c_arka)
            if o < ESIK:
                cikan.append("%s %.2f (%s / %s)"
                             % (secici.strip()[:30] or w.__class__.__name__,
                                o, on, arka))
    return cikan


@gui
def test_widget_agacinda_karsitlik(qapp):
    """Çalışan uygulamanın çözülmüş stylesheet'leri, yedi temada.

    Tek pencere kurulup tema değiştiriliyor: yedi ayrı pencere kurmakla
    aynı sonucu verdiği ölçüldü (2026-09-03), maliyeti yarısı.
    """
    pencere = mw.MainWindow()
    try:
        pencere.show()
        qapp.processEvents()
        kotu = {}
        for ad in THEMES:
            if ad in _ISTISNA_TEMALAR:
                continue
            pencere._theme_mgr.apply(ad)
            qapp.processEvents()
            bulgu = _bulgular(pencere)
            if bulgu:
                kotu[ad] = sorted(set(bulgu))
    finally:
        pencere.close()

    assert not kotu, "eşiğin altında kalan birleşimler: %s" % kotu


@gui
def test_tarama_GERCEKTEN_bir_sey_goruyor(qapp):
    """Tarama boş dönerse test anlamsızlaşır; gördüğünü de denetle.

    Eşik geçici olarak imkânsız bir değere çekilince bulgu ÇIKMALI. Yoksa
    'hiç bulgu yok' sonucu koddan değil taramanın kendisinden geliyordur.
    """
    global ESIK
    pencere = mw.MainWindow()
    try:
        pencere.show()
        qapp.processEvents()
        eski = ESIK
        try:
            ESIK = 99.0
            bulgu = _bulgular(pencere)
        finally:
            ESIK = eski
    finally:
        pencere.close()

    assert len(bulgu) > 10, (
        "tarama neredeyse hiçbir kural görmüyor (%d), muhtemelen "
        "stylesheet'leri okuyamıyor" % len(bulgu))


# ------------------------------------------------------- 4. setForeground

# `fg_dim` BILEREK disarida: dosya agacinda duzenlenemez dosyalari soluk
# gostermek icin kullaniliyor ve esigi gecirmek icin gereken deger fg_muted
# ile birebir ayni cikiyor, yani "duzenlenebilir / duzenlenemez" ayrimi
# tamamen kayboluyor (olculdu 2026-09-03). Kullanici karariyla kaliyor.
_ISTISNA_RENKLER = {"fg_dim"}

# Hangi dosyadaki `setForeground` hangi zemine çiziyor. Varsayım değil,
# çalışan uygulamadan ölçüldü (2026-09-03, widget'ların çözülmüş
# stylesheet'leri okunarak):
#
#   QTreeWidget / _DragTree   #1d2021 -> bg_secondary
#   QListWidget / QTableWidget #282828 -> bg_primary
#
# İlk halinde her rengi HER İKİ zemine karşı denetliyordum ve `fg_muted`
# `bg_primary` üzerinde dört temada düşük çıkıyordu; oysa `fg_muted` yalnız
# ağaçlarda kullanılıyor, listelerde değil. Yani bulgu gerçek değil, testin
# fazla geniş olmasındandı.
_DOSYA_ZEMINI = {
    "file_tree.py": "bg_secondary",
    "outline.py": "bg_secondary",
    "output_panel.py": "bg_primary",
}


def _setforeground_renkleri():
    """(tema anahtarı, zemin anahtarı) çiftleri, kaynaktan çıkarılıyor.

    Kaynaktan çıkarılıyor ki yeni bir renk bu yolla kullanılmaya başlarsa
    listeye elle eklemek gerekmesin.
    """
    ciftler = set()
    for yol, metin in _kaynaklar():
        zemin = _DOSYA_ZEMINI.get(os.path.basename(yol))
        if zemin is None:
            continue
        for m in re.finditer(r"set(?:Foreground|TextColor)\s*\([^)]*", metin):
            for k in re.findall(r"[\"']([a-z_]+)[\"']\s*\]", m.group(0)):
                ciftler.add((k, zemin))
    return ciftler


def test_setforeground_renkleri_kaynaktan_bulunuyor():
    """Katman 4 boş çalışırsa sessizce anlamsızlaşır."""
    bulunan = _setforeground_renkleri()
    zeminler = {z for _k, z in bulunan}

    assert len(bulunan) >= 4, (
        "setForeground ile verilen renk bulunamadı (%s); desen değişmiş "
        "olabilir ve bu katman artık hiçbir şey denetlemiyordur" % bulunan)
    assert zeminler == set(_DOSYA_ZEMINI.values()), (
        "beklenen zeminlerin hepsi taranmıyor: %s" % zeminler)


def test_setforeground_renkleri_okunabilir():
    """QSS taraması bunları görmüyor; `sem_error` tam buradan kaçmıştı."""
    dusuk = []
    for anahtar, zemin in sorted(_setforeground_renkleri()):
        if anahtar in _ISTISNA_RENKLER:
            continue
        for ad, t in THEMES.items():
            if ad in _ISTISNA_TEMALAR or anahtar not in t:
                continue
            on, arka = _coz(t[anahtar]), _coz(t.get(zemin))
            if on is None or arka is None:
                continue
            o = _karsitlik(on, arka)
            if o < ESIK:
                dusuk.append("%s/%s/%s %.2f" % (ad, anahtar, zemin, o))

    assert not dusuk, "okunmayan birleşimler: %s" % dusuk


def test_sem_renkleri_birbirinden_ayirt_edilebilir():
    """Karşıtlık düzeltmesi durum renklerini aynı tona getirmemeli.

    Klasör / derlenebilir / ipucu ayrımı dosya ağacında yalnızca renkten
    okunuyor; hepsi aynı griye çıkarsa karşıtlık kazanılır ama bilgi kaybolur.
    """
    cakisan = []
    for ad, t in THEMES.items():
        ayirt = ["sem_folder", "sem_compilable", "sem_hint"]
        renkler = [(k, _coz(t[k])) for k in ayirt if k in t]
        for i, (ka, ca) in enumerate(renkler):
            for kb, cb in renkler[i + 1:]:
                if sum(abs(x - y) for x, y in zip(ca, cb)) < 40:
                    cakisan.append("%s: %s ~ %s" % (ad, ka, kb))

    assert not cakisan, "durum renkleri ayırt edilemiyor: %s" % cakisan

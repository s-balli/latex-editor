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
  3. Stylesheet'ler     `build_stylesheet()` çıktısı ve kaynaktaki
                        `setStyleSheet` gövdeleri, QSS basamaklanması
                        modellenerek.
  4. setForeground      Renk QSS ile değil `QColor` ile veriliyor, yani
                        3. katman bunları GÖRMÜYOR. Bu boşluk ölçülerek
                        bulundu: `sem_error` beş temada eşiğin altındaydı
                        ve 3. katman onu kaçırıyordu.

Eşik WCAG AA normal metin: 4.50.

3. katman NEDEN widget kurmuyor: ilk halinde `MainWindow` kurup widget
ağacını geziyordu. Bu depoda başka hiçbir test MainWindow kurmuyor ve
sebebi CI'da görüldü: pencere `close()` ile yok olmuyor, sonra çöp toplama
sırasında başka bir testin içinde SIGABRT veriyor (exit 134, 3.12 ve
Windows işleri düştü, 3.10 geçti). Yerine `build_stylesheet()` saf
fonksiyonu ve kaynaktaki `setStyleSheet` gövdeleri okunuyor: hem çökme
riski yok hem de KAPSAM DAHA GENİŞ, çünkü widget ağacı taraması PDF
görüntüleyicinin kurallarını hiç görmüyordu (orada `fg_muted` altı temada
eşiğin altındaydı).
"""

import os
import re

import pytest

try:
    from gui.stylesheet import build_stylesheet
    from gui.theme import THEMES
    _VAR = True
except ImportError:  # pragma: no cover
    _VAR = False

gui = pytest.mark.skipif(not _VAR, reason="gui modülleri gerekli")

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

_RE_BLOK = re.compile(r"([^{}]*?)\{([^{}]*)\}")
_RE_BILDIRIM = re.compile(r"([a-z-]+)\s*:\s*([^;]+)")
_RE_RENK = re.compile(r"^#([0-9a-fA-F]{6})$")
_RE_RGBA = re.compile(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)")
# {t['x']}, {_t['x']}, {self._theme['x']}, {self._theme.get('x', '#fff')}
_RE_YER = re.compile(r"\{[A-Za-z_.]*(?:\[|\.get\()\s*[\"'](\w+)[\"'][^}]*\}")


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
    return v in ("transparent", "none", "")


def _kaynaklar():
    for kok, _d, dosyalar in os.walk(_GUI):
        for ad in dosyalar:
            if ad.endswith(".py"):
                yol = os.path.join(kok, ad)
                with open(yol, encoding="utf-8") as f:
                    yield os.path.relpath(yol, _KOK).replace("\\", "/"), f.read()


def _temalar():
    for ad, t in THEMES.items():
        if ad not in _ISTISNA_TEMALAR:
            yield ad, t


# ------------------------------------------------------- 1. HTML bağlantısı

def test_html_baglantilari_acik_renk_tasiyor():
    """Renk verilmezse Qt'nin koyu mavi palet rengi devreye giriyor.

    Bu kusur bir günde üç yerde bulundu; dördüncüsü eklenirse burada düşsün.
    """
    renksiz = []
    for yol, metin in _kaynaklar():
        for m in re.finditer(r"<a href=", metin):
            son = metin.find(">", m.start())
            etiket = metin[m.start():son if son > 0 else m.start() + 200]
            if "color:" not in etiket:
                renksiz.append("%s:%d" % (yol, metin[:m.start()].count("\n") + 1))

    assert not renksiz, (
        "bu bağlantılara açık renk verilmemiş, koyu temada okunmayacak: %s"
        % renksiz)


def test_html_baglantisi_taramasi_bos_degil():
    """Katman 1 hiç bağlantı bulamazsa sessizce anlamsızlaşır."""
    sayi = sum(metin.count("<a href=") for _y, metin in _kaynaklar())

    assert sayi >= 3, "kaynakta <a href bulunamadı (%d)" % sayi


# --------------------------------------------------------- 2. QTextBrowser

def test_metin_tarayicilarina_zemin_veriliyor():
    """QTextBrowser uygulamanın stylesheet'ine takılmıyor, beyaz kalıyor."""
    zeminsiz = []
    for yol, metin in _kaynaklar():
        for m in re.finditer(r"=\s*QTextBrowser\(", metin):
            satir = metin[:m.start()].count("\n") + 1
            sonrasi = "\n".join(metin.split("\n")[satir - 1:satir + 19])
            if "setStyleSheet" not in sonrasi or "background" not in sonrasi:
                zeminsiz.append("%s:%d" % (yol, satir))

    assert not zeminsiz, (
        "bu QTextBrowser'lara zemin verilmemiş, koyu temada beyaz kalır: %s"
        % zeminsiz)


# --------------------------------------------------------- 3. Stylesheet'ler

def _govde(metin, bas):
    """`setStyleSheet(` çağrısının parantez gövdesi."""
    i = metin.index("(", bas)
    derinlik, j = 0, i
    while j < len(metin):
        if metin[j] == "(":
            derinlik += 1
        elif metin[j] == ")":
            derinlik -= 1
            if derinlik == 0:
                return metin[i:j + 1]
        j += 1
    return metin[i:i + 400]


def _qss_uret(govde, tema):
    """Yer tutucuları tema değeriyle doldurup gerçek bir QSS üret.

    Yer tutucular TEK süslü parantezli, QSS ayraçları f-string içinde ÇİFT.
    Önce yer tutucular değiştiriliyor, SONRA çift ayraçlar teke indiriliyor;
    ters sırada yer tutucular bozulur.
    """
    qss = _RE_YER.sub(lambda m: str(tema.get(m.group(1), "#000000")), govde)
    return qss.replace("{{", "{").replace("}}", "}")


def _bulgular(qss, kaynak):
    """Basamaklanmayı modelleyerek eşiği geçemeyen etkin renk/zemin çiftleri.

    QSS'te `QPushButton { color: X }` ile `QPushButton:hover { background: Y }`
    ayrı kurallardır ama hover ANINDA ikisi birlikte görünür: metin taban
    kuraldan, zemin durum kuralından gelir. Bu modellenmezse gerçek kusur
    kaçar; modellenmeden "aynı çağrıda tek renk tek zemin" diye eşleştirmek
    de uydurma çiftler üretir (ikisini de yaşadım).
    """
    bloklar = [(s.split('"')[-1].strip(),
                dict((k, v.strip()) for k, v in _RE_BILDIRIM.findall(b)))
               for s, b in _RE_BLOK.findall(qss)]
    taban = {s: d for s, d in bloklar if ":" not in s}
    cikan = []
    for sec, d in bloklar:
        ust = taban.get(sec.split(":")[0].strip(), {})
        on = d.get("color") or ust.get("color")
        arka = (d.get("background") or d.get("background-color")
                or ust.get("background") or ust.get("background-color"))
        if not on or not arka or _saydam(arka):
            continue
        c_on, c_arka = _coz(on), _coz(arka)
        if c_on is None or c_arka is None:
            continue
        o = _karsitlik(c_on, c_arka)
        if o < ESIK:
            cikan.append("%s %s %.2f (%s / %s)" % (kaynak, sec, o, on, arka))
    return cikan


@gui
def test_global_stylesheet_karsitligi():
    """`build_stylesheet()` saf fonksiyon: widget kurmaya gerek yok."""
    kotu = []
    for ad, t in _temalar():
        kotu += ["%s %s" % (ad, x)
                 for x in _bulgular(build_stylesheet(t), "global")]

    assert not kotu, "eşiğin altında kalan kurallar: %s" % sorted(set(kotu))


@gui
def test_widget_stylesheetleri_karsitligi():
    """Kaynaktaki her `setStyleSheet` gövdesi, yedi temaya doldurularak."""
    kotu = []
    for yol, metin in _kaynaklar():
        kisa = yol.replace("desktop/gui/", "")
        for m in re.finditer(r"setStyleSheet\s*\(", metin):
            govde = _govde(metin, m.start())
            if "{" not in govde:
                continue
            yer = "%s:%d" % (kisa, metin[:m.start()].count("\n") + 1)
            for ad, t in _temalar():
                kotu += ["%s %s" % (ad, x)
                         for x in _bulgular(_qss_uret(govde, t), yer)]

    assert not kotu, "eşiğin altında kalan kurallar: %s" % sorted(set(kotu))


@gui
def test_stylesheet_taramasi_GERCEKTEN_kural_goruyor():
    """Ayrıştırıcı bozulursa tarama sessizce hiçbir şey görmez.

    Bu tarama yazılırken tam bu oldu: f-string'in çift süslü parantezi ve
    seçicideki Python sözdizimi yüzünden seçiciler boş çıkıyor, basamaklanma
    eşleşmiyor ve bulgu sayısı sıfıra düşüyordu. Kod düzgün görünüyordu.
    """
    tema = THEMES["dark"]
    kurallar = 0
    for _sec, bil in _RE_BLOK.findall(build_stylesheet(tema)):
        d = dict((k, v.strip()) for k, v in _RE_BILDIRIM.findall(bil))
        if d.get("color") and (d.get("background") or d.get("background-color")):
            kurallar += 1
    assert kurallar >= 10, (
        "global stylesheet'te renk+zemin veren kural sayısı %d, "
        "ayrıştırıcı bozuk olabilir" % kurallar)

    # Widget gövdelerinde de seçiciler DOLU çözülmeli
    seciciler = set()
    for _yol, metin in _kaynaklar():
        for m in re.finditer(r"setStyleSheet\s*\(", metin):
            govde = _govde(metin, m.start())
            if "{" not in govde:
                continue
            for s, _b in _RE_BLOK.findall(_qss_uret(govde, tema)):
                ad = s.split('"')[-1].strip()
                if ad:
                    seciciler.add(ad)
    assert any(":" in s for s in seciciler), (
        "hiçbir durum seçicisi (:hover gibi) çözülemedi; basamaklanma "
        "denetimi çalışmıyor demektir. Çözülenler: %s"
        % sorted(seciciler)[:10])


# ------------------------------------------------------- 4. setForeground

# `fg_dim` BILEREK dışarıda: dosya ağacında düzenlenemez dosyaları soluk
# göstermek için kullanılıyor ve eşiği geçirmek için gereken değer fg_muted
# ile birebir aynı çıkıyor, yani "düzenlenebilir / düzenlenemez" ayrımı
# tamamen kayboluyor (ölçüldü 2026-09-03). Kullanıcı kararıyla kalıyor.
_ISTISNA_RENKLER = {"fg_dim"}

# Hangi dosyadaki `setForeground` hangi zemine çiziyor. Varsayım değil,
# çalışan uygulamadan ölçüldü (2026-09-03, widget'ların çözülmüş
# stylesheet'leri okunarak):
#
#   QTreeWidget / _DragTree    #1d2021 -> bg_secondary
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
    """(tema anahtarı, zemin anahtarı) çiftleri, kaynaktan çıkarılıyor."""
    ciftler = set()
    for yol, metin in _kaynaklar():
        zemin = _DOSYA_ZEMINI.get(os.path.basename(yol))
        if zemin is None:
            continue
        for m in re.finditer(r"set(?:Foreground|TextColor)\s*\([^)]*", metin):
            for k in re.findall(r"[\"']([a-z_]+)[\"']\s*\]", m.group(0)):
                ciftler.add((k, zemin))
    return ciftler


@gui
def test_setforeground_renkleri_kaynaktan_bulunuyor():
    """Katman 4 boş çalışırsa sessizce anlamsızlaşır."""
    bulunan = _setforeground_renkleri()
    zeminler = {z for _k, z in bulunan}

    assert len(bulunan) >= 4, (
        "setForeground ile verilen renk bulunamadı (%s); desen değişmiş "
        "olabilir ve bu katman artık hiçbir şey denetlemiyordur" % bulunan)
    assert zeminler == set(_DOSYA_ZEMINI.values()), (
        "beklenen zeminlerin hepsi taranmıyor: %s" % zeminler)


@gui
def test_setforeground_renkleri_okunabilir():
    """QSS taraması bunları görmüyor; `sem_error` tam buradan kaçmıştı."""
    dusuk = []
    for anahtar, zemin in sorted(_setforeground_renkleri()):
        if anahtar in _ISTISNA_RENKLER:
            continue
        for ad, t in _temalar():
            if anahtar not in t:
                continue
            on, arka = _coz(t[anahtar]), _coz(t.get(zemin))
            if on is None or arka is None:
                continue
            o = _karsitlik(on, arka)
            if o < ESIK:
                dusuk.append("%s/%s/%s %.2f" % (ad, anahtar, zemin, o))

    assert not dusuk, "okunmayan birleşimler: %s" % dusuk


@gui
def test_sem_renkleri_birbirinden_ayirt_edilebilir():
    """Karşıtlık düzeltmesi durum renklerini aynı tona getirmemeli.

    Klasör / derlenebilir / ipucu ayrımı dosya ağacında yalnızca renkten
    okunuyor; hepsi aynı griye çıkarsa karşıtlık kazanılır ama bilgi kaybolur.
    """
    cakisan = []
    for ad, t in THEMES.items():
        renkler = [(k, _coz(t[k])) for k in
                   ("sem_folder", "sem_compilable", "sem_hint") if k in t]
        for i, (ka, ca) in enumerate(renkler):
            for kb, cb in renkler[i + 1:]:
                if sum(abs(x - y) for x, y in zip(ca, cb)) < 40:
                    cakisan.append("%s: %s ~ %s" % (ad, ka, kb))

    assert not cakisan, "durum renkleri ayırt edilemiyor: %s" % cakisan


@gui
def test_verbatim_rengi_YORUMDAN_ve_duz_metinden_ayirt_edilebilir():
    """Verbatim blogu ekranda yorum gibi gorunmemeli.

    VERBATIM'in tema anahtari YOKTU, `fg_muted`i odunc aliyordu; o her temada
    "sonuk gri" oldugu icin yorum rengiyle ayni sinifa dusuyordu. Olculdu
    2026-09-06 (kullanici bildirdi): gruvbox'ta fark 3, monokai 63, dracula
    64. Lexer dogru stilliyordu (VERBATIM=8), kusur RENKTEYDI.

    Butun syn_* ciftleri KARSILASTIRILMIYOR: temalarda bilerek esitlenmis
    ciftler var (light: syn_env_arg == syn_math_cmd, dracula: syn_bracket ==
    syn_env_arg). Verbatim yalnizca karisabildigi ikisiyle olculuyor.
    """
    cakisan = []
    for ad, t in THEMES.items():
        v = _coz(t["syn_verbatim"])
        for k in ("syn_comment", "syn_default"):
            c = _coz(t[k])
            fark = sum(abs(x - y) for x, y in zip(v, c))
            if fark < 40:
                cakisan.append("%s: syn_verbatim ~ %s (fark %d)" % (ad, k, fark))

    assert not cakisan, "verbatim ayirt edilemiyor: %s" % cakisan


@gui
def test_her_temada_syn_verbatim_ANAHTARI_var():
    """Kapi bos kosmasin: anahtar dusunce yukaridaki test KeyError verir,
    ama nedeni acik olsun diye ayrica siniyor."""
    eksik = [ad for ad, t in THEMES.items() if "syn_verbatim" not in t]
    assert not eksik, "syn_verbatim eksik: %s" % eksik

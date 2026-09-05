r"""İç bağlantı GERÇEKTEN hedefe götürüyor mu (döndürülmüş sayfa dahil).

NEDEN AYRI DOSYA. pdflatex + pdflscape + hyperref gerekiyor ve CI'da TeX Live
yalnız `derle` işinde kurulu. Matrix (`test`) işine konsaydı `skipif` yüzünden
HER ZAMAN atlanır, kapı sessizce ölü kalırdı; iş akışı bu tuzağı
`test_derle_sh`, `test_synctex_live`, `test_tablo_derleme` ve
`test_ipucu_derleme` için zaten belgeliyor.

NE SINANIYOR. `tests/test_pdf_rotate.py` dönüşümü sentetik sayfayla, tablo
düzeyinde sabitliyor. Buradaki testler asıl soruyu soruyor: kullanıcı
içindekiler bağlantısına bastığında belge doğru yere kayıyor mu.

YER GERÇEKLİĞİ RENDER'DAN OKUNUYOR, koddan değil. Hedefin hemen ardına kalın
siyah bir çizgi konuyor; sayfa pdfium ile render edilip o çizginin piksel
satırı bulunuyor. Beklenen değer bu; `resolve_dest_scroll_y` onun yakınında
kalmalı. Böylece test dönüşüm formülünün kendisini değil, GÖRÜNEN sonucu
denetliyor.

ÖLÇÜLEN KUSUR (2026-09-05): `resolve_dest_scroll_y`, GÖRSEL yüksekliği alıp
`/Rotate 0` formülünü uyguluyordu. Destination koordinatları ise
DÖNDÜRÜLMEMİŞ kullanıcı uzayında.

    /Rotate 0    olması gereken 339 px, çıkan  329 px  ->  10 px
    /Rotate 90   olması gereken 483 px, çıkan -5381 px -> 5864 px

Yatay sayfa LaTeX'te istisna değil: geniş tablo ve şekiller için `pdflscape`
tam da bunu yapıyor.
"""

import ctypes
import os
import shutil
import subprocess

import pytest

pdflatex = shutil.which("pdflatex")
pytestmark = pytest.mark.skipif(not pdflatex, reason="pdflatex gerekli")

pdfium = pytest.importorskip("pypdfium2")

from gui.pdf_donusum import geometri                                 # noqa: E402
from gui.pdf_links import (get_dest_page_index, get_link_at_point,   # noqa: E402
                           resolve_dest_scroll_y, resolve_link_action)
from gui.pdfium_lock import pdfium_lock                              # noqa: E402

OLCEK = 1.5

# Kabul ölçütü: kullanıcı bağlantıya bastığında hedef görünüm alanında
# olmalı. Yarım ekran ~400 px; 100 px cömert ama net bir sınır.
ESIK = 100

_BELGE = r"""\documentclass{article}
\usepackage{pdflscape}
\usepackage[colorlinks]{hyperref}
\begin{document}
\hyperlink{hedef0}{Duz sayfadaki hedefe git}

\vspace{1cm}
\hyperlink{hedef90}{Yatay sayfadaki hedefe git}
\newpage
\vspace*{3cm}
\hypertarget{hedef0}{}\noindent\rule{\linewidth}{8pt}
\newpage
\begin{landscape}
\vspace*{6cm}
\hypertarget{hedef90}{}\noindent\rule{\linewidth}{8pt}
\end{landscape}
\newpage
Son sayfa: kaydirma cubugu sonuna dayanmasin diye.
\end{document}
"""


def _cizgi_satiri(pil):
    """Render'da kalın siyah çizginin piksel satırı (ortanca)."""
    g = pil.convert("L")
    en, boy = g.size
    px = g.load()
    koyu = [y for y in range(boy)
            if sum(1 for x in range(0, en, 2) if px[x, y] < 128) / (en / 2) > 0.5]
    return koyu[len(koyu) // 2] if koyu else None


@pytest.fixture(scope="module")
def pdf_yolu(tmp_path_factory):
    """pdflscape ile /Rotate 90 sayfa taşıyan, iç bağlantılı belge."""
    d = str(tmp_path_factory.mktemp("baglanti"))
    tex = os.path.join(d, "a.tex")
    with open(tex, "w", encoding="utf-8") as f:
        f.write(_BELGE)
    for _ in range(2):                       # hyperref hedefleri için iki geçiş
        subprocess.run(["pdflatex", "-interaction=nonstopmode",
                        "-output-directory", d, tex],
                       capture_output=True, timeout=180)
    yol = os.path.join(d, "a.pdf")
    if not os.path.isfile(yol):
        pytest.skip("pdflscape/hyperref yok, belge derlenemedi")
    return yol


@pytest.fixture(scope="module")
def belge(pdf_yolu):
    """(PdfDocument, {hedef_sayfa: dest}).

    Bağlantılar uygulamanın GERÇEK yolundan bulunuyor: ilk sayfa
    döndürülmemiş kullanıcı uzayında taranıyor (`_events._link_at_pos` ne
    yapıyorsa aynısı), sonra aksiyon çözülüp hedef sayfa alınıyor.
    """
    with pdfium_lock:
        pdf = pdfium.PdfDocument(pdf_yolu)
        s0 = pdf[0]
        g0 = geometri(s0)
        hedefler = {}
        for uy in range(int(g0[2]) - 1, 0, -2):
            for ux in range(60, int(g0[1]) - 60, 15):
                lnk = get_link_at_point(s0.raw, float(ux), float(uy))
                if not lnk:
                    continue
                cz = resolve_link_action(pdf.raw, lnk)
                if cz and cz[0] in ("goto", "dest"):
                    hi = get_dest_page_index(pdf.raw, cz[1])
                    if hi >= 0 and hi not in hedefler:
                        hedefler[hi] = cz[1]
    # Kilit yield'in DIŞINDA bırakılıyor: modül kapsamlı fixture, içeride
    # tutulsa bütün modül boyunca elde kalırdı.
    yield pdf, hedefler
    with pdfium_lock:
        pdf.close()


class TestOnkosullar:
    """Kapı boşalmasın: belgenin gerçekten aradığımız şekli taşıdığını sına."""

    def test_belgede_dondurulmus_sayfa_var(self, belge):
        pdf, _h = belge
        donmeler = [geometri(pdf[i])[0] for i in range(len(pdf))]
        assert 90 in donmeler, \
            "pdflscape /Rotate 90 üretmedi, test hiçbir şey ölçmüyor: %s" % donmeler
        assert 0 in donmeler, "karşılaştırma için düz sayfa da gerek: %s" % donmeler

    def test_iki_ic_baglanti_da_cozuldu(self, belge):
        _pdf, hedefler = belge
        assert len(hedefler) >= 2, \
            "iç bağlantılar bulunamadı, hedef: %s" % sorted(hedefler)


class TestBaglantiDogruYereGoturuyor:

    def test_her_hedef_render_edilen_isaretin_yakininda(self, belge):
        pdf, hedefler = belge
        rapor = []
        for idx in sorted(hedefler):
            with pdfium_lock:
                sayfa = pdf[idx]
                g = geometri(sayfa)
                cikan = resolve_dest_scroll_y(pdf.raw, hedefler[idx], g, OLCEK)
                beklenen = _cizgi_satiri(sayfa.render(scale=OLCEK).to_pil())
            assert beklenen is not None, \
                "sayfa %d render'ında işaret çizgisi bulunamadı" % idx
            rapor.append((idx, g[0], beklenen, cikan, abs(cikan - beklenen)))

        kotu = [r for r in rapor if r[4] > ESIK]
        assert not kotu, "hedeften uzağa gidiliyor (sayfa, /Rotate, beklenen, " \
            "çıkan, fark): %s" % rapor

    def test_dondurulmus_sayfa_sayfanin_ICINDE_kaliyor(self, belge):
        """Kusurun en görünür yüzü: değer NEGATİF çıkıyordu (-5381 px)."""
        pdf, hedefler = belge
        for idx in sorted(hedefler):
            with pdfium_lock:
                sayfa = pdf[idx]
                g = geometri(sayfa)
                cikan = resolve_dest_scroll_y(pdf.raw, hedefler[idx], g, OLCEK)
                yukseklik = int(sayfa.get_height() * OLCEK)
            assert 0 <= cikan <= yukseklik, \
                "sayfa %d (/Rotate %d): scroll %d px, sayfa 0..%d px" % (
                    idx, g[0], cikan, yukseklik)

    def test_eski_hesap_bu_belgede_GERCEKTEN_dusuyor(self, belge):
        """Karşı yön: eski formül aynı belgede eşiği aşmalı.

        Aşmıyorsa belge kusuru göstermiyor demektir ve yukarıdaki testler
        boşa geçiyordur.
        """
        pdf, hedefler = belge
        with pdfium_lock:
            yatay = [i for i in sorted(hedefler) if geometri(pdf[i])[0] == 90]
        assert yatay, "yatay hedef yok"
        idx = yatay[0]

        # Eski kod: GÖRSEL yükseklik + /Rotate 0 formülü.
        from pypdfium2 import raw as praw
        n = ctypes.c_ulong()
        p = (ctypes.c_float * 4)()
        with pdfium_lock:
            sayfa = pdf[idx]
            beklenen = _cizgi_satiri(sayfa.render(scale=OLCEK).to_pil())
            praw.FPDFDest_GetView(hedefler[idx], ctypes.byref(n), p)
            eski = int((sayfa.get_height() - p[1]) * OLCEK)

        assert abs(eski - beklenen) > ESIK, \
            "eski hesap da doğru çıkıyor (%d vs %d): belge kusuru göstermiyor" \
            % (eski, beklenen)


# ---------------------------------------------------------------------------
# Çağrı yerinin kendisi: PdfViewer._goto_dest
#
# Yukarıdaki testler `resolve_dest_scroll_y`yi DOĞRUDAN çağırıyor, yani
# `_events._goto_dest`in ona ne verdiğini sınamıyorlar. MUTASYONLA ÖLÇÜLDÜ:
# çağrı yerini eski haline (GÖRSEL yükseklik) döndürmek hiçbir testi
# düşürmüyordu, yani kapı tam oradan boştu. Aşağıdaki test zinciri uçtan uca
# yürütüyor: gerçek PdfViewer, gerçek belge, gerçek kaydırma çubuğu.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def qapp():
    QApplication = pytest.importorskip("PyQt6.QtWidgets").QApplication
    app = QApplication.instance() or QApplication([])
    return app


class TestGotoDestUctanUca:

    def test_hedef_gorunum_alaninin_icine_geliyor(self, qapp, belge, pdf_yolu):
        from PyQt6.QtCore import QPoint
        from gui.pdf_viewer import PdfViewer
        from gui.theme import THEMES

        _pdf, hedefler = belge
        v = PdfViewer(theme=THEMES["dark"])
        try:
            v.resize(900, 700)
            v.show()
            qapp.processEvents()
            assert v.load_pdf(pdf_yolu)
            qapp.processEvents()
            # Offscreen'de sayfa kabı kendiliğinden boyutlanmıyor; bu çağrı
            # olmadan kaydırma aralığı 0 kalır ve test sessizce boşa geçer
            # (bkz. test_mikro_kalintilar._yerlesimi_zorla).
            v._pages_widget.adjustSize()
            qapp.processEvents()
            assert v._scroll.verticalScrollBar().maximum() > 0, \
                "kaydırma aralığı yok, test hiçbir şey ölçmüyor"

            rapor = []
            for idx in sorted(hedefler):
                v._goto_dest(hedefler[idx])
                qapp.processEvents()

                olcek = v._olcek(idx)
                label = v._page_labels[idx]
                # KİLİT ŞART. Render işçisi kendi belgesini render ederken ana
                # thread'in pdfium'a girmesi yığını bozuyor (B5'in aynısı, bu
                # kez test kodunda). ÖLÇÜLDÜ (2026-09-05): deseni yoğunlaştıran
                # stres betiğinde kilitsiz 16/25, kilitli 0/25 çökme; bu testin
                # kendisi tek başına 3/100 çöküyordu.
                with pdfium_lock:
                    isaret = _cizgi_satiri(
                        v._pdf[idx].render(scale=olcek).to_pil())
                    donme = geometri(v._pdf[idx])[0]
                assert isaret is not None, "sayfa %d işareti bulunamadı" % idx
                hedef_mutlak = label.mapTo(v._pages_widget,
                                           QPoint(0, 0)).y() + isaret

                cubuk = v._scroll.verticalScrollBar()
                kaydirma = cubuk.value()
                # ÖNKOŞUL: çubuk sonuna dayanmışsa hedef istenen yere değil
                # kalabildiği yere gelir; o durumda ölçüt anlamsızlaşır.
                # Belgenin sonundaki fazladan sayfa bunun için var.
                assert kaydirma < cubuk.maximum(), \
                    "kaydırma sonuna dayandı, sayfa %d ölçülemiyor" % idx
                rapor.append((idx, donme, hedef_mutlak - kaydirma))

            # `_goto_dest` hedefi görünüm alanının ÜSTÜNE koyuyor
            # (setValue(abs_y - 20)). Ölçüldü: işaret çapa noktasının biraz
            # altında kaldığı için fark 27-29 px çıkıyor.
            #
            # ÖLÇÜT GEVŞEK OLAMAZ: yalnızca "viewport içinde mi" diye
            # baksaydı sayfanın BAŞINA kayan bir kusur bile geçerdi.
            # Mutasyonla ölçüldü (çağrı yerine yine GÖRSEL yükseklik
            # verilmesi): yatay sayfada değer 0'a düşüyor ve işaret 353 px
            # aşağıda kalıyor, yani 651 px'lik görünüm alanının hâlâ içinde.
            kotu = [r for r in rapor if not 0 <= r[2] <= 150]
            assert not kotu, ("hedef görünüm alanının üstüne gelmedi "
                              "(sayfa, /Rotate, işaret - kaydırma): %s" % rapor)
        finally:
            v.shutdown()
            v.deleteLater()
            qapp.processEvents()

"""Backlog'daki "mikro kalıntılar" listesinin testleri (2026-08-31).

Sekiz maddenin her biri ayrı sınıfta. Hepsi düzeltme geri alınarak sınandı;
madde başına en az bir test düşüyor.

Ölçümle üretilen iki not:
- mapFrom bastırıcısı ÖLÜ koddu: Qt6'nın metni "QWidget::mapTo(): ..." ve
  içinde "mapFrom" geçmiyor; ayrıca 181 sayfalık PDF'te 10 senaryo boyunca
  uyarının kendisi hiç çıkmadı.
- _render_visible'ın ikili arama sürümü, doğrusal taramayla 1440 scroll
  konumunda (tek/çift sayfa × 3 zoom) BİREBİR aynı sonucu verdi.
"""

import io
import os
import subprocess
import time
from types import SimpleNamespace

import pytest

try:
    from PyQt6.QtWidgets import QApplication, QMessageBox, QWidget
    from PyQt6.QtCore import QPoint
    from gui.theme import THEMES
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / gui modülleri gerekli", allow_module_level=True)

_KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _spin(app, kosul, timeout_ms=8000):
    t0 = time.monotonic()
    while not kosul():
        app.processEvents()
        if (time.monotonic() - t0) * 1000 > timeout_ms:
            return False
    return True


def _yerlesimi_zorla(qapp, v):
    """Offscreen'de sayfa kabı kendiliğinden boyutlanmıyor — kaydırma çubuğu
    aralıksız kalıyor ve scroll KURGULARI SESSİZCE ETKİSİZ oluyor.

    Bu çağrı olmadan "240 scroll konumu" testi aslında tek konumda (0) koşar
    ve boş yere yeşil kalır. Dönen değer kaydırma aralığı; testler onun
    sıfırdan büyük olduğunu ayrıca doğruluyor.
    """
    v._pages_widget.adjustSize()
    qapp.processEvents()
    return v._scroll.verticalScrollBar().maximum()


def _pdf_yaz(yol, boyutlar):
    """Verilen (genişlik, yükseklik) listesinden gerçek bir PDF üret."""
    pypdfium2 = pytest.importorskip("pypdfium2")
    d = pypdfium2.PdfDocument.new()
    for w, h in boyutlar:
        d.new_page(w, h)
    tampon = io.BytesIO()
    d.save(tampon)
    with open(yol, "wb") as f:
        f.write(tampon.getvalue())
    return str(yol)


@pytest.fixture
def viewer(qapp):
    pytest.importorskip("pypdfium2")
    from gui.pdf_viewer import PdfViewer
    v = PdfViewer(theme=THEMES["dark"])
    v.resize(900, 700)
    v.show()
    qapp.processEvents()
    yield v
    v.shutdown()
    v.deleteLater()
    qapp.processEvents()


# --------------------------------------------------------------------------
# 1) _fit_zoom yalnız 1. sayfanın boyutunu kullanıyordu
# --------------------------------------------------------------------------

class TestFitZoomBakilanSayfa:

    def test_yatay_sayfada_genislige_sigdir_o_sayfayi_olcer(self, qapp, viewer, tmp_path):
        """Karışık boyutlu belge: sayfa 2 yatay, sayfa 3 A3.

        Eski kod her zaman `self._pdf[0]`a bakıyordu, yani yatay sayfadayken
        "Genişliğe Sığdır" dikey A4'ün genişliğine göre hesaplıyor ve sayfa
        görüntü alanının dışına taşıyordu.
        """
        yol = _pdf_yaz(tmp_path / "karisik.pdf", [(595, 842), (842, 595), (1190, 842)])
        assert viewer.load_pdf(yol)
        qapp.processEvents()

        zoomlar = []
        for sayfa in (0, 1, 2):
            viewer._current_page = sayfa
            viewer.fit_width()
            zoomlar.append(viewer._zoom)

        # Sayfa genişledikçe zoom küçülmeli — üçü de FARKLI olmalı.
        assert zoomlar[0] > zoomlar[1] > zoomlar[2], zoomlar
        assert len(set(zoomlar)) == 3, f"sayfa boyutu zoom'u etkilemiyor: {zoomlar}"

    def test_bakilan_sayfa_gorunum_alanina_sigar(self, qapp, viewer, tmp_path):
        """Asıl ölçüt: fit_width sonrası sayfa GERÇEKTEN sığmalı."""
        yol = _pdf_yaz(tmp_path / "karisik.pdf", [(595, 842), (1190, 842)])
        assert viewer.load_pdf(yol)
        qapp.processEvents()

        viewer._current_page = 1
        viewer.fit_width()
        qapp.processEvents()
        genislik, _yukseklik = viewer._get_page_size(1)
        vp = viewer._scroll.viewport().width()
        assert genislik <= vp, f"A3 sayfa {genislik}px, görünüm alanı {vp}px — taşıyor"

    def test_aralik_disi_current_page_cokmez(self, qapp, viewer, tmp_path):
        """_current_page bayat kalabilir (belge küçüldü): kırpılmalı."""
        yol = _pdf_yaz(tmp_path / "iki.pdf", [(595, 842), (595, 842)])
        assert viewer.load_pdf(yol)
        viewer._current_page = 99
        viewer.fit_page()               # patlamamalı
        assert 0.05 <= viewer._zoom <= 3.0


# --------------------------------------------------------------------------
# 2) _render_visible scroll'da sayfa 0'dan iterasyon
# --------------------------------------------------------------------------

def _dogrusal_tarama(v):
    """_render_visible'ın ESKİ gövdesi: sayfa 0'dan başlar."""
    istek, cur = [], v._current_page
    if not v._page_labels:
        return istek, cur
    vh = v._scroll.viewport().rect().height()
    sy = v._scroll.verticalScrollBar().value()
    for i, label in enumerate(v._page_labels):
        if i >= v._page_count:
            break
        ly = label.mapTo(v._pages_widget, QPoint(0, 0)).y()
        ust = ly - sy
        alt = ust + label.height()
        if ly <= sy < ly + label.height():
            cur = i
        gorunur = alt >= -200 and ust <= vh + 200
        if ust > vh + 200:
            break
        if gorunur and (label.pixmap() is None or label.pixmap().isNull()):
            istek.append(i)
    return istek, cur


def _yeni_tarama(v):
    """Yeni gövde: başlangıç indisi ikili aramadan."""
    istek, cur = [], v._current_page
    if not v._page_labels:
        return istek, cur
    vh = v._scroll.viewport().rect().height()
    sy = v._scroll.verticalScrollBar().value()
    for i in range(v._ilk_gorunur_aday(sy), len(v._page_labels)):
        label = v._page_labels[i]
        if i >= v._page_count:
            break
        ly = label.mapTo(v._pages_widget, QPoint(0, 0)).y()
        ust = ly - sy
        alt = ust + label.height()
        if ly <= sy < ly + label.height():
            cur = i
        gorunur = alt >= -200 and ust <= vh + 200
        if ust > vh + 200:
            break
        if gorunur and (label.pixmap() is None or label.pixmap().isNull()):
            istek.append(i)
    return istek, cur


class TestRenderVisibleBaslangic:

    def test_ikili_arama_dogrusal_taramayla_ayni(self, qapp, viewer, tmp_path):
        """Eşdeğerlik kapısı: hangi sayfalar render'a girdi + _current_page.

        Çift sayfa modu kritik: bir satırdaki iki etiketin `label_y`si eşit,
        yükseklikleri farklı olabilir, yani yordam o satırda monoton DEĞİL.
        Bir indis geri gitme kuralı burada sınanıyor.
        """
        boyutlar = [(595, 842)] * 20 + [(842, 595)] * 10 + [(595, 1000)] * 10
        yol = _pdf_yaz(tmp_path / "cok.pdf", boyutlar)
        assert viewer.load_pdf(yol)
        qapp.processEvents()

        fark = 0
        toplam = 0
        konumlar = set()
        for cift in (False, True):
            viewer._toggle_dual_page(cift)
            qapp.processEvents()
            for zoom in (0.4, 1.0, 2.0):
                viewer._zoom = zoom
                viewer._update_page_sizes()
                vmax = _yerlesimi_zorla(qapp, viewer)
                assert vmax > 0, "kaydırma aralığı yok — karşılaştırma tek konumda koşardı"
                sb = viewer._scroll.verticalScrollBar()
                for k in range(40):
                    sb.setValue(int(vmax * k / 39))
                    qapp.processEvents()
                    konumlar.add((cift, zoom, sb.value()))
                    toplam += 1
                    if _dogrusal_tarama(viewer) != _yeni_tarama(viewer):
                        fark += 1
        assert toplam >= 240
        assert len(konumlar) >= 200, f"gerçekten gezilen konum {len(konumlar)} — kapı boş koşuyor"
        assert fark == 0, f"{toplam} konumun {fark} tanesinde davranış değişti"

    def test_baslangic_indisi_gorunur_pencereye_yapisik(self, qapp, viewer, tmp_path):
        """Asıl kazanç: döngü sayfa 0'dan DEĞİL, görünür pencerenin başından.

        Kapı "kaç mapTo çağrıldı" değil "nereden başlandı" ölçüyor: doğrusal
        tarama her zaman 0'dan başlar, yenisi ilk görünür sayfanın en fazla
        bir gerisinden (çift sayfa satırı için bilerek bırakılan pay).
        """
        yol = _pdf_yaz(tmp_path / "uzun.pdf", [(595, 842)] * 60)
        assert viewer.load_pdf(yol)
        vmax = _yerlesimi_zorla(qapp, viewer)
        assert vmax > 0
        sb = viewer._scroll.verticalScrollBar()

        for oran in (0.0, 0.25, 0.5, 0.75, 1.0):
            sb.setValue(int(vmax * oran))
            qapp.processEvents()
            sy = sb.value()
            gercek_ilk = _dogrusal_tarama(viewer)[0]
            bas = viewer._ilk_gorunur_aday(sy)
            assert bas >= 0
            if gercek_ilk:
                assert 0 <= gercek_ilk[0] - bas <= 1, (
                    f"oran={oran}: ilk görünür {gercek_ilk[0]}, başlangıç {bas}"
                )
        # Belgenin sonunda 0'dan başlamıyor olmalı — düzeltmenin bütün özeti.
        sb.setValue(vmax)
        qapp.processEvents()
        assert viewer._ilk_gorunur_aday(sb.value()) > 30


# --------------------------------------------------------------------------
# 3) Global Qt mesaj handler'ı tüm mapFrom uyarılarını bastırıyordu
# --------------------------------------------------------------------------

class TestQtMesajHandleri:

    def test_pdf_viewer_global_handler_kurmuyor(self):
        """İmport edilir edilmez SÜRECİN mesaj yolunu ele geçiren kod olmamalı.

        Bastırıcı iki kez işlevsizdi: (a) süzgeç "mapFrom" arıyordu ama Qt6'nın
        bu koda ait metni "QWidget::mapTo(): parent must be in parent
        hierarchy" — içinde "mapFrom" YOK; (b) uyarının kendisi de çıkmıyor
        (181 sayfalık PDF, 10 senaryo, sıfır uyarı). Bedeli ise gerçekti:
        testler dâhil tüm süreç için Qt mesajları onun üstünden geçiyordu.
        """
        yol = os.path.join(_KOK, "desktop", "gui", "pdf_viewer.py")
        with open(yol, encoding="utf-8") as f:
            kaynak = f.read()
        assert "qInstallMessageHandler" not in kaynak, (
            "pdf_viewer.py yeniden global Qt mesaj handler'ı kuruyor — "
            "mapTo uyarısı bu kodda çıkmıyor, süzgeç de yanlış dizgeye bakıyordu"
        )

    def test_qt6_metni_mapFrom_icermiyor(self, qapp):
        """Süzgecin neden ölü olduğunun kanıtı; Qt metni değişirse burası düşer."""
        from PyQt6.QtCore import qInstallMessageHandler
        mesajlar = []
        onceki = qInstallMessageHandler(lambda t, c, m: mesajlar.append(m))
        try:
            a, b = QWidget(), QWidget()
            from PyQt6.QtWidgets import QLabel
            QLabel(a).mapTo(b, QPoint(0, 0))
        finally:
            qInstallMessageHandler(onceki)
        assert mesajlar, "Qt mapTo uyarısı hiç üretmedi"
        assert any("mapTo" in m for m in mesajlar)
        assert not any("mapFrom" in m for m in mesajlar), (
            f"eski süzgeç bu metni yakalardı: {mesajlar}"
        )


# --------------------------------------------------------------------------
# 4) WSL synctex subprocess timeout 3 sn
# --------------------------------------------------------------------------

class TestSyncTexZamanAsimi:

    def test_bütçe_soguk_wsl_baslangicini_kaldiriyor(self):
        from gui import synctex
        assert synctex._ZAMAN_ASIMI >= 10, (
            "sıcak WSL'de çağrı ~85 ms; bütçe yalnız SOĞUK başlangıç içindir "
            "ve systemd+snapd ile açılan dağıtımda saniyeler sürer"
        )

    @pytest.mark.parametrize("platform", ["win32", "linux"])
    @pytest.mark.parametrize("yon", ["forward", "reverse"])
    def test_dort_cagri_da_ayni_butceyi_kullanir(self, monkeypatch, platform, yon):
        """Sabit tek yerde ama dört çağrının HEPSİ ona bakmalı."""
        from gui import synctex
        yakalanan = {}

        def sahte_run(cmd, **kw):
            yakalanan.update(kw)
            return SimpleNamespace(returncode=1, stdout="")

        monkeypatch.setattr(synctex, "_PLATFORM", platform)
        monkeypatch.setattr(synctex.subprocess, "run", sahte_run)
        if yon == "forward":
            synctex.forward_search("/x/a.tex", 3, 1, "/x/a.pdf")
        else:
            synctex.reverse_search(1, 1.0, 2.0, "/x/a.pdf")
        assert yakalanan.get("timeout") == synctex._ZAMAN_ASIMI

    def test_zaman_asiminda_sessizce_none_doner(self, monkeypatch):
        """Uzatılan bütçe aşılırsa davranış eskisi gibi: istisna sızmaz."""
        from gui import synctex

        def sahte_run(cmd, **kw):
            raise subprocess.TimeoutExpired(cmd, kw.get("timeout", 0))

        monkeypatch.setattr(synctex, "_PLATFORM", "linux")
        monkeypatch.setattr(synctex.subprocess, "run", sahte_run)
        assert synctex.forward_search("/x/a.tex", 1, 1, "/x/a.pdf") is None
        assert synctex.reverse_search(1, 1.0, 2.0, "/x/a.pdf") is None


# --------------------------------------------------------------------------
# 5) load_pdf kullanıcının arama sonuçlarını siliyordu
# --------------------------------------------------------------------------

class TestAramaGeriYukleme:

    def _makale(self):
        yol = os.path.join(_KOK, "template", "template10", "article.pdf")
        if not os.path.exists(yol):
            pytest.skip("örnek PDF yok")
        return yol

    def test_derleme_sonrasi_acik_arama_geri_gelir(self, qapp, viewer):
        """Yaz–derle–bak döngüsünde her turda Enter'a basmak gerekiyordu."""
        yol = self._makale()
        assert viewer.load_pdf(yol)
        qapp.processEvents()

        viewer._search_bar_widget.show()
        viewer._search_input.setText("the")
        viewer._on_search_return()
        assert _spin(qapp, lambda: bool(viewer._search_results)), "ilk arama sonuç vermedi"
        onceki = len(viewer._search_results)

        viewer.load_pdf(yol)            # derleme sonrası yeniden yükleme
        qapp.processEvents()
        assert _spin(qapp, lambda: bool(viewer._search_results)), (
            "yeniden yüklemeden sonra arama geri gelmedi"
        )
        assert len(viewer._search_results) == onceki
        assert "0" not in viewer._search_count_label.text().split("/")[0].strip()

    def test_geri_yukleme_KAYDIRMIYOR(self, qapp, viewer):
        """Derlemeden sonra SyncTeX imlece zıplıyor; geri yükleme onu ezmemeli."""
        yol = self._makale()
        assert viewer.load_pdf(yol)
        qapp.processEvents()
        viewer._search_bar_widget.show()
        viewer._search_input.setText("the")
        viewer._on_search_return()
        assert _spin(qapp, lambda: bool(viewer._search_results))

        viewer.load_pdf(yol)
        vmax = _yerlesimi_zorla(qapp, viewer)
        assert vmax > 0, "kaydırma aralığı yok — bu kapı boş koşardı"
        sb = viewer._scroll.verticalScrollBar()
        # SyncTeX'in imlece zıpladığı anı taklit et: kaydırma SIFIR DEĞİL.
        hedef = vmax // 2
        sb.setValue(hedef)
        qapp.processEvents()
        assert _spin(qapp, lambda: bool(viewer._search_results))
        for _ in range(30):
            qapp.processEvents()
        assert sb.value() == hedef, "geri yükleme kaydırdı — SyncTeX zıplaması ezilir"

    def test_arama_cubugu_kapaliyken_geri_yukleme_yok(self, qapp, viewer):
        yol = self._makale()
        assert viewer.load_pdf(yol)
        viewer._search_bar_widget.hide()
        viewer._search_input.setText("the")
        viewer.load_pdf(yol)
        for _ in range(40):
            qapp.processEvents()
        assert viewer._search_results == []

    def test_bos_sorgu_arama_baslatmaz(self, qapp, viewer):
        yol = self._makale()
        assert viewer.load_pdf(yol)
        viewer._search_bar_widget.show()
        viewer._search_input.setText("   ")
        viewer.load_pdf(yol)
        for _ in range(40):
            qapp.processEvents()
        assert viewer._search_results == []


# --------------------------------------------------------------------------
# 6) find_replace.py "0/0" — çevrilmemiş ve panelin diliyle uyumsuz
# --------------------------------------------------------------------------

class TestBulPaneliSayaci:

    def _panel(self, qapp, metin):
        from gui.find_replace import FindReplaceBar
        from gui.editor import EditorWidget
        ed = EditorWidget()
        ed.setText(metin)
        bar = FindReplaceBar()
        bar.set_editor(ed) if hasattr(bar, "set_editor") else setattr(bar, "_editor", ed)
        return bar, ed

    def test_bulunamayinca_panelin_kendi_dili_kullanilir(self, qapp):
        bar, ed = self._panel(qapp, "alfa beta gama\n")
        try:
            bar._find_next_in_text("zzz", forward=True, wrap=True)
            assert bar._lbl_count.text() != "0/0"
            assert bar._lbl_count.text().strip() != ""
            assert bar._match_count == 0
        finally:
            ed.deleteLater()
            bar.deleteLater()
            qapp.processEvents()

    def test_bayat_sayac_ezilmiyordu(self, qapp):
        """İleri/geri tuşunda _update_current_match ESKİ sayıyı gösterebiliyordu."""
        bar, ed = self._panel(qapp, "fig fig fig\n")
        try:
            bar._count_matches("fig")
            assert bar._match_count == 3
            ed.setText("hiç yok\n")
            bar._find_input.setText("fig")
            bar._find_next()
            assert bar._match_count == 0, "eşleşme kalmadı ama sayaç bayat"
            assert "3" not in bar._lbl_count.text()
        finally:
            ed.deleteLater()
            bar.deleteLater()
            qapp.processEvents()

    def test_kaynakta_ceviri_disi_bicim_kalmadi(self):
        yol = os.path.join(_KOK, "desktop", "gui", "find_replace.py")
        with open(yol, encoding="utf-8") as f:
            kaynak = f.read()
        assert '.setText("0/0")' not in kaynak


# --------------------------------------------------------------------------
# 7) Anahat: iki düzey iç içe küme kırpılıyordu (G3 kalıntısı)
# --------------------------------------------------------------------------

class TestAnahatIcIceKume:

    def test_baslik_oku_keyfi_derinlik(self):
        from gui.outline import _baslik_oku
        # i, açılış küme parantezinden SONRAKİ konum
        assert _baslik_oku("{abc}", 1) == "abc"
        assert _baslik_oku("{a \\emph{b} c}", 1) == "a \\emph{b} c"
        assert _baslik_oku("{a \\textbf{\\emph{b}} c}", 1) == "a \\textbf{\\emph{b}} c"
        assert _baslik_oku("{a {b {c {d}}}}", 1) == "a {b {c {d}}}"

    def test_kacisli_kume_baslikta_kalir(self):
        from gui.outline import _baslik_oku
        assert _baslik_oku("{Küme \\{a,b\\}}", 1) == "Küme \\{a,b\\}"

    def test_kapanmayan_kume_none(self):
        from gui.outline import _baslik_oku
        assert _baslik_oku("{yarım kalmış", 1) is None

    def test_panel_iki_duzeyi_kirpmiyor(self, qapp):
        from gui.outline import OutlinePanel
        p = OutlinePanel(theme=THEMES["dark"])
        try:
            p.update_outline(
                "\\section{A \\textbf{\\emph{B}} C}\n"
                "\\subsection{Küme \\{x\\} ve \\texttt{\\bfseries kod}}\n"
            )
            metinler = [it.text(0) for it in p._items]
            assert metinler == [
                "A \\textbf{\\emph{B}} C",
                "Küme \\{x\\} ve \\texttt{\\bfseries kod}",
            ], metinler
        finally:
            p.deleteLater()
            qapp.processEvents()

    def test_g3_ve_onceki_davranislar_korunuyor(self, qapp):
        """Kısa başlık argümanı, yorum atlama, satır numarası — hepsi aynı."""
        from gui.outline import OutlinePanel
        p = OutlinePanel(theme=THEMES["dark"])
        try:
            p.update_outline(
                "önsöz\n"
                "\\chapter[Kısa]{Uzun Başlık}\n"
                "% \\section{Yorumdaki}\n"
                "\\section{Yöntem ve \\emph{Materyal}}\n"
            )
            from PyQt6.QtCore import Qt
            veriler = [(it.text(0), it.data(0, Qt.ItemDataRole.UserRole)) for it in p._items]
            assert veriler == [("Ch: Uzun Başlık", 1), ("Yöntem ve \\emph{Materyal}", 3)], veriler
        finally:
            p.deleteLater()
            qapp.processEvents()

    def test_kapanmayan_bolum_anahati_bozmuyor(self, qapp):
        from gui.outline import OutlinePanel
        p = OutlinePanel(theme=THEMES["dark"])
        try:
            p.update_outline("\\section{yarım\n\\section{Tam}\n")
            # İlk \section'ın kümesi hiç kapanmıyor, ikincisini de yutuyor:
            # anahat boş kalır ama ÇÖKMEZ.
            assert isinstance(p._items, list)
        finally:
            p.deleteLater()
            qapp.processEvents()


# --------------------------------------------------------------------------
# 8) _prompt_reload "Diskten Yükle"de open_file dönüşünü yok sayıyordu
# --------------------------------------------------------------------------

class _WatchStub:
    """file_watch'ın _prompt_reload'u için gereken en küçük ana pencere."""

    def __init__(self):
        self._save_hashes = {}
        self._reload_prompt_active = False
        self.engine_cagrildi = 0

    def _detect_engine(self, path):
        self.engine_cagrildi += 1

    def _file_hash(self, path):
        return "DISK"


class TestPromptReloadOkumaHatasi:

    def _kur(self, monkeypatch, acilir: bool, secim: str):
        from gui.mixins.file_watch import FileWatchMixin

        class _Dlg:
            def __init__(self, *a, **k):
                self._btns = {}

            def setWindowTitle(self, *a): pass
            def setText(self, *a): pass
            def setIcon(self, *a): pass
            def setDefaultButton(self, *a): pass
            def exec(self): return 0

            def addButton(self, text, role):
                nesne = object()
                self._btns[role] = nesne
                if role == QMessageBox.ButtonRole.AcceptRole:
                    self.kabul = nesne
                else:
                    self.ret = nesne
                return nesne

            def clickedButton(self):
                return self.kabul if secim == "yukle" else self.ret

        monkeypatch.setattr("gui.mixins.file_watch.QMessageBox", _Sahte(_Dlg))

        # `lines`/`text`/`ensureLineVisible`: yeniden yükleme imleci geçerli
        # aralığa kelepçeliyor (diskteki sürüm daha kısa olabilir) ve bunun
        # için belgeyi ölçüyor. Taklit gerçek EditorWidget'ın taşıdığı bu üçünü
        # taşımıyordu; bu testin kendi konusu hash, ama taklit eksik kalınca
        # AttributeError ile düşüyordu.
        editor = SimpleNamespace(
            isModified=lambda: False,
            getCursorPosition=lambda: (4, 2),
            setCursorPosition=lambda l, c: None,
            open_file=lambda p: acilir,
            lines=lambda: 10,
            text=lambda ln: "bir satir\n",
            ensureLineVisible=lambda ln: None,
        )
        stub = _WatchStub()
        stub._save_hashes["/x/a.tex"] = "ESKI"
        return FileWatchMixin._prompt_reload, stub, editor

    def test_okuma_basarisizsa_hash_KORUNUR(self, monkeypatch):
        """Aksi hâlde izleyici o disk durumunu 'soruldu' sayıp bir daha sormuyordu."""
        fn, stub, editor = self._kur(monkeypatch, acilir=False, secim="yukle")
        fn(stub, editor, "/x/a.tex", "YENI")
        assert stub._save_hashes["/x/a.tex"] == "ESKI"
        assert stub.engine_cagrildi == 0

    def test_okuma_basariliysa_hash_GUNCELLENIR(self, monkeypatch):
        fn, stub, editor = self._kur(monkeypatch, acilir=True, secim="yukle")
        fn(stub, editor, "/x/a.tex", "YENI")
        assert stub._save_hashes["/x/a.tex"] == "YENI"
        assert stub.engine_cagrildi == 1

    def test_kendiminkini_koru_yolu_degismedi(self, monkeypatch):
        fn, stub, editor = self._kur(monkeypatch, acilir=True, secim="koru")
        fn(stub, editor, "/x/a.tex", "YENI")
        assert stub._save_hashes["/x/a.tex"] == "DISK"


class _Sahte:
    """QMessageBox yerine geçen, sınıf gibi çağrılabilen sarmalayıcı."""

    def __init__(self, dlg_cls):
        self._dlg = dlg_cls
        self.ButtonRole = QMessageBox.ButtonRole
        self.Icon = QMessageBox.Icon

    def __call__(self, *a, **k):
        return self._dlg()


# --------------------------------------------------------------------------
# 9) _fit_zoom yer imi panelinin genişliğini İKİ KEZ düşüyordu
#
# Panel `_scroll`in KARDEŞİ (_ui_setup.py: body = QHBoxLayout, önce ağaç
# sonra scroll), yani düzen onu zaten düşmüş oluyor ve `viewport().width()`
# kalan genişliği veriyor. Eskiden bir kez daha çıkarılıyordu.
#
# ÖLÇÜLDÜ (2026-09-05, 900x700 pencere, 220 px panel): panel açıkken sayfa
# 664 px'lik alanda 423 px kalıyordu, yani %64. Panel kapalıyken %98.
# Yer imi paneli tam da uzun belgelerde (tez, kitap) açılıyor, sığdırmanın
# en çok gerektiği yerde.
# --------------------------------------------------------------------------

class TestFitZoomYerImiPaneli:
    PANEL = 220

    @staticmethod
    def _hazirla(qapp, viewer, tmp_path):
        yol = _pdf_yaz(tmp_path / "uzun.pdf", [(595, 842)] * 3)
        assert viewer.load_pdf(yol)
        qapp.processEvents()
        viewer._bookmark_tree.setFixedWidth(TestFitZoomYerImiPaneli.PANEL)
        return viewer

    @staticmethod
    def _sigdir(qapp, viewer, panel_acik, mod="width"):
        """Paneli aç/kapat, sığdır, (viewport_genişlik, sayfa_genişlik) ver."""
        viewer._bookmark_tree.setVisible(panel_acik)
        qapp.processEvents()
        viewer._pages_widget.adjustSize()
        qapp.processEvents()
        vp = viewer._scroll.viewport().width()
        viewer._current_page = 0
        (viewer.fit_width if mod == "width" else viewer.fit_page)()
        qapp.processEvents()
        genislik, yukseklik = viewer._get_page_size(0)
        return vp, genislik, yukseklik

    def test_panel_scrollun_KARDESI(self, qapp, viewer, tmp_path):
        """Düzeltmenin dayandığı olgu: panel viewport'un İÇİNDE değil.

        İçinde olsaydı çıkarma doğru olurdu. Yerleşim değişirse bu test
        düşer ve düzeltmenin gerekçesi gözden geçirilir.
        """
        self._hazirla(qapp, viewer, tmp_path)
        assert viewer._bookmark_tree.parent() is viewer._scroll.parent()
        assert not viewer._scroll.isAncestorOf(viewer._bookmark_tree)

    def test_panel_acikken_de_gorunum_alani_doluyor(self, qapp, viewer, tmp_path):
        v = self._hazirla(qapp, viewer, tmp_path)
        vp_kapali, gen_kapali, _y = self._sigdir(qapp, v, False)
        vp_acik, gen_acik, _y2 = self._sigdir(qapp, v, True)

        # önkoşul: panel gerçekten yer kaplamalı, yoksa test hiçbir şey ölçmez
        assert vp_acik < vp_kapali - 100, \
            "panel görünüm alanını daraltmadı: %d -> %d" % (vp_kapali, vp_acik)

        assert gen_kapali / vp_kapali > 0.90, (vp_kapali, gen_kapali)
        assert gen_acik / vp_acik > 0.90, \
            "panel açıkken %d px alanda sayfa %d px (%%%.0f), sağda %d px boş" % (
                vp_acik, gen_acik, 100.0 * gen_acik / vp_acik, vp_acik - gen_acik)

    def test_panel_genisligi_ikinci_kez_dusulmuyor(self, qapp, viewer, tmp_path):
        """Kusurun imzası: hata payı tam olarak panelin genişliği kadardı."""
        v = self._hazirla(qapp, viewer, tmp_path)
        _vp, gen_acik, _y = self._sigdir(qapp, v, True)
        _vp2, gen_kapali, _y2 = self._sigdir(qapp, v, False)
        fark = gen_kapali - gen_acik
        # Beklenen fark ~panel genişliği; iki kez düşülseydi ~iki katı olurdu.
        assert fark < self.PANEL * 1.5, \
            "sayfa panel genişliğinden fazla küçüldü: %d px (panel %d px)" % (
                fark, self.PANEL)

    def test_panel_acik_kapali_gidip_gelmek_kalici_iz_birakmiyor(
            self, qapp, viewer, tmp_path):
        v = self._hazirla(qapp, viewer, tmp_path)
        ilk = self._sigdir(qapp, v, False)
        self._sigdir(qapp, v, True)
        son = self._sigdir(qapp, v, False)
        assert ilk == son, (ilk, son)

    def test_sayfaya_sigdir_iki_boyutta_da_siniyor(self, qapp, viewer, tmp_path):
        """`fit_page`'te sınırlayan boyut yükseklik olabilir; ikisi de sığmalı."""
        v = self._hazirla(qapp, viewer, tmp_path)
        for acik in (False, True):
            vp_w, gen, yuk = self._sigdir(qapp, v, acik, mod="page")
            vp_h = v._scroll.viewport().height()
            assert gen <= vp_w and yuk <= vp_h, (acik, vp_w, vp_h, gen, yuk)
            # en az bir boyut alanı doldurmalı, yoksa gereksiz küçültme var
            assert max(gen / vp_w, yuk / vp_h) > 0.90, (acik, vp_w, vp_h, gen, yuk)

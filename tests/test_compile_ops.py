"""CompileOpsMixin — derleme meşgul guard testleri.

Regression: sürmekte olan derleme varken Ctrl+S/Ctrl+B, compile() çağrısından
ÖNCE yazılan durumları (hedef yolu, panel temizliği, imleç bağlamı) eski
derlemenin sonucunu zehirliyordu; compile() False döner ama atamalar çoktan
yapılmış olurdu. Guard bunları atamalardan önce kesmeli.
"""

from types import SimpleNamespace

import pytest

try:
    from PyQt6.QtWidgets import QApplication
    from gui.editor import EditorWidget
    from gui.mixins.compile_ops import CompileOpsMixin
    from gui.mixins.tab_ops import TabOpsMixin
    from tests.stub_main import StubMain
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / gui modülleri gerekli", allow_module_level=True)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class _FakeCompiler:
    def __init__(self, busy):
        self._busy = busy
        self.calls = []
        self.se = []
        self.stopped = 0

    def is_busy(self):
        return self._busy

    def stop(self):
        self.stopped += 1

    def compile(self, path, engine, shell_escape=None):
        self.calls.append((path, engine))
        self.se.append(shell_escape)
        return True


class _Stub(CompileOpsMixin, TabOpsMixin, StubMain):
    def __init__(self, editors, busy=False, root=""):
        StubMain.__init__(self, editors=editors, root=root)
        self._compiler = _FakeCompiler(busy)


def _tex(tmp_path):
    p = tmp_path / "ana.tex"
    p.write_text("\\begin{document}\nmerhaba\n\\end{document}\n", encoding="utf-8")
    return str(p)


def _dirty_editor(tex):
    ed = EditorWidget()
    assert ed.open_file(tex)
    return ed


def test_compile_busy_iken_durum_dokunulmaz(qapp, tmp_path, monkeypatch):
    tex = _tex(tmp_path)
    ed = _dirty_editor(tex)
    stub = _Stub([ed], busy=True)
    stub._compile_target = "eski/hedef.tex"
    stub._compile_cursor_ctx = ("eski.tex", 3, 1)
    cleared = []
    monkeypatch.setattr(stub._output_panel, "clear", lambda: cleared.append(1))

    stub._compile()

    assert stub._compiler.calls == []                  # yeni derleme başlamadı
    assert stub._compile_target == "eski/hedef.tex"    # bayat hedef ezilmedi
    assert stub._compile_cursor_ctx == ("eski.tex", 3, 1)
    assert cleared == []                               # süren derlemenin çıktısı duruyor
    assert "sürüyor" in stub._status.msg


def test_compile_bos_iken_normal_akis(qapp, tmp_path):
    tex = _tex(tmp_path)
    ed = _dirty_editor(tex)
    stub = _Stub([ed], busy=False)

    stub._compile()

    assert stub._compiler.calls == [(tex, "lualatex")]
    # minted yok: bayrak hiç gönderilmiyor, kullanıcıya da sorulmuyor
    assert stub._compiler.se == [None]
    assert stub._compile_target == tex
    assert stub._compile_cursor_ctx is not None
    assert "sürüyor" not in stub._status.msg


def test_compile_file_busy_iken_derlemez(qapp, tmp_path):
    tex = _tex(tmp_path)
    stub = _Stub([], busy=True)
    stub._compile_target = "eski/hedef.tex"

    stub._compile_file(tex)

    assert stub._compiler.calls == []
    assert stub._compile_target == "eski/hedef.tex"
    assert "sürüyor" in stub._status.msg


# =====================================================================
# Derleme DİSKTEN okuyor: açık kirli sekmeler önce kaydedilmeli
#
# Eskiden yalnız CARİ editör ve HEDEF kaydediliyordu. ÖLÇÜLDÜ (2026-09-07),
# `\input{bolum1}` bildiren projede: bolum1.tex düzenlenip ana.tex sekmesine
# geçiliyor ve derleniyor; derleme anında diskte bolum1.tex'in ESKİ hâli
# duruyor. PDF ile editörde görülen metin ayrışıyor, hata satırları var
# olmayan içeriğe işaret ediyor ve hiçbir uyarı çıkmıyor.
#
# Kapsam proje ile sınırlı: başka klasördeki ilgisiz bir belgeyi habersiz
# diske yazmak derlemenin işi değil.
# =====================================================================


class _DiskiOkuyanCompiler(_FakeCompiler):
    """compile() çağrıldığı ANDA izlenen dosyalarda ne yazıyor, onu saklar.

    Sıra kapıda: kayıt derleme başlamadan ÖNCE olmalı. Sonradan diske bakmak
    aynı sonucu verirdi ama sırayı ölçmezdi.
    """

    def __init__(self, busy=False, izlenen=()):
        _FakeCompiler.__init__(self, busy)
        self._izlenen = list(izlenen)
        self.disk = []

    def compile(self, path, engine, shell_escape=None):
        self.disk.append([p.read_text(encoding="utf-8").strip()
                          for p in self._izlenen])
        return _FakeCompiler.compile(self, path, engine, shell_escape)


def _proje(tmp_path):
    """ana.tex `\\input{bolum1}`; ikisi de diskte 'ESKI'."""
    proje = tmp_path / "proje"
    proje.mkdir()
    ana = proje / "ana.tex"
    ana.write_text("\\documentclass{article}\n\\begin{document}\n"
                   "\\input{bolum1}\n\\end{document}\n", encoding="utf-8")
    bolum = proje / "bolum1.tex"
    bolum.write_text("ESKI\n", encoding="utf-8")
    return proje, ana, bolum


def _acik(yol):
    ed = EditorWidget()
    assert ed.open_file(str(yol))
    return ed


def test_BASKA_sekmedeki_proje_dosyasi_derlemeden_ONCE_kaydediliyor(
        qapp, tmp_path):
    """Kırılırsa PDF, kullanıcının ekranda gördüğü metinden başka bir
    içerikten üretilir ve hata satırları var olmayan içeriğe işaret eder."""
    proje, ana, bolum = _proje(tmp_path)
    ed_ana, ed_bolum = _acik(ana), _acik(bolum)
    try:
        ed_bolum.setText("YENI\n")
        stub = _Stub([ed_ana, ed_bolum], root=str(proje))
        stub._compiler = _DiskiOkuyanCompiler(izlenen=[bolum])
        stub._current_editor = lambda: ed_ana          # kullanıcı ana.tex sekmesinde

        stub._compile()

        assert stub._compiler.calls, "derleme hiç başlamadı"
        assert stub._compiler.disk == [["YENI"]], \
            "derleme anında diskte: %r" % (stub._compiler.disk,)
        assert not ed_bolum.isModified()
    finally:
        ed_ana.deleteLater()
        ed_bolum.deleteLater()
        qapp.processEvents()


def test_PROJE_DISINDAKI_acik_belge_kaydedilmiyor(qapp, tmp_path):
    """Derleme onu okumuyor; habersiz diske yazmak kullanıcının kararını
    gasbeder. Salt okunur bir belge oradaysa derlemeyi de kilitlerdi."""
    proje, ana, _bolum = _proje(tmp_path)
    baska = tmp_path / "baska"
    baska.mkdir()
    ilgisiz = baska / "ilgisiz.tex"
    ilgisiz.write_text("ESKI\n", encoding="utf-8")

    ed_ana, ed_ilgisiz = _acik(ana), _acik(ilgisiz)
    try:
        ed_ilgisiz.setText("YENI\n")
        stub = _Stub([ed_ana, ed_ilgisiz], root=str(proje))

        stub._compile()

        assert stub._compiler.calls, "derleme hiç başlamadı"
        assert ilgisiz.read_text(encoding="utf-8").strip() == "ESKI"
        assert ed_ilgisiz.isModified()
    finally:
        ed_ana.deleteLater()
        ed_ilgisiz.deleteLater()
        qapp.processEvents()


def test_YOLSUZ_tampon_derlemeyi_kesmiyor(qapp, tmp_path, monkeypatch):
    """`save_file()` yolu olmayan tamponda False dönüyor. Onu kayıt hatası
    saymak, açık bir 'Yeni Dosya' sekmesi yüzünden derlemeyi tümden
    durdururdu; üstelik döngüde ondan SONRAKİ gerçek dosyalar da
    kaydedilmeden kalırdı.

    `chdir` ŞART: yolsuz sekmenin dizini `os.path.dirname("")` yani ""; onun
    `abspath`i çalışma dizini. Kabuk çalışma dizini projenin DIŞINDAysa kapsam
    denetimi tamponu zaten eliyor ve bu kapı hiçbir şey ölçmüyor (ilk hâlinde
    öyleydi, mutasyon yakalamadı). Uygulama proje klasöründen açıldığında
    kapsam denetimi onu ELEMİYOR; ayırt eden tek şey yol denetimi.
    """
    proje, ana, bolum = _proje(tmp_path)
    monkeypatch.chdir(proje)
    ed_adsiz = EditorWidget()               # hiç kaydedilmemiş
    ed_ana, ed_bolum = _acik(ana), _acik(bolum)
    try:
        ed_adsiz.setText("not\n")
        ed_bolum.setText("YENI\n")
        # Adsız tampon İLK sırada: döngü ona takılırsa bolum1.tex kaydedilmez
        stub = _Stub([ed_adsiz, ed_ana, ed_bolum], root=str(proje))
        stub._current_editor = lambda: ed_ana

        stub._compile()

        assert stub._compiler.calls, "adsız tampon derlemeyi kesti"
        assert bolum.read_text(encoding="utf-8").strip() == "YENI"
        assert ed_adsiz.isModified()        # dokunulmadı
    finally:
        for e in (ed_adsiz, ed_ana, ed_bolum):
            e.deleteLater()
        qapp.processEvents()


def test_proje_dosyasi_KAYDEDILEMEZSE_derleme_iptal(qapp, tmp_path):
    """Bayat girdiyle derlemek, hiç derlememekten kötü: sonuç sessizce
    yanlış olur."""
    proje, ana, bolum = _proje(tmp_path)
    ed_ana, ed_bolum = _acik(ana), _acik(bolum)
    try:
        ed_bolum.setText("YENI\n")
        ed_bolum.save_file = lambda: False          # salt okunur hedef taklidi
        stub = _Stub([ed_ana, ed_bolum], root=str(proje))
        stub._current_editor = lambda: ed_ana

        stub._compile()

        assert stub._compiler.calls == []
        assert "iptal" in stub._status.msg
    finally:
        ed_ana.deleteLater()
        ed_bolum.deleteLater()
        qapp.processEvents()


def test_KIRLI_OLMAYAN_dosyaya_dokunulmuyor(qapp, tmp_path):
    """Aşırı düzeltme kapısı: her derlemede bütün projeyi yeniden yazmak
    dosya izleyicisini tetikler, mtime'ları çalkalar ve kullanıcının hiç
    dokunmadığı dosyaları satır sonu/kodlama dönüşümünden geçirir."""
    proje, ana, bolum = _proje(tmp_path)
    ed_ana, ed_bolum = _acik(ana), _acik(bolum)
    try:
        kayitlar = []
        assert not ed_bolum.isModified()
        ed_bolum.save_file = lambda: (kayitlar.append(1), True)[1]
        stub = _Stub([ed_ana, ed_bolum], root=str(proje))

        stub._compile()

        assert stub._compiler.calls, "derleme hiç başlamadı"
        assert kayitlar == [], "kirli olmayan dosya yeniden yazıldı"
    finally:
        ed_ana.deleteLater()
        ed_bolum.deleteLater()
        qapp.processEvents()


def test_agactan_derlemede_de_proje_kaydediliyor(qapp, tmp_path):
    """`_compile_file` (dosya ağacından sağ tık) aynı yolu izlemeli."""
    proje, ana, bolum = _proje(tmp_path)
    ed_bolum = _acik(bolum)
    try:
        ed_bolum.setText("YENI\n")
        stub = _Stub([ed_bolum], root=str(proje))
        stub._compiler = _DiskiOkuyanCompiler(izlenen=[bolum])

        stub._compile_file(str(ana))

        assert stub._compiler.disk == [["YENI"]], \
            "derleme anında diskte: %r" % (stub._compiler.disk,)
    finally:
        ed_bolum.deleteLater()
        qapp.processEvents()


# =====================================================================
# Esc: olmayan bir derlemeyi "durdurmak"
#
# `_on_esc` bul çubuğu kapalıysa KOŞULSUZ `_stop_compile()` çağırıyor ve o da
# koşulsuz "Derleme durduruldu" yazıyordu. ÖLÇÜLDÜ (2026-09-07): hiçbir
# derleme yokken Esc'e basmak bu mesajı veriyordu. Esc editörde sıradan bir
# tuş (bul çubuğunu kapatmak, sunum kipinden çıkmak); kullanıcı olmayan bir
# işlemin iptal edildiğini okuyordu.
# =====================================================================


def test_derleme_YOKKEN_esc_durduruldu_demiyor(qapp, tmp_path):
    tex = _tex(tmp_path)
    ed = _dirty_editor(tex)
    try:
        stub = _Stub([ed], busy=False)
        stub._status.showMessage("onceki mesaj")

        stub._on_esc()

        assert stub._status.msg == "onceki mesaj", \
            "durum çubuğu ezildi: %r" % stub._status.msg
    finally:
        ed.deleteLater()
        qapp.processEvents()


def test_derleme_SURERKEN_esc_durduruyor_ve_bildiriyor(qapp, tmp_path):
    """Aşırı düzeltme kapısı: gerçek iptal hem olmalı hem söylenmeli."""
    tex = _tex(tmp_path)
    ed = _dirty_editor(tex)
    try:
        stub = _Stub([ed], busy=True)

        stub._on_esc()

        assert stub._compiler.stopped == 1
        assert "durduruldu" in stub._status.msg
    finally:
        ed.deleteLater()
        qapp.processEvents()


def test_esc_ONCE_bul_cubugunu_kapatiyor(qapp, tmp_path):
    """Bul çubuğu açıkken Esc derlemeye dokunmamalı."""
    tex = _tex(tmp_path)
    ed = _dirty_editor(tex)
    try:
        stub = _Stub([ed], busy=True)
        gizlendi = []
        stub._find_bar = SimpleNamespace(isVisible=lambda: True,
                                         hide=lambda: gizlendi.append(1))

        stub._on_esc()

        assert gizlendi == [1]
        assert stub._compiler.stopped == 0
    finally:
        ed.deleteLater()
        qapp.processEvents()

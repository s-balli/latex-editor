"""shell-escape izni: minted tespiti + "bir kez sor, sonra hatırla" kararı.

Neden test var: `-shell-escape` belgeye keyfi komut çalıştırma izni veriyor.
Eskiden proje klasöründe minted geçen KULLANILMAYAN tek bir dosya bile ana
belgedeki `\\write18`i çalıştırmaya yetiyordu. Kararın kullanıcıda kalması ve
`compile()`e doğru şekilde iletilmesi bu dosyanın konusu.
"""

import os
import subprocess

import pytest

from core.shell_escape import minted_kullaniliyor

DERLE_SH = os.path.join(os.path.dirname(__file__), "..", "core", "derle.sh")


def _yaz(dizin, ad, icerik):
    yol = os.path.join(str(dizin), ad)
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    with open(yol, "w", encoding="utf-8") as f:
        f.write(icerik)
    return yol


# --------------------------------------------------------------- tespit

@pytest.mark.parametrize("icerik", [
    "\\usepackage{minted}\n",
    "\\usepackage[cache=false]{minted}\n",
    "\\RequirePackage{minted}\n",
    "\\begin{minted}{python}\nprint(1)\n\\end{minted}\n",
])
def test_minted_bicimleri_yakalaniyor(tmp_path, icerik):
    _yaz(tmp_path, "ana.tex", icerik)
    assert minted_kullaniliyor(str(tmp_path))


@pytest.mark.parametrize("icerik", [
    "\\usepackage{listings}\n",
    "% minted kullanmiyoruz\n",          # düz metinde geçmesi yetmemeli
    "\\usepackage{mintedx}\n",
])
def test_yanlis_alarm_yok(tmp_path, icerik):
    _yaz(tmp_path, "ana.tex", icerik)
    assert not minted_kullaniliyor(str(tmp_path))


def test_alt_klasordeki_sty_de_sayiliyor(tmp_path):
    # Paket bir .sty içinden de yüklenebiliyor; derle.sh de böyle tarıyor.
    _yaz(tmp_path, "ana.tex", "\\documentclass{article}\n")
    _yaz(tmp_path, os.path.join("stiller", "tez.sty"),
         "\\RequirePackage{minted}\n")
    assert minted_kullaniliyor(str(tmp_path))


def test_tex_disi_uzanti_taranmiyor(tmp_path):
    _yaz(tmp_path, "notlar.md", "\\usepackage{minted}\n")
    assert not minted_kullaniliyor(str(tmp_path))


def test_olmayan_klasor(tmp_path):
    assert not minted_kullaniliyor(str(tmp_path / "yok"))
    assert not minted_kullaniliyor("")


def test_derleme_ciktisi_atlaniyor(tmp_path):
    # .git / build gibi klasörler SKIP_DIRS'te; oradaki artık soru sordurmamalı
    from core.project_search import SKIP_DIRS

    atlanan = next(iter(SKIP_DIRS))
    _yaz(tmp_path, os.path.join(atlanan, "eski.tex"), "\\usepackage{minted}\n")
    assert not minted_kullaniliyor(str(tmp_path))


# ------------------------------------------------------- karar ve hafıza

try:
    from PyQt6.QtWidgets import QApplication, QMessageBox
    from gui.mixins.compile_ops import CompileOpsMixin
    from tests.stub_main import StubMain
except ImportError:  # pragma: no cover
    CompileOpsMixin = None
    QMessageBox = None


gui = pytest.mark.skipif(CompileOpsMixin is None,
                         reason="PyQt6 / gui modülleri gerekli")


@pytest.fixture(scope="module", autouse=True)
def qapp():
    """StubMain widget kuruyor; QApplication olmadan süreç düşüyor."""
    if CompileOpsMixin is None:
        yield None
        return
    app = QApplication.instance() or QApplication([])
    yield app


class _SahteMB:
    """QMessageBox yerine: sorulanı kaydeder, ayarlanan cevabı verir."""

    # Gerçek enum: kod `Yes | No` ile bayrak birleştiriyor ve cevabı Yes ile
    # karşılaştırıyor; sahte sabitler bu iki davranışı sınamaz.
    StandardButton = getattr(QMessageBox, "StandardButton", None)

    def __init__(self, cevap):
        self.cevap = cevap
        self.sorular = []

    def question(self, parent, baslik, metin, *a, **k):
        self.sorular.append(metin)
        return self.cevap


def _karar_stub(kok, ayarlar=None):
    class _S(CompileOpsMixin, StubMain):
        pass

    s = _S(root=str(kok))
    if ayarlar:
        s._settings.d.update(ayarlar)
    return s


def _sor(monkeypatch, stub, cevap):
    import gui.mixins.compile_ops as co

    mb = _SahteMB(cevap)
    monkeypatch.setattr(co, "QMessageBox", mb)
    return mb


@gui
def test_minted_yoksa_sorulmuyor(tmp_path, monkeypatch):
    _yaz(tmp_path, "ana.tex", "\\documentclass{article}\n")
    stub = _karar_stub(tmp_path)
    mb = _sor(monkeypatch, stub, _SahteMB.StandardButton.Yes)

    # None: bayrak hiç gönderilmiyor. False (--no-shell-escape) OLMAMALI;
    # o, kısıtlı kipi de kapatıp epstopdf'i bozuyor ve hiçbir şey kazandırmıyor.
    assert stub._shell_escape_karari(str(tmp_path / "ana.tex")) is None
    assert mb.sorular == []
    # Karar KAYDEDİLMEMELİ: projeye sonradan minted eklenirse yine sorulmalı
    assert stub._settings.d == {}


@gui
def test_evet_denince_aciliyor_ve_hatirlaniyor(tmp_path, monkeypatch):
    _yaz(tmp_path, "ana.tex", "\\usepackage{minted}\n")
    stub = _karar_stub(tmp_path)
    mb = _sor(monkeypatch, stub, _SahteMB.StandardButton.Yes)

    assert stub._shell_escape_karari(str(tmp_path / "ana.tex")) is True
    assert len(mb.sorular) == 1
    assert "minted" in mb.sorular[0]
    assert os.path.normpath(str(tmp_path)) in stub._settings.d[
        CompileOpsMixin._SE_IZINLI]

    # İkinci derlemede tekrar sorulmamalı
    assert stub._shell_escape_karari(str(tmp_path / "ana.tex")) is True
    assert len(mb.sorular) == 1


@gui
def test_hayir_denince_kapali_ve_hatirlaniyor(tmp_path, monkeypatch):
    _yaz(tmp_path, "ana.tex", "\\usepackage{minted}\n")
    stub = _karar_stub(tmp_path)
    mb = _sor(monkeypatch, stub, _SahteMB.StandardButton.No)

    assert stub._shell_escape_karari(str(tmp_path / "ana.tex")) is False
    assert len(mb.sorular) == 1
    assert os.path.normpath(str(tmp_path)) in stub._settings.d[
        CompileOpsMixin._SE_RED]

    assert stub._shell_escape_karari(str(tmp_path / "ana.tex")) is False
    assert len(mb.sorular) == 1


@gui
def test_kayitli_karar_varken_tarama_yapilmiyor(tmp_path, monkeypatch):
    """Kayıtlı cevap her derlemede klasörü yeniden taratmamalı."""
    _yaz(tmp_path, "ana.tex", "\\usepackage{minted}\n")
    stub = _karar_stub(tmp_path, {
        CompileOpsMixin._SE_IZINLI: [os.path.normpath(str(tmp_path))]})
    _sor(monkeypatch, stub, _SahteMB.StandardButton.No)

    import core.shell_escape as se
    tarandi = []
    monkeypatch.setattr(se, "minted_kullaniliyor",
                        lambda k: tarandi.append(k) or True)

    assert stub._shell_escape_karari(str(tmp_path / "ana.tex")) is True
    assert tarandi == []


@gui
def test_tek_yol_string_olarak_kayitliysa_okunuyor(tmp_path, monkeypatch):
    """QSettings tek elemanlı listeyi düz string olarak geri verebiliyor."""
    _yaz(tmp_path, "ana.tex", "\\usepackage{minted}\n")
    stub = _karar_stub(tmp_path, {
        CompileOpsMixin._SE_RED: os.path.normpath(str(tmp_path))})
    mb = _sor(monkeypatch, stub, _SahteMB.StandardButton.Yes)

    assert stub._shell_escape_karari(str(tmp_path / "ana.tex")) is False
    assert mb.sorular == []


@gui
def test_ayri_projeye_ayri_soru(tmp_path, monkeypatch):
    a, b = tmp_path / "a", tmp_path / "b"
    _yaz(a, "ana.tex", "\\usepackage{minted}\n")
    _yaz(b, "ana.tex", "\\usepackage{minted}\n")

    stub_a = _karar_stub(a)
    mb_a = _sor(monkeypatch, stub_a, _SahteMB.StandardButton.Yes)
    assert stub_a._shell_escape_karari(str(a / "ana.tex")) is True

    stub_b = _karar_stub(b, dict(stub_a._settings.d))
    mb_b = _sor(monkeypatch, stub_b, _SahteMB.StandardButton.No)
    assert stub_b._shell_escape_karari(str(b / "ana.tex")) is False
    assert len(mb_a.sorular) == 1 and len(mb_b.sorular) == 1


@gui
def test_izin_sifirlaninca_yeniden_soruluyor(tmp_path, monkeypatch):
    """Yanlışlıkla verilen cevabın geri alınacak bir yolu olmalı."""
    _yaz(tmp_path, "ana.tex", "\\usepackage{minted}\n")
    stub = _karar_stub(tmp_path)
    mb = _sor(monkeypatch, stub, _SahteMB.StandardButton.No)
    assert stub._shell_escape_karari(str(tmp_path / "ana.tex")) is False

    stub._reset_shell_escape()
    assert "sıfırlandı" in stub._status.msg

    mb.cevap = _SahteMB.StandardButton.Yes
    assert stub._shell_escape_karari(str(tmp_path / "ana.tex")) is True
    assert len(mb.sorular) == 2


@gui
def test_sifirlama_diger_projeyi_etkilemiyor(tmp_path, monkeypatch):
    a, b = tmp_path / "a", tmp_path / "b"
    _yaz(a, "ana.tex", "\\usepackage{minted}\n")
    _yaz(b, "ana.tex", "\\usepackage{minted}\n")
    kayit = {CompileOpsMixin._SE_RED: [os.path.normpath(str(a)),
                                       os.path.normpath(str(b))]}

    stub = _karar_stub(a, kayit)
    stub._reset_shell_escape()

    kalan = stub._settings.d[CompileOpsMixin._SE_RED]
    assert os.path.normpath(str(a)) not in kalan
    assert os.path.normpath(str(b)) in kalan


@gui
def test_kayit_yokken_sifirlama_yaniltmiyor(tmp_path, monkeypatch):
    _yaz(tmp_path, "ana.tex", "\\usepackage{minted}\n")
    stub = _karar_stub(tmp_path)

    stub._reset_shell_escape()

    assert "yok" in stub._status.msg
    assert "sıfırlandı" not in stub._status.msg


# ------------------------------------------------------------- derle.sh

def test_derle_sh_no_shell_escape_bayragini_taniyor():
    """`--no-shell-escape` verildiğinde minted görülse bile bayrak açılmamalı."""
    with open(DERLE_SH, encoding="utf-8") as f:
        kaynak = f.read()
    assert "--no-shell-escape) DENY_SHELL_ESCAPE=true" in kaynak
    # Reddin önceliği olmalı: minted tespiti bunu geçersizleştirmemeli
    i_red = kaynak.index('if [ "${DENY_SHELL_ESCAPE:-false}" = true ]')
    i_izin = kaynak.index('elif [ "$FORCE_SHELL_ESCAPE" = true ]')
    assert i_red < i_izin


@pytest.mark.skipif(not os.path.exists(DERLE_SH), reason="derle.sh yok")
def test_derle_sh_sozdizimi():
    bash = "bash"
    try:
        r = subprocess.run([bash, "-n", DERLE_SH], capture_output=True,
                           text=True, encoding="utf-8")
    except OSError:  # pragma: no cover
        pytest.skip("bash yok")
    assert r.returncode == 0, r.stderr

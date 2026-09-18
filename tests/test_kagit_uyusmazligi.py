r"""Belgenin istediği kağıt ile üretilen PDF'in kağıdı uyuşuyor mu.

NEDEN VAR. Standart sınıfların kağıt seçeneği metin bloğunu kuruyor ama
FİZİKSEL sayfayı belirlemiyor; onu TeX dağıtımının öntanımı veriyor.
Debian/Ubuntu A4'e, MacTeX/BasicTeX US Letter'a ayarlı. ÖLÇÜLDÜ
(2026-09-19, aynı kaynak, aynı motor, iki platform):

    \documentclass{article}             Linux A4 | macOS US Letter
    \documentclass[a4paper]{article}    Linux A4 | macOS US Letter   <-- (*)
    [a4paper] + \usepackage{geometry}   Linux A4 | macOS A4
    [letterpaper] + geometry            Linux Letter | macOS Letter

(*) işaretli satır kusurun kendisi: belge A4 İSTEMİŞ, macOS'ta Letter
almış ve uygulama bunu söylememişti. Sayfa 17.6 mm kısa olduğu için metin
bloğu da sayfaya sığmıyor.

PDF'ler TeX'SİZ üretiliyor: kapının sorusu "bu boyut bu bildirimle uyuşuyor
mu", derleme değil. Böylece kapı üç CI işinde de koşuyor, TeX'i olmayan
matris işlerinde de.
"""

import os

import pytest

try:
    import pypdfium2
    from PyQt6.QtWidgets import QApplication
    from gui.main_window import MainWindow
    from gui.mixins.compile_ops import CompileOpsMixin
    from gui.mixins.edit_ops import EditOpsMixin
    from tests.stub_main import StubMain
except ImportError:                                   # pragma: no cover
    pytest.skip("PyQt6 / pypdfium2 / gui gerekli", allow_module_level=True)

A4 = (595.276, 841.890)
LETTER = (612.0, 792.0)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class _Stub(CompileOpsMixin, EditOpsMixin, StubMain):
    def __init__(self, target=""):
        super().__init__(target=target)


def _pdf_yaz(yol, boyut):
    """Verilen sayfa boyutunda boş bir PDF; TeX gerektirmiyor."""
    belge = pypdfium2.PdfDocument.new()
    belge.new_page(*boyut)
    belge.save(str(yol))
    belge.close()
    return str(yol)


def _kur(tmp_path, kaynak, boyut):
    tex = tmp_path / "belge.tex"
    tex.write_text(kaynak, encoding="utf-8")
    pdf = _pdf_yaz(tmp_path / "belge.pdf", boyut)
    return _Stub(target=str(tex)), pdf


def _oneriler(stub):
    liste = stub._output_panel._suggest_list
    return [liste.item(i).text() for i in range(liste.count())]


class TestUyusmazlikBildiriliyor:

    def test_A4_isteyip_LETTER_alan_belge_uyari_aliyor(self, qapp, tmp_path):
        """Kusurun kendisi: macOS'ta gerçekten böyle oluyor."""
        stub, pdf = _kur(tmp_path,
                         "\\documentclass[a4paper,11pt]{article}\n", LETTER)
        MainWindow._kagit_uyusmazligini_bildir(stub, pdf)
        satirlar = _oneriler(stub)
        assert len(satirlar) == 1, satirlar
        assert "A4" in satirlar[0] and "US Letter" in satirlar[0]
        # Çare de söylenmeli: paket adı geçmezse kullanıcı ne yapacağını
        # bilmiyor ve uyarı yalnız huzursuz ediyor.
        assert "geometry" in satirlar[0]
        assert "a4paper" in satirlar[0]

    def test_LETTER_isteyip_A4_alan_belge_de_uyari_aliyor(self, qapp, tmp_path):
        """Ters yön: Linux'ta Letter isteyen belgenin başına gelen."""
        stub, pdf = _kur(tmp_path,
                         "\\documentclass[letterpaper]{article}\n", A4)
        MainWindow._kagit_uyusmazligini_bildir(stub, pdf)
        satirlar = _oneriler(stub)
        assert len(satirlar) == 1, satirlar
        assert "US Letter" in satirlar[0] and "A4" in satirlar[0]


class TestSusmasiGerekenler:
    """Uyarı yalnız GERÇEK uyuşmazlıkta çıkmalı; yoksa gürültü olur."""

    def test_isteyip_ALAN_belge_susuyor(self, qapp, tmp_path):
        stub, pdf = _kur(tmp_path,
                         "\\documentclass[a4paper]{article}\n", A4)
        MainWindow._kagit_uyusmazligini_bildir(stub, pdf)
        assert _oneriler(stub) == []

    def test_kagit_BILDIRMEYEN_belge_susuyor(self, qapp, tmp_path):
        """Bildirim yoksa uyuşmazlık da yok: dağıtımın öntanımı geçerli."""
        stub, pdf = _kur(tmp_path, "\\documentclass{article}\n", LETTER)
        MainWindow._kagit_uyusmazligini_bildir(stub, pdf)
        assert _oneriler(stub) == []

    def test_YATAY_belge_uyari_almiyor(self, qapp, tmp_path):
        """`landscape` kenarları yer değiştiriyor, bu uyuşmazlık değil."""
        stub, pdf = _kur(tmp_path,
                         "\\documentclass[a4paper,landscape]{article}\n",
                         (A4[1], A4[0]))
        MainWindow._kagit_uyusmazligini_bildir(stub, pdf)
        assert _oneriler(stub) == []

    def test_YORUMDAKI_bildirim_sayilmiyor(self, qapp, tmp_path):
        """Yorum satırındaki eski bir `\\documentclass` gerçeğin yerine geçmemeli."""
        stub, pdf = _kur(
            tmp_path,
            "% \\documentclass[a4paper]{article}\n\\documentclass{article}\n",
            LETTER)
        MainWindow._kagit_uyusmazligini_bildir(stub, pdf)
        assert _oneriler(stub) == []

    def test_PDF_okunamazsa_sessiz(self, qapp, tmp_path):
        """Bozuk PDF'te uyarı değil, sessizlik: kağıt bilinmiyor."""
        tex = tmp_path / "belge.tex"
        tex.write_text("\\documentclass[a4paper]{article}\n", encoding="utf-8")
        bozuk = tmp_path / "bozuk.pdf"
        bozuk.write_bytes(b"bu bir PDF degil")
        stub = _Stub(target=str(tex))
        MainWindow._kagit_uyusmazligini_bildir(stub, str(bozuk))
        assert _oneriler(stub) == []

    def test_kaynak_YOKSA_sessiz(self, qapp, tmp_path):
        pdf = _pdf_yaz(tmp_path / "x.pdf", LETTER)
        stub = _Stub(target=str(tmp_path / "olmayan.tex"))
        MainWindow._kagit_uyusmazligini_bildir(stub, pdf)
        assert _oneriler(stub) == []


def test_SAF_islevler_dosya_acmiyor():
    """Ayrıştırma ve karşılaştırma çekirdekte, Qt'siz de sınanabilir."""
    from core.latex_utils import (
        bildirilen_kagit, kagit_adi, kagit_eslesiyor_mu,
    )
    assert bildirilen_kagit("\\documentclass[11pt,b5paper]{book}") == "b5paper"
    assert bildirilen_kagit("\\documentclass[11pt]{book}") is None
    assert kagit_eslesiyor_mu("a4paper", *A4)
    assert not kagit_eslesiyor_mu("a4paper", *LETTER)
    assert kagit_adi(*LETTER) == "US Letter"
    assert os.sep not in kagit_adi(500.0, 700.0)     # ölçü yazıyor, yol değil

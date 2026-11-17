"""Derleme ve dışa aktarma hata metinleri çeviriden geçiyor mu.

Ölçüldü (gerçek uygulama, WSLg, İngilizce arayüz, 2026-11-17): sonsuz
döngüye giren belge 120 sn'de zaman aşımıyla kesilince Hatalar sekmesi
"Derleme zaman aşımına uğradı (120s), iptal edildi." dedi; ileti
core/compiler.py'de `_()` dışındaydı. core/exporter.py'nin sabit hata
metinleri de aynı sınıftan: durum çubuğuna "Dışa aktarma başarısız: ..."
diye ekleniyor ve İngilizce arayüzde Türkçe kalıyordu.

Gerçek latexeditor_en.qm yeni metinleri katalog güncellenmeden taşımadığı
için testler sabit sözlüklü bir çevirmen kuruyor; kapı, metnin `_()`
yolundan geçip geçmediği. Sözlük kaynak metinleri kodla birebir aynı
olmalı (katalog kapısı tests/test_tr_extraction.py ayrıca bakıyor).
"""

import subprocess
from unittest.mock import MagicMock

import pytest

try:
    from PyQt6.QtCore import QProcess, QTranslator
    from PyQt6.QtWidgets import QApplication
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 gerekli", allow_module_level=True)

import core.exporter as ex
from core.compiler import LatexCompiler

_app = QApplication.instance() or QApplication([])

_SOZLUK = {
    "Derleme zaman aşımına uğradı ({sure}s), iptal edildi.":
        "Compilation timed out ({sure}s) and was cancelled.",
    "İşlem zaman aşımına uğradı": "The operation timed out",
    "Kaynak dosya bulunamadı": "Source file not found",
    "Dışa aktarma başarısız": "Export failed",
    "Çıktı dosyası kopyalanamadı": "The output file could not be copied",
    "pandoc bulunamadı, kurmak için: {komut}":
        "pandoc not found, to install it: {komut}",
    "pandoc bulunamadı, kurmak için (WSL içinde): {komut}":
        "pandoc not found, to install it (inside WSL): {komut}",
}


class _SabitCevirmen(QTranslator):
    def translate(self, context, sourceText, disambiguation=None, n=-1):
        # Sözlükte yoksa None: Qt kaynak metni olduğu gibi bırakır.
        return _SOZLUK.get(sourceText)


@pytest.fixture
def ingilizce():
    c = _SabitCevirmen()
    _app.installTranslator(c)
    try:
        yield
    finally:
        _app.removeTranslator(c)


def _turkce_yok(metin):
    for kelime in ("aşım", "uğradı", "bulunamadı", "başarısız",
                   "kopyalanamadı", "kurmak için", "içinde"):
        assert kelime not in metin, f"çevrilmemiş: {metin!r}"


def test_DERLEME_zaman_asimi_iletisi_cevriliyor(ingilizce):
    c = LatexCompiler()
    c.process = MagicMock()
    c.process.state.return_value = QProcess.ProcessState.Running
    c.process.processId.return_value = 0
    satirlar, sonuclar = [], []
    c.output_line.connect(satirlar.append)
    c.compilation_finished.connect(sonuclar.append)
    c._on_timeout()
    mesaj = sonuclar[0].errors[0].message
    assert "timed out" in mesaj and "120s" in mesaj, mesaj
    _turkce_yok(mesaj)
    hata = [s for s in satirlar if s.startswith("[hata]")]
    assert hata and "timed out" in hata[-1], satirlar


@pytest.mark.parametrize("islev", ["_export_native", "_export_wsl"])
def test_DISA_AKTARMA_zaman_asimi_cevriliyor(ingilizce, monkeypatch, islev):
    def _sahte(argv, *a, **k):
        # Yalnız pandoc çağrısı zaman aşımına uğrar; WSL kolunun sondaki
        # `rm -f` temizliği başarılı döner.
        if "rm" in argv:
            return MagicMock(returncode=0)
        raise subprocess.TimeoutExpired("pandoc", 30)

    monkeypatch.setattr(ex.subprocess, "run", MagicMock(side_effect=_sahte))
    ok, mesaj = getattr(ex, islev)("C:\\x\\a.tex", "C:\\x\\a.docx")
    assert ok is False
    assert mesaj == "The operation timed out", mesaj


@pytest.mark.parametrize("platform,beklenen", [
    ("win32", "pandoc not found, to install it (inside WSL): sudo apt install pandoc"),
    ("linux", "pandoc not found, to install it: sudo apt install pandoc"),
])
def test_PANDOC_yok_iletisi_cevriliyor(ingilizce, monkeypatch, platform,
                                       beklenen):
    monkeypatch.setattr(ex, "PLATFORM", platform)
    monkeypatch.setattr(ex.subprocess, "run",
                        MagicMock(side_effect=FileNotFoundError()))
    ok, mesaj = ex._export_native("a.tex", "b.docx")
    assert ok is False
    assert mesaj == beklenen, mesaj


def test_BOS_stderr_genel_iletisi_cevriliyor(ingilizce, monkeypatch):
    monkeypatch.setattr(ex.subprocess, "run",
                        MagicMock(return_value=MagicMock(returncode=1, stderr="")))
    ok, mesaj = ex._export_native("a.tex", "b.docx")
    assert (ok, mesaj) == (False, "Export failed")


def test_KAYNAK_yok_iletisi_cevriliyor(ingilizce, tmp_path):
    ok, mesaj = ex.export(str(tmp_path / "yok.tex"), str(tmp_path / "a.docx"))
    assert (ok, mesaj) == (False, "Source file not found")


def test_KOPYALAMA_hatasi_cevriliyor(ingilizce, monkeypatch):
    # pandoc başarılı, cp ve cat başarısız: "kopyalanamadı" yolu.
    def _sahte(argv, *a, **k):
        komut = argv[2] if len(argv) > 2 else ""
        kod = 1 if komut in ("cp", "cat") else 0      # pandoc ve rm başarılı
        return MagicMock(returncode=kod, stderr="", stdout=b"")

    monkeypatch.setattr(ex.subprocess, "run", MagicMock(side_effect=_sahte))
    ok, mesaj = ex._export_wsl("C:\\x\\a.tex", "C:\\x\\a.docx")
    assert (ok, mesaj) == (False, "The output file could not be copied")


def test_CEVIRMEN_yokken_kaynak_metin_TURKCE_kaliyor(monkeypatch):
    """Kontrol kolu: çevirmen kurulu değilken kaynak dil aynen görünür
    (testlerin ölçtüğü fark çevirmenden geliyor, başka bir yoldan değil)."""
    monkeypatch.setattr(ex.subprocess, "run", MagicMock(
        side_effect=subprocess.TimeoutExpired("pandoc", 30)))
    assert ex._export_native("a.tex", "b.docx") == (
        False, "İşlem zaman aşımına uğradı")

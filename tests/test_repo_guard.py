"""Yabancı git deposunda sürümleme uyarısı (version_ops._confirm_repo_use).

'Sürümle' ayrı bir geçmiş tutmaz: mevcut .git'e, bulunulan dala commit atar.
Kullanıcının kendi deposunda bu sürpriz olur ve 'Tüm Geçmişi Sil' gerçek
depoyu çöpe atar. Uyarı klasör başına bir kez çıkar; editörün kendi
depolarında hiç çıkmamalı (yoksa her Ctrl+K'da bir tıklama fazla).
"""

import time
from types import SimpleNamespace

import pytest

try:
    from PyQt6.QtWidgets import QApplication, QMessageBox, QWidget
    from gui.editor import EditorWidget
    from gui.mixins.version_ops import VersionOpsMixin
    from tests.stub_main import StubMain
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / gui modülleri gerekli", allow_module_level=True)

pytest.importorskip("dulwich")

from dulwich import porcelain  # noqa: E402
from dulwich.repo import Repo  # noqa: E402

from core import versioning as V  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class _Stub(VersionOpsMixin, StubMain, QWidget):
    """QWidget: _confirm_repo_use gerçek QMessageBox(self) kurar, parent ister."""

    def __init__(self, editors, root):
        QWidget.__init__(self)
        StubMain.__init__(self, editors=editors)
        self._file_tree = SimpleNamespace(_root=root)

    def _file_watch_record_save(self, path):
        pass


def _proje(tmp_path):
    tex = tmp_path / "ana.tex"
    tex.write_text("\\begin{document}\nmerhaba\n\\end{document}\n", encoding="utf-8")
    return str(tex)


def _stub(tmp_path, monkeypatch, root=None):
    import gui.mixins.version_ops as vo
    tex = _proje(tmp_path)
    ed = EditorWidget()
    ed.open_file(tex)
    monkeypatch.setattr(vo.QInputDialog, "getText",
                        staticmethod(lambda *a, **k: ("sürüm", True)))
    return _Stub([ed], root or str(tmp_path))


def _dialog_yakala(monkeypatch, tikla: str):
    """QMessageBox.exec'i sahtele; `tikla` ile başlayan düğmeyi seçtir."""
    kayit = {"cagrildi": 0, "metin": ""}

    def fake_exec(self):
        kayit["cagrildi"] += 1
        kayit["metin"] = self.text()
        for b in self.buttons():
            if b.text().startswith(tikla):
                self._secilen = b
                return 0
        raise AssertionError(f"düğme yok: {tikla} / {[b.text() for b in self.buttons()]}")

    monkeypatch.setattr(QMessageBox, "exec", fake_exec)
    monkeypatch.setattr(QMessageBox, "clickedButton",
                        lambda self: getattr(self, "_secilen", None))
    return kayit


def _snap(qapp, stub):
    stub._snapshot()
    deadline = time.monotonic() + 10
    while getattr(stub, "_snapshot_busy", False) and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    qapp.processEvents()


# --- editörün kendi akışı bozulmamalı ---


def test_bos_klasorde_uyari_cikmaz(qapp, tmp_path, monkeypatch):
    stub = _stub(tmp_path, monkeypatch)
    kayit = _dialog_yakala(monkeypatch, "Anladım")

    _snap(qapp, stub)

    assert kayit["cagrildi"] == 0, "sıfırdan kurulan depoda uyarı anlamsız"
    assert "Sürüm kaydedildi" in stub._status.msg


def test_editorun_kendi_deposunda_uyari_cikmaz(qapp, tmp_path, monkeypatch):
    """İkinci, üçüncü Ctrl+K'da da sessiz kalmalı."""
    stub = _stub(tmp_path, monkeypatch)
    _dialog_yakala(monkeypatch, "Anladım")
    _snap(qapp, stub)

    (tmp_path / "ana.tex").write_text("değişti\n", encoding="utf-8")
    kayit = _dialog_yakala(monkeypatch, "Anladım")
    _snap(qapp, stub)

    assert kayit["cagrildi"] == 0
    assert "Sürüm kaydedildi" in stub._status.msg


# --- yabancı depo: uyarı ve iptal ---


def _yabanci_depo(tmp_path):
    _proje(tmp_path)
    porcelain.init(str(tmp_path))
    repo = Repo(str(tmp_path))
    porcelain.add(repo)
    yazar = b"Ayse Yilmaz <ayse@example.com>"
    porcelain.commit(repo, message=b"kendi kaydim", author=yazar, committer=yazar)
    return repo


def test_yabanci_depoda_uyari_cikar(qapp, tmp_path, monkeypatch):
    _yabanci_depo(tmp_path)
    stub = _stub(tmp_path, monkeypatch)
    kayit = _dialog_yakala(monkeypatch, "Anladım")

    _snap(qapp, stub)

    assert kayit["cagrildi"] == 1
    assert "git deposu" in kayit["metin"]


def test_vazgecince_kayit_atilmaz(qapp, tmp_path, monkeypatch):
    repo = _yabanci_depo(tmp_path)
    onceki = repo.head()
    (tmp_path / "ana.tex").write_text("yeni içerik\n", encoding="utf-8")
    stub = _stub(tmp_path, monkeypatch)
    _dialog_yakala(monkeypatch, "Vazgeç")

    _snap(qapp, stub)

    assert Repo(str(tmp_path)).head() == onceki, "vazgeçildiği hâlde commit atıldı"
    assert "iptal" in stub._status.msg.lower()


def test_uyari_klasor_basina_bir_kez_sorulur(qapp, tmp_path, monkeypatch):
    _yabanci_depo(tmp_path)
    stub = _stub(tmp_path, monkeypatch)

    kayit1 = _dialog_yakala(monkeypatch, "Anladım")
    (tmp_path / "ana.tex").write_text("bir\n", encoding="utf-8")
    _snap(qapp, stub)
    assert kayit1["cagrildi"] == 1

    kayit2 = _dialog_yakala(monkeypatch, "Anladım")
    (tmp_path / "ana.tex").write_text("iki\n", encoding="utf-8")
    _snap(qapp, stub)
    assert kayit2["cagrildi"] == 0, "onay kalıcı olmalı"


def test_remote_adlari_uyaride_gosterilir(qapp, tmp_path, monkeypatch):
    repo = _yabanci_depo(tmp_path)
    cfg = repo.get_config()
    cfg.set((b"remote", b"origin"), b"url", b"git@github.com:kullanici/tez.git")
    cfg.write_to_path()
    stub = _stub(tmp_path, monkeypatch)
    kayit = _dialog_yakala(monkeypatch, "Anladım")

    _snap(qapp, stub)

    assert "origin" in kayit["metin"]


# --- iç içe depo ---


def test_ust_depo_altinda_uyari_cikar(qapp, tmp_path, monkeypatch):
    """repo/makale/ açıkken 'Sürümle' iç içe .git yaratır."""
    porcelain.init(str(tmp_path))
    alt = tmp_path / "makale"
    alt.mkdir()
    stub = _stub(alt, monkeypatch, root=str(alt))
    kayit = _dialog_yakala(monkeypatch, "Anladım")

    _snap(qapp, stub)

    assert kayit["cagrildi"] == 1
    assert "İÇ İÇE" in kayit["metin"]
    assert V.is_repo(str(alt)), "onaylandıysa depo yine de kurulmalı"


# --- silme dialogları ---


def test_tum_gecmisi_sil_yabanci_depoda_farkli_uyarir(qapp, tmp_path, monkeypatch):
    repo = _yabanci_depo(tmp_path)
    cfg = repo.get_config()
    cfg.set((b"remote", b"origin"), b"url", b"git@github.com:kullanici/tez.git")
    cfg.write_to_path()
    stub = _stub(tmp_path, monkeypatch)

    sorulan = {}

    def fake_question(parent, baslik, metin, *a, **k):
        sorulan["metin"] = metin
        return QMessageBox.StandardButton.No     # silme

    monkeypatch.setattr(QMessageBox, "question", staticmethod(fake_question))
    stub._drop_all_history(str(tmp_path))

    assert "SİZİN git deponuz" in sorulan["metin"]
    assert "origin" in sorulan["metin"]
    assert V.is_repo(str(tmp_path)), "No dendiği hâlde silindi"


def test_tum_gecmisi_sil_kendi_deposunda_kisa_uyarir(qapp, tmp_path, monkeypatch):
    stub = _stub(tmp_path, monkeypatch)
    _dialog_yakala(monkeypatch, "Anladım")
    _snap(qapp, stub)

    sorulan = {}

    def fake_question(parent, baslik, metin, *a, **k):
        sorulan["metin"] = metin
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "question", staticmethod(fake_question))
    stub._drop_all_history(str(tmp_path))

    assert "SİZİN git deponuz" not in sorulan["metin"]
    assert "TÜM sürüm geçmişi" in sorulan["metin"]


def test_surum_sil_yabanci_depoda_not_ekler(qapp, tmp_path, monkeypatch):
    _yabanci_depo(tmp_path)
    stub = _stub(tmp_path, monkeypatch)

    sorulan = {}

    def fake_question(parent, baslik, metin, *a, **k):
        sorulan["metin"] = metin
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "question", staticmethod(fake_question))
    stub._drop_version(str(tmp_path))

    assert "sizin git deponuz" in sorulan["metin"].lower()

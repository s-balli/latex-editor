"""F2 \\label yeniden adlandırma — editör sinyali ve MainWindow handler testleri.

İki katman:
- gui.editor.EditorWidget: F2 imleç altındaki anahtarı yakalar
- gui.mixins.edit_ops: anahtarı doküman + \\input zincirinde toplu değiştirir
  (sekme arabellekleri seç-değiştir ile, disk dosyaları atomik yazar)
"""

from unittest.mock import patch

import pytest

try:
    from PyQt6.QtCore import QEvent, Qt
    from PyQt6.QtGui import QKeyEvent
    from PyQt6.QtWidgets import QApplication
    from gui.editor import EditorWidget
    from gui.main_window import MainWindow
    from gui.mixins.edit_ops import EditOpsMixin
    from gui.mixins.tab_ops import TabOpsMixin
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / gui import edilemiyor", allow_module_level=True)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


# --- EditorWidget: F2 imleç altındaki anahtarı yakalar ---


def test_f2_on_label_arg(qapp):
    ed = EditorWidget()
    ed.setText("\\label{fig:a}\n")
    caught = []
    ed.rename_label_requested.connect(caught.append)
    ed.setCursorPosition(0, len("\\label{fig:a") - 2)
    ed._request_rename()
    assert caught == ["fig:a"]


def test_f2_on_ref_arg(qapp):
    ed = EditorWidget()
    ed.setText("bkz \\ref{fig:a} burada\n")
    caught = []
    ed.rename_label_requested.connect(caught.append)
    ed.setCursorPosition(0, len("bkz \\ref{fig:a") - 1)
    ed._request_rename()
    assert caught == ["fig:a"]


def test_f2_elsewhere_no_signal(qapp):
    ed = EditorWidget()
    ed.setText("\\label{fig:a}\ndüz metin\n")
    caught = []
    ed.rename_label_requested.connect(caught.append)
    ed.setCursorPosition(1, 3)
    ed._request_rename()
    assert caught == []


# --- MainWindow handler: zincirde toplu değiştirme ---


from tests.stub_main import StubMain


class _StubMain(EditOpsMixin, TabOpsMixin, StubMain):
    """MainWindow yerine: _on_rename_label'in ihtiyaç duyduğu arayüz."""


def test_rename_updates_tab_and_disk(qapp, tmp_path):
    """Ana dosya sekmede (arabellek), çocuk diskte → ikisi de değişir."""
    ch = tmp_path / "ch.tex"
    ch.write_text("metin \\ref{fig:a} ve \\cref{fig:a, tab:b}\n", encoding="utf-8")
    main = tmp_path / "m.tex"
    main.write_text("\\label{fig:a}\n\\input{ch}\n\\ref{fig:a}\n", encoding="utf-8")
    ed = EditorWidget()
    ed._file_path = str(main)
    ed.setText(main.read_text(encoding="utf-8"))

    stub = _StubMain(editors=[ed])
    with patch("gui.mixins.edit_ops.QInputDialog.getText", return_value=("fig:yeni", True)):
        MainWindow._on_rename_label(stub, "fig:a")

    buf = ed.text()
    assert buf.count("fig:yeni") == 2      # \label + \ref
    assert "fig:a" not in buf
    disk = ch.read_text(encoding="utf-8")
    assert disk == "metin \\ref{fig:yeni} ve \\cref{fig:yeni, tab:b}\n"
    assert "2 dosya" in stub._status.msg


def test_rename_child_open_in_tab(qapp, tmp_path):
    """Çocuk da sekmedeyse arabelleği değişir, disk dokunulmaz (kullanıcı kaydeder)."""
    ch = tmp_path / "ch.tex"
    ch.write_text("\\ref{fig:a}\n", encoding="utf-8")
    main = tmp_path / "m.tex"
    main.write_text("\\label{fig:a}\n\\input{ch}\n", encoding="utf-8")
    ed_main = EditorWidget(); ed_main._file_path = str(main)
    ed_main.setText(main.read_text(encoding="utf-8"))
    ed_ch = EditorWidget(); ed_ch._file_path = str(ch)
    ed_ch.setText(ch.read_text(encoding="utf-8"))

    stub = _StubMain(editors=[ed_main, ed_ch])
    with patch("gui.mixins.edit_ops.QInputDialog.getText", return_value=("fig:yeni", True)):
        MainWindow._on_rename_label(stub, "fig:a")

    assert "fig:yeni" in ed_ch.text()
    assert ch.read_text(encoding="utf-8") == "\\ref{fig:a}\n"   # disk değişmedi
    assert ed_ch.isModified()


def test_rename_undo_restores(qapp, tmp_path):
    """Sekme değişikliği tek undo adımıyla geri alınabilir."""
    main = tmp_path / "m.tex"
    main.write_text("\\label{fig:a}\n\\ref{fig:a}\n", encoding="utf-8")
    ed = EditorWidget(); ed._file_path = str(main)
    ed.setText(main.read_text(encoding="utf-8"))

    stub = _StubMain(editors=[ed])
    with patch("gui.mixins.edit_ops.QInputDialog.getText", return_value=("fig:yeni", True)):
        MainWindow._on_rename_label(stub, "fig:a")
    assert "fig:yeni" in ed.text()
    ed.undo()
    assert ed.text() == main.read_text(encoding="utf-8")


def test_rename_duplicate_blocked(qapp, tmp_path):
    """Yeni ad projede varsa engellenir, hiçbir şey değişmez."""
    ch = tmp_path / "ch.tex"
    ch.write_text("\\ref{fig:b}\n", encoding="utf-8")
    main = tmp_path / "m.tex"
    main.write_text("\\label{fig:a}\n\\label{fig:b}\n\\input{ch}\n", encoding="utf-8")
    ed = EditorWidget(); ed._file_path = str(main)
    ed.setText(main.read_text(encoding="utf-8"))

    stub = _StubMain(editors=[ed])
    with patch("gui.mixins.edit_ops.QInputDialog.getText", return_value=("fig:b", True)), \
         patch("gui.mixins.edit_ops.QMessageBox.warning") as warn:
        MainWindow._on_rename_label(stub, "fig:a")

    warn.assert_called_once()
    assert ed.text() == main.read_text(encoding="utf-8")
    assert ch.read_text(encoding="utf-8") == "\\ref{fig:b}\n"


def test_rename_invalid_chars_blocked(qapp, tmp_path):
    main = tmp_path / "m.tex"
    main.write_text("\\label{fig:a}\n", encoding="utf-8")
    ed = EditorWidget(); ed._file_path = str(main)
    ed.setText(main.read_text(encoding="utf-8"))

    stub = _StubMain(editors=[ed])
    with patch("gui.mixins.edit_ops.QInputDialog.getText", return_value=("boşluk lu", True)):
        MainWindow._on_rename_label(stub, "fig:a")
    assert ed.text() == main.read_text(encoding="utf-8")
    assert "Geçersiz" in stub._status.msg


# --- F2 cite: .bib anahtarını tüm \cite kullanımlarıyla değiştirme ---


def test_f2_on_cite_arg(qapp):
    ed = EditorWidget()
    ed.setText("bkz \\cite{karaca2024} burada\n")
    caught = []
    ed.rename_cite_requested.connect(caught.append)
    ed.setCursorPosition(0, len("bkz \\cite{karaca2024") - 1)
    ed._request_rename()
    assert caught == ["karaca2024"]


def test_f2_in_bib_file_on_entry(qapp):
    ed = EditorWidget()
    ed._file_path = "/x/refs.bib"
    ed.setText("@article{karaca2024,\n title={X},\n}\n")
    caught = []
    ed.rename_cite_requested.connect(caught.append)
    ed.setCursorPosition(0, len("@article{karaca2024") - 1)
    ed._request_rename()
    assert caught == ["karaca2024"]


def test_f2_BUYUK_HARFLI_bib_dosyasinda_da_calisiyor(qapp):
    """`.BIB` uzantısı da .bib sayılmalı; F2 sessizce ölmemeli.

    Uzantı süzgeci harf duyarlıydı: `.BIB` dosyasında F2 bib dalına hiç
    girmiyor, satırı `\\label`/`\\bibitem` diye arayıp bulamıyor ve
    hiçbir şey yapmıyordu.
    """
    ed = EditorWidget()
    ed._file_path = "/x/refs.BIB"
    ed.setText("@article{karaca2024,\n title={X},\n}\n")
    caught = []
    ed.rename_cite_requested.connect(caught.append)
    ed.setCursorPosition(0, len("@article{karaca2024") - 1)
    ed._request_rename()
    assert caught == ["karaca2024"]


def test_rename_cite_BUYUK_HARFLI_bib_editorunden_TEX_i_de_degistiriyor(
        qapp, tmp_path):
    r"""`.BIB` editöründen F2: makaledeki `\cite` de değişmeli.

    `_on_rename_cite` dal kararını `ed.file_path.endswith('.bib')` ile
    veriyordu. `.BIB` yanlış dala girince `base_path` .bib'in KENDİSİ
    oluyor, `find_bib_path` bir .bib içinde `\bibliography` arayıp boş
    dönüyor ve değiştirilecek listede yalnız .bib kalıyordu: girdi yeni
    ada geçiyor, makaledeki `\cite{eski}` olduğu gibi kalıyor ve
    kaynakçada `[?]` basılıyordu.
    """
    bib = tmp_path / "refs.BIB"
    bib.write_text("@article{karaca2024,\n title={X},\n}\n", encoding="utf-8")
    tex = tmp_path / "m.tex"
    tex.write_text("\\addbibresource{refs.BIB}\n\\cite{karaca2024}\n",
                   encoding="utf-8")
    ed = EditorWidget()
    ed._file_path = str(bib)
    ed.setText(bib.read_text(encoding="utf-8"))

    stub = _StubMain(editors=[ed])
    with patch("gui.mixins.edit_ops.QInputDialog.getText",
               return_value=("yeni2024", True)):
        MainWindow._on_rename_cite(stub, "karaca2024")

    assert ed.text().startswith("@article{yeni2024,"), ".bib girdisi değişmedi"
    tex_disk = tex.read_text(encoding="utf-8")
    assert "yeni2024" in tex_disk, "makaledeki \\cite değişmedi (sarkan atıf)"
    assert "\\cite{karaca2024}" not in tex_disk


def test_rename_cite_updates_tex_chain_and_bib(qapp, tmp_path):
    """Ana dosya sekmede, çocuk + .bib diskte → üçü de değişir."""
    bib = tmp_path / "refs.bib"
    bib.write_text("@article{karaca2024,\n title={X},\n}\n", encoding="utf-8")
    ch = tmp_path / "ch.tex"
    ch.write_text("bakın \\citep{karaca2024} ve \\cite{karaca2024, baska}\n", encoding="utf-8")
    main = tmp_path / "m.tex"
    main.write_text("\\addbibresource{refs.bib}\n\\input{ch}\n\\cite{karaca2024}\n", encoding="utf-8")
    ed = EditorWidget()
    ed._file_path = str(main)
    ed.setText(main.read_text(encoding="utf-8"))

    stub = _StubMain(editors=[ed])
    with patch("gui.mixins.edit_ops.QInputDialog.getText", return_value=("yeni2024", True)):
        MainWindow._on_rename_cite(stub, "karaca2024")

    assert ed.text().count("yeni2024") == 1
    ch_disk = ch.read_text(encoding="utf-8")
    assert ch_disk.count("yeni2024") == 2          # \citep + çoklu \cite segmenti
    assert "karaca2024" not in ch_disk
    bib_disk = bib.read_text(encoding="utf-8")
    assert bib_disk.startswith("@article{yeni2024,")
    assert "3 dosya" in stub._status.msg


def test_rename_yazilamayan_dosyayi_bildiriyor(qapp, tmp_path):
    """Kısmi yeniden adlandırma sessiz geçemez: uyarı diyaloğu çıkmalı.

    Salt okunur .bib ile .tex değişip .bib değişmiyordu; kullanıcı ise
    'N dosya' başarı mesajı görüyor, sonraki derlemede atıflar '[?]' basıyordu.
    """
    bib = tmp_path / "refs.bib"
    bib.write_text("@article{karaca2024,\n title={X},\n}\n", encoding="utf-8")
    main = tmp_path / "m.tex"
    main.write_text("\\addbibresource{refs.bib}\n\\cite{karaca2024}\n", encoding="utf-8")
    ed = EditorWidget()
    ed._file_path = str(main)
    ed.setText(main.read_text(encoding="utf-8"))

    # Yazma hatası doğrudan üretiliyor: gerçek tetikleyici platforma göre
    # değişiyor (Windows'ta salt okunur DOSYA yeter; Linux'ta os.replace
    # dizin iznine baktığı için salt okunur DİZİN gerekiyor). Test edilen
    # şey tetikleyici değil, hatanın kullanıcıya bildirilmesi.
    from gui.editor import EditorWidget as _EW
    gercek = _EW._write_atomic

    def yazamaz(path, text, enc):
        if str(path).endswith(".bib"):
            raise OSError(13, "Permission denied")
        return gercek(path, text, enc)

    stub = _StubMain(editors=[ed])
    with patch.object(_EW, "_write_atomic", staticmethod(yazamaz)), \
         patch("gui.mixins.edit_ops.QInputDialog.getText",
               return_value=("yeni2024", True)), \
         patch("gui.mixins.edit_ops.QMessageBox.warning") as uyari:
        MainWindow._on_rename_cite(stub, "karaca2024")

    assert uyari.called, "yazılamayan dosya için uyarı çıkmadı"
    metin = " ".join(str(a) for a in uyari.call_args[0])
    assert "refs.bib" in metin, "uyarı hangi dosyanın elde kaldığını söylemiyor"
    # .bib gerçekten değişmedi — sessizce 'başarılı' denmemeli
    assert "karaca2024" in bib.read_text(encoding="utf-8")
    assert "yeniden adlandırıldı" not in stub._status.msg


def test_rename_cite_from_bib_editor(qapp, tmp_path):
    """.bib sekmede tetiklenirse: .bib arabelleği + kullanım dosyası (disk) değişir."""
    bib = tmp_path / "refs.bib"
    bib.write_text("@article{k, title={X}}\n", encoding="utf-8")
    main = tmp_path / "m.tex"
    main.write_text("\\bibliography{refs}\n\\cite{k}\n", encoding="utf-8")
    ed_bib = EditorWidget(); ed_bib._file_path = str(bib)
    ed_bib.setText(bib.read_text(encoding="utf-8"))

    stub = _StubMain(editors=[ed_bib])
    with patch("gui.mixins.edit_ops.QInputDialog.getText", return_value=("yeni", True)):
        MainWindow._on_rename_cite(stub, "k")

    assert "@article{yeni," in ed_bib.text()
    assert "\\cite{yeni}" in main.read_text(encoding="utf-8")
    assert "2 dosya" in stub._status.msg


def test_rename_cite_duplicate_blocked(qapp, tmp_path):
    bib = tmp_path / "refs.bib"
    bib.write_text("@article{a, title={X}}\n@book{b, title={Y}}\n", encoding="utf-8")
    main = tmp_path / "m.tex"
    main.write_text("\\bibliography{refs}\n\\cite{a}\n", encoding="utf-8")
    ed = EditorWidget(); ed._file_path = str(main)
    ed.setText(main.read_text(encoding="utf-8"))

    stub = _StubMain(editors=[ed])
    with patch("gui.mixins.edit_ops.QInputDialog.getText", return_value=("b", True)), \
         patch("gui.mixins.edit_ops.QMessageBox.warning") as warn:
        MainWindow._on_rename_cite(stub, "a")

    warn.assert_called_once()
    assert "\\cite{a}" in ed.text()
    assert "@article{a," in bib.read_text(encoding="utf-8")


# --- F2 fallback: Alt+tıkla satır başına gelinen durum (imleç argüman dışında) ---


def test_f2_bib_entry_line_start(qapp):
    """Alt+tık .bib girdisine zıplar → imleç sütun 0'da; F2 yine çalışmalı."""
    ed = EditorWidget()
    ed._file_path = "/x/refs.bib"
    ed.setText("@article{karaca2024,\n title={X},\n}\n")
    caught = []
    ed.rename_cite_requested.connect(caught.append)
    ed.setCursorPosition(0, 0)
    ed._request_rename()
    assert caught == ["karaca2024"]


def test_f2_cite_line_start(qapp):
    """Alt+tık kullanıma zıplar → imleç sütun 0'da; satırdaki cite yakalanır."""
    ed = EditorWidget()
    ed.setText("Metin \\cite{karaca2024} burada.\n")
    caught = []
    ed.rename_cite_requested.connect(caught.append)
    ed.setCursorPosition(0, 0)
    ed._request_rename()
    assert caught == ["karaca2024"]


def test_f2_label_line_start(qapp):
    ed = EditorWidget()
    ed.setText("Metin \\label{fig:a} burada.\n")
    caught = []
    ed.rename_label_requested.connect(caught.append)
    ed.setCursorPosition(0, 0)
    ed._request_rename()
    assert caught == ["fig:a"]


# --- F2 tuş basışı (keyPressEvent dalı) ---


def test_f2_keypress_triggers(qapp):
    """Gerçek QKeyEvent ile F2 → imleç altındaki anahtar yakalanır."""
    ed = EditorWidget()
    ed.setText("\\label{fig:a}\n")
    caught = []
    ed.rename_label_requested.connect(caught.append)
    ed.setCursorPosition(0, 7)
    ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_F2, Qt.KeyboardModifier.NoModifier)
    ed.keyPressEvent(ev)
    assert caught == ["fig:a"]


def test_f2_with_modifier_ignored(qapp):
    """Ctrl+F2 yakalanmaz — pencere/menü kısayollarına kalır."""
    ed = EditorWidget()
    ed.setText("\\label{fig:a}\n")
    caught = []
    ed.rename_label_requested.connect(caught.append)
    ed.setCursorPosition(0, 7)
    ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_F2,
                   Qt.KeyboardModifier.ControlModifier)
    ed.keyPressEvent(ev)
    assert caught == []


# --- kodlama round-trip: eski Türkçe (cp1254) zincir dosyası ---


def test_rename_preserves_legacy_encoding(qapp, tmp_path):
    """Diskteki çocuk cp1254 ise rename sonrası da cp1254 kalmalı (baytlar bozulmaz)."""
    ch_bytes = "metin \\ref{fig:a} ve Türkçe karakter: şğı\n".encode("cp1254")
    (tmp_path / "ch.tex").write_bytes(ch_bytes)
    main = tmp_path / "m.tex"
    main.write_text("\\label{fig:a}\n\\input{ch}\n", encoding="utf-8")
    ed = EditorWidget()
    ed._file_path = str(main)
    ed.setText(main.read_text(encoding="utf-8"))

    stub = _StubMain(editors=[ed])
    with patch("gui.mixins.edit_ops.QInputDialog.getText", return_value=("fig:yeni", True)):
        MainWindow._on_rename_label(stub, "fig:a")

    raw = (tmp_path / "ch.tex").read_bytes()
    # cp1254 olarak decode edilip birebir korunmuş olmalı; utf-8'e dönüşmemiş
    assert raw.decode("cp1254") == "metin \\ref{fig:yeni} ve Türkçe karakter: şğı\n"
    assert "şğı".encode("cp1254") in raw


# --- F2 bibitem: el ile kaynakça (thebibliography) ---


def test_f2_on_bibitem_arg(qapp):
    ed = EditorWidget()
    ed.setText("\\bibitem[Yazar(2020)]{karaca2024} Açıklama.\n")
    caught = []
    ed.rename_bibitem_requested.connect(caught.append)
    ed.setCursorPosition(0, len("\\bibitem[Yazar(2020)]{karaca2024") - 1)
    ed._request_rename()
    assert caught == ["karaca2024"]


def test_f2_bibitem_line_start_fallback(qapp):
    """Alt+tıkla kullanıma gidip döndükten sonra \bibitem satırında F2."""
    ed = EditorWidget()
    ed.setText("\\bibitem{karaca2024} Açıklama.\n")
    caught = []
    ed.rename_bibitem_requested.connect(caught.append)
    ed.setCursorPosition(0, 0)
    ed._request_rename()
    assert caught == ["karaca2024"]


def test_rename_bibitem_updates_chain(qapp, tmp_path):
    r"""bibitem + zincirdeki tüm \cite kullanımları birlikte değişir."""
    ch = tmp_path / "ch.tex"
    ch.write_text("bakın \\cite{karaca2024} ve \\cite{karaca2024, baska}\n", encoding="utf-8")
    main = tmp_path / "m.tex"
    main.write_text(
        "\\begin{thebibliography}{}\n"
        "\\bibitem{karaca2024} K.\n"
        "\\end{thebibliography}\n"
        "\\input{ch}\n", encoding="utf-8")
    ed = EditorWidget()
    ed._file_path = str(main)
    ed.setText(main.read_text(encoding="utf-8"))

    stub = _StubMain(editors=[ed])
    with patch("gui.mixins.edit_ops.QInputDialog.getText", return_value=("yeni2024", True)):
        MainWindow._on_rename_bibitem(stub, "karaca2024")

    assert "\\bibitem{yeni2024} K." in ed.text()
    ch_disk = ch.read_text(encoding="utf-8")
    assert ch_disk.count("yeni2024") == 2
    assert "karaca2024" not in ch_disk
    assert "2 dosya" in stub._status.msg


def test_rename_bibitem_duplicate_blocked(qapp, tmp_path):
    main = tmp_path / "m.tex"
    main.write_text(
        "\\bibitem{a} X.\n\\bibitem{b} Y.\n", encoding="utf-8")
    ed = EditorWidget()
    ed._file_path = str(main)
    ed.setText(main.read_text(encoding="utf-8"))

    stub = _StubMain(editors=[ed])
    with patch("gui.mixins.edit_ops.QInputDialog.getText", return_value=("b", True)), \
         patch("gui.mixins.edit_ops.QMessageBox.warning") as warn:
        MainWindow._on_rename_bibitem(stub, "a")

    warn.assert_called_once()
    assert ed.text() == main.read_text(encoding="utf-8")

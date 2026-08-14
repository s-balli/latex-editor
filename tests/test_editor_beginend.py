"""EditorWidget eşleşen \\begin/\\end vurgulama testleri (C.11).

İmleç bir \\begin{X} veya \\end{X} üzerindeyken eşleşen tag (iç içe ve farklı
adları sayarak) bulunur ve ikisi indicator ile vurgulanır.
"""

import pytest

try:
    from PyQt6.QtCore import QEvent, Qt
    from PyQt6.QtGui import QKeyEvent
    from PyQt6.QtWidgets import QApplication
    from gui.editor import EditorWidget
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / gui.editor import edilemiyor", allow_module_level=True)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _ensure_qapp(qapp):
    """Tüm testler EditorWidget kurar; QApplication'ı garantile."""

def _editor():
    return EditorWidget()


def _setup(text):
    ed = _editor()
    ed.setText(text)
    return ed


def _right_key():
    """Imleç hareketi taklidi yapan zararsız bir tuş olayı (metin eklemez)."""
    return QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Right, Qt.KeyboardModifier.NoModifier)


B_BEGIN = len("\\begin{a}")     # 9
B_END = len("\\end{a}")         # 7


# --- tag ayrıştırma ---


def test_get_tags_parses_begin_and_end():
    ed = _setup("\\begin{a}\nx\n\\end{a}")
    tags = ed._get_beginend_tags()
    assert (0, 0, B_BEGIN, "begin", "a") in tags
    assert (2, 0, B_END, "end", "a") in tags
    assert len(tags) == 2


def test_get_tags_trailing_newline():
    """Sondaki boş satır tag satır numarasını kaydırmaz (split('\n') seçimi)."""
    ed = _setup("a\n\\begin{a}\n")   # satırlar: "a", "\\begin{a}", ""
    tags = ed._get_beginend_tags()
    assert (1, 0, B_BEGIN, "begin", "a") in tags
    assert len(tags) == 1


def test_get_tags_crlf_document():
    """\\r\\n EOL'li belgede tag'ler doğru satırda (split('\\n') \r'yi satır sonunda bırakır)."""
    ed = _setup("\\begin{a}\r\n\\end{a}\r\n")
    tags = ed._get_beginend_tags()
    assert (0, 0, B_BEGIN, "begin", "a") in tags
    assert (1, 0, B_END, "end", "a") in tags
    assert len(tags) == 2


# --- eşleşme algoritması ---


def test_match_begin_to_end():
    ed = _setup("\\begin{equation}\nx\n\\end{equation}")
    cur = (0, 0, len("\\begin{equation}"), "begin", "equation")
    m = ed._find_matching_tag(cur)
    assert m is not None
    assert m[0] == 2                       # \end satırı


def test_match_end_to_begin():
    ed = _setup("\\begin{a}\nx\n\\end{a}")
    cur = (2, 0, B_END, "end", "a")
    m = ed._find_matching_tag(cur)
    assert m is not None
    assert m[0] == 0                       # \begin satırı


def test_match_nested_same_name():
    # \begin{a} \begin{a} x \end{a} \end{a}
    ed = _setup("\\begin{a}\n\\begin{a}\nx\n\\end{a}\n\\end{a}")
    outer = ed._find_matching_tag((0, 0, B_BEGIN, "begin", "a"))
    inner = ed._find_matching_tag((1, 0, B_BEGIN, "begin", "a"))
    assert outer[0] == 4                   # en dıştaki \end
    assert inner[0] == 3                   # içteki \end


def test_match_different_names_skip_unrelated():
    # \begin{a} \begin{b} \end{b} \end{a}
    ed = _setup("\\begin{a}\n\\begin{b}\n\\end{b}\n\\end{a}")
    m = ed._find_matching_tag((0, 0, B_BEGIN, "begin", "a"))
    assert m[0] == 3                       # \end{a}; b bloğu atlanır
    m = ed._find_matching_tag((1, 0, len("\\begin{b}"), "begin", "b"))
    assert m[0] == 2                       # \end{b}


def test_match_starred_environment():
    ed = _setup("\\begin{equation*}\n\\end{equation*}")
    m = ed._find_matching_tag((0, 0, len("\\begin{equation*}"), "begin", "equation*"))
    assert m is not None
    assert m[0] == 1                       # \end{equation*} satır 1


def test_match_unmatched_returns_none():
    ed = _setup("\\begin{a}\nx")           # \end yok
    assert ed._find_matching_tag((0, 0, B_BEGIN, "begin", "a")) is None


# --- vurgu uygulama ---


def test_update_highlight_on_tag(qapp):
    ed = _setup("\\begin{a}\n\\end{a}")
    ed._update_beginend_highlight(0, 3)    # imleç \begin{a} üzerinde
    assert len(ed._beginend_ranges) == 2   # her iki tag vurgulu


def test_update_highlight_not_on_tag(qapp):
    ed = _setup("hello\n\\begin{a}\n\\end{a}")
    ed._update_beginend_highlight(0, 2)    # imleç "hello" üzerinde
    assert len(ed._beginend_ranges) == 0


def test_update_highlight_unmatched_no_highlight(qapp):
    ed = _setup("\\begin{a}\nx")           # \end yok
    ed._update_beginend_highlight(0, 3)
    assert len(ed._beginend_ranges) == 0   # eşleşme yok -> vurgu yok


def test_keypress_triggers_highlight(qapp):
    """Tuş olayı imleç konumuna göre vurguyu günceller (C.11 kanca)."""
    ed = _setup("\\begin{a}\n\\end{a}")
    ed.setCursorPosition(0, 3)             # caret \begin{a} üzerinde
    ed.keyPressEvent(_right_key())         # kanca -> _update_beginend_highlight
    assert len(ed._beginend_ranges) == 2


def test_keypress_moving_off_tag_clears(qapp):
    """Tag dışına imleç gidince vurgu temizlenir."""
    ed = _setup("x\n\\begin{a}\n\\end{a}")
    ed.setCursorPosition(1, 3)             # \begin{a} üzerinde -> vurgu
    ed.keyPressEvent(_right_key())
    assert len(ed._beginend_ranges) == 2
    ed.setCursorPosition(0, 0)             # "x" satırına (tag dışı)
    ed.keyPressEvent(_right_key())         # kanca -> temizlenir
    assert len(ed._beginend_ranges) == 0


# --- UTF-8 byte aralığı ---


def test_tag_byte_range_utf8_prefix():
    """Türkçe önek sonrası tag byte offseti doğru (char != byte)."""
    ed = _setup("Çığ \\begin{a}\n\\end{a}")
    # "Çığ " = 4 karakter, 7 bayt (Ç,ı,ğ 2'şer + boşluk 1)
    byte_start, byte_len = ed._tag_byte_range(0, 4, 4 + B_BEGIN)
    assert byte_start == 7
    assert byte_len == B_BEGIN             # tag ASCII -> byte == char


def test_highlight_ranges_match_tag_bytes(qapp):
    ed = _setup("Çığ \\begin{a}\n\\end{a}")
    ed._update_beginend_highlight(0, 7)    # imleç \begin{a} içinde (char 7)
    # ilk range \begin{a}: byte 7'den 9 bayt
    assert (7, B_BEGIN) in ed._beginend_ranges


# --- önbellek ---


def test_cache_invalidated_on_text_change(qapp):
    ed = _setup("\\begin{a}\n\\end{a}")
    ed._get_beginend_tags()
    assert ed._beginend_tags_cache is not None
    ed.setText("\\begin{b}\n\\end{b}")
    assert ed._beginend_tags_cache is None  # textChanged -> invalid

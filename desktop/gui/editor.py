"""QScintilla tabanlı LaTeX kod editörü."""

import bisect
import os
import re
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication, QMessageBox

from core.log import get_logger
from core.latex_refs import collect_cite_keys, collect_image_paths, collect_input_paths, collect_labels
from PyQt6.QtCore import QCoreApplication

_ = lambda s: QCoreApplication.translate("EditorWidget", s)
_logger = get_logger("editor")
from PyQt6.Qsci import QsciScintilla
from PyQt6.QtCore import pyqtSignal

from syntax.latex_lexer import LatexLexer


# Otomatik parantezleme eşleştirmeleri — açma → kapanma
_PAIRS = {'(': ')', '[': ']', '{': '}', '$': '$'}

# Otomatik tamamlama ile seçilen \cmd{ / \cmd[ girdisinin kapanışı
_CLOSE_FOR_OPEN = {'{': '}', '[': ']'}

# Eşleşen \begin{X} / \end{X} tag'lerini yakala (C.11)
_BEGINEND_RE = re.compile(r'\\(begin|end)\s*\{([A-Za-z]+\*?)\}')

# Alt+tık ile \ref/\cite tanıma git: tıklanan konumdaki argümanı yakala.
# (cite ailesi opsiyonel [...] argümanları olabilir: \citep[see][]{key})
_RE_REFARG = re.compile(r'\\(?:ref|eqref|pageref|autoref|nameref|vref|cref|Cref)\s*\{([^}]*)\}')
_RE_CITEARG = re.compile(
    r'\\(?:cite|citep|citet|citeauthor|citeyear|citealp|parencite|textcite|nocite)'
    r'\s*(?:\[[^\]]*\]\s*)*\{([^}]*)\}'
)
# .bib girdi anahtarı: @article{key, — Alt+tık ile makaledeki \cite yerine git
_RE_BIBENTRY = re.compile(r'@\w+\s*\{\s*([^,\s}]+)\s*,')
# \bibitem{key} (thebibliography) — Alt+tık ile ters yön: makaledeki \cite yerine
_RE_BIBITEMARG = re.compile(r'\\bibitem\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}')
# \label{key} — F2 yeniden adlandırma için imleç altındaki anahtar
_RE_LABELARG = re.compile(r'\\label\s*\{([^}]*)\}')


def _decode_bytes(raw: bytes) -> tuple[str, str]:
    """Baytları decode et -> (metin, encoding).

    UTF-8 (katı) önce denenir; başarısız olursa eski Türkçe kodlamalar (cp1254 /
    iso-8859-9). Böylece eski Türkçe LaTeX dosyaları errors='replace' ile sessizce
    bozulmaz (her bayt tanımlı bir karaktere eşlenir). Dönen encoding ile kayıt
    edilirse baytlar birebir korunur (round-trip güvenli).

    Not: charset_normalizer Türkçe tek-baytlı kodlamaları yanlışca cp1252
    tespit ettiği için kullanılmaz; cp1254 doğrudan Türkçe harfleri doğru verir
    ve yaygın Batı Avrupa metniyle de büyük oranda uyuşur.
    """
    try:
        return raw.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        pass
    for enc in ("cp1254", "iso-8859-9"):
        try:
            return raw.decode(enc), enc
        except (UnicodeDecodeError, LookupError):
            continue
    # Son çare (normalde ulaşılmaz — cp1254 tüm baytları karşılar).
    return raw.decode("utf-8", errors="replace"), "utf-8"


class EditorWidget(QsciScintilla):
    forward_search_requested = pyqtSignal(str, int, int)  # file_path, line(1-based), col(1-based)
    image_paste_requested = pyqtSignal()  # Ctrl+V + panoda resim → resim yapıştırma
    goto_definition_requested = pyqtSignal(str, str)  # key, kind("label"|"cite") — Alt+tık
    rename_label_requested = pyqtSignal(str)  # key — F2
    rename_cite_requested = pyqtSignal(str)   # bib anahtarı — F2 (\cite veya .bib girdisi)
    rename_bibitem_requested = pyqtSignal(str)  # thebibliography anahtarı — F2 (\bibitem)

    def __init__(self, parent=None, *, theme: dict = None):
        super().__init__(parent)
        self._file_path = ""
        self._detected_engine = ""
        self._initial_theme = theme
        self._encoding = "utf-8"
        self._newline = "lf"      # dosyanın satır sonu stili ('lf' | 'crlf'); kayıtta korunur
        self._font_size = 11      # ayarlardan (apply_editor_settings) değişir
        self._theme = None        # son uygulanan tema (font boyutu korunarak yeniden uygulanır)
        self._setup_editor()

    def _setup_editor(self):
        lexer = LatexLexer(self)
        self.setLexer(lexer)

        self.setMarginLineNumbers(1, True)
        self.setMarginWidth(1, "0000")
        self.linesChanged.connect(self._update_margin_width)

        # Derleme hataları için gutter (margin 0) işareti.
        self._ERR_MARKER = 10
        self.setMarginType(0, QsciScintilla.MarginType.SymbolMargin)
        self.setMarginWidth(0, 16)
        self.setMarginMarkerMask(0, 1 << self._ERR_MARKER)
        self.markerDefine(QsciScintilla.MarkerSymbol.Circle, self._ERR_MARKER)

        # C.11: eşleşen \begin/\end vurgulama
        self._beginend_indicator = 0
        self._beginend_ranges = []          # vurgulu byte aralıkları (temizlik için)
        self._beginend_tags_cache = None     # doküman tag listesi (textChanged'de invalid)
        self.cursorPositionChanged.connect(self._update_beginend_highlight)
        self.textChanged.connect(self._invalidate_beginend_cache)
        self.SendScintilla(QsciScintilla.SCI_INDICSETSTYLE, self._beginend_indicator,
                           QsciScintilla.INDIC_FULLBOX)
        self.SendScintilla(QsciScintilla.SCI_INDICSETALPHA, self._beginend_indicator, 60)
        self.setFolding(QsciScintilla.FoldStyle.PlainFoldStyle, 2)
        self.setWrapMode(QsciScintilla.WrapMode.WrapWord)
        self.setTabWidth(4)
        self.setIndentationGuides(True)
        self.setAutoIndent(True)
        self.setBraceMatching(QsciScintilla.BraceMatch.SloppyBraceMatch)
        self.setCaretLineVisible(True)
        self.setAutoFillBackground(True)
        self.setMinimumWidth(300)

        if self._initial_theme:
            self.apply_theme(self._initial_theme)

        # Otomatik tamamlama kabul edilince \cmd{ / \cmd[ kapanışını ekle.
        # Popup seçimi keyPressEvent'i atladığı için normal autopair tetiklenmez;
        # bu yüzden tamamlama sinyalinde manuel kapatıyoruz.
        self.SCN_AUTOCCOMPLETED.connect(self._on_autoc_completed)

    def _update_margin_width(self):
        """Satır numarası margin'ini satır sayısına göre dinamik genişlet (C.10).

        Sabit 4 hane yerine satır sayısının basamak sayısına uyar; 9999+ satırlı
        dosyalarda satır numaralarının kesilmesini önler (minimum 4 hane).
        """
        digits = max(4, len(str(self.lines())))
        self.setMarginWidth(1, "0" * digits)

    def clear_error_markers(self):
        """Derleme hatalarının gutter işaretlerini temizle."""
        self.markerDeleteAll(self._ERR_MARKER)

    def add_error_marker(self, line_1based: int):
        """Belirli bir satıra hata işareti koy (gutter). 1-based satır."""
        ln = line_1based - 1
        if 0 <= ln < self.lines():
            self.markerAdd(ln, self._ERR_MARKER)

    @staticmethod
    def _hex_to_scintilla(hex_color: str) -> int:
        h = hex_color.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return (b << 16) | (g << 8) | r

    def apply_theme(self, t: dict):
        self._theme = t
        c = lambda key: QColor(t[key])
        s = lambda key: self._hex_to_scintilla(t[key])

        self.SendScintilla(QsciScintilla.SCI_STYLESETBACK, 32, s("bg_primary"))
        self.SendScintilla(QsciScintilla.SCI_STYLESETFORE, 32, s("fg_editor"))

        self.setColor(c("fg_editor"))
        self.setPaper(c("bg_primary"))
        self.setCaretForegroundColor(c("fg_editor"))
        self.setMarginsForegroundColor(c("fg_line_numbers"))
        self.setMarginsBackgroundColor(c("bg_primary"))
        self.setSelectionBackgroundColor(c("accent_selection"))
        self.setSelectionForegroundColor(c("fg_bright"))
        self.setFoldMarginColors(c("bg_primary"), c("bg_primary"))
        self.setCaretLineBackgroundColor(c("bg_hover"))

        pal = self.palette()
        pal.setColor(QPalette.ColorRole.Window, c("bg_primary"))
        pal.setColor(QPalette.ColorRole.Base, c("bg_primary"))
        pal.setColor(QPalette.ColorRole.WindowText, c("fg_editor"))
        pal.setColor(QPalette.ColorRole.Text, c("fg_editor"))
        self.setPalette(pal)

        if self.lexer():
            self.lexer().apply_theme(t, self._font_size)

        # C.11: eşleşen \begin/\end vurgu kutusu rengi
        self.SendScintilla(QsciScintilla.SCI_INDICSETFORE, 0,
                           self._hex_to_scintilla(t.get("accent", "#3a6ea5")))

        # Derleme hata işareti (gutter) rengi.
        self.SendScintilla(QsciScintilla.SCI_MARKERSETBACK, self._ERR_MARKER,
                           self._hex_to_scintilla(t.get("error", "#c62828")))
        self.SendScintilla(QsciScintilla.SCI_MARKERSETFORE, self._ERR_MARKER,
                           self._hex_to_scintilla(t.get("fg_bright", "#ffffff")))

    def apply_editor_settings(self, tab_width: int, font_size: int, wrap: bool):
        """Ayarlar dialogu değerlerini uygula; tema yeniden uygulansa da korunur."""
        self._font_size = font_size
        self.setTabWidth(tab_width)
        self.setWrapMode(QsciScintilla.WrapMode.WrapWord if wrap
                         else QsciScintilla.WrapMode.WrapNone)
        if self._theme:
            self.apply_theme(self._theme)

    def mousePressEvent(self, event):
        if (event.button() == Qt.MouseButton.LeftButton and self._file_path):
            mods = event.modifiers()
            if mods & Qt.KeyboardModifier.ControlModifier:
                # Ctrl+tık → SyncTeX forward-search (editör→PDF)
                pos = self.SendScintilla(
                    self.SCI_POSITIONFROMPOINT,
                    int(event.position().toPoint().x()),
                    int(event.position().toPoint().y()),
                )
                if pos >= 0:
                    line, col = self.lineIndexFromPosition(pos)
                    self.forward_search_requested.emit(self._file_path, line + 1, col + 1)
                    return
            elif mods & Qt.KeyboardModifier.AltModifier:
                # Alt+tık → \ref/\cite tanıma git (\label veya .bib girişi);
                # .bib dosyasındaysa ters yön: girdiden makaledeki \cite yerine git
                pos = self.SendScintilla(
                    self.SCI_POSITIONFROMPOINT,
                    int(event.position().toPoint().x()),
                    int(event.position().toPoint().y()),
                )
                if pos >= 0:
                    line, col = self.lineIndexFromPosition(pos)
                    line_text = self.text(line)
                    if self._file_path.endswith('.bib'):
                        key = self._bib_key_at(line_text, col)
                        if key:
                            self.goto_definition_requested.emit(key, "cite-usage")
                            return
                    else:
                        hit = self._ref_cite_key_at(line_text, col)
                        if hit:
                            self.goto_definition_requested.emit(hit[0], hit[1])
                            return
                        # \bibitem{key} üzerinden ters yön: makalede \cite edildiği yere
                        bkey = self._bibitem_key_at(line_text, col)
                        if bkey:
                            self.goto_definition_requested.emit(bkey, "cite-usage")
                            return
        super().mousePressEvent(event)
        self._update_beginend_highlight(*self.getCursorPosition())

    def mouseMoveEvent(self, event):
        mods = event.modifiers()
        if (mods & Qt.KeyboardModifier.ControlModifier) or (mods & Qt.KeyboardModifier.AltModifier):
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.setCursor(Qt.CursorShape.IBeamCursor)
        super().mouseMoveEvent(event)

    def _ref_cite_key_at(self, line_text: str, col: int) -> tuple[str, str] | None:
        """line_text'te col bir \\ref/\\cite ailesi argümanı içindeyse (key, kind).

        kind 'label' (ref ailesi) veya 'cite'. Çok anahtarlı \\cite{a,b,c}'de
        imlece en yakın segmenti döndürür. Alt+tık tanıma git için kullanılır.
        """
        for m in _RE_REFARG.finditer(line_text):
            a, b = m.span(1)
            if a <= col <= b:
                return (self._nearest_key(m.group(1), col - a), "label")
        for m in _RE_CITEARG.finditer(line_text):
            a, b = m.span(1)
            if a <= col <= b:
                return (self._nearest_key(m.group(1), col - a), "cite")
        return None

    @staticmethod
    def _nearest_key(keys_text: str, offset: int) -> str:
        """'a, b, c' gibi virgülle ayrılmış anahtarlar içinde offset'e düşen segment."""
        start = 0
        last = ""
        for part in keys_text.split(','):
            k = part.strip()
            if k:
                last = k
            end = start + len(part)
            if offset <= end:
                return k
            start = end + 1  # virgülü atla
        return last

    @staticmethod
    def _bib_key_at(line_text: str, col: int) -> str | None:
        """line_text'te col bir '@type{key,' girdi anahtarındaysa key'i döndür."""
        for m in _RE_BIBENTRY.finditer(line_text):
            a, b = m.span(1)
            if a <= col <= b:
                return m.group(1)
        return None

    @staticmethod
    def _bibitem_key_at(line_text: str, col: int) -> str | None:
        """line_text'te col bir '\\bibitem{key}' girdi anahtarındaysa key'i döndür."""
        for m in _RE_BIBITEMARG.finditer(line_text):
            a, b = m.span(1)
            if a <= col <= b:
                return m.group(1).strip()
        return None

    def keyPressEvent(self, event):
        # F2 -> imleç altındaki \label / \ref / \cite anahtarını yeniden adlandır
        if event.key() == Qt.Key.Key_F2 and not event.modifiers():
            self._request_rename()
            return
        # Ctrl+V + panoda resim varsa resim yapıştırma (metin yapıştırmayı bırak).
        if (event.modifiers() & Qt.KeyboardModifier.ControlModifier and
                event.key() == Qt.Key.Key_V):
            if not QApplication.clipboard().image().isNull():
                self.image_paste_requested.emit()
                return
        # Ctrl+Space -> manuel tamamlama (C.7)
        if (event.modifiers() & Qt.KeyboardModifier.ControlModifier and
                event.key() == Qt.Key.Key_Space):
            self._check_autocomplete(manual=True)
        elif self._handle_autopair(event):
            pass
        else:
            super().keyPressEvent(event)
            text = event.text()
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._smart_indent_after_enter()
            elif text and text.isalpha():
                self._check_autocomplete()
        # C.11: imleç hareketinde eşleşen tag'i vurgula. cursorPositionChanged
        # headless'te programatik harekette tetiklenmediğinden, tuş yolundan da
        # güncelliyoruz (gerçek GUI'de her ikisi de çalışır).
        self._update_beginend_highlight(*self.getCursorPosition())

    # --- Otomatik parantezleme + \begin/\end kapanışı ---

    def _handle_autopair(self, event) -> bool:
        """Açma karakterine kapanışı otomatik ekle; \\begin{ad}'e \\end{ad} kapanışı.
        Olayı tüketirse True döner."""
        text = event.text()
        if not text:
            return False
        has_sel = self.hasSelectedText()

        # Skip-over: imlecin sağındaki karakter yazılan kapanışla aynıysa ekleme, atla
        if not has_sel and text in (')', ']', '}', '$') and self._char_after_cursor() == text:
            line, index = self.getCursorPosition()
            self.setCursorPosition(line, index + 1)
            return True

        # \begin{ad} kapanışı — '}' yazılınca \end{ad} bloğu ekle
        if not has_sel and text == '}':
            m = re.search(r'\\begin\{([A-Za-z]+\*?)$', self._text_before_cursor())
            if m:
                self._insert_begin_end(m.group(1))
                return True

        # Açma karakteri → çift ekle
        if not has_sel and text in _PAIRS:
            # \begin/\end sonrası '{' çiftlenmez — yoksa '}' hiç yazılmaz, \end tetiklenmez
            if text == '{' and re.search(r'\\(begin|end)$', self._text_before_cursor()):
                return False
            self._insert_pair(text, _PAIRS[text])
            return True

        return False

    def _request_rename(self):
        """F2: imleç altındaki anahtara göre doğru yeniden adlandırma sinyali.

        .tex içinde \\label{key}/\\ref ailesi → label rename; \\cite ailesi →
        .bib anahtarı rename. .bib dosyasında girdi anahtarı → bib anahtarı
        rename. İmleç argüman dışındaysa (ör. Alt+tıkla satır başına gelinen
        durumda) satırdaki kullanımın imlece en yakın anahtarı kabul edilir.
        Anahtar MainWindow'da zincirde toplu değiştirilir.
        """
        line, col = self.getCursorPosition()
        line_text = self.text(line)
        if self._file_path.endswith('.bib'):
            key = self._bib_key_at(line_text, col)
            if not key:
                m = _RE_BIBENTRY.search(line_text)
                key = m.group(1) if m else None
            if key:
                self.rename_cite_requested.emit(key)
            return
        for m in _RE_LABELARG.finditer(line_text):
            a, b = m.span(1)
            if a <= col <= b:
                self.rename_label_requested.emit(m.group(1).strip())
                return
        for m in _RE_BIBITEMARG.finditer(line_text):
            a, b = m.span(1)
            if a <= col <= b:
                self.rename_bibitem_requested.emit(m.group(1).strip())
                return
        hit = self._ref_cite_key_at(line_text, col) or self._nearest_family_hit(line_text, col)
        if not hit:
            return
        if hit[1] == "label":
            self.rename_label_requested.emit(hit[0])
        elif hit[1] == "bibitem":
            self.rename_bibitem_requested.emit(hit[0])
        else:
            self.rename_cite_requested.emit(hit[0])

    def _nearest_family_hit(self, line_text: str, col: int) -> tuple[str, str] | None:
        """İmleç argüman dışındaysa satırdaki ilk \\bibitem/\\label/\\ref/\\cite
        kullanımının imlece en yakın segmentini döndür.

        Dönüş: (anahtar, 'label' | 'cite' | 'bibitem').
        """
        for m in _RE_BIBITEMARG.finditer(line_text):
            return (m.group(1).strip(), "bibitem")
        for m in _RE_LABELARG.finditer(line_text):
            return (self._nearest_key(m.group(1), max(0, col - m.start(1))), "label")
        for m in _RE_REFARG.finditer(line_text):
            return (self._nearest_key(m.group(1), max(0, col - m.start(1))), "label")
        for m in _RE_CITEARG.finditer(line_text):
            return (self._nearest_key(m.group(1), max(0, col - m.start(1))), "cite")
        return None

    def _text_before_cursor(self) -> str:
        line, index = self.getCursorPosition()
        return self.text(line)[:index]

    def _char_after_cursor(self) -> str:
        line, index = self.getCursorPosition()
        line_text = self.text(line)
        return line_text[index] if index < len(line_text) else ''

    def _insert_pair(self, open_ch: str, close_ch: str):
        """Açma + kapanma ekle, imleci aralarına koy (tek undo adımı)."""
        line, index = self.getCursorPosition()
        self.beginUndoAction()
        self.insert(open_ch + close_ch)
        self.setCursorPosition(line, index + 1)
        self.endUndoAction()

    def _smart_indent_after_enter(self):
        """Enter'da önceki satır \\begin{X} ile bitiyorsa yeni satırı +1 girintile (C.9).

        Yalnızca 'bare' begin satırı (sonra sadece boşluk) tetikler; aynı satırda
        içerik varsa veya başka bir satırsa dokunmaz. autoIndent zaten önceki
        satırın girintisini kopyaladığı için burada sadece ek bir seviye eklenir.
        """
        line, _ = self.getCursorPosition()
        if line == 0:
            return
        prev = self.text(line - 1).rstrip("\n")
        if not re.search(r'\\begin\{([A-Za-z]+\*?)\}\s*$', prev):
            return
        prev_indent = self.SendScintilla(QsciScintilla.SCI_GETLINEINDENTATION, line - 1)
        new_indent = prev_indent + self.tabWidth()
        self.SendScintilla(QsciScintilla.SCI_SETLINEINDENTATION, line, new_indent)
        self.setCursorPosition(line, len(self.text(line).rstrip("\n")))

    def _insert_begin_end(self, name: str):
        r"""\\begin{ad} → '}' + gövde + \\end{ad}; gövde +1 seviye, \end \\begin hizasında.

        \begin satırının girintisi okunur; gövde satırı bir seviye girintili,
        \end satırı \begin ile aynı hizada yazılır. Böylece iç içe ortamlarda
        hizalama bozulmaz (C.9).
        """
        line, _index = self.getCursorPosition()
        indent = self.SendScintilla(QsciScintilla.SCI_GETLINEINDENTATION, line)
        body_indent = indent + self.tabWidth()
        self.beginUndoAction()
        self.insert("}\n\n\\end{" + name + "}")
        # gövde satırı +1 seviye, \end satırı \begin ile aynı girintide
        self.SendScintilla(QsciScintilla.SCI_SETLINEINDENTATION, line + 1, body_indent)
        self.SendScintilla(QsciScintilla.SCI_SETLINEINDENTATION, line + 2, indent)
        # imleç gövde satırında girintinin sonunda (tab/space fark etmez)
        self.setCursorPosition(line + 1, len(self.text(line + 1).rstrip("\n")))
        self.endUndoAction()

    def _check_autocomplete(self, manual=False):
        line, col = self.getCursorPosition()
        # Yorum/verbatim içinde komut tamamlaması yapma (C.8)
        if col > 0:
            style_before = self.SendScintilla(
                QsciScintilla.SCI_GETSTYLEAT, self._cursor_byte_pos() - 1)
            if style_before in (LatexLexer.COMMENT, LatexLexer.VERBATIM):
                return
        line_text = self.text(line)
        text_before = line_text[:col]

        # \begin{ / \end{ sonrası ortam adı tamamlama (C.6)
        env = re.search(r'\\(?:begin|end)\{([A-Za-z*]*)$', text_before)
        if env:
            self._show_env_completion(env.group(1), manual)
            return

        # \ref{ / \cite{ sonrası doküman-farkında tamamlama
        ref = re.search(r'\\(?:ref|eqref|pageref|autoref|nameref|vref|cref|Cref)\{([A-Za-z0-9_:.\-]*)$',
                        text_before)
        if ref:
            self._show_ref_completion(ref.group(1))
            return
        cite = re.search(r'\\(?:cite|citep|citet|citeauthor|citeyear|citealp|parencite|textcite|nocite)\{([A-Za-z0-9_:.,\-]*)$',
                         text_before)
        if cite:
            self._show_cite_completion(cite.group(1))
            return

        # \includegraphics{ sonrası proje resmi tamamlama (opsiyonel [width=..]
        # argümanı atlanır; bu komut \include dalına da düşmez).
        gfx = re.search(r'\\includegraphics\*?\s*(?:\[[^\]]*\]\s*)?\{([^}]*)$', text_before)
        if gfx:
            self._show_graphics_completion(gfx.group(1))
            return

        # \input{ / \include{ sonrası proje dosyası tamamlama.
        inp = re.search(r'\\(?:input|include)\s*\{([^}]*)$', text_before)
        if inp:
            self._show_input_completion(inp.group(1))
            return

        if not manual and col < 3:
            return

        # \ ile başlayan komut kelimesini bul (manuel modda 0 harfe izin ver)
        pattern = r'\\[a-zA-Z]*$' if manual else r'\\[a-zA-Z]+$'
        match = re.search(pattern, text_before)
        if not match:
            return

        word = match.group(0)
        if not manual and len(word) < 3:  # auto: \ + en az 2 harf
            return

        # Binary search ile eşleşen komutları bul (sorted listede aralık bul)
        lo = bisect.bisect_left(_LATEX_COMMANDS, word)
        if word:
            hi = bisect.bisect_left(_LATEX_COMMANDS, word[:-1] + chr(ord(word[-1]) + 1))
        else:
            hi = len(_LATEX_COMMANDS)
        matches = [cmd for cmd in _LATEX_COMMANDS[lo:hi] if cmd != word]
        if not matches:
            return

        # Autocompletion separator ayarla ve popup göster
        self.SendScintilla(QsciScintilla.SCI_AUTOCSETSEPARATOR, ord(' '))
        entries = " ".join(matches).encode('utf-8')
        self.SendScintilla(QsciScintilla.SCI_AUTOCSHOW, len(word), entries)

    def _show_env_completion(self, typed: str, manual: bool):
        """\\begin{ / \\end{ sonrası yaygın ortam adlarını tamamlar (C.6).

        `typed`: kaşlı ayraçtan sonra yazılan kısmın adı. Auto tetikleme için en az
        1 harf gerekir; manuel (Ctrl+Space) tüm listeyi gösterir.
        """
        if not manual and len(typed) < 1:
            return
        if typed:
            lo = bisect.bisect_left(_LATEX_ENVIRONMENTS, typed)
            hi = bisect.bisect_left(_LATEX_ENVIRONMENTS, typed[:-1] + chr(ord(typed[-1]) + 1))
        else:
            lo, hi = 0, len(_LATEX_ENVIRONMENTS)
        matches = [e for e in _LATEX_ENVIRONMENTS[lo:hi] if e != typed]
        if not matches:
            return
        self.SendScintilla(QsciScintilla.SCI_AUTOCSETSEPARATOR, ord(' '))
        entries = " ".join(matches).encode('utf-8')
        self.SendScintilla(QsciScintilla.SCI_AUTOCSHOW, len(typed), entries)

    def _show_ref_completion(self, typed: str):
        r"""\ref{...} için projedeki \label anahtarlarını öner (doküman-farkında)."""
        try:
            labels = collect_labels(self.text(), self._file_path)
        except Exception:
            _logger.debug("label toplama başarısız", exc_info=True)
            return
        matches = [lab for lab in labels if lab.startswith(typed) and lab != typed]
        if not matches:
            return
        self.SendScintilla(QsciScintilla.SCI_AUTOCSETSEPARATOR, ord(' '))
        entries = " ".join(matches).encode('utf-8')
        self.SendScintilla(QsciScintilla.SCI_AUTOCSHOW, len(typed), entries)

    def _show_cite_completion(self, typed: str):
        r"""\cite{...} için .bib anahtarlarını öner (key1,key2 çoklu destek)."""
        partial = typed.rsplit(',', 1)[-1]   # son virgülden sonraki segment
        try:
            keys = collect_cite_keys(self.text(), self._file_path)
        except Exception:
            _logger.debug("cite anahtar toplama başarısız", exc_info=True)
            return
        matches = [k for k in keys if k.startswith(partial) and k != partial]
        if not matches:
            return
        self.SendScintilla(QsciScintilla.SCI_AUTOCSETSEPARATOR, ord(' '))
        entries = " ".join(matches).encode('utf-8')
        self.SendScintilla(QsciScintilla.SCI_AUTOCSHOW, len(partial), entries)

    def _show_input_completion(self, typed: str):
        r"""\input{...} için projedeki .tex dosyalarını öner (göreli yol, .tex'siz)."""
        if not self._file_path:
            return
        try:
            paths = collect_input_paths(self._file_path)
        except Exception:
            _logger.debug("input dosya toplama başarısız", exc_info=True)
            return
        # Tamamlama listesi ayırıcısı boşluk olduğundan adında boşluk geçen
        # yollar listeye konamaz (popup'a sığmaz).
        matches = [p for p in paths if p.startswith(typed) and p != typed and " " not in p]
        if not matches:
            return
        self.SendScintilla(QsciScintilla.SCI_AUTOCSETSEPARATOR, ord(' '))
        entries = " ".join(matches).encode('utf-8')
        self.SendScintilla(QsciScintilla.SCI_AUTOCSHOW, len(typed), entries)

    def _show_graphics_completion(self, typed: str):
        r"""\includegraphics{...} için projedeki resimleri öner (uzantılı göreli yol)."""
        if not self._file_path:
            return
        try:
            paths = collect_image_paths(self._file_path)
        except Exception:
            _logger.debug("resim dosya toplama başarısız", exc_info=True)
            return
        # Tamamlama listesi ayırıcısı boşluk — adında boşluk geçen yollar
        # listeye konamaz (popup'a sığmaz).
        matches = [p for p in paths if p.startswith(typed) and p != typed and " " not in p]
        if not matches:
            return
        self.SendScintilla(QsciScintilla.SCI_AUTOCSETSEPARATOR, ord(' '))
        entries = " ".join(matches).encode('utf-8')
        self.SendScintilla(QsciScintilla.SCI_AUTOCSHOW, len(typed), entries)

    def _on_autoc_completed(self, text, *rest):
        """Otomatik tamamlama popup'ından seçilen komut kapanış ayracı ekler.

        Popup seçimi SCN_AUTOCCOMPLETED ile gelir ve keyPressEvent'i atladığı için
        normal autopair tetiklenmez. Bu yüzden \\cmd{ / \\cmd[ formundaki girdiler
        seçilince karşılık gelen } / ] eklenir, imleç açılış ve kapanış arasında
        kalır. Böylece elle yazılan \\cmd{ (autopair ile çiftlenir) ile popup'tan
        seçilen aynı komut tutarlı olur.

        \\begin{/\\end{ hariçtir: bunların { ayracı kasıtlı eşlenmez (begin/end
        kapanışı ayrı çalışır). \\left( / \\left\\{ / \\verb| gibi ayraç-sözdizimi
        girdileri regex ile eşleşmez.
        """
        try:
            completed = bytes(text).decode("utf-8", "replace")
        except Exception:
            return
        m = re.match(r'^(\\[a-zA-Z]+)([{\[])$', completed)
        if not m:
            return
        cmd, open_ch = m.group(1), m.group(2)
        if cmd in ("\\begin", "\\end"):
            return
        close = _CLOSE_FOR_OPEN.get(open_ch)
        if not close:
            return
        # Manuel akışta zaten kapanış varsa (autopair eklediyse) çiftleme
        if self._char_after_cursor() == close:
            return
        line, index = self.getCursorPosition()
        self.insert(close)
        self.setCursorPosition(line, index)  # imleç açılış ve kapanış arasında

    # --- C.11: eşleşen \begin/\end vurgulama ---

    def _invalidate_beginend_cache(self):
        """textChanged'te önbelleği bırak ve eski vurguları temizle."""
        self._beginend_tags_cache = None
        self._clear_beginend_highlight()

    def _clear_beginend_highlight(self):
        if not self._beginend_ranges:
            return
        self.SendScintilla(QsciScintilla.SCI_SETINDICATORCURRENT, self._beginend_indicator)
        for start, length in self._beginend_ranges:
            self.SendScintilla(QsciScintilla.SCI_INDICATORCLEARRANGE, start, length)
        self._beginend_ranges = []

    def _highlight_range(self, byte_start: int, byte_len: int):
        self.SendScintilla(QsciScintilla.SCI_SETINDICATORCURRENT, self._beginend_indicator)
        self.SendScintilla(QsciScintilla.SCI_INDICATORFILLRANGE, byte_start, byte_len)
        self._beginend_ranges.append((byte_start, byte_len))

    def _get_beginend_tags(self):
        """Dokümandaki tüm \\begin{X}/\\end{X} tag'leri (satır, char_baş, char_son, kind, ad)."""
        if self._beginend_tags_cache is None:
            tags = []
            # Tek self.text() çek + Python'da split: eski kod her satırda ayrı
            # self.text(ln) (n Scintilla çağrısı) yapıyordu. split('\n') Scintilla
            # satır sayısına en yakın (sondaki boş satırı korur).
            full = self.text()
            for ln, line_text in enumerate(full.split('\n')):
                for m in _BEGINEND_RE.finditer(line_text):
                    tags.append((ln, m.start(), m.end(), m.group(1), m.group(2)))
            self._beginend_tags_cache = tags
        return self._beginend_tags_cache

    def _tag_byte_range(self, line: int, char_start: int, char_end: int) -> tuple[int, int]:
        """Tag'in doküman byte offsetini ve uzunluğunu hesapla (satır-bazlı, UTF-8)."""
        line_byte_start = self.SendScintilla(QsciScintilla.SCI_POSITIONFROMLINE, line)
        lt = self.text(line)
        byte_off = len(lt[:char_start].encode("utf-8"))
        byte_len = len(lt[char_start:char_end].encode("utf-8"))
        return line_byte_start + byte_off, byte_len

    def _cursor_byte_pos(self) -> int:
        """İmlecin doküman byte offseti (satır-bazlı, UTF-8)."""
        line, index = self.getCursorPosition()
        line_byte_start = self.SendScintilla(QsciScintilla.SCI_POSITIONFROMLINE, line)
        lt = self.text(line)
        return line_byte_start + len(lt[:index].encode("utf-8"))

    def _update_beginend_highlight(self, line: int, index: int):
        """İmleç bir \\begin{X}/\\end{X} üzerindeyse eşleşen tag'i vurgula."""
        self._clear_beginend_highlight()
        line_text = self.text(line)
        cur = None
        for m in _BEGINEND_RE.finditer(line_text):
            if m.start() <= index <= m.end():
                cur = (line, m.start(), m.end(), m.group(1), m.group(2))
                break
        if cur is None:
            return
        match = self._find_matching_tag(cur)
        if match is None:
            return
        self._highlight_range(*self._tag_byte_range(cur[0], cur[1], cur[2]))
        self._highlight_range(*self._tag_byte_range(match[0], match[1], match[2]))

    def _find_matching_tag(self, cur):
        """Yığın (stack) ile eşleşen tag'i bul. İç içe ve farklı adları sayar."""
        cur_line, _, _, kind, name = cur
        tags = self._get_beginend_tags()
        cur_idx = None
        for i, (ln, s, e, k, n) in enumerate(tags):
            if ln == cur_line and k == kind and n == name:
                cur_idx = i
                break
        if cur_idx is None:
            return None
        if kind == "begin":
            depth = 0
            for i in range(cur_idx, len(tags)):
                ln, s, e, k, n = tags[i]
                if n != name:
                    continue
                depth += 1 if k == "begin" else -1
                if depth == 0:
                    return (ln, s, e)
            return None
        # end -> geriye doğru
        depth = 0
        for i in range(cur_idx, -1, -1):
            ln, s, e, k, n = tags[i]
            if n != name:
                continue
            depth += 1 if k == "end" else -1
            if depth == 0:
                return (ln, s, e)
        return None

    @property
    def file_path(self) -> str:
        return self._file_path

    def open_file(self, path: str) -> bool:
        try:
            with open(path, "rb") as f:
                raw = f.read()
            # İkili dosya koruması: null bayt -> binary, metin olarak açma
            if b"\x00" in raw[:8192]:
                raise ValueError(_("İkili (binary) dosya; metin editöründe açılamaz."))
            text, encoding = _decode_bytes(raw)
            # Satır sonu stilini hatırla: kayıtta aynen korunur (Windows text-
            # mode yazımı \n'i \r\n'e çevirip \r\r\n üretmesin diye — bu dosyayı
            # derlemez hale getiriyordu)
            self._newline = "crlf" if b"\r\n" in raw[:8192] else "lf"
            # Belge bütünüyle değişiyor: lexer'ın satır-durum önbelleği eski
            # belgeye ait; erken çıkış yanlış eşleşme yapmasın diye sıfırla.
            lexer = self.lexer()
            if lexer is not None:
                lexer.reset_state()
            self.setText(text)
            self._file_path = os.path.normpath(path)
            self._encoding = encoding
            self.setModified(False)
            if encoding != "utf-8":
                _logger.warning("Dosya UTF-8 değil, %s olarak açıldı: %s", encoding, path)
                QMessageBox.warning(
                    self, _("Kodlama Uyarısı"),
                    _("Bu dosya UTF-8 değil ({enc}). {enc} olarak açıldı ve aynı "
                      "kodlamayla kaydedilecek. Sorunsuz derleme için UTF-8'e "
                      "dönüştürmeniz önerilir.").format(enc=encoding),
                )
            return True
        except Exception as e:
            _logger.error("Dosya açılamadı: %s", path, exc_info=True)
            QMessageBox.critical(self, _("Dosya Açma Hatası"), _("Dosya açılamadı:\n{path}\n\n{e}").format(path=path, e=e))
            return False

    @staticmethod
    def _write_atomic(path: str, content: "str | bytes", encoding: str = "utf-8") -> None:
        """Aynı dizinde geçici dosyaya yaz, fsync et, atomik rename ile yerine koy.

        Orijinal dosyaya truncate-on-open ile değil, tamamlanmış geçici dosyanın
        atomik yer değiştirmesiyle yazılır; böylece yazma yarıda kalırsa orijinal
        içerik korunur. Geçici dosya hedefle aynı filesystem'te (aynı dizinde)
        tutulur ki os.replace gerçekten atomik olsun (çapraz-mount rename değil).
        encoding verilirse o kodlamayla yazılır (UTF-8 dışı dosyalar round-trip
        için); bu durumda UnicodeEncodeError da temizlik için yakalanır.
        content bytes ise olduğu gibi yazılır (kodlama dönüşümü YOK — sürümden
        geri yüklemede ham blob'u değiştirmeden yazmanın tek güvenli yolu).
        """
        tmp = path + ".tmp"
        try:
            if isinstance(content, bytes):
                with open(tmp, "wb") as f:
                    f.write(content)
                    f.flush()
                    os.fsync(f.fileno())
            else:
                # newline='' : örtük satır sonu ÇEVRİMİ yok (Windows text-mode
                # \n→\r\n çevirir; içerikte \r\n varsa \r\r\n bozulması üretirdi)
                with open(tmp, "w", encoding=encoding, newline="") as f:
                    f.write(content)
                    f.flush()
                    os.fsync(f.fileno())
            os.replace(tmp, path)
        except (OSError, UnicodeError):
            # Geçici dosya kalmasın; orijinal dokunulmadı (truncate edilmedi).
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def save_file(self) -> bool:
        if not self._file_path:
            return False
        try:
            # Arabellek metnini dosyanın satır sonu stiline indir: QScintilla
            # Windows'ta CRLF üretebilir; çift çevirim (\r\r\n) derlemeyi bozar.
            # Sıra önemli: \r\r\n önce TEK \n'e inmelidir; yoksa iki aşamalı
            # replace onu \n\n yapar (dosyayı çift satıra boğar).
            content = (self.text()
                       .replace("\r\r\n", "\n")
                       .replace("\r\n", "\n")
                       .replace("\r", "\n"))
            if self._newline == "crlf":
                content = content.replace("\n", "\r\n")
            self._write_atomic(self._file_path, content, self._encoding)
            self.setModified(False)
            return True
        except Exception as e:
            _logger.error("Dosya kaydedilemedi: %s", self._file_path, exc_info=True)
            QMessageBox.critical(self, _("Kaydetme Hatası"), _("Dosya kaydedilemedi:\n{path}\n\n{e}").format(path=self._file_path, e=e))
            return False

    def save_file_as(self, path: str) -> bool:
        self._file_path = os.path.normpath(path)
        self._encoding = "utf-8"  # yeni dosya -> modern varsayılan
        self._newline = "lf"      # LaTeX dünyası tercihi; platform bağımsız
        return self.save_file()

    @property
    def display_name(self) -> str:
        if self._file_path:
            return Path(self._file_path).name
        return _("Yeni Dosya")


_LATEX_ENVIRONMENTS = sorted([
    # Belge yapısı
    "document", "abstract", "titlepage", "frontmatter",
    # Bölüm/materyal
    "figure", "figure*", "table", "table*", "tabular", "tabular*", "tabbing",
    "subfigure", "wrapfigure", "minipage", "picture",
    # Matematik
    "equation", "equation*", "align", "align*", "gather", "gather*",
    "multline", "multline*", "eqnarray", "displaymath", "math", "array",
    "cases", "matrix", "pmatrix", "bmatrix", "vmatrix", "Vmatrix", "split",
    # Listeler
    "itemize", "enumerate", "description", "list", "trivlist",
    # Hizalama/blok
    "center", "centering", "flushleft", "flushright", "quote", "quotation",
    "verse",
    # Kod/katı metin
    "verbatim", "verbatim*", "lstlisting", "minted", "comment", "alltt",
    # Teorem benzeri
    "theorem", "proof", "lemma", "corollary", "definition", "proposition",
    "remark", "example",
    # Kaynakça/dizin
    "thebibliography", "theindex",
])


_LATEX_COMMANDS = sorted([
    # Document structure
    "\\documentclass{", "\\begin{", "\\end{",
    "\\section{", "\\subsection{", "\\subsubsection{",
    "\\paragraph{", "\\subparagraph{",
    "\\chapter{", "\\part{", "\\appendix",
    "\\title{", "\\author{", "\\date{", "\\maketitle",
    "\\tableofcontents", "\\listoffigures", "\\listoftables",
    "\\frontmatter", "\\mainmatter", "\\backmatter",

    # Packages & includes
    "\\usepackage{", "\\include{", "\\input{",
    "\\includegraphics{",
    "\\bibliography{", "\\bibliographystyle{", "\\addbibresource{",

    # Cross-references
    "\\label{", "\\ref{", "\\eqref{", "\\pageref{",
    "\\cite{", "\\citep{", "\\citet{", "\\nocite{",
    "\\index{", "\\glossary{",

    # Text formatting
    "\\textbf{", "\\textit{", "\\underline{", "\\emph{",
    "\\textrm{", "\\textsf{", "\\texttt{", "\\textsc{",
    "\\textsl{", "\\textup{",
    "\\textcolor{", "\\colorbox{", "\\fcolorbox{", "\\pagecolor{",

    # Font size
    "\\tiny", "\\scriptsize", "\\footnotesize", "\\small",
    "\\normalsize", "\\large", "\\Large", "\\LARGE", "\\huge", "\\Huge",

    # Paragraph & page
    "\\newline", "\\newpage", "\\clearpage",
    "\\linebreak", "\\nolinebreak", "\\pagebreak", "\\nopagebreak",
    "\\par", "\\indent", "\\noindent",
    "\\centering", "\\raggedright", "\\raggedleft",

    # Spacing
    "\\hspace{", "\\vspace{",
    "\\setlength{", "\\addtolength{",
    "\\settowidth{", "\\settoheight{", "\\settodepth{",
    "\\stretch{", "\\fill",
    "\\linewidth", "\\textwidth", "\\columnwidth", "\\pageheight",
    "\\baselineskip", "\\parindent", "\\parskip",

    # Footnotes & marginalia
    "\\footnote{", "\\footnotetext{", "\\footnotemark", "\\marginpar{",

    # Lists
    "\\item", "\\item[",

    # Tables
    "\\caption{", "\\captionof{",
    "\\multicolumn{", "\\multirow{",
    "\\hline", "\\cline{",
    "\\toprule", "\\midrule", "\\bottomrule",
    "\\figurename", "\\tablename",

    # Custom commands
    "\\newcommand{", "\\renewcommand{", "\\providecommand{", "\\def{",
    "\\newenvironment{", "\\renewenvironment{",
    "\\newlength{", "\\newcounter{",
    "\\setcounter{", "\\stepcounter{", "\\addtocounter{",
    "\\value{", "\\arabic{", "\\roman{", "\\Roman{",
    "\\alph{", "\\Alph{", "\\fnsymbol{",

    # Conditionals
    "\\ifluatex", "\\ifxetex", "\\ifpdftex",
    "\\else", "\\fi", "\\newif",

    # Verbatim & code
    "\\verb|", "\\verbatiminput{", "\\lstinputlisting{", "\\mint{",

    # Boxes
    "\\mbox{", "\\makebox{", "\\fbox{", "\\framebox{",
    "\\parbox{", "\\minipage{", "\\raisebox{", "\\rule{",

    # Floats
    "\\floatstyle{", "\\newfloat{", "\\floatname{", "\\listof{",

    # Hyperlinks
    "\\href{", "\\url{",

    # Theorem-like
    "\\theoremstyle{", "\\newtheorem{",

    # Math: operators
    "\\frac{", "\\dfrac{", "\\tfrac{",
    "\\sqrt{", "\\overline{", "\\underline{",
    "\\hat{", "\\bar{", "\\dot{", "\\ddot{", "\\tilde{", "\\vec{",
    "\\overrightarrow{", "\\overleftarrow{",
    "\\widehat{", "\\widetilde{",
    "\\overbrace{", "\\underbrace{",
    "\\stackrel{", "\\overset{", "\\underset{",

    # Math: big operators
    "\\sum", "\\prod", "\\coprod",
    "\\int", "\\iint", "\\iiint", "\\oint",
    "\\lim", "\\limsup", "\\liminf",
    "\\sup", "\\inf", "\\max", "\\min",
    "\\bigcup", "\\bigcap", "\\bigsqcup",
    "\\bigoplus", "\\bigotimes", "\\bigodot",
    "\\bigvee", "\\bigwedge", "\\biguplus",

    # Math: styles
    "\\mathrm{", "\\mathbf{", "\\mathit{", "\\mathsf{", "\\mathtt{",
    "\\mathcal{", "\\mathbb{", "\\mathfrak{", "\\mathscr{",

    # Math: delimiters
    "\\left(", "\\right)", "\\left[", "\\right]",
    "\\left\\{", "\\right\\}", "\\left|", "\\right|",
    "\\left\\|", "\\right\\|",
    "\\left\\langle", "\\right\\rangle",
    "\\big(", "\\big[", "\\big\\{",
    "\\Big(", "\\Bigg(",

    # Math: binary operators
    "\\cdot", "\\times", "\\div", "\\pm", "\\mp",
    "\\circ", "\\bullet",
    "\\oplus", "\\ominus", "\\otimes", "\\oslash", "\\odot",
    "\\dagger", "\\ddagger", "\\star", "\\ast",
    "\\triangleleft", "\\triangleright", "\\bigtriangleup", "\\bigtriangledown",
    "\\wedge", "\\vee", "\\cap", "\\cup", "\\setminus",
    "\\wr", "\\diamond", "\\amalg",

    # Math: relations
    "\\leq", "\\geq", "\\neq", "\\approx", "\\equiv",
    "\\sim", "\\simeq", "\\cong", "\\propto",
    "\\perp", "\\parallel", "\\mid",
    "\\ll", "\\gg", "\\doteq", "\\models",
    "\\prec", "\\succ", "\\preceq", "\\succeq",
    "\\bowtie", "\\asymp", "\\smile", "\\frown",

    # Math: arrows
    "\\rightarrow", "\\leftarrow",
    "\\Rightarrow", "\\Leftarrow",
    "\\Leftrightarrow", "\\leftrightarrow",
    "\\longrightarrow", "\\longleftarrow",
    "\\Longrightarrow", "\\Longleftarrow",
    "\\Longleftrightarrow", "\\longleftrightarrow",
    "\\uparrow", "\\downarrow",
    "\\Uparrow", "\\Downarrow",
    "\\Updownarrow", "\\updownarrow",
    "\\nearrow", "\\searrow", "\\swarrow", "\\nwarrow",
    "\\mapsto", "\\longmapsto",
    "\\hookrightarrow", "\\hookleftarrow",
    "\\rightharpoonup", "\\rightharpoondown",
    "\\leftharpoonup", "\\leftharpoondown",
    "\\rightleftharpoons",
    "\\to", "\\gets",

    # Math: misc symbols
    "\\infty", "\\partial", "\\nabla",
    "\\forall", "\\exists", "\\nexists",
    "\\in", "\\notin", "\\ni",
    "\\subset", "\\supset", "\\subseteq", "\\supseteq",
    "\\sqsubset", "\\sqsupset", "\\sqsubseteq", "\\sqsupseteq",
    "\\emptyset", "\\varnothing",
    "\\Re", "\\Im", "\\aleph", "\\hbar", "\\ell", "\\wp",
    "\\top", "\\bot", "\\angle", "\\triangle", "\\square", "\\lozenge",
    "\\clubsuit", "\\diamondsuit", "\\heartsuit", "\\spadesuit",
    "\\sharp", "\\flat", "\\natural",
    "\\neg", "\\lnot", "\\land", "\\lor",
    "\\vdash", "\\dashv",

    # Math: dots
    "\\ldots", "\\cdots", "\\vdots", "\\ddots", "\\dots",

    # Greek lowercase
    "\\alpha", "\\beta", "\\gamma", "\\delta", "\\epsilon",
    "\\varepsilon", "\\zeta", "\\eta", "\\theta", "\\vartheta",
    "\\iota", "\\kappa", "\\lambda", "\\mu", "\\nu",
    "\\xi", "\\pi", "\\varpi",
    "\\rho", "\\varrho", "\\sigma", "\\varsigma",
    "\\tau", "\\upsilon", "\\phi", "\\varphi",
    "\\chi", "\\psi", "\\omega",

    # Greek uppercase
    "\\Gamma", "\\Delta", "\\Theta", "\\Lambda", "\\Xi",
    "\\Pi", "\\Sigma", "\\Upsilon", "\\Phi", "\\Psi", "\\Omega",
])

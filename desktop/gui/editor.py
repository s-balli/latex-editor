"""QScintilla tabanlı LaTeX kod editörü."""

import bisect
import os
import re
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QMessageBox

from core.log import get_logger
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

    def __init__(self, parent=None, *, theme: dict = None):
        super().__init__(parent)
        self._file_path = ""
        self._detected_engine = ""
        self._initial_theme = theme
        self._encoding = "utf-8"
        self._setup_editor()

    def _setup_editor(self):
        lexer = LatexLexer(self)
        self.setLexer(lexer)

        self.setMarginLineNumbers(1, True)
        self.setMarginWidth(1, "0000")
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

    @staticmethod
    def _hex_to_scintilla(hex_color: str) -> int:
        h = hex_color.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return (b << 16) | (g << 8) | r

    def apply_theme(self, t: dict):
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
            self.lexer().apply_theme(t)

    def mousePressEvent(self, event):
        if (event.modifiers() & Qt.KeyboardModifier.ControlModifier and
                event.button() == Qt.MouseButton.LeftButton and self._file_path):
            pos = self.SendScintilla(
                self.SCI_POSITIONFROMPOINT,
                int(event.position().toPoint().x()),
                int(event.position().toPoint().y()),
            )
            if pos >= 0:
                line, col = self.lineIndexFromPosition(pos)
                self.forward_search_requested.emit(self._file_path, line + 1, col + 1)
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.setCursor(Qt.CursorShape.IBeamCursor)
        super().mouseMoveEvent(event)

    def keyPressEvent(self, event):
        if self._handle_autopair(event):
            return
        super().keyPressEvent(event)
        text = event.text()
        if text and text.isalpha():
            self._check_autocomplete()

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

    def _insert_begin_end(self, name: str):
        r"""\\begin{ad} → '}' + boş satır + \\end{ad}, imleç boş satırda."""
        line, _index = self.getCursorPosition()
        self.beginUndoAction()
        self.insert("}\n\n\\end{" + name + "}")
        self.setCursorPosition(line + 1, 0)
        self.endUndoAction()

    def _check_autocomplete(self):
        line, col = self.getCursorPosition()
        if col < 3:
            return

        line_text = self.text(line)
        text_before = line_text[:col]

        # \ ile başlayan kelimeyi bul
        match = re.search(r'\\[a-zA-Z]+$', text_before)
        if not match:
            return

        word = match.group(0)
        if len(word) < 3:  # \ + en az 2 harf
            return

        # Binary search ile eşleşen komutları bul (sorted listede aralık bul)
        lo = bisect.bisect_left(_LATEX_COMMANDS, word)
        hi = bisect.bisect_left(_LATEX_COMMANDS, word[:-1] + chr(ord(word[-1]) + 1))
        matches = [cmd for cmd in _LATEX_COMMANDS[lo:hi] if cmd != word]
        if not matches:
            return

        # Autocompletion separator ayarla ve popup göster
        self.SendScintilla(QsciScintilla.SCI_AUTOCSETSEPARATOR, ord(' '))
        entries = " ".join(matches).encode('utf-8')
        self.SendScintilla(QsciScintilla.SCI_AUTOCSHOW, len(word), entries)

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

    def _write_atomic(self, path: str, content: str, encoding: str = "utf-8") -> None:
        """Aynı dizinde geçici dosyaya yaz, fsync et, atomik rename ile yerine koy.

        Orijinal dosyaya truncate-on-open ile değil, tamamlanmış geçici dosyanın
        atomik yer değiştirmesiyle yazılır; böylece yazma yarıda kalırsa orijinal
        içerik korunur. Geçici dosya hedefle aynı filesystem'te (aynı dizinde)
        tutulur ki os.replace gerçekten atomik olsun (çapraz-mount rename değil).
        encoding verilirse o kodlamayla yazılır (UTF-8 dışı dosyalar round-trip
        için); bu durumda UnicodeEncodeError da temizlik için yakalanır.
        """
        tmp = path + ".tmp"
        try:
            with open(tmp, "w", encoding=encoding) as f:
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
            self._write_atomic(self._file_path, self.text(), self._encoding)
            self.setModified(False)
            return True
        except Exception as e:
            _logger.error("Dosya kaydedilemedi: %s", self._file_path, exc_info=True)
            QMessageBox.critical(self, _("Kaydetme Hatası"), _("Dosya kaydedilemedi:\n{path}\n\n{e}").format(path=self._file_path, e=e))
            return False

    def save_file_as(self, path: str) -> bool:
        self._file_path = os.path.normpath(path)
        self._encoding = "utf-8"  # yeni dosya -> modern varsayılan
        return self.save_file()

    @property
    def display_name(self) -> str:
        if self._file_path:
            return Path(self._file_path).name
        return _("Yeni Dosya")


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

from bisect import bisect_left

from PyQt6.Qsci import QsciLexerCustom
from PyQt6.QtGui import QColor, QFont

# Monospace font ailesi — yedeklerle. Consolas Windows'ta varsayılan; Linux/macOS'ta
# bulunmazsa DejaVu Sans Mono / Menlo / Courier New / monospace düşer (taşınabilirlik).
_MONO_FONTS = ["Consolas", "DejaVu Sans Mono", "Menlo", "Courier New", "monospace"]


class LatexLexer(QsciLexerCustom):
    """LaTeX sözdizimi renklendirme — byte-offset bazlı, UTF-8 güvenli, incremental."""

    DEFAULT = 0
    COMMAND = 1
    CMD_ARG = 2
    BRACKET = 3
    COMMENT = 4
    MATH = 5
    MATH_CMD = 6
    ENV_ARG = 7
    VERBATIM = 8

    _ENV_COMMANDS = {"begin", "end"}

    # İçeriği raw (komut/math stillenmeden) işlenen ortamlar (C.8 verbatim)
    _VERB_ENVS = ("verbatim", "verbatim*", "lstlisting", "minted", "alltt",
                  "comment", "Verbatim", "BVerbatim", "LVerbatim", "listing")

    # _line_states satır-durumu: 0=normal, 1=math, 2=verbatim (math/verbatim
    # birbirini dışlar). 0 falsy -> güvenli satır; 1/2 truthy -> devam eden.
    def __init__(self, parent=None):
        super().__init__(parent)
        self._line_states = {0: 0}

    def apply_theme(self, t: dict):
        bg = QColor(t["bg_primary"])
        mono = QFont(_MONO_FONTS, 11)

        self.setColor(QColor(t["syn_default"]), self.DEFAULT)
        self.setPaper(bg, self.DEFAULT)
        self.setFont(mono, self.DEFAULT)

        self.setColor(QColor(t["syn_command"]), self.COMMAND)
        self.setPaper(bg, self.COMMAND)
        self.setFont(mono, self.COMMAND)

        self.setColor(QColor(t["syn_cmd_arg"]), self.CMD_ARG)
        self.setPaper(bg, self.CMD_ARG)
        self.setFont(mono, self.CMD_ARG)

        self.setColor(QColor(t["syn_bracket"]), self.BRACKET)
        self.setPaper(bg, self.BRACKET)
        self.setFont(mono, self.BRACKET)

        comment_font = QFont(_MONO_FONTS, 11, italic=True)
        self.setColor(QColor(t["syn_comment"]), self.COMMENT)
        self.setPaper(bg, self.COMMENT)
        self.setFont(comment_font, self.COMMENT)

        math_bg = QColor(t["bg_math"])
        self.setColor(QColor(t["syn_math"]), self.MATH)
        self.setPaper(math_bg, self.MATH)

        self.setColor(QColor(t["syn_math_cmd"]), self.MATH_CMD)
        self.setPaper(math_bg, self.MATH_CMD)
        self.setFont(mono, self.MATH_CMD)

        env_font = QFont(_MONO_FONTS, 11, QFont.Weight.Bold)
        self.setColor(QColor(t["syn_env_arg"]), self.ENV_ARG)
        self.setPaper(bg, self.ENV_ARG)
        self.setFont(env_font, self.ENV_ARG)

        # Verbatim (raw kod) — yumuşak renkle, komut/math stillenmez (C.8)
        self.setColor(QColor(t.get("fg_muted", t["syn_default"])), self.VERBATIM)
        self.setPaper(bg, self.VERBATIM)
        self.setFont(mono, self.VERBATIM)

    def language(self):
        return "LaTeX"

    def description(self, style):
        names = {
            0: "Default", 1: "Command", 2: "CmdArg", 3: "Bracket",
            4: "Comment", 5: "Math", 6: "MathCmd", 7: "EnvArg", 8: "Verbatim",
        }
        return names.get(style, "")

    def styleText(self, start, end):
        editor = self.editor()
        if editor is None:
            return

        source = editor.text()
        if not source:
            return

        # Karakter → byte offset tablosu
        byte_at = [0] * (len(source) + 1)
        for idx, ch in enumerate(source):
            byte_at[idx + 1] = byte_at[idx] + len(ch.encode('utf-8'))

        n = len(source)

        # byte start → karakter offset
        char_start = bisect_left(byte_at, start)

        # Satır başını bul
        line_start = source.rfind('\n', 0, char_start) + 1
        line_no = source[:line_start].count('\n')

        # Cache'den state bul
        states = self._line_states
        cached = states.get(line_no)

        if cached is None or cached:
            # math modunda veya cache yoksa — güvenli satır bul
            safe = line_no
            while safe > 0 and states.get(safe, True):
                safe -= 1
            # safe satırının karakter offsetini bul
            line_start = 0
            for _ in range(safe):
                pos = source.find('\n', line_start)
                if pos == -1:
                    break
                line_start = pos + 1
            line_no = safe

        self.startStyling(byte_at[line_start])

        # Tarama — satır başlarında state kaydet
        new_states = {}
        in_math = False
        in_verbatim = False
        math_delim = None
        verb_name = None
        i = line_start

        # Eğer güvenli satırda değilsek (en baştan başlıyoruz demek)
        # line_no 0 ve line_start 0 olacak, zaten in_math=False

        while i < n:
            ch = source[i]

            # Newline — satır numarasını artır
            if ch == '\n':
                self.setStyling(byte_at[i + 1] - byte_at[i], self.DEFAULT)
                i += 1
                line_no += 1
                new_states[line_no] = self._state_val(in_math, in_verbatim)
                continue

            if in_verbatim:
                i, in_verbatim = self._style_verbatim_continue(source, i, n, byte_at, verb_name)
                continue

            if in_math:
                i, in_math = self._style_math_continue(source, i, n, byte_at, math_delim)
                continue

            if ch == '%':
                j = i + 1
                while j < n and source[j] != '\n':
                    j += 1
                self.setStyling(byte_at[j] - byte_at[i], self.COMMENT)
                i = j
                continue

            if ch == '$':
                i, in_math = self._style_math(source, i, n, byte_at)
                if in_math:
                    math_delim = '$'
                continue

            if ch == '\\':
                # verbatim ortamı başlangıcı: \begin{verbatim|lstlisting|...} (C.8).
                # İçerik raw işlenir (komut/math stillenmez); kapanış \end{ad}'e kadar.
                verb_env = self._match_verbatim_begin(source, i, n)
                if verb_env is not None:
                    pos, closed = self._style_verbatim_block(source, i, n, byte_at, verb_env)
                    in_verbatim = not closed
                    if in_verbatim:
                        verb_name = verb_env
                    i = pos
                    continue
                nxt = source[i + 1] if i + 1 < n else ''
                # \[ ... \] (display) ve \( ... \) (inline) math ayracı.
                # Bu delimiter'lar birden çok satıra yayılabilir; _style_math_block
                # kapanışı bulana (veya EOF'a) kadar tarayıp math modunu açar.
                if nxt == '[':
                    pos, closed = self._style_math_block(source, i, n, byte_at, '\\]')
                    in_math = not closed
                    if in_math:
                        math_delim = '\\]'
                    i = pos
                    continue
                if nxt == '(':
                    pos, closed = self._style_math_block(source, i, n, byte_at, '\\)')
                    in_math = not closed
                    if in_math:
                        math_delim = '\\)'
                    i = pos
                    continue
                i = self._style_command(source, i, n, byte_at)
                continue

            if ch in '{}':
                self.setStyling(byte_at[i + 1] - byte_at[i], self.DEFAULT)
                i += 1
                continue

            if ch in '[]':
                self.setStyling(byte_at[i + 1] - byte_at[i], self.BRACKET)
                i += 1
                continue

            j = i + 1
            # '\n' durma setinde OLMALI — yoksa düz metin akışı yeni satırı yutar
            # ve ch == '\n' dalı (line_no++ / satır durumu kaydı) çalışmaz. Bu,
            # _line_states önbelleğinin çoğu satır için asla doldurulmamasına ve
            # dolayısıyla bir sonraki artımlı çağrıda güvenli satır aramanın line 0'a
            # kadar geri dönüp tüm belgeyi yeniden taramasına yol açar.
            while j < n and source[j] not in '\\%${}[]\n':
                j += 1
            self.setStyling(byte_at[j] - byte_at[i], self.DEFAULT)
            i = j

        # Son satırın state'ini de kaydet
        new_states[line_no] = self._state_val(in_math, in_verbatim)
        # Önceki satır durumlarını koru. styleText artımlı çağrılır: yalnızca
        # [line_start, EOF] aralığı taranır ve new_states de yalnızca bu aralığı
        # içerir. Eski davranış (`= new_states`) tarama dışındaki satırların doğru
        # hesaplanmış durumlarını siliyordu; bir sonraki çağrı güvenli satır bulmak
        # için line 0'a kadar geri dönüp tüm belgeyi yeniden tarıyordu.
        self._line_states.update(new_states)

    # --- Matematik ---

    def _style_math(self, source, i, n, ba):
        if i + 1 < n and source[i + 1] == '$':
            pos, closed = self._style_math_block(source, i, n, ba, '$$')
            return pos, not closed
        pos, closed = self._style_math_block(source, i, n, ba, '$')
        return pos, not closed

    def _style_math_block(self, source, i, n, ba, delim):
        dlen = len(delim)
        j = i + dlen
        self.setStyling(ba[j] - ba[i], self.MATH)

        while j + dlen - 1 < n:
            if source[j:j + dlen] == delim:
                end = j + dlen
                self.setStyling(ba[end] - ba[j], self.MATH)
                return end, True

            if source[j] == '\\':
                k = j + 1
                if k < n and source[k].isalpha():
                    while k < n and source[k].isalpha():
                        k += 1
                    self.setStyling(ba[k] - ba[j], self.MATH_CMD)
                else:
                    k = min(j + 2, n)
                    self.setStyling(ba[k] - ba[j], self.MATH_CMD)
                j = k
                continue

            k = j + 1
            while k + dlen - 1 < n and source[k] not in '\\$':
                k += 1
            self.setStyling(ba[min(k, n)] - ba[j], self.MATH)
            j = min(k, n)

        if j < n:
            self.setStyling(ba[n] - ba[j], self.MATH)
        return n, False

    def _style_math_continue(self, source, i, n, ba, delim):
        dlen = len(delim)
        j = i

        while j + dlen - 1 < n:
            if source[j:j + dlen] == delim:
                end = j + dlen
                self.setStyling(ba[end] - ba[i], self.MATH)
                return end, False

            if source[j] == '\\':
                k = j + 1
                if k < n and source[k].isalpha():
                    while k < n and source[k].isalpha():
                        k += 1
                    self.setStyling(ba[k] - ba[j], self.MATH_CMD)
                else:
                    k = min(j + 2, n)
                    self.setStyling(ba[k] - ba[j], self.MATH_CMD)
                j = k
                continue

            k = j + 1
            while k + dlen - 1 < n and source[k] not in '\\$':
                k += 1
            self.setStyling(ba[min(k, n)] - ba[j], self.MATH)
            j = min(k, n)

        if j < n:
            self.setStyling(ba[n] - ba[j], self.MATH)
        return n, True

    # --- Verbatim (C.8) ---

    @staticmethod
    def _state_val(in_math: bool, in_verbatim: bool) -> int:
        """Satır-durumu kodu: 0=normal, 1=math, 2=verbatim (birbirini dışlar)."""
        if in_math:
            return 1
        if in_verbatim:
            return 2
        return 0

    def _match_verbatim_begin(self, source, i, n):
        """source[i:] \\begin{<verbenv>} ile başlıyorsa ortam adını, yoksa None."""
        for env in self._VERB_ENVS:
            tag = "\\begin{" + env + "}"
            if source.startswith(tag, i):
                return env
        return None

    def _style_verbatim_block(self, source, i, n, ba, env):
        """\\begin{env} ... \\end{env} arasını (sınırlar dahil) VERBATIM stiller.

        Kapanış bulunursa (end, True), bulunamazsa EOF'a kadar (n, False) döner.
        """
        close = "\\end{" + env + "}"
        j = source.find(close, i + 1)
        if j == -1:
            self.setStyling(ba[n] - ba[i], self.VERBATIM)
            return n, False
        end = j + len(close)
        self.setStyling(ba[end] - ba[i], self.VERBATIM)
        return end, True

    def _style_verbatim_continue(self, source, i, n, ba, env):
        """Açık verbatim bloğunun devamı (artımlı tarama için, math_continue gibi)."""
        close = "\\end{" + env + "}"
        j = source.find(close, i)
        if j == -1:
            self.setStyling(ba[n] - ba[i], self.VERBATIM)
            return n, True
        end = j + len(close)
        self.setStyling(ba[end] - ba[i], self.VERBATIM)
        return end, False

    # --- Komutlar ---

    def _style_command(self, source, i, n, ba):
        j = i + 1
        if j >= n:
            self.setStyling(ba[j] - ba[i], self.COMMAND)
            return n

        if not source[j].isalpha():
            j = min(i + 2, n)
            self.setStyling(ba[j] - ba[i], self.COMMAND)
            return j

        start_name = j
        while j < n and source[j].isalpha():
            j += 1
        cmd_name = source[start_name:j]

        if j < n and source[j] == '*':
            j += 1

        self.setStyling(ba[j] - ba[i], self.COMMAND)

        if cmd_name in self._ENV_COMMANDS:
            k = self._skip_ws(source, j, n, ba)
            k = self._consume_braces(source, k, n, ba, self.ENV_ARG)
            return k

        k = self._skip_ws(source, j, n, ba)
        if k < n and source[k] == '[':
            k = self._consume_brackets(source, k, n, ba)
            k = self._skip_ws(source, k, n, ba)
        if k < n and source[k] == '{':
            k = self._consume_braces(source, k, n, ba, self.CMD_ARG)
        return k

    # --- Yardımcılar ---

    def _skip_ws(self, source, k, n, ba):
        start = k
        while k < n and source[k] in ' \t':
            k += 1
        if k > start:
            self.setStyling(ba[k] - ba[start], self.DEFAULT)
        return k

    def _consume_braces(self, source, k, n, ba, style):
        if k >= n or source[k] != '{':
            return k
        start = k
        k += 1
        depth = 1
        while k < n and depth > 0:
            if source[k] == '\\':
                k += 1
                if k < n:
                    k += 1
                continue
            if source[k] == '{':
                depth += 1
            elif source[k] == '}':
                depth -= 1
            k += 1
        byte_len = ba[k] - ba[start]
        self.setStyling(byte_len, style)
        return k

    def _consume_brackets(self, source, k, n, ba):
        if k >= n or source[k] != '[':
            return k
        start = k
        k += 1
        depth = 1
        while k < n and depth > 0:
            if source[k] == '\\':
                k += 1
                if k < n:
                    k += 1
                continue
            if source[k] == '[':
                depth += 1
            elif source[k] == ']':
                depth -= 1
            k += 1
        self.setStyling(ba[k] - ba[start], self.BRACKET)
        return k

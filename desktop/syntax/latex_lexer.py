from PyQt6.Qsci import QsciLexerCustom
from PyQt6.QtGui import QColor, QFont

# Monospace font ailesi — yedeklerle. Consolas Windows'ta varsayılan; Linux/macOS'ta
# bulunmazsa DejaVu Sans Mono / Menlo / Courier New / monospace düşer (taşınabilirlik).
_MONO_FONTS = ["Consolas", "DejaVu Sans Mono", "Menlo", "Courier New", "monospace"]

# Tarama UTF-8 baytları üzerinde çalışır: Scintilla pozisyonları bayt-offset
# olduğundan char→byte dönüşüm tablosuna gerek kalmaz (bayt index == offset).
_NL = 0x0A    # \n
_BS = 0x5C    # backslash
_PCT = 0x25   # %
_DLR = 0x24   # $


def _is_alpha(c: int) -> bool:
    """Bayt ASCII harf mi? (LaTeX komut adları yalnız ASCII harflerden oluşur.)"""
    return 65 <= c <= 90 or 97 <= c <= 122


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

    _ENV_COMMANDS = {b"begin", b"end"}

    # İçeriği raw (komut/math stillenmeden) işlenen ortamlar (C.8 verbatim)
    _VERB_ENVS = ("verbatim", "verbatim*", "lstlisting", "minted", "alltt",
                  "comment", "Verbatim", "BVerbatim", "LVerbatim", "listing")
    _VERB_BEGIN_TAGS = tuple(b"\\begin{" + env.encode() + b"}" for env in _VERB_ENVS)

    # Önbellekler (hepsi son commit anındaki belge koordinatlarında):
    # _line_states:  satır no → o satıra GİRİŞ durumu (geri yürüyüş için).
    #                0=normal, 1=math, 2=verbatim (birbirini dışlar); 0 falsy
    #                -> güvenli satır, 1/2 truthy -> devam eden.
    # _offset_states: satır başı byte offset → giriş durumu. Erken çıkışın
    #                İSPATI için: yeni belgedeki satır başı q, düzenleme
    #                bölgesinin ötesindeyse karşılığı eski belgede
    #                q - byte_delta'tır; orada önbellek varsa ve durum eşitse
    #                kalan stiller kanıtlanmış şekilde doğrudur (aynı içerik +
    #                aynı giriş durumu = aynı parse). Satır numarasıyla kanıt
    #                YETMEZ: satır bölünen düzenlemelerde bölünen satırın orta
    #                durumu önbellekte yoktur.
    # _doc_len/_doc_lines: delta hesabı için son commit anındaki boy/satır.
    def __init__(self, parent=None):
        super().__init__(parent)
        self._line_states = {0: 0}
        self._offset_states = {0: 0}
        self._doc_len = None
        self._doc_lines = None
        # Belge baytları önbelleği: editor.text() tüm belgeyi Python'a çekip
        # encode eder (iki tam-kopya); tuş başına bu taban maliyeti kaldırmak
        # için aynı zamanda byte uzunluğuyla doğrulanır. Editor.textChanged ->
        # invalidate_cache bağlar (beginend önbelleğiyle aynı faz).
        self._src_cache: tuple[bytes, int] | None = None

    def invalidate_cache(self):
        """Belge değişti: bayt önbelleğini düşür (textChanged'e bağlı)."""
        self._src_cache = None

    def _source_bytes(self, editor) -> bytes:
        cached = self._src_cache
        n = editor.length()   # Scintilla uzunluğu bayt cinsindendir
        if cached is not None and cached[1] == n:
            return cached[0]
        data = editor.text().encode("utf-8")
        self._src_cache = (data, len(data))
        return data

    def reset_state(self):
        """Belge bütünüyle değiştiğinde (setText ile yeniden yükleme) önbelleği
        sıfırla. Aksi halde eski belgenin satır durumları yeni belgeyle yanlış
        eşleşip erken çıkışı suistimal edebilir."""
        self._line_states = {0: 0}
        self._offset_states = {0: 0}
        self._doc_len = None
        self._doc_lines = None
        self._src_cache = None

    def apply_theme(self, t: dict, font_size: int = 11):
        bg = QColor(t["bg_primary"])
        mono = QFont(_MONO_FONTS, font_size)

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

        comment_font = QFont(_MONO_FONTS, font_size, italic=True)
        self.setColor(QColor(t["syn_comment"]), self.COMMENT)
        self.setPaper(bg, self.COMMENT)
        self.setFont(comment_font, self.COMMENT)

        math_bg = QColor(t["bg_math"])
        self.setColor(QColor(t["syn_math"]), self.MATH)
        self.setPaper(math_bg, self.MATH)
        self.setFont(mono, self.MATH)   # eksikti: math metni tema fontuna düşüyordu

        self.setColor(QColor(t["syn_math_cmd"]), self.MATH_CMD)
        self.setPaper(math_bg, self.MATH_CMD)
        self.setFont(mono, self.MATH_CMD)

        env_font = QFont(_MONO_FONTS, font_size, QFont.Weight.Bold)
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

        # Tarama doğrudan UTF-8 baytları üzerinde: bayt offsetleri Scintilla
        # pozisyonlarıyla birebir örtüşür. Baytlar önbellekten gelir
        # (_source_bytes): tuş başına çift tam-belge kopyası (text + encode)
        # yalnızca belge gerçekten değiştiğinde ödenir.
        source = self._source_bytes(editor)
        if not source:
            self.reset_state()
            return

        n = len(source)

        # Satır başını bul
        line_start = source.rfind(b"\n", 0, start) + 1
        line_no = source.count(b"\n", 0, line_start)

        # Cache'den state bul
        states = self._line_states
        cached = states.get(line_no)

        if cached is None or cached:
            # math modunda veya cache yoksa — güvenli satır bul
            safe = line_no
            while safe > 0 and states.get(safe, True):
                safe -= 1
            # safe satırının bayt offsetini bul
            line_start = 0
            for _ in range(safe):
                pos = source.find(b"\n", line_start)
                if pos == -1:
                    break
                line_start = pos + 1
            line_no = safe

        self.startStyling(line_start)

        # Tarama her zaman giriş durumu 0 olan satırdan başlar (yukarıdaki
        # güvenli satır araması bunu garanti eder) — kaydet.
        scan_line = line_no
        scan_start = line_start
        new_states = {scan_line: 0}
        new_offsets = {scan_start: 0}

        # Erken çıkış hazırlığı. QScintilla stilleri idle-time'da koalese
        # ederek ister: start = en eski kirli pozisyon, end = en yeni kirli
        # pozisyon (end belge sonu DEĞİL). [start, end) düzenlemelerinin
        # ÖTESİNDEKI ilk satır başında kanıtlanabilir durumlarda taramayı
        # durdurmak güvenlidir: düzenlemelerin ötesinde içerik, önceki belgeye
        # göre byte_delta kadar ötelenmiş aynı içeriktir; q - byte_delta
        # eski belgede bir satır başıysa ve giriş durumları eşitse, lexer
        # deterministik olduğundan kalan stiller zaten doğrudur. Böylece
        # normal bir tuş vuruşu tüm belgeyi değil, düzenlenen birkaç satırı
        # yeniden tarar.
        total_lines = source.count(b"\n") + 1
        byte_delta = None if self._doc_len is None else n - self._doc_len

        # Tarama — satır başlarında state kaydet
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
            if ch == _NL:
                self.setStyling(1, self.DEFAULT)
                i += 1
                line_no += 1
                s = self._state_val(in_math, in_verbatim)
                new_states[line_no] = s
                new_offsets[i] = s
                if (i >= end and byte_delta is not None
                        and self._offset_states.get(i - byte_delta) == s):
                    self._commit(scan_line, scan_start, line_no, i,
                                 new_states, new_offsets, total_lines, n)
                    return
                continue

            if in_verbatim:
                prev = i
                i, in_verbatim = self._style_verbatim_continue(source, i, n, verb_name)
                line_no += source.count(b"\n", prev, i)  # çok satırlı blok: satır no senkron
                continue

            if in_math:
                prev = i
                i, in_math = self._style_math_continue(source, i, n, math_delim)
                line_no += source.count(b"\n", prev, i)
                continue

            if ch == _PCT:
                j = i + 1
                while j < n and source[j] != _NL:
                    j += 1
                self.setStyling(j - i, self.COMMENT)
                i = j
                continue

            if ch == _DLR:
                prev = i
                i, in_math = self._style_math(source, i, n)
                line_no += source.count(b"\n", prev, i)  # $$...$$ çok satırlı olabilir
                if in_math:
                    math_delim = b"$"
                continue

            if ch == _BS:
                # verbatim ortamı başlangıcı: \begin{verbatim|lstlisting|...} (C.8).
                # İçerik raw işlenir (komut/math stillenmez); kapanış \end{ad}'e kadar.
                verb_env = self._match_verbatim_begin(source, i)
                if verb_env is not None:
                    pos, closed = self._style_verbatim_block(source, i, n, verb_env)
                    line_no += source.count(b"\n", i, pos)  # çok satırlı blok: satır no senkron
                    in_verbatim = not closed
                    if in_verbatim:
                        verb_name = verb_env
                    i = pos
                    continue
                nxt = source[i + 1] if i + 1 < n else 0
                # \[ ... \] (display) ve \( ... \) (inline) math ayracı.
                # Bu delimiter'lar birden çok satıra yayılabilir; _style_math_block
                # kapanışı bulana (veya EOF'a) kadar tarayıp math modunu açar.
                if nxt == 0x5B:  # '['
                    pos, closed = self._style_math_block(source, i, n, b"\\]")
                    line_no += source.count(b"\n", i, pos)  # çok satırlı blok: satır no senkron
                    in_math = not closed
                    if in_math:
                        math_delim = b"\\]"
                    i = pos
                    continue
                if nxt == 0x28:  # '('
                    pos, closed = self._style_math_block(source, i, n, b"\\)")
                    line_no += source.count(b"\n", i, pos)
                    in_math = not closed
                    if in_math:
                        math_delim = b"\\)"
                    i = pos
                    continue
                i = self._style_command(source, i, n)
                continue

            if ch in b"{}":
                self.setStyling(1, self.DEFAULT)
                i += 1
                continue

            if ch in b"[]":
                self.setStyling(1, self.BRACKET)
                i += 1
                continue

            j = i + 1
            # '\n' durma setinde OLMALI — yoksa düz metin akışı yeni satırı yutar
            # ve ch == '\n' dalı (line_no++ / satır durumu kaydı) çalışmaz. Bu,
            # _line_states önbelleğinin çoğu satır için asla doldurulmamasına ve
            # dolayısıyla bir sonraki artımlı çağrıda güvenli satır aramanın line 0'a
            # kadar geri dönüp tüm belgeyi yeniden taramasına yol açar.
            while j < n and source[j] not in b"\\%${}[]\n":
                j += 1
            self.setStyling(j - i, self.DEFAULT)
            i = j

        # Son satırın state'ini de kaydet
        new_states[line_no] = self._state_val(in_math, in_verbatim)
        self._commit(scan_line, scan_start, line_no, n,
                     new_states, new_offsets, total_lines, n)

    def _commit(self, scan_line, scan_start, exit_line, exit_offset,
                new_states, new_offsets, total_lines, n):
        """Tarama bitti (erken çıkışta exit_offset < n, tam taramada == n).

        Taranan [scan_start, exit_offset) bölgesi yeni koordinatlarla yeniden
        yazılır; bölge İÇİNDEKİ eski girdiler tamamen düşürülür. Bu kritik:
        blok uzadığında (ör. kapanış \\end{verbatim} silinince) tarama atladığı
        ara satırlar için girdi YAZMAZ; update()-le eski 0'lar yerinde kalsaydı
        bir sonraki geri yürüyüş o satırları yanlışlıkla 'güvenli' sanırdı.
        Bölge ÖNCESİ girdiler dokunulmadan kalır (düzenleme bölgede ya da
        sonrasında olduğundan koordinatları değişmez). Bölge SONRASI eski
        girdiler byte_delta/line_delta kadar ötelenir: içerik değişmedi, yalnız
        konumu kaydı; durumları hâlâ geçerlidir. exit_offset == n (tam tarama)
        durumunda kuyruk boştur, öteleleme etkisizdir.
        """
        if self._doc_len is None:
            # İlk tarama (ya da reset sonrası): kuyruk yok, bölge sıfırdan yazılır
            byte_delta = 0
            line_delta = 0
        else:
            byte_delta = n - self._doc_len
            line_delta = total_lines - self._doc_lines

        # _offset_states (erken çıkışın kanıtı): eski koordinattaki kuyruğu
        # byte_delta ile kaydır
        old = self._offset_states
        old_boundary = exit_offset - byte_delta
        self._offset_states = {k: v for k, v in old.items() if k < scan_start}
        self._offset_states.update(
            {k + byte_delta: v for k, v in old.items() if k >= old_boundary})
        self._offset_states.update(new_offsets)

        # _line_states (geri yürüyüş): aynı kural satır numaralarıyla
        states = self._line_states
        base = exit_line - line_delta  # exit_line'ın eski koordinattaki karşılığı
        self._line_states = {k: v for k, v in states.items() if k < scan_line}
        self._line_states.update(
            {k + line_delta: v for k, v in states.items() if k >= base})
        self._line_states.update(new_states)

        self._doc_len = n
        self._doc_lines = total_lines

    # --- Matematik ---

    def _style_math(self, source, i, n):
        if i + 1 < n and source[i + 1] == _DLR:
            pos, closed = self._style_math_block(source, i, n, b"$$")
            return pos, not closed
        pos, closed = self._style_math_block(source, i, n, b"$")
        return pos, not closed

    def _style_math_block(self, source, i, n, delim):
        dlen = len(delim)
        j = i + dlen
        self.setStyling(dlen, self.MATH)

        while j + dlen - 1 < n:
            if source[j:j + dlen] == delim:
                end = j + dlen
                self.setStyling(end - j, self.MATH)
                return end, True

            if source[j] == _BS:
                k = j + 1
                if k < n and _is_alpha(source[k]):
                    while k < n and _is_alpha(source[k]):
                        k += 1
                    self.setStyling(k - j, self.MATH_CMD)
                else:
                    k = min(j + 2, n)
                    self.setStyling(k - j, self.MATH_CMD)
                j = k
                continue

            k = j + 1
            while k + dlen - 1 < n and source[k] not in b"\\$":
                k += 1
            self.setStyling(min(k, n) - j, self.MATH)
            j = min(k, n)

        if j < n:
            self.setStyling(n - j, self.MATH)
        return n, False

    def _style_math_continue(self, source, i, n, delim):
        dlen = len(delim)
        j = i

        while j + dlen - 1 < n:
            if source[j:j + dlen] == delim:
                end = j + dlen
                self.setStyling(end - i, self.MATH)
                return end, False

            if source[j] == _BS:
                k = j + 1
                if k < n and _is_alpha(source[k]):
                    while k < n and _is_alpha(source[k]):
                        k += 1
                    self.setStyling(k - j, self.MATH_CMD)
                else:
                    k = min(j + 2, n)
                    self.setStyling(k - j, self.MATH_CMD)
                j = k
                continue

            k = j + 1
            while k + dlen - 1 < n and source[k] not in b"\\$":
                k += 1
            self.setStyling(min(k, n) - j, self.MATH)
            j = min(k, n)

        if j < n:
            self.setStyling(n - j, self.MATH)
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

    def _match_verbatim_begin(self, source, i):
        """source[i:] \\begin{<verbenv>} ile başlıyorsa ortam adını, yoksa None."""
        for tag, env in zip(self._VERB_BEGIN_TAGS, self._VERB_ENVS):
            if source.startswith(tag, i):
                return env
        return None

    def _style_verbatim_block(self, source, i, n, env):
        """\\begin{env} ... \\end{env} arasını (sınırlar dahil) VERBATIM stiller.

        Kapanış bulunursa (end, True), bulunamazsa EOF'a kadar (n, False) döner.
        """
        close = b"\\end{" + env.encode() + b"}"
        j = source.find(close, i + 1)
        if j == -1:
            self.setStyling(n - i, self.VERBATIM)
            return n, False
        end = j + len(close)
        self.setStyling(end - i, self.VERBATIM)
        return end, True

    def _style_verbatim_continue(self, source, i, n, env):
        """Açık verbatim bloğunun devamı (artımlı tarama için, math_continue gibi)."""
        close = b"\\end{" + env.encode() + b"}"
        j = source.find(close, i)
        if j == -1:
            self.setStyling(n - i, self.VERBATIM)
            return n, True
        end = j + len(close)
        self.setStyling(end - i, self.VERBATIM)
        return end, False

    # --- Komutlar ---

    def _style_command(self, source, i, n):
        j = i + 1
        if j >= n:
            self.setStyling(j - i, self.COMMAND)
            return n

        if not _is_alpha(source[j]):
            j = min(i + 2, n)
            self.setStyling(j - i, self.COMMAND)
            return j

        start_name = j
        while j < n and _is_alpha(source[j]):
            j += 1
        cmd_name = source[start_name:j]

        if j < n and source[j] == 0x2A:  # '*'
            j += 1

        self.setStyling(j - i, self.COMMAND)

        if cmd_name in self._ENV_COMMANDS:
            k = self._skip_ws(source, j, n)
            k = self._consume_braces(source, k, n, self.ENV_ARG)
            return k

        k = self._skip_ws(source, j, n)
        if k < n and source[k] == 0x5B:  # '['
            k = self._consume_brackets(source, k, n)
            k = self._skip_ws(source, k, n)
        if k < n and source[k] == 0x7B:  # '{'
            k = self._consume_braces(source, k, n, self.CMD_ARG)
        return k

    # --- Yardımcılar ---

    def _skip_ws(self, source, k, n):
        start = k
        while k < n and source[k] in b" \t":
            k += 1
        if k > start:
            self.setStyling(k - start, self.DEFAULT)
        return k

    def _consume_braces(self, source, k, n, style):
        if k >= n or source[k] != 0x7B:  # '{'
            return k
        start = k
        k += 1
        depth = 1
        while k < n and depth > 0:
            if source[k] == _BS:
                k += 1
                if k < n:
                    k += 1
                continue
            if source[k] == 0x7B:  # '{'
                depth += 1
            elif source[k] == 0x7D:  # '}'
                depth -= 1
            k += 1
        self.setStyling(k - start, style)
        return k

    def _consume_brackets(self, source, k, n):
        if k >= n or source[k] != 0x5B:  # '['
            return k
        start = k
        k += 1
        depth = 1
        while k < n and depth > 0:
            if source[k] == _BS:
                k += 1
                if k < n:
                    k += 1
                continue
            if source[k] == 0x5B:  # '['
                depth += 1
            elif source[k] == 0x5D:  # ']'
                depth -= 1
            k += 1
        self.setStyling(k - start, self.BRACKET)
        return k

"""LaTeX derleme motoru — Windows (WSL), Linux, macOS desteği."""

import codecs
import os
import re
import sys
import time
from pathlib import Path

from PyQt6.QtCore import QCoreApplication, QObject, QProcess, QTimer, pyqtSignal

from core.log_parser import CompileResult, LatexError, LatexSuggestion, parse_output
from core.paths import windows_to_wsl

PLATFORM = sys.platform  # win32, linux, darwin

# Bu modül zaten QtCore'a bağımlı (QProcess); kullanıcıya görünen derleme
# hataları İngilizce arayüzde Türkçe kalmasın diye çevrilebilir.
_ = lambda s: QCoreApplication.translate("Compiler", s)

# Derleme watchdog sınırı: bu sürede bitmeyen derleme iptal edilir.
DEFAULT_TIMEOUT_MS = 120_000

# ANSI renk dizisi (bayt uzayında): chunk sınırında bölünen dizi metne ham kaçmasın
_RE_ANSI = re.compile(rb'\x1b\[[0-9;]*m')


def _find_derle_sh() -> str:
    """derle.sh'nin yolunu bul."""
    core_dir = Path(__file__).resolve().parent  # core/
    candidates = [
        core_dir / "derle.sh",  # core/derle.sh
    ]
    # PyInstaller ile paketlenmişse
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS)
        candidates.insert(0, base / "core" / "derle.sh")
        candidates.insert(1, Path(sys.executable).parent / "core" / "derle.sh")
    for c in candidates:
        if c.is_file():
            return str(c)
    return str(core_dir / "derle.sh")


class LatexCompiler(QObject):
    compilation_started = pyqtSignal()
    compilation_finished = pyqtSignal(object)  # CompileResult
    output_line = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process: QProcess | None = None
        self._output = ""
        self._ansi_tail = b""
        self._utf8_dec = codecs.getincrementaldecoder("utf-8")("replace")
        self._start_time = 0.0
        self._pdf_damgasi_once = None
        self._tex_dir = ""
        self._tex_name = ""
        self._tex_path = ""
        self._engine = "lualatex"
        self._shell_escape = None
        self._finished_emitted = False
        self._timeout_ms = DEFAULT_TIMEOUT_MS
        self._timeout_timer = QTimer(self)
        self._timeout_timer.setSingleShot(True)
        self._timeout_timer.timeout.connect(self._on_timeout)

    def is_busy(self) -> bool:
        """Bir derleme sürüyorsa True: yeni derleme başlatılmamalı.

        GUI katmanı durum değişikliklerini (hedef yolu, panel temizliği,
        imleç bağlamı) compile() ÇAĞIRMADAN önce bu guard'a bakar; çağrıyı
        yapıp False dönüşüne bırakırsa bayat durum yazmış olur.
        """
        return bool(self.process and
                    self.process.state() != QProcess.ProcessState.NotRunning)

    def compile(self, tex_path: str, engine: str = "lualatex",
                timeout_ms: int | None = None,
                shell_escape: bool | None = None) -> bool:
        """`shell_escape`: True aç, False kapat, None karar verme.

        None derle.sh'in eski davranışını bırakıyor (minted görünce
        kendiliğinden aç); GUI bunu KULLANMIYOR, kullanıcıya sorup açıkça
        True/False geçiyor. Sebep: bayrak belgeye keyfi komut çalıştırma
        izni veriyor ve otomatik açılması ölçülmüş bir riskti
        (bkz. core/shell_escape.py).
        """
        if self.is_busy():
            return False
        self._shell_escape = shell_escape

        if timeout_ms is not None:
            self._timeout_ms = timeout_ms
        tex_path = os.path.normpath(tex_path)
        self._tex_dir = str(Path(tex_path).parent)
        self._tex_name = Path(tex_path).stem
        self._tex_path = tex_path
        self._engine = engine
        self._output = ""
        self._ansi_tail = b""
        self._utf8_dec = codecs.getincrementaldecoder("utf-8")("replace")
        self._start_time = time.time()
        # PDF'in derleme ÖNCESİ damgası — tazelik bunun DEĞİŞİP değişmediğine
        # bakılarak anlaşılır (bkz. _pdf_damgasi). Duvar saatiyle karşılaştırma
        # yapılmaz: derlemeyi WSL koşuyor, damgayı WSL'in saati basıyor, biz ise
        # Windows'un saatiyle ölçüyoruz.
        self._pdf_damgasi_once = self._pdf_damgasi(
            os.path.join(self._tex_dir, f"{self._tex_name}.pdf"))
        self._finished_emitted = False

        # Önceki derlemenin QProcess'ini bırak: her derleme yeni nesne yaratır,
        # eskisi QObject child olarak birikir (uzun oturumda sızıntı). Üstteki
        # guard NotRunning garantisi verir; deleteLater bağlantılarını da koparır.
        if self.process is not None:
            self.process.deleteLater()

        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._on_output)
        self.process.finished.connect(self._on_finished)
        self.process.errorOccurred.connect(self._on_error)

        self.compilation_started.emit()
        self.output_line.emit(f"[derleniyor] {Path(tex_path).name} ({engine}) ...\n")

        if PLATFORM == "win32":
            self._start_windows(tex_path, engine)
        else:
            self._start_native(tex_path, engine)

        # Watchdog: bu sürede bitmezse derlemeyi iptal et.
        self._timeout_timer.stop()
        self._timeout_timer.start(self._timeout_ms)

        return True

    def _start_windows(self, tex_path: str, engine: str):
        """Windows: WSL üzerinden derle."""
        derle_sh = _find_derle_sh()
        wsl_derle = windows_to_wsl(derle_sh)
        wsl_tex = windows_to_wsl(tex_path)

        args = ["-e", "bash", wsl_derle, wsl_tex]
        if engine == "pdflatex":
            args.append("--pdflatex")
        elif engine == "xelatex":
            args.append("--xelatex")
        if self._shell_escape is True:
            args.append("--shell-escape")
        elif self._shell_escape is False:
            args.append("--no-shell-escape")
        self.process.start("wsl", args)

    def _start_native(self, tex_path: str, engine: str):
        """Linux/macOS: doğrudan bash ile derle."""
        derle_sh = _find_derle_sh()

        args = [derle_sh, tex_path]
        if engine == "pdflatex":
            args.append("--pdflatex")
        elif engine == "xelatex":
            args.append("--xelatex")

        if self._shell_escape is True:
            args.append("--shell-escape")
        elif self._shell_escape is False:
            args.append("--no-shell-escape")
        self.process.start("bash", args)

    def _on_output(self):
        if not self.process:
            return
        data = self._ansi_tail + self.process.readAllStandardOutput().data()
        # Chunk sınırı yarım ANSI dizisiyle biterse (ESC yazıldı, dizinin
        # 'm'si sonraki chunk'ta) regex eşleşmez, ham kaçardı. Son ESC'den
        # itibaren dizi tamamlanmamışsa o kısmı sonraki tura taşı.
        i = data.rfind(b"\x1b")
        if i >= 0 and not _RE_ANSI.match(data, i):
            self._ansi_tail, data = data[i:], data[:i]
        else:
            self._ansi_tail = b""
        data = _RE_ANSI.sub(b"", data)
        # wsl.exe KENDİ hata mesajlarını UTF-16LE yazıyor ("Sağlanan ada sahip
        # dağıtım yok", "Wsl/Service/..." gibi). UTF-8 çözücüden geçince panele
        # NUL dolu çöp düşüyordu ('S\x00a\x00\x1f\x01l\x00...') ve log_parser
        # de oradan öneri çıkaramıyordu — WSL kurulu olmayan kullanıcı, sorunun
        # ne olduğunu söyleyen tek mesajı hiç göremiyordu.
        # NUL baytı ayırt edici: derle.sh/LaTeX çıktısı (UTF-8 metin) NUL
        # içermez, UTF-16LE'ye kodlanmış ASCII ise her karakterde bir tane
        # taşır. İki akış iç içe gelmiyor (wsl.exe hatası bash hiç başlamadan
        # yazılıyor), o yüzden chunk bazında karar vermek yeterli.
        if b"\x00" in data:
            text = data.decode("utf-16-le", errors="replace")
        else:
            # Artımlı UTF-8 çözücü çok baytlı karakteri chunk sınırında bölünse
            # bile tamamlanını bekler; errors="replace" ancak gerçek bozuklukta devreye girer
            text = self._utf8_dec.decode(data, final=False)
        self._output += text
        self.output_line.emit(text)

    def _flush_output(self):
        """Süreç kapandı: yarım kalan ANSI/UTF-8 parçalarını son kez boşalt."""
        text = self._utf8_dec.decode(_RE_ANSI.sub(b"", self._ansi_tail), final=True)
        self._ansi_tail = b""
        if text:
            self._output += text
            self.output_line.emit(text)

    @staticmethod
    def _pdf_damgasi(pdf_path: str) -> tuple[int, int] | None:
        """Dosyanın kimlik damgası: (mtime_ns, boyut). Dosya yoksa None.

        Yalnızca AYNI dosyanın iki okuması karşılaştırılır, bu yüzden damgayı
        hangi saatin bastığı önemsizdir — WSL/Windows saat farkı sadeleşir.
        Boyut ikinci ölçüt: mtime çözünürlüğü kaba olan dosya sistemlerinde
        (bazı ağ sürücüleri 1 sn) aynı saniyedeki iki derlemeyi ayırt eder.
        """
        try:
            st = os.stat(pdf_path)
        except OSError:
            return None
        return (st.st_mtime_ns, st.st_size)

    def _on_finished(self, exit_code, exit_status):
        self._timeout_timer.stop()
        self._flush_output()
        result = parse_output(self._output, self._tex_path)
        result.duration = time.time() - self._start_time

        pdf_path = os.path.join(self._tex_dir, f"{self._tex_name}.pdf")
        # PDF ancak BU derleme üretmişse geçerli; yoksa önceki bir derlemeden
        # kalan bayat dosya olabilir. exit != 0 olsa bile taze PDF varsa yolunu
        # bildir — GUI bunu kısmi önizleme için yükler.
        #
        # İki ölçüt, ikisi de duvar saatinden BAĞIMSIZ:
        #  - exit 0: derle.sh sıfırı YALNIZCA taze PDF'i yerine taşıdıktan sonra
        #    döndürüyor (PDF üretilmediyse "PDF olusmadi" + return 1). Sıfır
        #    görüyorsak dosya bu koşunun ürünüdür.
        #  - exit != 0: dosyanın damgası derleme boyunca DEĞİŞTİYSE bu koşu
        #    yazmıştır (nonstopmode'un kurtardığı kısmi çıktı).
        #
        # Eskiden ölçüt `os.path.getmtime(pdf) >= self._start_time` idi ve
        # İKİ FARKLI SAATİ karşılaştırıyordu: _start_time Windows'un saatinden,
        # mtime ise dosyayı yazan WSL'in saatinden geliyor. WSL2'nin saati ana
        # makineye göre kayıyor ve periyodik olarak ~1 sn'lik sıçramayla
        # senkronlanıyor; kayma derleme süresini aştığında taze PDF "bayat"
        # sayılıyordu. Sonuç kullanıcıya şöyle görünüyordu: log "[basarili]"
        # diyor, PDF diskte duruyor, ama panel "başarısız — 0 hata" yazıp motor
        # değiştirme önerisi gösteriyor ve önizleme temizleniyor. Ölçüldü
        # (25 tur, ~1 sn'lik derleme): 11 tur düştü, mtime-start_time farkı
        # +1.67 sn ile -0.30 sn arasında geziniyordu.
        damga = self._pdf_damgasi(pdf_path)
        if damga is not None and (exit_code == 0 or damga != self._pdf_damgasi_once):
            result.pdf_path = pdf_path

        result.success = (exit_code == 0 and bool(result.pdf_path))

        if not self._finished_emitted:
            self._finished_emitted = True
            self.compilation_finished.emit(result)

    def _on_error(self, error: QProcess.ProcessError):
        self._timeout_timer.stop()
        self._flush_output()
        msg = _("Derleme hatası")
        if error == QProcess.ProcessError.FailedToStart:
            if PLATFORM == "win32":
                msg = _("Süreç başlatılamadı, WSL yüklü mü?")
            else:
                msg = _("Süreç başlatılamadı, bash/derle.sh bulunamadı")
        self.output_line.emit(f"[hata] {msg}\n")

        result = CompileResult(success=False)
        result.errors = [LatexError(message=msg)]
        result.duration = time.time() - self._start_time
        if error == QProcess.ProcessError.FailedToStart and PLATFORM == "win32":
            # WSL tamamen eksik: kurulum önerisi olarak girsin. Öneriler
            # sekmesi hem komutu gösterir hem (kurulum önerisi taşıyan
            # sonuçlarda) Ortam Denetimi satırını açar.
            result.suggestions.append(LatexSuggestion(
                message=_("WSL bulunamadı"),
                install_command="wsl --install  (yönetici PowerShell, ardından yeniden başlat)",
            ))
        if not self._finished_emitted:
            self._finished_emitted = True
            self.compilation_finished.emit(result)

    def _on_timeout(self):
        """Derleme watchdog: süre doldu — süreci sonlandır ve hata bildir."""
        if not self.process or self.process.state() == QProcess.ProcessState.NotRunning:
            return
        self._timeout_timer.stop()
        self._flush_output()
        # kill sonrası gelen _on_finished tekrar emit etmesin
        self._finished_emitted = True
        self.process.kill()
        self.process.waitForFinished(3000)
        sure = max(1, self._timeout_ms // 1000)
        msg = f"Derleme zaman aşımına uğradı ({sure}s), iptal edildi."
        self.output_line.emit(f"[hata] {msg}\n")
        result = CompileResult(success=False)
        result.errors = [LatexError(message=msg)]
        result.duration = time.time() - self._start_time
        self.compilation_finished.emit(result)

    def stop(self):
        """Derlemeyi iptal et — sonuç YAYMADAN.

        _finished_emitted burada da set edilmeli (_on_timeout ile aynı kalıp).
        Eskiden set edilmiyordu: waitForFinished içinde finished sinyali
        senkron gelip _on_finished'i çalıştırıyor, exit_code != 0 olduğu için
        normal bir "başarısız derleme" sonucu yayılıyordu. compile_ops o kolda
        PDF panelini temizleyip _current_pdf'i boşaltıyor — oysa ekrandaki PDF
        son BAŞARILI derlemenin çıktısı ve hâlâ geçerli. Yan etki olarak
        _current_pdf boşaldığı için SyncTeX de bir sonraki başarılı derlemeye
        kadar "Önce derleyin" demeye başlıyordu. İptal, başarısız derleme
        değildir.
        """
        if self.process and self.process.state() != QProcess.ProcessState.NotRunning:
            self._finished_emitted = True
            self.process.kill()
            self.process.waitForFinished(3000)
            self._timeout_timer.stop()

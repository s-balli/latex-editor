"""LaTeX derleme motoru — Windows (WSL), Linux, macOS desteği."""

import os
import re
import sys
import time
from pathlib import Path

from PyQt6.QtCore import QObject, QProcess, QTimer, pyqtSignal

from core.log_parser import CompileResult, LatexError, LatexSuggestion, parse_output
from core.paths import windows_to_wsl

PLATFORM = sys.platform  # win32, linux, darwin

# Derleme watchdog sınırı: bu sürede bitmeyen derleme iptal edilir.
DEFAULT_TIMEOUT_MS = 120_000


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
        self._start_time = 0.0
        self._tex_dir = ""
        self._tex_name = ""
        self._tex_path = ""
        self._engine = "lualatex"
        self._finished_emitted = False
        self._timeout_ms = DEFAULT_TIMEOUT_MS
        self._timeout_timer = QTimer(self)
        self._timeout_timer.setSingleShot(True)
        self._timeout_timer.timeout.connect(self._on_timeout)

    def compile(self, tex_path: str, engine: str = "lualatex", timeout_ms: int | None = None) -> bool:
        if self.process and self.process.state() != QProcess.ProcessState.NotRunning:
            return False

        if timeout_ms is not None:
            self._timeout_ms = timeout_ms
        tex_path = os.path.normpath(tex_path)
        self._tex_dir = str(Path(tex_path).parent)
        self._tex_name = Path(tex_path).stem
        self._tex_path = tex_path
        self._engine = engine
        self._output = ""
        self._start_time = time.time()
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
        self.process.start("wsl", args)

    def _start_native(self, tex_path: str, engine: str):
        """Linux/macOS: doğrudan bash ile derle."""
        derle_sh = _find_derle_sh()

        args = [derle_sh, tex_path]
        if engine == "pdflatex":
            args.append("--pdflatex")
        elif engine == "xelatex":
            args.append("--xelatex")

        self.process.start("bash", args)

    def _on_output(self):
        if not self.process:
            return
        data = self.process.readAllStandardOutput().data()
        text = data.decode("utf-8", errors="replace")
        text = re.sub(r'\x1b\[[0-9;]*m', '', text)
        self._output += text
        self.output_line.emit(text)

    def _on_finished(self, exit_code, exit_status):
        self._timeout_timer.stop()
        result = parse_output(self._output, self._tex_path)
        result.duration = time.time() - self._start_time

        pdf_path = os.path.join(self._tex_dir, f"{self._tex_name}.pdf")
        # PDF ancak bu derleme üretmişse geçerli (mtime >= derleme başlangıcı). Yoksa
        # önceki başarılı bir derlemeden kalan eski PDF olabilir — bayat. exit != 0
        # olsa bile taze PDF varsa yolunu bildir; GUI bunu kısmi önizleme için yükler.
        if os.path.exists(pdf_path) and os.path.getmtime(pdf_path) >= self._start_time:
            result.pdf_path = pdf_path

        result.success = (exit_code == 0 and bool(result.pdf_path))

        if not self._finished_emitted:
            self._finished_emitted = True
            self.compilation_finished.emit(result)

    def _on_error(self, error: QProcess.ProcessError):
        self._timeout_timer.stop()
        msg = "Derleme hatası"
        if error == QProcess.ProcessError.FailedToStart:
            msg = "Süreç başlatılamadı"
            if PLATFORM == "win32":
                msg += " — WSL yüklü mü?"
            else:
                msg += " — bash/derle.sh bulunamadı"
        self.output_line.emit(f"[hata] {msg}\n")

        result = CompileResult(success=False)
        result.errors = [LatexError(message=msg)]
        result.duration = time.time() - self._start_time
        if error == QProcess.ProcessError.FailedToStart and PLATFORM == "win32":
            # WSL tamamen eksik: kurulum önerisi olarak girsin. Öneriler
            # sekmesi hem komutu gösterir hem (kurulum önerisi taşıyan
            # sonuçlarda) Ortam Denetimi satırını açar.
            result.suggestions.append(LatexSuggestion(
                message="WSL bulunamadı",
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
        if self.process and self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill()
            self.process.waitForFinished(3000)

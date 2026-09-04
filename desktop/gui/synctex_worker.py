"""Arka plan SyncTeX arama worker'ı.

`gui.synctex` bridge fonksiyonları (`forward_search`/`reverse_search`) senkron
olarak `subprocess.run` çağırır; Windows'ta WSL soğuk başlangıcı 1–3 sn sürebilir.
Bunları doğrudan UI thread'inde çağırmak uygulamayı dondurur.

Bu worker, SyncTeX aramalarını tek bir uzun ömürlü QThread üzerinde yürütür.
Uygulama ömrü boyunca yalnızca bir thread ve en fazla bir WSL süreci aynı anda
çalışır. Hızlı art arda tıklamada kuyruk her zaman en son isteği tutar (yenisi
gelince eskisi ezilir); böylece gereksiz WSL süreçleri çoğalmaz.

Doğruluk: her istek kendi `context`'ini (tex_path/line veya page) taşır ve
worker `done` sinyaliyle bu context'i geri verir. UI thread'i sonucu daima
doğru context'e uygular — worker meşgulken gelen yeni istekler kuyrukta en
sonla değiştirilse de, işlenmiş bir sonucun etiketi asla yanlış context'e
yazılmaz.

İletişim (thread-safe — mutex + koşul değişkeni):
- UI thread → worker:  `submit(kind, args, synctex_dir, context)` ile yeni istek.
- worker → UI thread:  `done(kind, result, context)` sinyali.

Kapatma: `stop()` çağrısı sentinel ile thread'in temiz çıkması sağlanır.
"""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QMutex, QMutexLocker, QThread, QWaitCondition, pyqtSignal

from core.log import get_logger
from gui.synctex import forward_search, reverse_search

_logger = get_logger("synctex_worker")


class SyncTexWorker(QThread):
    """Uzun ömürlü SyncTeX arama worker'ı — tek thread, tek WSL süreci.

    En fazla bir istek kuyruğa alınır; yeni submit eskisinin yerini alır. Her
    istek kendi context'ini taşıdığı için sonuç daima doğru context'e uygulanır.
    """

    # kind, result, context
    done = pyqtSignal(str, object, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        # Kuyruk en fazla tek istek tutar; yeni istek eskisinin yerini alır.
        self._mutex = QMutex()
        self._cond = QWaitCondition()
        self._args = None           # (kind, args, synctex_dir, context) | None
        self._args_set = False      # Yeni istek geldi mi?
        self._stop = False

    def submit(self, kind: str, args: tuple, synctex_dir: str, context: Any = None):
        """Yeni SyncTeX arama isteği — eskisinin yerini alır (thread-safe).

        Worker meşgulse bile yeni istek bir sonraki iş döngüsünde alınır; arada
        gelmiş diğer istekler ezilmiş olur. `context` done sinyaliyle geri
        döndürülür, böylece sonuç doğru etikete uygulanır.
        """
        with QMutexLocker(self._mutex):
            self._args = (kind, args, synctex_dir, context)
            self._args_set = True
            self._cond.wakeAll()

    def stop(self):
        """Worker'ı temiz kapat — bir sonraki kontrol noktasında çıkar."""
        with QMutexLocker(self._mutex):
            self._stop = True
            self._args_set = True  # Bekleyen run()'u uyandırmak için
            self._cond.wakeAll()

    def run(self) -> None:  # noqa: D401 — QThread entry point
        while True:
            request = None
            with QMutexLocker(self._mutex):
                # Yeni istek veya stop gelene kadar bekle (periyodik stop kontrolü).
                while not self._args_set:
                    self._cond.wait(self._mutex, 100)
                    if self._stop:
                        return
                if self._stop:
                    return
                self._args_set = False
                request = self._args
                self._args = None

            if request is None:
                continue

            kind, args, synctex_dir, context = request
            try:
                if kind == "forward":
                    tex_path, line, col, pdf_path = args
                    result = forward_search(tex_path, line, col, pdf_path, synctex_dir)
                elif kind == "reverse":
                    page, x, y, pdf_path = args
                    result = reverse_search(page, x, y, pdf_path, synctex_dir)
                else:  # pragma: no cover — beklenmeyen kind
                    _logger.warning("SyncTeX worker bilinmeyen kind: %s", kind)
                    result = None
            # BU KOL YÜK TAŞIYOR, "her ihtimale karşı" değil. Ölçüldü:
            # `except Exception` daraltılınca (ör. `except ZeroDivisionError`)
            # köprüden kaçan bir RuntimeError iş parçacığını öldürmekle
            # kalmıyor, SÜRECİ öldürüyor — PyQt6 sanal metot (QThread.run)
            # içindeki yakalanmamış istisnada qFatal çağırıyor. Test koşusu
            # bu mutasyonla temiz bir hata değil, çıkış 127 veriyor.
            #
            # Üstelik tek uzun ömürlü işçi var ve onu yeniden başlatan yok:
            # kol kaldırılsaydı tek bir köprü hatası hem uygulamayı
            # kapatırdı hem de öncesinde SyncTeX'i tamamen ölü bırakırdı.
            except Exception:
                _logger.exception("SyncTeX worker beklenmeyen hata (kind=%s)", kind)
                result = None

            self.done.emit(kind, result, context)

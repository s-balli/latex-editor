"""SyncTeX forward/reverse arama mixin.

Aramalar tek bir uzun ömürlü `gui.synctex_worker.SyncTexWorker` thread'inde
yürütülür — WSL soğuk başlangıcı UI thread'ini bloklamaz. Worker kuyruğu her
zaman en son isteği tuttuğu için (yenisi gelince eskisi ezilir) gereksiz WSL
süreçleri çoğalmaz. Her istek kendi context'ini taşıdığı için sonuç daima
doğru etikete (tex_path:line veya page) uygulanır.
"""

import os

from core.log import get_logger
from gui.synctex_worker import SyncTexWorker
from PyQt6.QtCore import QCoreApplication

_ = lambda s: QCoreApplication.translate("SyncTexMixin", s)
_logger = get_logger("synctex_ops")


class SyncTexMixin:

    def _init_synctex_worker(self):
        """Worker'ı başlat — MainWindow.__init__'te çağrılır.

        Uzun ömürlü tek worker; done sinyali UI thread'inde callback'leri tetikler.
        """
        self._synctex_worker = SyncTexWorker(self)
        self._synctex_worker.done.connect(self._on_synctex_done)
        self._synctex_worker.start()

    def _on_synctex_done(self, kind: str, result, context):
        if kind == "forward":
            self._apply_forward(result, context)
        elif kind == "reverse":
            self._apply_reverse(result, context)

    def _on_forward_search(self, tex_path: str, line: int, col: int, quiet: bool = False):
        """İleri arama isteği. quiet=True: derleme sonrası otomatik atlamada
        durum çubuğu mesajları ezilmez, yalnızca kaydırma yapılır."""
        if not self._current_pdf or not os.path.exists(self._current_pdf):
            _logger.info("SyncTeX forward atlandı, PDF yok: %s:%d", os.path.basename(tex_path), line)
            if not quiet:
                self._status.showMessage(_("SyncTeX: Önce derleyin"))
            return
        if not self._synctex_gz_var_mi(self._current_pdf):
            _logger.info("SyncTeX forward atlandı, .synctex.gz yok: %s:%d", os.path.basename(tex_path), line)
            if not quiet:
                self._status.showMessage(_("SyncTeX: .synctex.gz bulunamadı, yeniden derleyin"))
            return

        self._synctex_worker.submit(
            "forward", (tex_path, line, col, self._current_pdf), self._synctex_dir,
            context=(tex_path, line, quiet),
        )

    def _apply_forward(self, result, context):
        tex_path, line, quiet = context
        if result:
            _logger.info("SyncTeX forward: %s:%d → sayfa %d", os.path.basename(tex_path), line, result.page)
            self._pdf_viewer.scroll_to_position(
                result.page, result.x, result.y,
                result.left, result.width, result.height,
            )
            if not quiet:
                # Cümle TEK PARÇA çevriliyor. Eskiden parçalardan kuruluyordu
                # ("SyncTeX: " + _("Satır") + ...) ve çevirmene bağlamsız tek
                # bir "Satır" kelimesi gidiyordu: katalogda "Row" olarak
                # çevrilmişti, yani İngilizce arayüzde "SyncTeX: Row 42 →
                # Page 3" yazıyordu. "Row" tablo satırı demek; burada
                # kastedilen kaynak satırı, yani "Line". Bütün cümleyi
                # görmeyen çevirmen bunu bilemez.
                self._status.showMessage(
                    _("SyncTeX: Satır {satir} → Sayfa {sayfa}").format(
                        satir=line, sayfa=result.page))
        else:
            _logger.info("SyncTeX forward eşleşme yok: %s:%d", os.path.basename(tex_path), line)
            if not quiet:
                self._status.showMessage(_("SyncTeX: Eşleşme bulunamadı"))

    def _synctex_gz_var_mi(self, pdf_path: str) -> bool:
        """Derleme dizininde bu PDF'in `.synctex.gz`i var mı.

        TEK KAYNAK: ileri ve ters arama AYNI ön koşula bağlı. Denetim
        yalnız ileri aramada yazılıydı ve ters arama onu almamıştı; ölçüldü
        2026-09-06, `.gz` yokken ters arama işçiye iş gönderiyordu.
        """
        gz_name = os.path.splitext(os.path.basename(pdf_path))[0] + ".synctex.gz"
        return os.path.exists(os.path.join(self._synctex_dir, gz_name))

    def _on_reverse_search(self, page: int, x: float, y: float, pdf_path: str):
        if not pdf_path or not os.path.exists(pdf_path):
            return
        # `.synctex.gz` denetimi ileri aramada vardı, burada YOKTU. Ölçüldü
        # 2026-09-06: `.gz` yokken ters arama yine de işçiye iş gönderiyor,
        # yani bir synctex/WSL süreci boşuna başlıyor (bu modülün başlığı
        # "Windows'ta WSL soğuk başlangıcı 1-3 sn sürebilir" diyor) ve sonuç
        # None döndüğü için kullanıcıya "Eşleşme bulunamadı" yazılıyordu.
        # Yanlış mesaj: kullanıcı konumu yanlış sanıyor, oysa yapması
        # gereken derlemek. İleri arama bu dersi zaten biliyordu.
        if not self._synctex_gz_var_mi(pdf_path):
            _logger.info("SyncTeX reverse atlandı, .synctex.gz yok: sayfa %d", page)
            self._status.showMessage(
                _("SyncTeX: .synctex.gz bulunamadı, yeniden derleyin"))
            return
        self._synctex_worker.submit(
            "reverse", (page, x, y, pdf_path), self._synctex_dir,
            context=page,
        )

    def _apply_reverse(self, result, context):
        page = context
        if result and result.file_path:
            _logger.info("SyncTeX reverse: sayfa %d → %s:%d", page, os.path.basename(result.file_path), result.line)
            self._goto_line(result.file_path, result.line)
            self._status.showMessage(
                _("SyncTeX: Sayfa {sayfa} → {dosya}:{satir}").format(
                    sayfa=page, dosya=os.path.basename(result.file_path),
                    satir=result.line))
        else:
            _logger.info("SyncTeX reverse eşleşme yok: sayfa %d", page)
            self._status.showMessage(_("SyncTeX: Eşleşme bulunamadı"))

    def _cleanup_synctex_worker(self):
        """closeEvent'te çağrılır — worker'ı temiz durdur ve bekle."""
        w = getattr(self, "_synctex_worker", None)
        if w is None:
            return
        w.stop()
        if w.isRunning():
            # Uçtaki synctex subprocess'u 3 sn timeout'la koşar; wait en az
            # onu kapsasın ki thread nesne yok edilirken çalışıyor kalmasın
            w.wait(4000)

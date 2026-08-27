"""Dosya izleme mixin — açık dosyaların diskte değişmesini algılar ve yeniden yükleme sunar."""

import hashlib
import os

from PyQt6.QtCore import QFileSystemWatcher, QTimer, QCoreApplication
from PyQt6.QtWidgets import QMessageBox

from gui.editor import EditorWidget
from core.log import get_logger

_ = lambda s: QCoreApplication.translate("FileWatchMixin", s)
_logger = get_logger("file_watch")


class FileWatchMixin:
    """MainWindow mixin: açık sekmelerdeki dosyaları QFileSystemWatcher ile izler,
    dış değişikliklerde kullanıcıya yeniden yükleme dialog'u gösterir."""

    def _file_watch_init(self):
        self._watcher = QFileSystemWatcher(self)
        self._watcher.fileChanged.connect(self._file_watch_on_change)

        self._pending_reloads: set[str] = set()
        self._save_hashes: dict[str, str] = {}
        # Modal "dosya değişti" dialog'u açıkken yeniden tur koşmasın:
        # dialog exec() event loop'u döndürür, debounce timer tekrar tetiklenip
        # farklı dosyalar için ikinci/üçüncü promptu üst üste yığardı
        self._reload_prompt_active = False

        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(500)
        self._debounce_timer.timeout.connect(self._file_watch_process_queue)

    # ------------------------------------------------------------------
    # Public API — file_ops / tab_ops tarafından çağrılır
    # ------------------------------------------------------------------

    def _file_watch_add(self, path: str):
        """Dosyayı izlemeye al (sekme açıldığında çağrılır)."""
        path = os.path.normpath(path)
        if not os.path.isfile(path):
            return
        if path not in self._watcher.files():
            self._watcher.addPath(path)
        self._save_hashes[path] = self._file_hash(path)
        _logger.debug("Watch eklendi: %s", path)

    def _file_watch_remove(self, path: str):
        """Dosyayı izlemeden kaldır (sekme kapatıldığında çağrılır)."""
        if not path:
            return
        path = os.path.normpath(path)
        if path in self._watcher.files():
            self._watcher.removePath(path)
        self._save_hashes.pop(path, None)
        self._pending_reloads.discard(path)
        _logger.debug("Watch kaldırıldı: %s", path)

    def _file_watch_record_save(self, path: str):
        """Kendi kaydımız sonrası hash'i güncelle — false-positive önler."""
        if not path:
            return
        path = os.path.normpath(path)
        if os.path.isfile(path):
            self._save_hashes[path] = self._file_hash(path)
            # Bazı platformlarda kaydetme watcher'ı kaldırır, yeniden ekle
            if path not in self._watcher.files():
                self._watcher.addPath(path)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _file_hash(path: str) -> str:
        """Dosya içeriğinin MD5 hash'ini döndürür."""
        h = hashlib.md5()
        try:
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    h.update(chunk)
        except OSError:
            return ""
        return h.hexdigest()

    def _file_watch_on_change(self, path: str):
        """QFileSystemWatcher.fileChanged sinyali handler — debounce."""
        path = os.path.normpath(path)
        self._pending_reloads.add(path)
        self._debounce_timer.start()  # zaten çalışıyorsa restart

    def _file_watch_process_queue(self):
        """Debounce süresi dolunca bekleyen tüm değişiklikleri işle."""
        if self._reload_prompt_active:
            # Dialog açık: promptlar üst üste birikmesin; kuyruk duruyor,
            # dialog kapanınca sonraki tur (aşağıdaki restart ile) devralır
            self._debounce_timer.start()
            return
        paths = set(self._pending_reloads)
        self._pending_reloads.clear()

        for path in paths:
            self._process_single(path)

    def _process_single(self, path: str):
        # 1) Dosya silinmiş mi?
        if not os.path.isfile(path):
            _logger.info("Dosya silinmiş: %s", path)
            self._watcher.removePath(path)
            self._save_hashes.pop(path, None)
            # İlgili sekmeyi bul ve kullanıcıya bildir
            editor = self._editor_by_path(path)
            if editor:
                self._handle_deleted_file(editor, path)
            return

        # 2) Hash aynı mı? (kendi kaydımız → atla)
        current_hash = self._file_hash(path)
        saved_hash = self._save_hashes.get(path)
        if saved_hash and current_hash == saved_hash:
            _logger.debug("Hash aynı, atlanıyor: %s", path)
            # Bazı OS'ler dosya dokunma anında watcher'ı kaldırır
            if path not in self._watcher.files():
                self._watcher.addPath(path)
            return

        # 3) İlgili editörü bul
        editor = self._editor_by_path(path)
        if editor is None:
            _logger.debug("Editör bulunamadı, watcher'dan kaldırılıyor: %s", path)
            self._watcher.removePath(path)
            self._save_hashes.pop(path, None)
            return

        # 4) Dialog göster
        self._prompt_reload(editor, path, current_hash)

        # 5) Bazı platformlarda fileChanged sonrası watcher kaldırılır, yeniden ekle
        if os.path.isfile(path) and path not in self._watcher.files():
            self._watcher.addPath(path)

    def _handle_deleted_file(self, editor: EditorWidget, path: str):
        """Dosya diskten silinmiş — kullanıcıya bildir ve sekmeyi kapat."""
        fname = os.path.basename(path)
        QMessageBox.information(
            self, _("Dosya Silindi"),
            _("{fname} dosyası diskten silindi.\nİlgili sekme kapatılacak.").format(fname=fname),
        )
        idx = self._editor_tabs.indexOf(editor)
        if idx >= 0:
            editor.setModified(False)  # save prompt olmadan kapat
            self._close_tab_safe(idx)

    def _prompt_reload(self, editor: EditorWidget, path: str, new_hash: str):
        """Kullanıcıya yeniden yükleme dialog'u göster."""
        fname = os.path.basename(path)

        if editor.isModified():
            msg = _(
                "{fname} dosyası diskte değiştirildi.\n\n"
                "Kaydedilmemiş yerel değişiklikleriniz var.\n"
                "Diskteki sürümü yüklerseniz yerel değişiklikleriniz kaybolacak."
            ).format(fname=fname)
            btn_reload_text = _("Diskten Yükle")
            btn_keep_text = _("Kendiminkini Koru")
        else:
            msg = _(
                "{fname} dosyası diskte başka bir program tarafından değiştirildi."
            ).format(fname=fname)
            btn_reload_text = _("Yeniden Yükle")
            btn_keep_text = _("Yoksay")

        dlg = QMessageBox(self)
        dlg.setWindowTitle(_("Dosya Değiştirildi"))
        dlg.setText(msg)
        dlg.setIcon(QMessageBox.Icon.Question)

        btn_reload = dlg.addButton(btn_reload_text, QMessageBox.ButtonRole.AcceptRole)
        btn_keep = dlg.addButton(btn_keep_text, QMessageBox.ButtonRole.RejectRole)
        dlg.setDefaultButton(btn_keep)

        self._reload_prompt_active = True
        try:
            dlg.exec()
        finally:
            self._reload_prompt_active = False

        if dlg.clickedButton() == btn_reload:
            # Cursor konumunu hatırla
            line, col = editor.getCursorPosition()
            editor.open_file(path)
            editor.setCursorPosition(line, col)
            self._save_hashes[path] = new_hash
            self._detect_engine(path)
            _logger.info("Dosya diskten yeniden yüklendi: %s", path)
        else:
            # Kullanıcı kendi sürümünü korumak istiyor — hash'i editor içeriğine güncelle
            # Böylece sonraki dış değişiklikte tekrar uyarı verilir
            self._save_hashes[path] = current_hash if (current_hash := self._file_hash(path)) else self._save_hashes.get(path, "")

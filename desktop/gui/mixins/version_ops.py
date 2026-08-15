"""Sürümleme mixin — Ctrl+K 'Sürümle', Geçmiş sekmesi, geri yükleme/fark.

Çekirdek core/versioning.py'dedir (dulwich). Kullanıcı hiçbir git kavramı
görmez: anlık görüntü metaforu. Klasör .git içeriyorsa olduğu gibi kullanılır.
"""

import os

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QInputDialog, QMessageBox

from core import versioning
from core.log import get_logger

_ = lambda s: QCoreApplication.translate("VersionOpsMixin", s)
_logger = get_logger("version_ops")


class VersionOpsMixin:

    def _version_root(self) -> str:
        tree = getattr(self, "_file_tree", None)
        return getattr(tree, "_root", "") or ""

    def _save_all_open(self) -> bool:
        """Açık kirli sekmeleri kaydet (anlık görüntü diskteki hâli alır)."""
        from gui.editor import EditorWidget
        for i in range(self._editor_tabs.count()):
            editor = self._editor_tabs.widget(i)
            if isinstance(editor, EditorWidget) and editor.isModified():
                if not editor.save_file():
                    return False
                if hasattr(self, "_file_watch_record_save"):
                    self._file_watch_record_save(editor.file_path)
        return True

    # --- Sürümle (Ctrl+K) ---

    def _snapshot(self):
        root = self._version_root()
        if not root or not os.path.isdir(root):
            self._status.showMessage(_("Önce bir klasör açın"))
            return
        if not versioning.DULWICH_AVAILABLE:
            self._status.showMessage(
                _("Sürümleme için 'dulwich' paketi gerekli") + " (pip install dulwich)")
            return
        if not self._save_all_open():
            self._status.showMessage(_("Kayıt başarısız — sürümleme iptal"))
            return

        first = not versioning.is_repo(root)
        default_msg = _("Başlangıç sürümü") if first else ""
        msg, ok = QInputDialog.getText(self, _("Sürümle"), _("Sürüm adı:"), text=default_msg)
        if not ok:
            return
        msg = msg.strip() or (_("Başlangıç sürümü") if first else _("Güncelleme"))

        try:
            if first:
                versioning.init_repo(root)
            entry = versioning.snapshot(root, msg)
        except Exception as e:
            _logger.error("Sürüm kaydı başarısız: %s", root, exc_info=True)
            self._status.showMessage(_("Sürüm kaydı başarısız") + f": {e}")
            return

        if entry is None:
            self._status.showMessage(_("Değişiklik yok — sürüm atlandı"))
            return
        self._status.showMessage(
            _("Sürüm kaydedildi") + f": {entry.short} · {entry.nfiles} " + _("dosya"))
        _logger.info("Sürüm kaydedildi: %s (%d dosya) — %s",
                     entry.short, entry.nfiles, msg)
        self._refresh_history(select_tab=True)

    # --- Geçmiş ---

    def _show_history(self):
        if not self._version_root():
            self._status.showMessage(_("Önce bir klasör açın"))
            return
        self._refresh_history(select_tab=True)

    def _refresh_history(self, select_tab: bool = False):
        root = self._version_root()
        try:
            entries = versioning.history(root) if root else []
        except Exception:
            _logger.error("Geçmiş okunamadı: %s", root, exc_info=True)
            entries = []
        self._output_panel.show_history(entries)
        if select_tab:
            self._output_panel._tabs.setCurrentIndex(
                self._output_panel._history_tab_index)

    # --- Geçmiş eylemleri (panel sinyali) ---

    def _on_version_action(self, action: str, sha: str):
        root = self._version_root()
        editor = self._current_editor()
        if not root or not editor or not editor.file_path:
            self._status.showMessage(_("Açık dosya yok"))
            return
        rel = os.path.relpath(editor.file_path, root).replace(os.sep, "/")

        if action == "diff":
            self._show_version_diff(root, sha, rel)
        elif action == "restore":
            self._restore_version(root, sha, rel, editor)

    def _show_version_diff(self, root: str, sha: str, rel: str):
        try:
            diff = versioning.file_diff(root, sha, rel)
        except Exception:
            _logger.error("Fark okunamadı: %s@%s", rel, sha, exc_info=True)
            self._status.showMessage(_("Fark okunamadı"))
            return
        if not diff:
            self._status.showMessage(_("Bu sürümle arasında fark yok"))
            return

        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QPlainTextEdit, \
            QDialogButtonBox
        dlg = QDialog(self)
        dlg.setWindowTitle(_("Fark") + f": {rel} @ {sha[:7]}")
        dlg.resize(720, 480)
        v = QVBoxLayout(dlg)
        view = QPlainTextEdit()
        view.setReadOnly(True)
        view.setPlainText(diff)
        view.setStyleSheet(
            "font-family: Consolas, 'DejaVu Sans Mono', monospace; font-size: 12px;")
        v.addWidget(view)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(dlg.reject)
        btns.accepted.connect(dlg.accept)
        v.addWidget(btns)
        dlg.exec()

    def _restore_version(self, root: str, sha: str, rel: str, editor):
        from gui.editor import EditorWidget

        answer = QMessageBox.question(
            self, _("Sürümden Geri Yükle"),
            _("{f} dosyası seçilen sürüme döndürülecek. Kaydedilmemiş "
              "değişiklikler kaybolur.").format(f=rel),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            content = versioning.file_content(root, sha, rel)
        except Exception:
            content = None
            _logger.error("Sürümden okunamadı: %s@%s", rel, sha, exc_info=True)
        if content is None:
            self._status.showMessage(_("Dosya bu sürümde bulunamadı"))
            return
        EditorWidget._write_atomic(editor.file_path, content, editor._encoding)
        editor.open_file(editor.file_path)
        self._status.showMessage(
            _("Geri yüklendi") + f": {rel} @ {sha[:7]}")
        _logger.info("Sürümden geri yüklendi: %s @ %s", rel, sha[:7])

"""Çökme kurtarma mixin — kirli sekmelerin periyodik anlık görüntüsü.

Saf disk mantığı core/recovery.py'de; burada yalnız zamanlayıcı, sekme
gezintisi ve kullanıcıya sorma var (bkz. o modülün başlığı).

Yaşam döngüsü:
    açılış   → _recovery_init  : dizini kur, zamanlayıcıyı başlat
    açılış   → _recovery_prompt: artık dosya varsa SOR, geri yükle ya da sil
    her 30sn → _recovery_tick  : kirli sekmeleri yaz, temizlenenleri sil
    kapanış  → _recovery_clear : temiz çıkışta hepsini sil

Temiz kapanışta silmek ŞART: silinmezse bir sonraki açılışta "kaydedilmemiş
değişiklik bulundu" diye sorar ve kullanıcı her açılışta aynı soruyu görür.
"""

import os
import uuid

from PyQt6.QtCore import QCoreApplication, QStandardPaths, QTimer
from PyQt6.QtWidgets import QMessageBox

from core import recovery
from core.log import get_logger
from gui.editor import EditorWidget

_ = lambda s: QCoreApplication.translate("RecoveryOpsMixin", s)
_logger = get_logger("recovery")

# 30 sn: basit ve öngörülebilir; en kötü hâlde 30 sn'lik yazım kaybedilir.
# Daha sık yazmak büyük belgede boşuna disk trafiği, daha seyrek yazmak
# kurtarmanın değerini düşürür.
_ARALIK_MS = 30_000


class RecoveryOpsMixin:

    # --- kurulum ---

    def _recovery_init(self, dizin: str = ""):
        """Kurtarma dizinini ve periyodik yazıcıyı kur.

        ``dizin`` yalnız testler için: verilmezse uygulama veri dizini
        kullanılır. Testin gerçek kurulum yolunu geçmesi, zamanlayıcının
        kurulduğunu da doğrular.
        """
        self._recovery_dir = dizin or _recovery_dizini()
        self._recovery_timer = QTimer(self)
        self._recovery_timer.setInterval(_ARALIK_MS)
        self._recovery_timer.timeout.connect(self._recovery_tick)
        self._recovery_timer.start()

    def _recovery_prompt(self):
        """Açılışta artık anlık görüntü varsa kullanıcıya sor.

        Sessiz geri yükleme BİLEREK yapılmıyor: kullanıcı kaydettiğini sandığı
        bir belgeyi "değişmiş" bulursa neye güveneceğini bilemez. Sorulur ve
        varsayılan kurtarmadır.
        """
        snaplar = recovery.oku(self._recovery_dir)
        if not snaplar:
            return
        # Diskte zaten aynı içerik varsa kayıp yok — sormadan at. (Kullanıcı
        # kaydetmiş, sonra uygulama çökmüş olabilir; boşuna korkutmayalım.)
        kayipli = [s for s in snaplar if recovery.kayip_var_mi(s)]
        temiz = len(snaplar) - len(kayipli)
        if temiz:
            _logger.info("%d anlık görüntü diskle aynı, atlandı", temiz)
        if not kayipli:
            recovery.hepsini_sil(self._recovery_dir)
            return

        adlar = "\n".join("  • " + s.display_name for s in kayipli[:10])
        if len(kayipli) > 10:
            adlar += "\n  • ..."
        dlg = QMessageBox(self)
        dlg.setWindowTitle(_("Kurtarma"))
        dlg.setIcon(QMessageBox.Icon.Question)
        dlg.setText(_(
            "Uygulama düzgün kapanmamış. {n} dosyada kaydedilmemiş değişiklik "
            "bulundu:\n\n{adlar}\n\n"
            "Geri yüklensin mi? (Geri yüklenen içerik sekmede açılır; siz "
            "kaydedene kadar diskteki dosyaya DOKUNULMAZ.)"
        ).format(n=len(kayipli), adlar=adlar))
        btn_yukle = dlg.addButton(_("Geri Yükle"), QMessageBox.ButtonRole.AcceptRole)
        btn_at = dlg.addButton(_("At"), QMessageBox.ButtonRole.DestructiveRole)
        dlg.setDefaultButton(btn_yukle)
        dlg.exec()

        if dlg.clickedButton() is btn_at:
            n = recovery.hepsini_sil(self._recovery_dir)
            _logger.info("Kurtarma reddedildi, %d anlık görüntü silindi", n)
            return

        yuklenen = 0
        for s in kayipli:
            if self._recovery_restore(s):
                yuklenen += 1
        # Geri yüklenenler artık sekmede ve KİRLİ; anlık görüntüleri bir sonraki
        # tick zaten tazeleyecek. Eskilerini bırakmak ikinci bir açılışta aynı
        # soruyu ürettiğinden temizle.
        recovery.hepsini_sil(self._recovery_dir)
        _logger.info("Kurtarma: %d/%d sekme geri yüklendi", yuklenen, len(kayipli))
        self._status.showMessage(
            _("{n} dosya kurtarıldı — kaydetmek için Ctrl+S").format(n=yuklenen))

    def _recovery_restore(self, snap) -> bool:
        """Bir anlık görüntüyü sekmeye yükle. İçerik KİRLİ olarak işaretlenir."""
        try:
            editor = self._editor_by_path(snap.file_path) if snap.file_path else None
            if editor is None:
                editor = EditorWidget(theme=self._theme_mgr.theme)
                self._apply_editor_settings(editor)
                if snap.file_path:
                    # open_file'ı ÇAĞIRMA: diskteki (eski) içeriği yükleyip
                    # üstüne yazmak gereksiz; yalnız kimliği kur.
                    editor._file_path = os.path.normpath(snap.file_path)
                    editor._encoding = snap.encoding
                    editor._newline = snap.newline
                self._connect_editor_signals(editor)
                idx = self._editor_tabs.addTab(editor, editor.display_name)
                self._add_tab_close_button(idx)
                if snap.file_path:
                    self._file_watch_add(snap.file_path)
            editor.setText(snap.content)
            editor.setModified(True)          # kaydetmek kullanıcının kararı
            return True
        except Exception:
            _logger.error("Anlık görüntü geri yüklenemedi: %s",
                          snap.file_path or "(yeni dosya)", exc_info=True)
            return False

    # --- periyodik yazım ---

    def _recovery_tick(self):
        """Kirli sekmeleri yaz, temizlenmiş olanların artığını sil."""
        for i in range(self._editor_tabs.count()):
            editor = self._editor_tabs.widget(i)
            if not isinstance(editor, EditorWidget):
                continue
            snap_id = _snap_id(editor)
            if editor.isModified():
                recovery.yaz(
                    self._recovery_dir, snap_id,
                    file_path=editor.file_path,
                    content=editor.text(),
                    encoding=getattr(editor, "_encoding", "utf-8"),
                    newline=getattr(editor, "_newline", "lf"),
                )
            else:
                # Kaydedildi → kurtarılacak bir şey kalmadı. Bırakılırsa
                # çökme sonrası bayat içerik "kaydedilmemiş değişiklik" diye
                # sunulur ve kullanıcı yeni kaydını eskisiyle ezebilir.
                recovery.sil(self._recovery_dir, snap_id)

    def _recovery_drop(self, editor):
        """Sekme kapanırken anlık görüntüsünü düşür (tab_ops çağırır)."""
        if isinstance(editor, EditorWidget):
            recovery.sil(self._recovery_dir, _snap_id(editor))

    def _recovery_clear(self):
        """Temiz kapanış: kurtarılacak bir şey yok."""
        self._recovery_timer.stop()
        recovery.hepsini_sil(self._recovery_dir)


def _snap_id(editor: EditorWidget) -> str:
    """Sekme başına kalıcı kimlik.

    Yol TABANLI olamaz: hiç kaydedilmemiş sekmelerin yolu yok ve "Farklı
    Kaydet" yolu değiştirdiğinde eski anlık görüntü öksüz kalırdı.
    """
    sid = getattr(editor, "_recovery_id", "")
    if not sid:
        sid = uuid.uuid4().hex
        editor._recovery_id = sid
    return sid


def _recovery_dizini() -> str:
    """Uygulama veri dizini altındaki kurtarma klasörü (log ile aynı kök)."""
    return os.path.join(
        QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation),
        "LatexEditor", "recovery",
    )

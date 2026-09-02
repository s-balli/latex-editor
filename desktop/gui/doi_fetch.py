"""DOI ile kaynak ekleme: arka plan getirme + onay diyalogu.

Ağ çağrısı UI thread'inde YAPILAMAZ: ölçülen süre ~0.5 sn ama zaman aşımı
8 sn ve kopuk bağlantıda o süre boyunca arayüz tamamen donardı. Desen
`file_ops._ExportRunner` ile aynı: daemon thread + sinyal.

Getirilen BibTeX doğrudan dosyaya YAZILMIYOR; önce normalleştirilip
kullanıcıya gösteriliyor. Gerekçe `core.bibtex.normallestir` içinde: gelen
girdi tek satır, ayı standart olmayan bir makroya bağlıyor ve sayfa
aralığını orta tireyle veriyor (üçü de gerçek derlemeyle ölçüldü).
"""

import threading

from PyQt6.QtCore import QCoreApplication, QObject, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QLabel, QPlainTextEdit, QVBoxLayout,
)

from core.bibtex import DoiHatasi, doi_getir, normallestir
from core.log import get_logger

_ = lambda s: QCoreApplication.translate("DoiFetch", s)
_logger = get_logger("doi_fetch")


class DoiRunner(QObject):
    """DOI'yi arka planda getirip normalleştirir."""

    # (basarili, girdi_metni, anahtar, hata_kodu)
    done = pyqtSignal(bool, str, str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread = None

    def start(self, doi: str, mevcut_anahtarlar):
        anahtarlar = list(mevcut_anahtarlar or ())

        def work():
            try:
                ham = doi_getir(doi)
                metin, anahtar = normallestir(ham, mevcut_anahtarlar=anahtarlar)
            except DoiHatasi as e:
                self.done.emit(False, "", "", str(e) or "ag")
                return
            except Exception:
                _logger.warning("DOI getirme beklenmedik hata: %s", doi, exc_info=True)
                self.done.emit(False, "", "", "ag")
                return
            self.done.emit(True, metin, anahtar, "")

        self._thread = threading.Thread(target=work, name="doi-fetch", daemon=True)
        self._thread.start()

    def wait(self, timeout_ms: int) -> bool:
        """İş bitene kadar bekle. True = bitti/zaten boştaydı."""
        t = self._thread
        if t is None or not t.is_alive():
            return True
        t.join(timeout_ms / 1000)
        return not t.is_alive()


class DoiOnayDialog(QDialog):
    """Eklenecek girdiyi göster ve onaylat.

    Metin DÜZENLENEBİLİR: getirilen kayıt her zaman eksiksiz değil (yayıncı
    verisi eksik olabiliyor) ve kullanıcı dosyaya yazılmadan önce düzeltmek
    isteyebilir. Düzenleme burada güvenli, çünkü dosyaya eklenen tam olarak
    ekranda görünen metin.
    """

    def __init__(self, girdi_metni: str, bib_adi: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_("DOI ile Kaynak Ekle"))
        self.setMinimumSize(640, 380)

        yerlesim = QVBoxLayout(self)
        yerlesim.addWidget(QLabel(
            _("Bu girdi '{d}' dosyasının sonuna eklenecek:").format(d=bib_adi)))

        self._metin = QPlainTextEdit(girdi_metni)
        self._metin.setStyleSheet(
            "font-family: Consolas, 'DejaVu Sans Mono', monospace; font-size: 12px;")
        yerlesim.addWidget(self._metin)

        dugmeler = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        dugmeler.button(QDialogButtonBox.StandardButton.Ok).setText(_("Ekle"))
        dugmeler.accepted.connect(self.accept)
        dugmeler.rejected.connect(self.reject)
        yerlesim.addWidget(dugmeler)

    def girdi(self) -> str:
        return self._metin.toPlainText().strip()

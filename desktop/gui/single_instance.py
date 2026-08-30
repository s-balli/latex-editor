"""Tek örnek koruması + çalışan örneğe dosya iletimi.

Neden gerekli
-------------
Uygulama Windows'ta `.tex` için ProgID kaydediyor, ikon kopyalıyor ve
`shell\\open\\command` yazıyor — yani "Birlikte Aç" listesine giriyor. Ama
ikinci örnek yalnızca QLockFile ile reddediliyordu: uygulama açıkken bir
`.tex`'e çift tıklayan kullanıcı dosyayı açamıyor, "zaten çalışıyor"
uyarısı alıyordu. Dosya ilişkilendirmesinin tamamı ilk açılıştan sonra
işlevsizdi.

Burada eksik halka tamamlanıyor: ikinci örnek yolu çalışan örneğe iletip
sessizce çıkıyor, çalışan örnek dosyayı yeni sekmede açıp öne geliyor.

Ad neden kullanıcıyı içeriyor
-----------------------------
Kilit dosyası QStandardPaths.TempLocation altına yazılıyor; bu Windows'ta
kullanıcıya özel (AppData\\Local\\Temp) ama Linux'ta PAYLAŞIMLI (/tmp).
Sabit adla, çok kullanıcılı bir Linux makinesinde (üniversite laboratuvarı —
bu uygulamanın tipik ortamı) ikinci kullanıcı uygulamayı HİÇ açamıyordu:
QLockFile birinci kullanıcının canlı PID'ini görüp reddediyordu. Ada
kullanıcı adı katılınca her kullanıcının kendi kilidi ve kendi soketi olur.
"""

import os
import re
import time

from PyQt6.QtCore import (QCoreApplication, QEventLoop, QLockFile, QObject,
                          QStandardPaths, pyqtSignal)
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

from core.log import get_logger

_logger = get_logger("single_instance")

# İkinci örnek bağlanırken/yazarken bu süreden fazla beklemez: çalışan örnek
# donmuşsa kullanıcı süresiz asılı kalmasın, uyarıyı görüp devam etsin.
_TIMEOUT_MS = 3000


def _kullanici() -> str:
    """Ad bileşeni olarak güvenli kullanıcı adı (bulunamazsa 'default')."""
    ham = os.environ.get("USER") or os.environ.get("USERNAME") or "default"
    temiz = re.sub(r"[^A-Za-z0-9_-]", "_", ham)[:32]
    return temiz or "default"


class SingleInstance(QObject):
    """Tek örnek kilidi + çalışan örneğe yol iletimi.

    Kullanım:
        si = SingleInstance()
        if si.try_become_primary():
            si.file_received.connect(pencere.dosya_ac)
        else:
            si.send(yol)   # veya False dönerse kullanıcıyı uyar
    """

    file_received = pyqtSignal(str)   # iletilen dosya yolu ("" = yalnız öne getir)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ad = f"latex-editor-{_kullanici()}"
        self._lock: QLockFile | None = None
        self._server: QLocalServer | None = None

    # --- birincil taraf ---

    def try_become_primary(self) -> bool:
        """Kilidi al ve dinlemeye başla. False = başka bir örnek çalışıyor."""
        lock_dir = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.TempLocation)
        self._lock = QLockFile(os.path.join(lock_dir, f"{self._ad}.lock"))
        # 0 = zamana bağlı bayatlama yok. QLockFile ayrıca PID canlılığına
        # bakar, o yüzden çökme sonrası kilit yine de devralınır.
        self._lock.setStaleLockTime(0)
        if not self._lock.tryLock(100):
            self._lock = None
            return False

        # Çökmeden kalan soket dosyası/pipe'ı temizle. Kilidi aldığımıza göre
        # başka canlı birincil yok; bu silme güvenli.
        QLocalServer.removeServer(self._ad)
        self._server = QLocalServer(self)
        if not self._server.listen(self._ad):
            # Dinleyemesek bile birincil olarak çalışmaya devam ederiz;
            # yalnız ikinci örnekten dosya iletimi çalışmaz.
            _logger.warning("Yerel sunucu dinlenemedi (%s): %s",
                            self._ad, self._server.errorString())
            self._server = None
        else:
            self._server.newConnection.connect(self._on_connection)
        return True

    def _on_connection(self):
        if self._server is None:
            return
        sock = self._server.nextPendingConnection()
        if sock is None:
            return
        tampon = bytearray()
        islendi = []

        def oku():
            # Çerçeve: "<bayt sayısı>\n<yük>". Uzunluk öneki şart — "gönderen
            # kapatınca mesaj bitti" varsayımı Windows'ta ÇALIŞMIYOR: named pipe
            # üzerinde disconnectFromServer bekleyen veriyi atabiliyor ve sunucu
            # boş yük görüyordu. Önekle mesajın tamamlandığı kapanmadan bilinir.
            tampon.extend(bytes(sock.readAll()))
            if islendi or b"\n" not in tampon:
                return
            bas, _, govde = bytes(tampon).partition(b"\n")
            try:
                uzunluk = int(bas)
            except ValueError:
                _logger.warning("Geçersiz çerçeve başlığı; bağlantı kapatılıyor")
                sock.abort()
                return
            if len(govde) < uzunluk:
                return                      # gerisi henüz gelmedi
            islendi.append(True)
            yol = govde[:uzunluk].decode("utf-8", "replace")
            _logger.info("İkinci örnekten istek geldi: %s", yol or "(yalnız öne getir)")
            # Önce kapat: gönderen kapanmayı "teslim edildi" onayı sayıyor ve
            # bekliyor; sinyal işleyicisi (dosya açma, pencere öne alma) uzun
            # sürerse onu boşuna bekletmeyelim.
            sock.disconnectFromServer()
            self.file_received.emit(yol)

        sock.readyRead.connect(oku)
        sock.disconnected.connect(sock.deleteLater)

    # --- ikincil taraf ---

    def send(self, payload: str = "") -> bool:
        """Çalışan örneğe yolu ilet. False = ulaşılamadı (uyarı göster)."""
        sock = QLocalSocket()
        sock.connectToServer(self._ad)
        if not sock.waitForConnected(_TIMEOUT_MS):
            _logger.warning("Çalışan örneğe bağlanılamadı: %s", sock.errorString())
            return False
        # waitForBytesWritten KULLANILMIYOR: Windows'ta QLocalSocket adlandırılmış
        # boru üzerinde çalışıyor ve orada bu çağrı güvenilir değil — yazım
        # tamamlansa bile "Unknown error" ile False dönüyor.
        veri = payload.encode("utf-8")
        sock.write(str(len(veri)).encode("ascii") + b"\n" + veri)
        sock.flush()

        # Teslim onayı: karşı taraf çerçeveyi TAMAMEN okuyunca bağlantıyı
        # kapatıyor. Kapanmayı beklemek "ulaştı" demektir; kapanmazsa çalışan
        # örnek donmuş demektir ve çağıran kullanıcıyı uyarır.
        #
        # waitForDisconnected yerine olay döngüsü çevriliyor: bu süreç kendi
        # penceresini hiç açmayacak, olayları burada işlemek zararsız — ve
        # testlerde sunucu aynı süreçte olduğundan bloklayan bekleme kilitlenir.
        son = time.monotonic() + _TIMEOUT_MS / 1000
        while sock.state() != QLocalSocket.LocalSocketState.UnconnectedState:
            if time.monotonic() > son:
                _logger.warning("Çalışan örnek teslimi onaylamadı (zaman aşımı)")
                return False
            QCoreApplication.processEvents(
                QEventLoop.ProcessEventsFlag.AllEvents, 20)
        return True

    # --- temizlik ---

    def stop(self):
        if self._server is not None:
            self._server.close()
            self._server = None
        if self._lock is not None:
            self._lock.unlock()
            self._lock = None

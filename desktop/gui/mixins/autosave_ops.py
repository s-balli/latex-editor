"""Otomatik kaydetme mixin — kirli sekmeleri periyodik olarak KENDİ dosyasına yaz.

Çökme kurtarmanın (recovery_ops) kardeşi ama aynı iş DEĞİL: kurtarma yan bir
kopya yazıp açılışta soruyor, burada kullanıcının kendi dosyası yazılıyor.
İkisi birlikte çalışıyor; otomatik kaydetme başarılı olunca sekme temizleniyor
ve `_recovery_tick` artığı kendiliğinden siliyor.

Yaşam döngüsü:
    açılış       → _autosave_init   : ayarı oku, zamanlayıcıyı kur
    ayar değişti → _autosave_uygula : açıklığı ve aralığı güncelle
    her N dk     → _autosave_tick   : kirli VE yolu olan sekmeleri kaydet

Üç kural, üçü de bilerek:

1. YOLU OLMAYAN sekme kaydedilmiyor. Hiç kaydedilmemiş bir tampon için
   zamanlayıcıdan "Farklı Kaydet" kutusu açmak, kullanıcının istemediği bir
   anda önüne modal bir pencere koymak olurdu. O tamponları çökme kurtarma
   zaten koruyor.
2. Yazma MODAL kutu açmıyor (`save_file(sessiz=True)`). Salt okunur bir
   hedefte kutu her turda tekrar açılırdı; kullanıcıya durum çubuğundan bir
   kez söyleniyor ve aynı dosya için tekrarlanmıyor.
3. Kayıt `_file_watch_record_save` ile işaretleniyor. İşaretlenmezse dosya
   izleyici kendi yazdığımızı "dosya dışarıdan değişti" sanıp her turda
   yeniden yükleme sorardı.

Derleme TETIKLENMIYOR: Ctrl+S yolundaki `_on_save_and_compile` otomatik
derlemeyi de çalıştırıyor, otomatik kaydetme onu kullanmıyor. Yoksa arka
planda her N dakikada bir derleme başlardı.
"""

import os

from PyQt6.QtCore import QCoreApplication, QTimer

from core.log import get_logger
from gui.editor import EditorWidget

_ = lambda s: QCoreApplication.translate("AutosaveOpsMixin", s)
_logger = get_logger("autosave")

# Dakika cinsinden sınırlar: sıfır aralık sürekli yazma, absürt büyük değer
# özelliği işlevsiz demek. Ayar dosyası bozuksa varsayılana dönülüyor
# (bkz. main_window._ayar_sayi, aynı ders orada ölçülmüştü).
AUTOSAVE_MIN_DK = 1
AUTOSAVE_MAX_DK = 60
AUTOSAVE_VARSAYILAN_DK = 3


class AutosaveOpsMixin:

    def _autosave_init(self):
        """Zamanlayıcıyı kur ve ayara göre başlat."""
        self._autosave_timer = QTimer(self)
        self._autosave_timer.timeout.connect(self._autosave_tick)
        # Yazılamayan dosyalar: aynı hata her turda tekrar söylenmesin.
        self._autosave_bildirilen = set()
        self._autosave_uygula()

    def _autosave_uygula(self):
        """Ayarı oku, zamanlayıcıyı ona göre çalıştır ya da durdur."""
        s = self._read_editor_settings()
        self._autosave_timer.setInterval(s["autosave_dk"] * 60_000)
        if s["autosave"]:
            self._autosave_timer.start()
        else:
            self._autosave_timer.stop()

    def _autosave_tick(self):
        """Kirli ve yolu olan sekmeleri sessizce kaydet."""
        kaydedilen = 0
        for i in range(self._editor_tabs.count()):
            editor = self._editor_tabs.widget(i)
            if not isinstance(editor, EditorWidget):
                continue
            if not editor.isModified() or not editor.file_path:
                continue
            yol = editor.file_path
            # Kullanıcı dosyayı diskten silmiş ve "Sekmede Tut" demişse
            # DİSKE GERİ YAZMA. ÖLÇÜLDÜ (2026-09-09): dosya silindikten
            # sonra otomatik kaydetme onu sessizce yeniden yaratıyordu;
            # kullanıcı sildiğini sandığı dosyayı dosya ağacında, git
            # durumunda ve derleme çıktısında yeniden buluyordu. İçerik
            # sekmede duruyor ve çökme kurtarması onu zaten koruyor;
            # geri yazmak istiyorsa Ctrl+S bunu açıkça yapıyor.
            if yol in getattr(self, "_silinen_tutulanlar", ()):
                continue
            # Disk DIŞARIDAN değişti ve kullanıcı "Kendiminkini Koru" dedi.
            # O karar "arabelleğim kalsın" demek, "diski ez" demek DEĞİL.
            # ÖLÇÜLDÜ (2026-09-09): dıştan gelen değişiklik (git checkout,
            # ortak yazar, senkron istemcisi) üç dakika içinde sessizce
            # kayboluyordu. Kullanıcı ezmek isterse Ctrl+S bunu açıkça
            # yapıyor ve işareti de düşürüyor.
            if yol in getattr(self, "_disk_ayristi", ()):
                continue
            if editor.save_file(sessiz=True):
                kaydedilen += 1
                self._autosave_bildirilen.discard(yol)
                if hasattr(self, "_file_watch_record_save"):
                    self._file_watch_record_save(yol)
            elif yol not in self._autosave_bildirilen:
                self._autosave_bildirilen.add(yol)
                _logger.warning("Otomatik kaydetme başarısız: %s", yol)
                self._status.showMessage(
                    _("Otomatik kaydedilemedi: {ad}").format(
                        ad=os.path.basename(yol)), 8000)
        if kaydedilen:
            self._status.showMessage(
                _("Otomatik kaydedildi ({n} dosya)").format(n=kaydedilen),
                3000)

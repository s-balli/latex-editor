"""Projede ara (Ctrl+Shift+F) — proje kökü altındaki dosyaların İÇERİĞİNDE arama.

Uygulamadaki diğer aramalardan farkı:
  Ctrl+F        → yalnız açık sekmede (tek belge)
  PDF araması   → derlenmiş PDF'te
  Ctrl+P        → dosya ADLARINDA
Burada aranan, sekmede açık OLMAYANLAR dahil tüm .tex/.cls/.sty/.bib
dosyalarının içeriği.

Tarama `gui.project_search_worker` thread'inde koşar (gerekçesi orada
ölçümle birlikte). Sonuçlar `search_id` ile damgalıdır: yazarken art arda
Enter'a basılınca eski taramanın geç dönen sonucu yenisini ezmez.

Kök, dosya ağacının köküdür — Ctrl+P ile aynı kaynak, yani "hangi proje"
sorusunun tek bir cevabı var.
"""

import os

from PyQt6.QtCore import QCoreApplication

from core.log import get_logger
from gui.project_search_worker import ProjectSearchWorker

_ = lambda s: QCoreApplication.translate("ProjectSearchMixin", s)
_logger = get_logger("project_search")

# Kutuya taşınacak seçili metnin üst sınırı: bütün bir paragrafı seçip
# Ctrl+Shift+F'e basmak arama kutusunu kullanılmaz hâle getirmesin.
_SECIM_SINIRI = 100


class ProjectSearchMixin:

    def _init_project_search(self):
        """MainWindow.__init__'te çağrılır."""
        self._psearch_id = 0
        self._psearch_root = ""
        self._project_search_worker = ProjectSearchWorker()
        self._project_search_worker.found.connect(self._on_project_search_done)
        self._project_search_worker.start()

    def _project_search(self):
        """Ctrl+Shift+F: paneli aç, kutuya odaklan."""
        secili = ""
        ed = self._current_editor()
        if ed is not None and ed.hasSelectedText():
            metin = ed.selectedText()
            # Çok satırlı seçim sorgu olmaz (arama düz metin, satır içi)
            if "\n" not in metin and " " not in metin and len(metin) <= _SECIM_SINIRI:
                secili = metin
        # Kök ARAMADAN ÖNCE görünsün: kullanıcı yanlış klasörde arattığını
        # sonuç beklemeden anlasın.
        self._output_panel.set_project_search_root(self._file_tree._root)
        self._output_panel.focus_project_search(secili)

    def _kok_disinda_mi(self, kok: str) -> str:
        """Açık dosya kökün DIŞINDAysa açıklama metni, değilse boş dize.

        "bulunamadı" tek başına yanıltıcıydı: kök QSettings'ten geri yüklenen
        eski bir klasörde kalmışken (template15) kullanıcı bambaşka bir
        dosyada (tmp/bigpdf/big.tex) 1800 kez geçen bir kelimeyi arayıp boş
        sonuç aldı. Arama doğru çalışıyordu, YANLIŞ YERDE arıyordu.
        """
        ed = self._current_editor()
        yol = getattr(ed, "file_path", "") if ed is not None else ""
        if not yol or not kok:
            return ""
        try:
            ortak = os.path.commonpath([os.path.abspath(yol), os.path.abspath(kok)])
        except ValueError:      # farklı sürücü (Windows)
            return _("açık dosya bu klasörün dışında ({ad})").format(
                ad=os.path.basename(yol))
        if ortak == os.path.abspath(kok):
            return ""
        return _("açık dosya bu klasörün dışında ({ad})").format(
            ad=os.path.basename(yol))

    def _on_project_search_requested(self, sorgu: str, case_sensitive: bool):
        root = self._file_tree._root
        if not root or not os.path.isdir(root):
            # Ctrl+P ile aynı davranış: klasör açılmadan proje diye bir şey yok.
            self._output_panel.show_project_search([], False, "")
            self._status.showMessage(_("Önce bir klasör açın"))
            _logger.info("Projede ara: klasör açık değil, arama yapılmadı")
            return
        self._psearch_id += 1
        self._psearch_root = root
        self._project_search_worker.search(
            self._psearch_id, root, sorgu, case_sensitive)

    def _on_project_search_done(self, search_id: int, bulgular: list, kesildi: bool):
        if search_id != self._psearch_id:
            return          # bayat sonuç: kullanıcı yeni sorgu yazmış
        uyari = self._kok_disinda_mi(self._psearch_root) if not bulgular else ""
        self._output_panel.show_project_search(
            bulgular, kesildi, self._psearch_root, uyari)
        _logger.info("Projede ara: %d bulgu%s — kök: %s", len(bulgular),
                     " (kırpıldı)" if kesildi else "", self._psearch_root)

    def _cleanup_project_search(self):
        """closeEvent'te çağrılır — işçiyi temiz durdur ve bekle."""
        w = getattr(self, "_project_search_worker", None)
        if w is None:
            return
        w.stop()
        if w.isRunning():
            # Süren tarama dosya başına iptal denetliyor; tek dosyanın okunması
            # ağ paylaşımında birkaç yüz ms sürebilir, pay bırakılıyor.
            w.wait(6000)

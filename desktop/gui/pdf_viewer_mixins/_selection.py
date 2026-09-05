"""PdfViewer secim mixin — metin secme, vurgulama ve kopyalama."""

import unicodedata

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QLabel, QApplication, QMenu

from gui.pdfium_lock import pdfium_lock
from gui.pdf_donusum import geometri, kullaniciya, kutu_gorsele

from PyQt6.QtCore import QCoreApplication
_ = lambda s: QCoreApplication.translate("PdfViewer", s)


class PdfSelectionMixin:

    def _init_selection_state(self):
        self._selection_start_label_pos = None
        self._selection_start_page = None
        self._selection_start_label = None
        self._selection_drag_started = False
        self._selection_highlights = []
        self._selected_text = ""
        self._selection_char_range = None
        self._pending_click_timer = None

    def _pos_to_page(self, pos, obj):
        """pos (obj koordinatlarinda) → (sayfa indeksi, label uzerinde pozisyon).

        `obj` sayfa etiketinin KENDİSİYSE döngüye hiç girilmiyor. Kardeş bir
        etikete `mapFrom` çağırmak Qt'de tanımlı değil: dönen nokta
        `pos - label.pos()` oluyor ve eş boyutlu sayfalarda çoğu zaman İLK
        etiketin dikdörtgenine düşüyor. Ölçüldü (2026-09-02, dış rapor
        6. tur; Qt 6.11):

            pencere geniş (sayfa yatayda ortalı)  x negatife düşüyor, doğru
                                                  sayfa bulunuyor (TESADÜF)
            pencere dar   (ortalama payı yok)     2. sayfaya tıklama 1.
                                                  sayfaya çözümleniyor

        Yani hata sürüme değil, pencere genişliğine bağlıydı: aynı kullanıcı
        pencereyi daralttığında SyncTeX geri araması, metin seçimi ve
        bağlantı tıklaması yanlış sayfaya gidiyordu.
        """
        if not self._pdf:
            return None, None
        try:
            i = self._page_labels.index(obj)
        except ValueError:
            i = -1
        if i >= 0:
            if i < self._page_count and obj.rect().contains(pos):
                return i, pos
            return None, None
        # Kapsayıcıdan geldiyse mapFrom meşru: obj gerçekten ata.
        for i, label in enumerate(self._page_labels):
            if i >= self._page_count:
                break
            label_pos = label.mapFrom(obj, pos)
            if label.rect().contains(label_pos):
                return i, label_pos
        return None, None

    def _selection_press(self, pos, obj):
        self._clear_selection()
        page_idx, label_pos = self._pos_to_page(pos, obj)
        if page_idx is None:
            return
        self._selection_start_label_pos = label_pos
        self._selection_start_page = page_idx
        self._selection_start_label = self._page_labels[page_idx]
        self._selection_drag_started = False

    def _selection_move(self, pos, obj):
        if self._selection_start_label_pos is None:
            return False
        label = self._selection_start_label
        label_pos = label.mapFrom(obj, pos) if obj != label else pos
        delta = (label_pos - self._selection_start_label_pos).manhattanLength()
        if delta < 4:
            return False

        if not self._selection_drag_started:
            self._selection_drag_started = True

        self._update_selection_highlight(
            self._selection_start_page,
            self._selection_start_label_pos,
            label_pos,
        )
        return True

    def _selection_release(self, pos, obj):
        if self._selection_drag_started:
            self._selection_drag_started = False
            return True

        if self._pending_click_timer:
            self._pending_click_timer.stop()
            self._pending_click_timer.deleteLater()
        self._pending_click_timer = QTimer(self)
        self._pending_click_timer.setSingleShot(True)

        def _deferred_click(pos=pos, obj=obj):
            try:
                self._handle_link_click(pos, obj)
            except RuntimeError:
                # 150 ms içinde derleme refresh'i placeholder'ı sildi: label'ın
                # C++ tarafı çoktan yok, tıklamayı sessizce düşür
                pass

        self._pending_click_timer.timeout.connect(_deferred_click)
        self._pending_click_timer.start(150)
        return False

    def _selection_dblclick(self, pos, obj):
        if self._pending_click_timer:
            self._pending_click_timer.stop()
            # deleteLater şart: sadece = None bırakılırsa viewer'a parent'lı
            # QTimer her çift tıklamada öksüz kalır (birikir)
            self._pending_click_timer.deleteLater()
            self._pending_click_timer = None

        self._clear_selection()
        page_idx, label_pos = self._pos_to_page(pos, obj)
        if page_idx is None:
            return

        try:
            with pdfium_lock:
                page = self._pdf[page_idx]
                textpage = page.get_textpage()
                scale = self._olcek(page_idx)
                # `get_index` DONDURULMEMIS kullanici uzayi bekliyor;
                # `get_height()` ise GORSEL boyut. /Rotate'li sayfada bu
                # karisim hicbir karakteri bulamiyordu (bkz. pdf_donusum).
                x_pdf, y_pdf = kullaniciya(geometri(page), label_pos.x(),
                                           label_pos.y(), scale)
                idx = textpage.get_index(x_pdf, y_pdf, x_tol=5.0, y_tol=5.0)
                if idx is None or idx < 0:
                    return

                total = textpage.count_chars()
                start = idx
                end = idx
                while start > 0 and not self._is_word_boundary(textpage, start):
                    start -= 1
                while end < total - 1 and not self._is_word_boundary(textpage, end + 1):
                    end += 1

                if start <= end:
                    self._selection_char_range = (page_idx, start, end)
                    self._selected_text = textpage.get_text_range(start, end - start + 1) or ""
                    self._draw_selection_highlights(page_idx, start, end, textpage)
        except Exception:
            pass

    def _is_word_boundary(self, textpage, idx):
        try:
            with pdfium_lock:
                ch = textpage.get_text_range(idx, 1)
            if not ch:
                return True
            return ch[0].isspace()
        except Exception:
            return True

    def _selection_right_click(self, pos, obj):
        if not self._selected_text:
            return False
        global_pos = self.mapToGlobal(pos)
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background: {self._theme['bg_toolbar']}; color: {self._theme['fg_primary']}; "
            f"border: 1px solid {self._theme['border_separator']}; padding: 4px; }}"
            f"QMenu::item {{ padding: 5px 24px; border-radius: 3px; }}"
            f"QMenu::item:selected {{ background: {self._theme['bg_pressed']}; }}"
        )
        copy_action = menu.addAction(_("Kopyala"))
        action = menu.exec(global_pos)
        if action == copy_action:
            self._copy_selection()
        return True

    def _update_selection_highlight(self, page_idx, start_lp, end_lp):
        """Iki label-pozisyonu arasini sec (ayni sayfa label koordinatlarinda)."""
        try:
            with pdfium_lock:
                page = self._pdf[page_idx]
                textpage = page.get_textpage()
                scale = self._olcek(page_idx)

                g = geometri(page)
                x1, y1 = kullaniciya(g, start_lp.x(), start_lp.y(), scale)
                x2, y2 = kullaniciya(g, end_lp.x(), end_lp.y(), scale)

                idx1 = textpage.get_index(x1, y1, x_tol=5.0, y_tol=5.0)
                idx2 = textpage.get_index(x2, y2, x_tol=5.0, y_tol=5.0)
                if idx1 is None or idx2 is None or idx1 < 0 or idx2 < 0:
                    return

                lo, hi = (idx1, idx2) if idx1 <= idx2 else (idx2, idx1)

                if self._selection_char_range == (page_idx, lo, hi):
                    return

                self._selection_char_range = (page_idx, lo, hi)
                self._selected_text = textpage.get_text_range(lo, hi - lo + 1) or ""
                self._draw_selection_highlights(page_idx, lo, hi, textpage)
        except Exception:
            pass

    def _draw_selection_highlights(self, page_idx, start_idx, end_idx, textpage):
        self._clear_selection_overlays()
        label = self._page_labels[page_idx] if page_idx < len(self._page_labels) else None
        # PIXMAP ARANMIYOR. Eskiden sayfa henüz çizilmemişse buradan
        # dönülüyordu ve render sonradan gelince vurguyu kimse yeniden
        # çizmiyordu: kullanıcı metni seçmiş oluyor (sağ tık > Kopyala
        # çalışıyor) ama ekranda HİÇBİR ŞEY görmüyor, bir daha da gelmiyor
        # (ölçüldü 2026-09-05). Etiket yükleme anında doğru boyutla
        # kuruluyor (_create_placeholders -> setFixedSize) ve `_olcek` aynı
        # ölçeği veriyor, yani geometri pixmap olmadan da doğru.
        if not label:
            return

        scale = self._olcek(page_idx)
        with pdfium_lock:
            g = geometri(self._pdf[page_idx])
        t = self._theme

        runs = []
        current_run = None

        for i in range(start_idx, end_idx + 1):
            try:
                with pdfium_lock:
                    left, bottom, right, top = textpage.get_charbox(i, loose=True)
            except Exception:
                continue
            if right - left < 0.5 or top - bottom < 0.5:
                continue

            x, y, w, h = kutu_gorsele(g, left, bottom, right, top, scale)

            if current_run and abs(y - current_run[1]) < 2:
                # Koşu İKİ YÖNE de genişliyor. Eskiden yalnız sağa
                # genişliyordu ve metnin ekranda soldan sağa ilerlediği
                # varsayılıyordu; /Rotate 180'de görsel x AZALIYOR, yani
                # `x + w` hep koşunun solunda kalıyor ve koşu hiç
                # büyümüyordu. ÖLÇÜLDÜ (2026-09-05, uçtan uca): 10 karakter
                # seçilince vurgu gereken alanın yalnız %11'ini kaplıyor,
                # yani sadece ilk karakter görünüyordu.
                sol = min(current_run[0], x)
                sag = max(current_run[0] + current_run[2], x + w)
                current_run[0] = sol
                current_run[2] = sag - sol
                current_run[3] = max(current_run[3], h)
            else:
                if current_run:
                    runs.append(tuple(current_run))
                current_run = [x, y, w, max(h, 4)]

        if current_run:
            runs.append(tuple(current_run))

        for rx, ry, rw, rh in runs:
            hl = QLabel(label)
            hl.setStyleSheet(
                f"background-color: {t['pdf_sel_bg']}; "
                f"border: 1px solid {t['pdf_sel_border']}; "
                "border-radius: 1px;"
            )
            hl.setGeometry(int(rx), int(ry), max(int(rw), 2), max(int(rh), 4))
            hl.show()
            hl.raise_()
            self._selection_highlights.append(hl)

    def _clear_selection_overlays(self):
        for hl in self._selection_highlights:
            try:
                hl.deleteLater()
            except RuntimeError:
                pass
        self._selection_highlights = []

    def _clear_selection(self):
        self._clear_selection_overlays()
        self._selected_text = ""
        self._selection_char_range = None
        self._selection_start_label_pos = None
        self._selection_start_page = None
        self._selection_start_label = None
        self._selection_drag_started = False

    @staticmethod
    def _normalize_pdf_text(text):
        """PDF metnindeki ayrık aksanları birlestir (Turkce: ş, ğ, Ş, Ğ)."""
        # Once 2-karakter pattern'lerini degistir
        for old, new in [
            ("¸s", "ş"), ("¸S", "Ş"),
            ("s¸", "ş"), ("S¸", "Ş"),
            ("˘g", "ğ"), ("˘G", "Ğ"),
            ("g˘", "ğ"), ("G˘", "Ğ"),
            ("¸c", "ç"), ("¸C", "Ç"),
            ("c¸", "ç"), ("C¸", "Ç"),
        ]:
            text = text.replace(old, new)
        # Tek kalan aksanlari temizle
        text = text.replace("¸", "").replace("˘", "")
        # Unicode NFC normalizasyonu
        return unicodedata.normalize("NFC", text)

    def _copy_selection(self):
        if self._selected_text:
            text = self._normalize_pdf_text(self._selected_text)
            QApplication.clipboard().setText(text)

# _handle_selection_key kaldırıldı (2026-08-30, F3): hiçbir yerden
# çağrılmıyordu. İşlevi PdfViewer.keyPressEvent'e taşınmış (pdf_viewer.py:69-73),
# aynı StandardKey.Copy denetimini orası yapıyor — bu yalnız geride kalan kopyaydı.

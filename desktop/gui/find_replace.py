"""VS Code tarzı bul/değiştir inline paneli."""

import re as _re

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLineEdit, QPushButton, QLabel,
    QMessageBox, QCheckBox,
)
from PyQt6.Qsci import QsciScintilla

from PyQt6.QtCore import QCoreApplication
_ = lambda s: QCoreApplication.translate("FindReplaceBar", s)


# Scintilla'nın ECMAScript kipi std::regex'e dayanıyor ve desen ÇÖZÜMLEMESİ
# özyinelemeli: çok derin iç içe yakalayan grup yığını taşırıyor. Ölçüldü
# (2026-09-02): 100 kat sorunsuz, 150 kat süreci 0xC0000005 ile öldürüyor.
# Python istisnası değil, süreç ölümü — yakalanamıyor, kaydedilmemiş her şey
# gidiyor. `(a|(a|...))` biçimi de aynı. Sınır ölçülen eşiğin epey altında:
# gerçek bir aramada bu derinliğe yaklaşan desen yok.
_MAX_GRUP_DERINLIGI = 50


def _desen_guvenli(desen: str) -> bool:
    """Desen, motoru yıkacak kadar derin iç içe grup taşıyor mu."""
    derinlik = enbuyuk = 0
    kacis = sinif = False
    for c in desen:
        if kacis:
            kacis = False
        elif c == "\\":
            kacis = True
        elif sinif:
            # Karakter sınıfı içinde `(` düz karakter, grup açmıyor.
            sinif = c != "]"
        elif c == "[":
            sinif = True
        elif c == "(":
            derinlik += 1
            if derinlik > enbuyuk:
                enbuyuk = derinlik
        elif c == ")":
            derinlik = max(0, derinlik - 1)
    return enbuyuk <= _MAX_GRUP_DERINLIGI


class FindReplaceBar(QWidget):
    # "Tümünü Değiştir" için üst sınır. Döngü normalde kendiliğinden biter
    # (arama wrap'siz ileri gider, imleç her değiştirmede ilerler); bu yalnız
    # patolojik bir durumda takılmamak için konmuş bir emniyet kemeri.
    # Sınıra ULAŞILDIĞINDA kullanıcı UYARILMAK zorunda: eskiden sessizce
    # kesiliyor, etiket yine sayıyı yazıyordu ve kullanıcı belgenin yarım
    # değiştiğini ancak derleme hatasından anlıyordu (2026-08-30 denetimi, D5).
    _REPLACE_LIMIT = 10000

    # Sayaç üst sınırı. Sıfır genişlikli düzenli ifadeler (`x*`, `^`) belgedeki
    # HER konumda eşleşiyor: 5 MB'lık bir .tex için milyonlarca tur demek.
    # Sınıra dayanınca etiket "N+ sonuç" diyor, sessizce yanlış sayı vermiyor.
    _COUNT_LIMIT = 10000

    def __init__(self, parent=None):
        super().__init__(parent)
        self._editor: QsciScintilla | None = None
        self._match_count = 0
        self._sayim_kesildi = False
        self._gecersiz_desen = False
        self._count_timer = QTimer(self)
        self._count_timer.setSingleShot(True)
        self._count_timer.setInterval(300)
        self._count_timer.timeout.connect(self._do_count_matches)
        self._count_text = ""
        self._setup_ui()

    def _setup_ui(self):
        # ÜÇ SATIR: bul / değiştir / seçenekler. Hepsi tek satırdayken çubuk
        # 1000 px istiyordu ve sabit genişlikli parçalar daralamadığı için
        # fazlası görünmez oluyordu. ÖLÇÜLDÜ (bölme genişliğine göre değiştir
        # alanının konumu):
        #
        #     bölme 1000 px -> tamam
        #     bölme  900 px -> "Tümünü Değiştir" kesiliyor
        #     bölme  600 px -> "Değiştir" kutusu da kesiliyor
        #
        # KULLANICI BİLDİRDİ (2026-09-01): "Ctrl+H'e basınca bir şey olmuyor".
        # Aslında oluyordu; çubuk açılıyor, değiştir alanı bölmenin sağına
        # taşıp görünmüyordu.
        #
        # Üç satırda değiştir alanı 525 px'de bitiyor, yani 540 px'lik bir
        # bölmede bile görünür. Kutuları esneyebilir yapmayı da denedim;
        # ÖLÇÜMDE HİÇBİR ŞEY DEĞİŞTİRMEDİ, çünkü çubuğun asgari genişliğini
        # seçenek satırı (660 px) belirliyor ve kutular oraya kadar zaten
        # daralmıyor. O yüzden sabit genişlikler duruyor.
        #
        # KALAN SINIR: çubuk açıkken editör bölmesi 680 px'in altına
        # inemiyor (seçenek satırının asgarisi). Önce 1000 px'di.
        dis = QVBoxLayout(self)
        dis.setContentsMargins(4, 2, 4, 2)
        dis.setSpacing(2)

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        dis.addLayout(layout)

        self._find_input = QLineEdit()
        self._find_input.setPlaceholderText(_("Bul"))
        self._find_input.setFixedWidth(250)
        self._find_input.textChanged.connect(self._on_find_text_changed)
        self._find_input.returnPressed.connect(self._find_next)
        layout.addWidget(self._find_input)

        self._btn_prev = QPushButton("<")
        self._btn_prev.setFixedWidth(28)
        self._btn_prev.clicked.connect(self._find_prev)
        layout.addWidget(self._btn_prev)

        self._btn_next = QPushButton(">")
        self._btn_next.setFixedWidth(28)
        self._btn_next.clicked.connect(self._find_next)
        layout.addWidget(self._btn_next)

        self._lbl_count = QLabel("")
        self._lbl_count.setFixedWidth(80)
        layout.addWidget(self._lbl_count)

        layout.addStretch()

        self._btn_close = QPushButton("X")
        self._btn_close.setFixedWidth(24)
        self._btn_close.clicked.connect(self.hide)
        layout.addWidget(self._btn_close)

        # --- 2. satır: değiştir (yalnız Ctrl+H'de görünür) ---
        degistir = QHBoxLayout()
        degistir.setContentsMargins(0, 0, 0, 0)
        degistir.setSpacing(4)
        dis.addLayout(degistir)

        self._replace_input = QLineEdit()
        self._replace_input.setPlaceholderText(_("Değiştir"))
        self._replace_input.setFixedWidth(250)
        self._replace_input.returnPressed.connect(self._replace_next)
        degistir.addWidget(self._replace_input)

        self._btn_replace = QPushButton(_("Değiştir"))
        self._btn_replace.clicked.connect(self._replace_next)
        degistir.addWidget(self._btn_replace)

        self._btn_replace_all = QPushButton(_("Tümünü Değiştir"))
        self._btn_replace_all.clicked.connect(self._replace_all)
        degistir.addWidget(self._btn_replace_all)

        degistir.addStretch()

        # --- 3. satır: arama seçenekleri (iki kipte de görünür) ---
        # Etiketler "Aa" / ".*" gibi kısaltmalar DEĞİL: projede ara panelinde
        # önce "Aa", sonra "Harf duyarlı" denendi, ikisi de anlaşılmadı;
        # yerleşen terim "Büyük/küçük harf eşleştir" oldu (Word/LibreOffice).
        # Aynı kavram iki panelde aynı kelimelerle anılıyor.
        secenekler = QHBoxLayout()
        secenekler.setContentsMargins(0, 0, 0, 0)
        secenekler.setSpacing(12)
        dis.addLayout(secenekler)

        self._cb_case = QCheckBox(_("Büyük/küçük harf eşleştir"))
        self._cb_case.setToolTip(_("İşaretliyse 'Şekil' ile 'şekil' ayrı sayılır"))
        secenekler.addWidget(self._cb_case)

        self._cb_word = QCheckBox(_("Tam kelime"))
        self._cb_word.setToolTip(_("İşaretliyse 'fig' araması 'figure' içinde eşleşmez"))
        secenekler.addWidget(self._cb_word)

        self._cb_regex = QCheckBox(_("Düzenli ifade"))
        self._cb_regex.setToolTip(
            _("Desen araması: \\d rakam, [A-Z] harf kümesi, a|b almaşık, "
              "(...) grup. Değiştirmede \\1 yakalanan gruba karşılık gelir."))
        secenekler.addWidget(self._cb_regex)

        secenekler.addStretch()

        for cb in (self._cb_case, self._cb_word, self._cb_regex):
            cb.toggled.connect(self._on_option_toggled)

        self._replace_input.hide()
        self._btn_replace.hide()
        self._btn_replace_all.hide()

        self.setStyleSheet("")

    def apply_theme(self, t: dict):
        self.setStyleSheet(
            f"QWidget {{ background: {t['bg_secondary']}; }}"
            f"QLineEdit {{ background: {t['bg_button']}; color: {t['fg_primary']}; border: 1px solid {t['border_input']}; "
            f"padding: 4px 8px; border-radius: 4px; }}"
            f"QLineEdit:focus {{ border: 1px solid {t['accent']}; }}"
            f"QPushButton {{ background: {t['bg_button']}; color: {t['fg_primary']}; border: 1px solid {t['border_input']}; "
            f"padding: 3px 10px; border-radius: 4px; }}"
            f"QPushButton:hover {{ background: {t['bg_hover']}; border: 1px solid {t['accent']}; }}"
            f"QPushButton:pressed {{ background: {t['bg_pressed']}; }}"
            f"QLabel {{ color: {t['fg_label']}; background: transparent; }}"
        )

    def set_editor(self, editor: QsciScintilla):
        self._editor = editor

    def show_find(self):
        self._replace_input.hide()
        self._btn_replace.hide()
        self._btn_replace_all.hide()
        self.show()
        self._find_input.setFocus()
        self._find_input.selectAll()
        self._do_find()

    def show_replace(self):
        self._replace_input.show()
        self._btn_replace.show()
        self._btn_replace_all.show()
        self.show()
        self._find_input.setFocus()
        self._find_input.selectAll()
        self._do_find()

    def hide(self):
        super().hide()
        if self._editor:
            self._editor.setFocus()
            # Seçimi temizle ama indicator'ları bırak

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            return
        super().keyPressEvent(event)

    def _on_find_text_changed(self):
        self._do_find()

    def _on_option_toggled(self, _checked):
        """Seçenek değişince arama BAŞTAN koşar.

        Yeniden aramazsak imleç önceki kuralın bulduğu yerde kalır ve sayaç
        eski kuralın sayısını gösterirdi: kullanıcı kutuyu işaretler, ekranda
        hiçbir şey değişmezdi.
        """
        # Düzenli ifade kipinde Scintilla tam-kelime bayrağını yok sayıyor.
        # Etkisiz bir kutuyu tıklanabilir bırakmak yalan olurdu; bu kipte
        # karşılığı desenin kendisinde: \bfig\b.
        self._cb_word.setEnabled(not self._cb_regex.isChecked())
        self._do_find()

    def _arama_bayraklari(self) -> tuple[bool, bool, bool]:
        """(düzenli_ifade, harf_duyarlı, tam_kelime): üç yol için TEK kaynak.

        Bul, sayaç ve değiştir aynı üçlüyü kullanıyor. Sayaç eskiden ayrı bir
        yoldan geçiyordu (`text().lower().count()`) ve aramadan ayrışabiliyordu:
        etiket "3 sonuç" derken ileri tuşu hiçbir şey bulamayabiliyordu.
        """
        re_ = self._cb_regex.isChecked()
        # Tam kelime düzenli ifadeyle birlikte anlamsız (yukarıya bakın),
        # bayrağı da göndermiyoruz ki sayaç ile arama aynı kuralı görsün.
        return re_, self._cb_case.isChecked(), self._cb_word.isChecked() and not re_

    @staticmethod
    def _desen_derlenebilir(desen: str) -> bool:
        try:
            _re.compile(desen)
            return True
        except _re.error:
            return False

    def _find_first(self, text, *, wrap, forward=True, line=None, col=None):
        """findFirst'ü seçenek bayraklarıyla çağır (imleçten ya da verilen yerden).

        cxx11=True ŞART: Scintilla'nın öntanımlı lehçesinde `|` almaşık değil
        düz karakter, `(` grup açmıyor (ölçüldü). Kullanıcı
        `\\section|\\subsection` yazınca sessizce "Sonuç yok" alırdı. Bu bayrak
        ECMAScript lehçesini açıyor; ipucu metni de onu anlatıyor.
        """
        re_, cs, wo = self._arama_bayraklari()
        if re_ and not _desen_guvenli(text):
            return False
        if line is None:
            line, col = self._editor.getCursorPosition()
        return self._editor.findFirst(
            text, re_, cs, wo, wrap, forward, line, col, True, False, re_
        )

    def _do_find(self):
        if not self._editor:
            return
        text = self._find_input.text()
        if not text:
            self._lbl_count.setText("")
            self._match_count = 0
            self._gecersiz_desen = False
            return

        self._gecersiz_desen = False
        if self._cb_regex.isChecked() and not _desen_guvenli(text):
            self._gecersiz_desen = True
            self._match_count = 0
            self._update_current_match()
            return
        # İlk eşleşmeyi bul
        bulundu = self._find_next_in_text(text, forward=True, wrap=True)

        # "Geçersiz desen" YALNIZ hiçbir şey bulunamayınca söyleniyor: Python'ın
        # `re`si ile Scintilla'nın ECMAScript'i birebir aynı değil (adlandırılmış
        # grup söz dizimi ayrışıyor). Eşleşme varsa desen zaten geçerlidir ve
        # Python'ın itirazı kullanıcıyı ilgilendirmez.
        if not bulundu and self._cb_regex.isChecked() and not self._desen_derlenebilir(text):
            self._gecersiz_desen = True
            self._match_count = 0
            self._update_current_match()
            return

        # Sayıyı debounce et: her tuş vuruşunda belgeyi baştan taramasın
        self._count_text = text
        self._count_timer.start()

    def _find_next_in_text(self, text, forward=True, wrap=True) -> bool:
        if not self._editor or not text:
            return False

        found = self._find_first(text, wrap=wrap, forward=forward)
        if not found:
            # wrap=True ile bulunamadıysa belgede GERÇEKTEN eşleşme yok:
            # sayaç 0'dır ve etiket panelin geri kalanıyla aynı dili konuşur.
            # Burada `setText("0/0")` vardı — çeviri kataloğunda olmayan,
            # başka hiçbir yerde kullanılmayan bir biçim. Yazarken 300 ms'lik
            # debounce boyunca ekranda kalıp sonra "Sonuç yok"a dönüyordu
            # (titreme), ileri/geri tuşlarında ise _update_current_match onu
            # anında BAYAT _match_count ile eziyordu: eşleşme kalmamışken
            # etiket hâlâ eski "{n} sonuç" değerini gösterebiliyordu.
            self._match_count = 0
            self._update_current_match()
        return found

    def _find_next(self):
        text = self._find_input.text()
        if not text:
            return
        self._find_next_in_text(text, forward=True, wrap=True)
        self._update_current_match()

    def _find_prev(self):
        text = self._find_input.text()
        if not text:
            return
        self._find_next_in_text(text, forward=False, wrap=True)
        self._update_current_match()

    def _do_count_matches(self):
        if not self._editor or not self._count_text:
            return
        self._count_matches(self._count_text)

    def _count_matches(self, text):
        if not self._editor or not text:
            self._match_count = 0
            self._lbl_count.setText("")
            return

        self._match_count, self._sayim_kesildi = self._say(text)
        self._update_current_match()

    def _say(self, text) -> tuple[int, bool]:
        """Eşleşmeleri ARAMANIN KENDİ MOTORUYLA say. (sayı, sınıra_dayandı).

        Hedef aramasi (SCI_SEARCHINTARGET) imleci ve seçimi değiştirmiyor, bu
        yüzden kullanıcı yazarken belge yerinde duruyor. Eski yol belgenin
        tamamını Python'a kopyalayıp `str.count` çağırıyordu: hem seçenekleri
        (harf duyarlılığı, tam kelime, desen) hiç bilmiyordu hem de büyük
        .tex'lerde her tuş vuruşunda megabaytlarca kopyalama yapıyordu.
        """
        ed = self._editor
        re_, cs, wo = self._arama_bayraklari()
        if re_ and not _desen_guvenli(text):
            return 0, False
        bayrak = 0
        if cs:
            bayrak |= QsciScintilla.SCFIND_MATCHCASE
        if wo:
            bayrak |= QsciScintilla.SCFIND_WHOLEWORD
        if re_:
            bayrak |= QsciScintilla.SCFIND_REGEXP | QsciScintilla.SCFIND_CXX11REGEX
        ed.SendScintilla(QsciScintilla.SCI_SETSEARCHFLAGS, bayrak)

        # Scintilla konumları BAYT cinsinden; belge UTF-8 olduğu için sorgu da
        # bayta çevriliyor. Sayım için karakter ofseti gerekmiyor.
        ham = text.encode("utf-8")
        son = ed.SendScintilla(QsciScintilla.SCI_GETLENGTH)
        konum, n = 0, 0
        while konum <= son and n < self._COUNT_LIMIT:
            ed.SendScintilla(QsciScintilla.SCI_SETTARGETSTART, konum)
            ed.SendScintilla(QsciScintilla.SCI_SETTARGETEND, son)
            bas = ed.SendScintilla(QsciScintilla.SCI_SEARCHINTARGET, len(ham), ham)
            if bas < 0:
                break
            bit = ed.SendScintilla(QsciScintilla.SCI_GETTARGETEND)
            n += 1
            # Sıfır genişlikli eşleşmede (bit == bas) bir bayt ilerle, yoksa
            # aynı konumda sonsuza kadar dönerdik.
            konum = bit if bit > bas else bas + 1
        return n, n >= self._COUNT_LIMIT

    def _update_current_match(self):
        if self._gecersiz_desen:
            self._lbl_count.setText(_("Geçersiz desen"))
        elif self._match_count == 0:
            self._lbl_count.setText(_("Sonuç yok"))
        elif self._sayim_kesildi:
            self._lbl_count.setText(_("{n}+ sonuç").format(n=self._match_count))
        else:
            self._lbl_count.setText(_("{n} sonuç").format(n=self._match_count))

    def _replace_next(self):
        if not self._editor:
            return
        find_text = self._find_input.text()
        replace_text = self._replace_input.text()
        if not find_text:
            return

        self._editor.setFocus()
        self._editor.beginUndoAction()

        # İleriye doğru ara (wrap=False)
        found = self._find_first(find_text, wrap=False)

        # Bulunamazsa başa dönüp tekrar ara
        if not found or not self._editor.hasSelectedText():
            found = self._find_first(find_text, wrap=False, line=0, col=0)

        if found and self._editor.hasSelectedText():
            # replaceSelectedText DEĞİL: geri referansları (\1) düz metin gibi
            # yazıyor. `replace` desen kipinde onları çözüyor, düz kipte zaten
            # harfi harfine bırakıyor (ikisi de ölçüldü).
            self._editor.replace(replace_text)

            # Sonrakini bul ve göster
            line, col = self._editor.getCursorPosition()
            self._find_first(find_text, wrap=True, line=line, col=col)

        self._editor.endUndoAction()
        self._count_matches(find_text)

    def _replace_all(self):
        if not self._editor:
            return
        find_text = self._find_input.text()
        replace_text = self._replace_input.text()
        if not find_text:
            return

        self._editor.setFocus()
        self._editor.beginUndoAction()

        # Başa dönüp tek tek bul ve değiştir
        self._editor.setCursorPosition(0, 0)
        count = 0
        found = self._find_first(find_text, wrap=False, line=0, col=0)
        sinira_ulasildi = False
        # hasSelectedText koşulu sıfır genişlikli deseni de kesiyor: `x*` gibi
        # bir desende findFirst True dönüp hiçbir şey seçmiyor (ölçüldü),
        # döngü ilk turda çıkıyor ve belge bozulmuyor.
        while found and self._editor.hasSelectedText():
            if count >= self._REPLACE_LIMIT:
                sinira_ulasildi = True
                break
            self._editor.replace(replace_text)
            count += 1
            line, col = self._editor.getCursorPosition()
            found = self._find_first(find_text, wrap=False, line=line, col=col)

        self._editor.endUndoAction()
        self._match_count = 0
        self._sayim_kesildi = False
        self._gecersiz_desen = False
        self._lbl_count.setText(_("{n} değişiklik").format(n=count))

        if sinira_ulasildi:
            # Sessiz kesme yok: belge YARIM değişti, kullanıcı bilmeli.
            # Arama ileri yönlü ve wrap'siz olduğu için komutu tekrarlamak
            # kaldığı yerden devam eder — eyleme dönük tavsiye bu.
            QMessageBox.warning(
                self, _("Tümünü Değiştir"),
                _("{n} değişiklik yapıldı ve güvenlik sınırına ulaşıldı.\n\n"
                  "Belgede değiştirilmemiş eşleşmeler kalmış olabilir; "
                  "işlemi tekrarlayarak kaldığı yerden sürdürebilirsiniz.").format(n=count),
            )

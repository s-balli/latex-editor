"""Ortam denetimi diyaloğu: core.env_check sonuçlarını gösterir.

Kontroller arka plan thread'inde koşar: Windows'ta wsl çağrıları soğuk
başlangıçta 1-3 sn sürer, UI thread bloklanmaz (main_window'daki arka plan
pandoc kontrolüyle aynı desen). Dialog hemen açılır, sonuçlar gelince dolar.
"""

import threading
from html import escape

from PyQt6.QtCore import QCoreApplication, QObject, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication, QDialog, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QTextBrowser, QVBoxLayout,
)

from core import env_check
from core.env_check import CheckResult

_ = lambda s: QCoreApplication.translate("EnvDoctor", s)

_MARK = {"ok": "✅", "missing": "❌", "error": "⚠️", "info": "ℹ️"}


def _yerellestir(metin: str) -> str:
    """core/env_check.py'nin ham Türkçe durum metnini arayüz diline çevir.

    core/ bilinçli olarak Qt'süz; çeviri bu yüzden SUNUM katmanında yapılıyor.
    Sözlük çağrı anında kuruluyor: QTranslator uygulama başladıktan sonra
    yükleniyor, modül düzeyinde kurulsa çeviriler boşa düşerdi. Bu satırlar
    İngilizce arayüzde Türkçe kalıyordu ("pdflatex: kurulu değil").

    Bileşik metinler ("kurulu değil (minted belgeleri için gerekli)") parça
    parça çevrilir; ``fix_hint`` kabuk komutu olduğu için ÇEVRİLMEZ.
    """
    if not metin:
        return metin
    tablo = {
        "kurulu değil": _("kurulu değil"),
        "çalışıyor": _("çalışıyor"),
        "wsl bulunamadı": _("wsl bulunamadı"),
        "WSL olmadığından denetlenemedi": _("WSL olmadığından denetlenemedi"),
        "WSL çalışmadığından denetlenemedi": _("WSL çalışmadığından denetlenemedi"),
        "çalıştırılamadı (dağıtım kurulu olmayabilir)":
            _("çalıştırılamadı (dağıtım kurulu olmayabilir)"),
        "minted belgeleri için gerekli": _("minted belgeleri için gerekli"),
        "hiç motor kurulu değil; eksik paketleri tek tek kurmak yerine "
        "README'nin tam kurulumu önerilir":
            _("hiç motor kurulu değil; eksik paketleri tek tek kurmak yerine "
              "README'nin tam kurulumu önerilir"),
        "TeX Live kurulumu": _("TeX Live kurulumu"),
        "Sonraki adım": _("Sonraki adım"),
        "WSL kurulduktan sonra TeX Live de gerekiyor; taze bir dağıtımda "
        "hiçbir TeX aracı bulunmuyor":
            _("WSL kurulduktan sonra TeX Live de gerekiyor; taze bir "
              "dağıtımda hiçbir TeX aracı bulunmuyor"),
    }
    if metin in tablo:
        return tablo[metin]
    # "temel (not)" biçimi — ikisini ayrı ayrı çevir
    if metin.endswith(")") and " (" in metin:
        temel, _ayrac, not_ = metin[:-1].partition(" (")
        if temel in tablo or not_ in tablo:
            return f"{tablo.get(temel, temel)} ({tablo.get(not_, not_)})"
    return metin


class _CheckSignal(QObject):
    """Arka plan denetimden UI'ya sonuç taşıyan sinyal köprüsü."""
    done = pyqtSignal(list)


class EnvDoctorDialog(QDialog):
    """WSL / TeX motorları / biber / pandoc / synctex durum tablosu."""

    def __init__(self, parent=None, *, theme: dict = None):
        super().__init__(parent)
        self._theme = theme or {}
        self._results: list[CheckResult] | None = None

        self.setWindowTitle(_("Ortam Denetimi"))
        self.resize(680, 440)

        self._sig = _CheckSignal()
        self._sig.done.connect(self._on_done)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        self._busy = QProgressBar()
        self._busy.setRange(0, 0)
        self._busy.setTextVisible(False)
        self._busy.setFixedHeight(12)
        layout.addWidget(self._busy)

        self._view = QTextBrowser()
        # Zemin ACIKCA veriliyor: QTextBrowser kendi palet Base rengini
        # (beyaz) koruyor ve uzerine koyu temanin acik metni basiliyordu.
        # Olculdu (2026-09-03, gruvbox): govde 1.37, soluk 3.67, hata 3.44;
        # WCAG AA esigi 4.50. Tema bos gelebilir, o yuzden .get + yedek.
        _t = self._theme or {}
        self._view.setStyleSheet(
            "QTextBrowser {{ background: {bg}; color: {fg};"
            " border: 1px solid {kenar}; }}".format(
                bg=_t.get("bg_primary", "#1e1e1e"),
                fg=_t.get("fg_primary", "#dddddd"),
                kenar=_t.get("border_normal", "#3c3c3c")))
        self._view.setOpenExternalLinks(False)
        layout.addWidget(self._view, 1)

        self._note = QLabel("")
        layout.addWidget(self._note)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self._rerun_btn = QPushButton(_("Yeniden Denetle"))
        self._rerun_btn.clicked.connect(self._start)
        buttons.addWidget(self._rerun_btn)
        self._copy_btn = QPushButton(_("Raporu Kopyala"))
        self._copy_btn.clicked.connect(self._copy_report)
        buttons.addWidget(self._copy_btn)
        close_btn = QPushButton(_("Kapat"))
        close_btn.clicked.connect(self.accept)
        buttons.addWidget(close_btn)
        layout.addLayout(buttons)

        self._start()

    def _start(self):
        """Denetimi arka planda başlat; dialog 'denetleniyor' durumuna geçer."""
        self._results = None
        self._rerun_btn.setEnabled(False)
        self._copy_btn.setEnabled(False)
        self._busy.show()
        fg = (self._theme or {}).get("fg_muted", "")
        self._view.setHtml(
            f"<span style='color:{fg}'>{_('Denetleniyor: WSL, TeX motorları, biber, pandoc, synctex ...')}</span>"
        )

        def _bg(sig=self._sig):
            try:
                sig.done.emit(env_check.run_checks())
            except RuntimeError:
                # Dialog kapatıldı, sinyal köprüsü çoktan silindi: sorun değil
                pass

        threading.Thread(target=_bg, name="env-check", daemon=True).start()

    def _on_done(self, results: list):
        self._results = results
        self._busy.hide()
        self._rerun_btn.setEnabled(True)
        self._copy_btn.setEnabled(True)
        self._view.setHtml(self._render_html(results))

    def _render_html(self, results: list[CheckResult]) -> str:
        t = self._theme or {}
        fg = t.get("fg_primary", "#dddddd")
        err = t.get("sem_error", "#c62828")
        muted = t.get("fg_muted", fg)
        rows = []
        for r in results:
            color = err if r.status == "missing" else (muted if r.status == "info" else fg)
            # KAÇIŞ ŞART: bu üç alan DIŞARIDAN geliyor. `detail` kurulu
            # araçta `shutil.which`/WSL çıktısındaki araç YOLU, başarısız
            # dalda `_run`ın döndürdüğü ham hata metni. Kaçışsız gömülünce
            # QTextBrowser `<...>` içeren bir yolu bilinmeyen etiket sanıp
            # YUTUYORDU: ölçüldü, `/home/x/<deneme>/bin/pdflatex` kullanıcıya
            # `/home/x//bin/pdflatex` görünüyor, yani var olmayan bir dizine
            # yönlendiriyordu. Adı `<...>` olan bir satır ise adsız kalıyordu.
            line = (f"<span style='color:{color}'>{_MARK.get(r.status, '•')} "
                    f"<b>{escape(_yerellestir(r.name))}</b>")
            if r.detail:
                line += f": {escape(_yerellestir(r.detail))}"
            if r.fix_hint and r.status != "ok":
                line += (f"<br>&nbsp;&nbsp;&nbsp;&nbsp;"
                         f"<span style='color:{muted}'>→ {escape(r.fix_hint)}</span>")
            line += "</span>"
            rows.append(line)
        return "<br><br>".join(rows)

    def _copy_report(self):
        if not self._results:
            return
        QApplication.clipboard().setText(env_check.report_text(self._results))
        self._note.setText(_("Rapor panoya kopyalandı"))
        QTimer.singleShot(2000, lambda: self._note.setText(""))

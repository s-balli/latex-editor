# -*- coding: utf-8 -*-
r"""Sonuç listelerine tıklamak BUGÜNKÜ satıra gidiyor (2026-09-27).

Uyarılar, Referans Denetimi, Klasörde Ara, Yazım ve Kaynakça öğesi satırı
listenin kurulduğu metne göre tutuyor. Kullanıcı sonra yukarıya satır
ekleyince öğe eski satıra gidiyordu; derleme, arama, kaynakça ve denetimin
bölüm dosyaları DİSKİ okuduğu için kirli sekmede satır daha baştan kayıktı.
ÖLÇÜLDÜ (gerçek pencere, Ctrl+B ile gerçek derleme, gerçek tıklama; LF ve
CRLF): 14 adımın 11'inde yanlış satır.

Her liste GERÇEK üreticiyle kuruluyor; derleme uyarısı TeX'siz koşsun diye
elle, panel onu derlemedeki yoldan (`show_result`) dolduruyor. Sekme liste
kurulmadan ÖNCE kirli, kurulduktan SONRA bir satır daha alıyor. Kehanet
öğenin metninin editördeki satırı.
"""
import re

import pytest

pytest.importorskip("PyQt6")


def _kehanet(ed, jeton):
    satirlar = re.split(r"\r\n|\r|\n", ed.text())
    bulunan = [i + 1 for i, s in enumerate(satirlar) if jeton in s]
    assert len(bulunan) == 1, (jeton, bulunan)
    return bulunan[0]


class _SahteDenetleyici:
    """Sözlük yerine: yalnız 'yanlisyazim' bulgu (kullanıcının sözlüğüne dokunmuyor)."""

    def denetle_kelimeler(self, kelimeler, buyuk_atla=False, **_k):
        from core.yazim import Bulgu
        return [Bulgu(k.kelime, k.satir, k.sutun, k.ofset) for k in kelimeler
                if k.kelime == "yanlisyazim"]


@pytest.mark.parametrize("liste", ["uyari", "denetim", "arama", "yazim", "kaynakca"])
def test_sonuc_listesi_tiklamasi_BUGUNKU_satira_gidiyor(ana_pencere, tmp_path, liste):
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication
    from core.log_parser import CompileResult, LatexWarning

    ana = tmp_path / "main.tex"
    ana.write_text("\\documentclass{article}\n\\begin{document}\n"
                   "Burada \\ref{yokiki} ARANAN yanlisyazim var.\n"
                   "\\bibliography{refs}\n\\end{document}\n", encoding="utf-8")
    bib = tmp_path / "refs.bib"
    bib.write_text("@misc{birinci,\n  title = {Bir},\n}\n\n"
                   "@misc{ikinci,\n  title = {Iki},\n}\n", encoding="utf-8")
    w = ana_pencere(open_file=str(ana))
    op = w._output_panel
    ed = w._current_editor()
    hedef, jeton = ed, "\\ref{yokiki}"
    if liste == "kaynakca":
        w._open_file_in_editor(str(bib))
        hedef, jeton = w._editor_by_path(str(bib)), "@misc{ikinci"
        w._editor_tabs.setCurrentWidget(ed)
    hedef.insertAt("% kaydedilmedi\n", 0, 0)

    if liste == "uyari":
        op.show_result(CompileResult(warnings=[LatexWarning(
            3, "Reference `yokiki' on page 1 undefined on input line 3.", "LaTeX",
            str(ana))]))
        lst = op._warn_list
    elif liste == "denetim":
        w._audit_references()
        lst = op._warn_list
    elif liste == "arama":
        w._file_tree.set_root(str(tmp_path))
        w._on_project_search_requested("ARANAN", True)
        lst = op._psearch_list
        for _ in range(250):
            if lst.count():
                break
            QTest.qWait(20)
    elif liste == "yazim":
        op._yazim_ikinci.setChecked(False)
        w._yazim_denetleyici = _SahteDenetleyici()
        w._yazim_anahtar = (op._yazim_dil.currentData(), "")
        op._on_yazim_denetle()
        lst = op._yazim_list
    else:
        w._show_bibliography()
        lst = op._bib_table

    hedef.insertAt("% sonra\n", 0, 0)
    if liste == "kaynakca":
        item = next(lst.item(r, 0) for r in range(lst.rowCount())
                    if lst.item(r, 0).text() == "ikinci")
    else:
        assert lst.count() == 1, [lst.item(i).text() for i in range(lst.count())]
        item = lst.item(0)
    lst.itemClicked.emit(item)
    QApplication.processEvents()
    e = w._current_editor()
    assert (e is hedef, e.getCursorPosition()[0] + 1) == (True, _kehanet(hedef, jeton))

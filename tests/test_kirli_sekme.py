# -*- coding: utf-8 -*-
r"""Kaydedilmemiş sekmeyi proje okumaları görüyor (2026-09-27).

Klasörde Ara, Referans Denetimi, Kaynakça sekmesi, \ref tamamlaması ve tanıma
git bölüm dosyalarını ve .bib'i DİSKTEN okuyordu. ÖLÇÜLDÜ (gerçek pencere;
kök, bölüm ve .bib açık ve üçü de kirli; LF ve CRLF, `\input{Bolum}` ile harf
farkı): 7 denetimin 7'si yanlıştı. Arama kaydedilmemiş metni bulmuyor, yalnız
diskte kalanı buluyordu; denetim arabellekte tanımlı etikete ve kaynağa
"tanımsız" diyor, silineni ve yeni yazılan \ref'i görmüyordu; kaynakça yeni
girdiyi, tamamlama yeni etiketi göstermiyor, tanıma git onu bulamıyordu.
"""
import os
import re

import pytest

from core import fs_ops
from core.latex_refs import collect_cite_keys, collect_labels


def test_blok_SEKME_metnini_veriyor_ic_ice_ve_disarida_geri_donuyor(tmp_path):
    yol = str(tmp_path / "a.tex")
    with open(yol, "wb") as f:
        f.write(b"disk\n")
    with fs_ops.acik_metinlerle({yol: "dis\r\n"}):
        with fs_ops.acik_metinlerle({yol: "ic\r\n"}):
            assert fs_ops.metni_oku(yol) == "ic\n"       # diskten okunmuş gibi LF
        assert fs_ops.metni_oku(yol) == "dis\n"
    assert fs_ops.metni_oku(yol) == "disk\n"


def test_zincir_ONBELLEGI_acik_sekmeyi_ezmiyor(tmp_path):
    """Bölüm etiketleri ve .bib anahtarları diskte mtime önbellekli; açık
    sekmede önbellek DİSKE ait ve atlanmalı."""
    kok = tmp_path / "main.tex"
    kok.write_bytes(b"\\input{bolum}\n\\cite{x}\n\\bibliography{refs}\n")
    (tmp_path / "bolum.tex").write_bytes(b"\\label{eski}\n")
    (tmp_path / "refs.bib").write_bytes(b"@misc{eski,\n}\n")
    icerik = kok.read_text(encoding="utf-8")
    assert (collect_labels(icerik, str(kok)), collect_cite_keys(icerik, str(kok))) \
        == (["eski"], ["eski"])                          # önbellek doldu
    with fs_ops.acik_metinlerle({str(tmp_path / "bolum.tex"): "\\label{yeni}\n",
                                 str(tmp_path / "refs.bib"): "@misc{yeni,\n}\n"}):
        assert (collect_labels(icerik, str(kok)), collect_cite_keys(icerik, str(kok))) \
            == (["yeni"], ["yeni"])


def _degistir(editor, eski, yeni):
    """Arabellekte gerçek düzenleme (kaydedilmemiş kalır)."""
    metin = editor.text()
    assert metin.count(eski) == 1, (eski, metin)
    i = metin.index(eski)
    editor.SendScintilla(editor.SCI_SETTARGETRANGE, len(metin[:i].encode("utf-8")),
                         len(metin[:i + len(eski)].encode("utf-8")))
    editor.SendScintilla(editor.SCI_REPLACETARGET, len(yeni.encode("utf-8")),
                         yeni.encode("utf-8"))


def _tikla(w, liste, item):
    """Öğeye tıkla, gidilen (dosya adı, satır): liste kirli sekmeden
    kurulduysa satır da o metne ait olmalı (bkz. OutputPanel._taban). Öğe
    yoksa None: yuvaya None gitse istisna PyQt'de süreci durduruyor."""
    if item is None:
        return None
    liste.itemClicked.emit(item)
    e = w._current_editor()
    return os.path.basename(e.file_path), e.getCursorPosition()[0] + 1


@pytest.mark.parametrize("okuyan", ["arama", "denetim", "kaynakca", "tamamlama",
                                    "tanima_git"])
def test_KIRLI_sekme_proje_okumalarinda_gorunuyor(ana_pencere, tmp_path, okuyan):
    pytest.importorskip("PyQt6")
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication

    ana, bolum, bib = (tmp_path / a for a in ("main.tex", "bolum.tex", "refs.bib"))
    ana.write_bytes(b"\\documentclass{article}\n\\begin{document}\n"
                    b"Metin ESKIKELIME burada.\n"
                    b"\\ref{yeni} ve \\ref{eski} ve \\cite{yenikaynak} ve \\cite{birinci}.\n"
                    b"\\input{bolum}\n\\bibliographystyle{plain}\n\\bibliography{refs}\n"
                    b"\\end{document}\n")
    bolum.write_bytes(b"Bolum basi.\n\\label{eski}\n")
    bib.write_bytes(b"@misc{birinci,\n  title = {Bir},\n}\n")
    w = ana_pencere(open_file=str(ana))
    op = w._output_panel
    for yol in (bolum, bib):
        w._open_file_in_editor(str(yol))
    ed, bed, bibed = (w._editor_by_path(str(y)) for y in (ana, bolum, bib))
    _degistir(ed, "ESKIKELIME", "YENIKELIME")
    _degistir(bed, "\\label{eski}", "Yeni \\ref{yokyeni} satiri.\n\\label{yeni}")
    _degistir(bibed, "}\n", "}\n\n@misc{yenikaynak,\n  title = {Yeni},\n}\n")
    w._editor_tabs.setCurrentWidget(ed)
    QApplication.processEvents()

    if okuyan == "arama":
        w._file_tree.set_root(str(tmp_path))

        def ara(sorgu):
            op._psearch_list.clear()
            op._psearch_status.setText("")
            w._on_project_search_requested(sorgu, True)
            for _ in range(250):
                QTest.qWait(20)
                if op._psearch_status.text() not in ("", "Aranıyor..."):
                    break
            return [op._psearch_list.item(i).text().split("  ", 1)[0]
                    for i in range(op._psearch_list.count())]

        bulunan = (ara("YENIKELIME"), ara("ESKIKELIME"), ara("yokyeni"),
                   _tikla(w, op._psearch_list, op._psearch_list.item(0)))
        beklenen = (["main.tex:3"], [], ["bolum.tex:2"], ("bolum.tex", 2))
    elif okuyan == "denetim":
        w._audit_references()
        wl = op._warn_list
        bulunan = (sorted(re.sub(r"^\S+:\d+\s+", "", wl.item(i).text())
                          for i in range(wl.count())),
                   _tikla(w, wl, next((wl.item(i) for i in range(wl.count())
                                       if "yokyeni" in wl.item(i).text()), None)))
        beklenen = (["Tanımsız \\ref: eski", "Tanımsız \\ref: yokyeni"], ("bolum.tex", 2))
    elif okuyan == "kaynakca":
        w._show_bibliography()
        bt = op._bib_table
        bulunan = (sorted(bt.item(r, 0).text() for r in range(bt.rowCount())),
                   _tikla(w, bt, next((bt.item(r, 0) for r in range(bt.rowCount())
                                       if bt.item(r, 0).text() == "yenikaynak"), None)))
        beklenen = (["birinci", "yenikaynak"], ("refs.bib", 5))
    elif okuyan == "tamamlama":
        bulunan = ed._projeden(collect_labels)
        beklenen = ["yeni"]
    else:
        w._on_goto_definition("yeni", "label")
        e = w._current_editor()
        bulunan = (os.path.basename(e.file_path), e.getCursorPosition()[0] + 1)
        beklenen = ("bolum.tex", 3)
    for e in (ed, bed, bibed):
        e.setModified(False)
    assert bulunan == beklenen

# -*- coding: utf-8 -*-
r"""Çakışma denetimleri projeyi görüyor: kök belge, kardeş bölümler ve
kaydedilmemiş sekmeler (2026-09-27).

ÖLÇÜLDÜ (gerçek pencere, tez düzeni; işlem bölüm2'den, bölüm1 ve .bib açık
ve kirli): 7 denetimin 1'i doğruydu. Tablo sihirbazı kardeş bölümün
etiketini, DOI ile ekleme kökte bildirilen .bib'in anahtarını görmüyordu,
kayıtlı olanları da. F2 kaydedilmemiş kardeş etiketle ve kaydedilmemiş
`\bibitem`le aynı adı engellemiyordu. Sonuç: derlemede "multiply defined",
.bib'de BibTeX'in ilkini aldığı mükerrer anahtar.
"""
import pytest

from tests.test_kirli_sekme import _degistir

pytest.importorskip("PyQt6")


def _yaz(yol, metin):
    yol.write_bytes(metin.encode("utf-8"))


@pytest.mark.parametrize("yol_", ["sihirbaz", "doi", "f2_etiket", "f2_bibitem"])
def test_cakisma_denetimi_KOKU_ve_KIRLI_sekmeyi_goruyor(ana_pencere, tmp_path,
                                                         monkeypatch, yol_):
    from PyQt6.QtWidgets import QInputDialog, QMessageBox
    import gui.doi_fetch as df
    import gui.table_wizard as tw

    kok = tmp_path / "tez"
    kok.mkdir()
    _yaz(kok / "main.tex", "\\documentclass{article}\n\\begin{document}\n"
         "\\input{bolum1}\n\\input{bolum2}\n\\nocite{*}\n\\bibliographystyle{plain}\n"
         "\\bibliography{refs}\n\\end{document}\n")
    _yaz(kok / "bolum1.tex", "Bir.\n\\label{sec:kayitli}\n\\label{tab:kayitli}\n")
    _yaz(kok / "bolum2.tex", "Iki.\n\\label{eski}\nBkz. \\ref{eski}.\n")
    _yaz(kok / "refs.bib", "@misc{kayitli2020,\n  title = {K},\n}\n")
    w = ana_pencere(open_file=str(kok / "main.tex"))
    for ad in ("bolum1.tex", "refs.bib", "bolum2.tex"):
        w._open_file_in_editor(str(kok / ad))
    b1, bib, b2 = (w._editor_by_path(str(kok / a))
                   for a in ("bolum1.tex", "refs.bib", "bolum2.tex"))
    _degistir(b1, "\\label{tab:kayitli}\n",
              "\\label{tab:kayitli}\n\\label{sec:kirli}\n\\label{tab:kirli}\n")
    _degistir(bib, "}\n", "}\n\n@misc{kirli2021,\n  title = {Y},\n}\n")
    w._editor_tabs.setCurrentWidget(b2)
    uyarilar = []
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: uyarilar.append(a[2]) or 0))

    def adlandir(yeni, isleyici, anahtar, ed):
        uyarilar.clear()
        monkeypatch.setattr(QInputDialog, "getText",
                            staticmethod(lambda *a, **k: (yeni, True)))
        once = ed.text()
        isleyici(anahtar)
        return bool(uyarilar) and ed.text() == once          # engellendi

    if yol_ == "sihirbaz":
        yakalanan = []
        monkeypatch.setattr(tw.TableWizardDialog, "exec",
                            lambda self: yakalanan.append(set(self._existing)) or 0)
        w._table_wizard()
        sonuc = {"tab:kayitli", "tab:kirli"} <= yakalanan[-1]
    elif yol_ == "doi":
        anahtarlar = []
        monkeypatch.setattr(QInputDialog, "getText",
                            staticmethod(lambda *a, **k: ("10.1000/x", True)))
        monkeypatch.setattr(df.DoiRunner, "start",
                            lambda self, doi, kullanilan: anahtarlar.append(set(kullanilan)))
        w._add_by_doi()
        sonuc = {"kayitli2020", "kirli2021"} <= anahtarlar[-1]
    elif yol_ == "f2_etiket":
        sonuc = (adlandir("sec:kayitli", w._on_rename_label, "eski", b2),
                 adlandir("sec:kirli", w._on_rename_label, "eski", b2))
        sonuc = sonuc == (True, True)
    else:
        p2 = tmp_path / "elle"
        p2.mkdir()
        _yaz(p2 / "main2.tex", "\\documentclass{article}\n\\begin{document}\n"
             "Bkz. \\cite{eskib}.\n\\input{kaynaklar2}\n\\end{document}\n")
        _yaz(p2 / "kaynaklar2.tex", "\\begin{thebibliography}{9}\n"
             "\\bibitem{eskib} A. Yazar, Kitap.\n\\end{thebibliography}\n")
        w._open_file_in_editor(str(p2 / "kaynaklar2.tex"))
        k2 = w._editor_by_path(str(p2 / "kaynaklar2.tex"))
        _degistir(k2, "\\end{thebibliography}",
                  "\\bibitem{kirlib} B. Yazar, Makale.\n\\end{thebibliography}")
        w._open_file_in_editor(str(p2 / "main2.tex"))
        m2 = w._editor_by_path(str(p2 / "main2.tex"))
        w._editor_tabs.setCurrentWidget(m2)
        sonuc = adlandir("kirlib", w._on_rename_bibitem, "eskib", m2)
        k2.setModified(False)
    for e in (b1, bib, b2):
        e.setModified(False)
    assert sonuc

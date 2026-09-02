"""Referans denetimi — edit_ops handler ve OutputPanel tıklanabilir bulgu testleri.

İki katman:
- gui.mixins.edit_ops: _audit_references bulguları (metin, dosya, satır) üretir
- gui.output_panel: show_audit listeleri doldurur, tıklama error_clicked üretir
"""

import os

import pytest

try:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication
    from gui.editor import EditorWidget
    from gui.main_window import MainWindow
    from gui.mixins.edit_ops import EditOpsMixin
    from gui.output_panel import OutputPanel
    from gui.theme import THEMES
    from tests.stub_main import StubMain
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / gui import edilemiyor", allow_module_level=True)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class _StubMain(EditOpsMixin, StubMain):
    """MainWindow yerine: _audit_references'in ihtiyaç duyduğu arayüz.

    EditOpsMixin'den miras alır — handler self._collect_audit_items çağırır.
    """

    def __init__(self, editor):
        super().__init__(editors=[editor])


# --- handler: bulgular (metin, dosya, satır) üretir ---


def test_handler_undefined_ref_clickable(qapp, tmp_path):
    main = tmp_path / "m.tex"
    main.write_text("\\ref{fig:yok}\n", encoding="utf-8")
    ed = EditorWidget()
    ed._file_path = str(main)
    ed.setText(main.read_text(encoding="utf-8"))

    stub = _StubMain(ed)
    MainWindow._audit_references(stub)
    panel = stub._output_panel
    assert panel._suggest_list.count() == 0
    assert panel._warn_list.count() == 1
    item = panel._warn_list.item(0)
    assert "Tanımsız \\ref" in item.text() and "fig:yok" in item.text()
    assert "m.tex:1" in item.text()
    assert item.data(Qt.ItemDataRole.UserRole) == (str(main), 1)
    assert "1 tanımsız ref" in stub._status.msg


def test_handler_unused_bib_clickable(qapp, tmp_path):
    bib = tmp_path / "refs.bib"
    # Girdi TAM olmalı: eksik alan denetimi de aynı listeye yazıyor ve sahte
    # yarım bırakılırsa bu test iki bulgu görüp neyi ölçtüğünü kaybediyor.
    bib.write_text(
        "@article{kullanilmayan, author={A}, title={T}, journal={J}, year={2020}}\n",
        encoding="utf-8")
    main = tmp_path / "m.tex"
    main.write_text("\\label{a}\n\\ref{a}\n\\bibliography{refs}\n", encoding="utf-8")
    ed = EditorWidget()
    ed._file_path = str(main)
    ed.setText(main.read_text(encoding="utf-8"))

    stub = _StubMain(ed)
    MainWindow._audit_references(stub)
    panel = stub._output_panel
    assert panel._warn_list.count() == 0
    assert panel._suggest_list.count() == 1
    item = panel._suggest_list.item(0)
    assert "Kullanılmayan .bib girdisi" in item.text() and "kullanilmayan" in item.text()
    assert "refs.bib:1" in item.text()
    assert item.data(Qt.ItemDataRole.UserRole) == (str(bib), 1)


def test_handler_unused_label_clickable(qapp, tmp_path):
    main = tmp_path / "m.tex"
    main.write_text("\\label{bos}\n", encoding="utf-8")
    ed = EditorWidget()
    ed._file_path = str(main)
    ed.setText(main.read_text(encoding="utf-8"))

    stub = _StubMain(ed)
    MainWindow._audit_references(stub)
    panel = stub._output_panel
    assert panel._warn_list.count() == 0
    assert panel._suggest_list.count() == 1
    item = panel._suggest_list.item(0)
    assert "Kullanılmayan label" in item.text() and "bos" in item.text()
    assert "m.tex:1" in item.text()
    assert item.data(Qt.ItemDataRole.UserRole) == (str(main), 1)
    assert "1 kullanılmayan label" in stub._status.msg


def test_handler_clean_doc(qapp, tmp_path):
    main = tmp_path / "m.tex"
    main.write_text("\\label{a}\n\\ref{a}\n", encoding="utf-8")
    ed = EditorWidget()
    ed._file_path = str(main)
    ed.setText(main.read_text(encoding="utf-8"))

    stub = _StubMain(ed)
    MainWindow._audit_references(stub)
    panel = stub._output_panel
    assert panel._warn_list.count() == 0
    # temiz belgede tek 'Sorun bulunamadı' mesajı Öneriler'de
    assert panel._suggest_list.count() == 1
    assert "Sorun bulunamadı" in panel._suggest_list.item(0).text()
    assert "sorun yok" in stub._status.msg


def test_handler_needs_saved_file(qapp):
    ed = EditorWidget()  # dosya yolu yok
    stub = _StubMain(ed)
    MainWindow._audit_references(stub)
    panel = stub._output_panel
    assert panel._warn_list.count() == 0
    assert panel._suggest_list.count() == 0   # temiz-belge mesajı da yok
    assert ".tex dosyası açın" in stub._status.msg


# --- OutputPanel: show_audit + tıklama ---


def _panel(qapp):
    return OutputPanel(theme=THEMES["dark"])


def test_panel_show_audit_lists_and_tabs(qapp):
    panel = _panel(qapp)
    panel.show_audit(
        [("m.tex:3 — Tanımsız \\ref: fig:yok", "/tmp/m.tex", 3)],
        [("refs.bib:1 — Kullanılmayan .bib girdisi: a", "/tmp/refs.bib", 1)],
    )
    assert panel._warn_list.count() == 1
    assert panel._suggest_list.count() == 1
    assert panel._tabs.currentIndex() == panel._warn_tab_index


def test_panel_audit_click_emits_jump(qapp):
    panel = _panel(qapp)
    jumps = []
    panel.error_clicked.connect(lambda p, l: jumps.append((p, l)))
    panel.show_audit([("m.tex:3 — Tanımsız \\ref: fig:yok", "/tmp/m.tex", 3)], [])
    panel._on_result_click(panel._warn_list.item(0))
    assert jumps == [("/tmp/m.tex", 3)]


def test_panel_audit_click_without_location_no_emit(qapp):
    panel = _panel(qapp)
    jumps = []
    panel.error_clicked.connect(lambda p, l: jumps.append((p, l)))
    panel.show_audit([("Tanımsız \\ref: fig:yok", "", 0)], [])
    panel._on_result_click(panel._warn_list.item(0))
    assert jumps == []


def test_panel_audit_clean_shows_message(qapp):
    panel = _panel(qapp)
    panel.show_audit([], [])
    assert panel._suggest_list.count() == 1
    assert "Sorun bulunamadı" in panel._suggest_list.item(0).text()
    assert panel._tabs.currentIndex() == panel._suggest_tab_index


# --- Denetim maliyeti bulgu sayısıyla BÜYÜMEMELİ ---
#
# _collect_audit_items eskiden her bulgu için ayrı konum araması yapıyordu ve
# her arama \input zincirini diskten baştan okuyordu. 30 bölümlü, 200 girdilik
# .bib'li bir tezde ölçüldü: 495 arama = 1.74 sn, hepsi UI thread'inde
# (derleme sonrası denetim açıksa HER derlemeden sonra). 2026-08-31, G6.
#
# Süre ölçmek CI'da kırılgan olur; ölçülen şey DİSK OKUMASI: zincir okuma
# sayısı bulgu sayısından bağımsız, küçük bir sabit olmalı.

def _tez_projesi(tmp_path, n_bolum, n_etiket):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "k.bib").write_text(
        "".join("@article{a%d, title={T}}\n" % i for i in range(20)), encoding="utf-8")
    ana = ["\\documentclass{book}", "\\bibliography{k}", "\\begin{document}"]
    for b in range(n_bolum):
        satir = []
        for j in range(n_etiket):
            satir.append("\\section{S%d}" % j)
            satir.append("\\label{sec:b%d-%d}" % (b, j))   # hiç \ref edilmiyor
        (tmp_path / ("b%d.tex" % b)).write_text("\n".join(satir), encoding="utf-8")
        ana.append("\\input{b%d}" % b)
    ana.append("\\end{document}")
    icerik = "\n".join(ana)
    yol = tmp_path / "main.tex"
    yol.write_text(icerik, encoding="utf-8")
    return icerik, str(yol)


def _dosya_okuma_sayisi(monkeypatch, icerik, ana):
    """Denetim sırasında açılan .tex/.bib sayısı + denetim sonucu.

    Sayılan şey gerçek disk erişimi; hangi fonksiyonun yaptığı önemsiz.
    (İlk hâli ``_chain_texts`` çağrısını sayıyordu ve kapı düzeltmeden ÖNCEKİ
    kodda da yeşil kalıyordu: eski yol zinciri ``_flatten_input_paths``
    üzerinden okuyordu, sayaç onu hiç görmüyordu.)
    """
    import builtins

    from core import latex_refs
    latex_refs._label_file_cache.clear()
    latex_refs._bib_cache.clear()

    sayac = {"n": 0}
    gercek_open = builtins.open

    def sayan_open(dosya, *a, **kw):
        if isinstance(dosya, (str, os.PathLike)) and str(dosya).endswith((".tex", ".bib")):
            sayac["n"] += 1
        return gercek_open(dosya, *a, **kw)

    monkeypatch.setattr(builtins, "open", sayan_open)
    try:
        bulgular = EditOpsMixin._collect_audit_items(icerik, ana)
    finally:
        monkeypatch.undo()
    return sayac["n"], bulgular


def test_denetim_maliyeti_bulgu_sayisiyla_buyumuyor(tmp_path, monkeypatch):
    """Aynı DOSYA sayısı, 20 kat BULGU → disk okuması değişmemeli.

    İki proje de 4 bölüm dosyası + 1 .bib içerir; tek fark kullanılmayan
    label sayısıdır (4'e karşı 80). Eski kod her bulgu için zinciri baştan
    okuduğundan okuma sayısı bulguyla birlikte artıyordu.
    """
    kucuk = _tez_projesi(tmp_path / "az", 4, 1)      # 4 kullanılmayan label
    buyuk = _tez_projesi(tmp_path / "cok", 4, 20)    # 80 kullanılmayan label

    az_okuma, (_w1, _o1, az_c) = _dosya_okuma_sayisi(monkeypatch, *kucuk)
    cok_okuma, (_w2, _o2, cok_c) = _dosya_okuma_sayisi(monkeypatch, *buyuk)

    assert (az_c["l"], cok_c["l"]) == (4, 80), "test projesi beklendiği gibi değil"
    assert az_okuma == cok_okuma, (
        f"disk okuması bulgu sayısıyla büyüyor: {az_okuma} → {cok_okuma} "
        f"({az_c['l']} → {cok_c['l']} bulgu)")


def test_kullanilmayan_label_konumu_dogru_kaliyor(tmp_path):
    """Hız düzeltmesi 'dosya:satır' bağlantısını bozmamalı."""
    icerik, ana = _tez_projesi(tmp_path, 2, 1)
    _w, oneriler, _c = EditOpsMixin._collect_audit_items(icerik, ana)
    kayit = {t: (d, s) for t, d, s in oneriler}
    hedef = next(t for t in kayit if "sec:b1-0" in t)
    dosya, satir = kayit[hedef]
    assert dosya.endswith("b1.tex")
    assert satir == 2                      # \section{S0} 1, \label 2
    assert "b1.tex:2" in hedef


# --- .bib iç tutarlılığı: mükerrer anahtar + eksik zorunlu alan ---
#
# Bu iki denetim .tex ile .bib arasındaki bağa değil, .bib'in KENDİ içine
# bakıyor. Mükerrer anahtar özellikle sinsi: BibTeX uyarmadan ilk tanımı
# alıyor, kullanıcı ikinciyi düzeltip çıktının değişmemesine anlam veremiyor.


def _proje(tmp_path, bib_icerik: str, tex_icerik: str = None):
    bib = tmp_path / "refs.bib"
    bib.write_text(bib_icerik, encoding="utf-8")
    main = tmp_path / "m.tex"
    main.write_text(tex_icerik or "\\cite{a}\n\\bibliography{refs}\n", encoding="utf-8")
    ed = EditorWidget()
    ed._file_path = str(main)
    ed.setText(main.read_text(encoding="utf-8"))
    return _StubMain(ed), bib


def test_mukerrer_anahtar_uyari_olarak_cikiyor(qapp, tmp_path):
    """Belgeyi sessizce bozduğu için ÖNERİ değil UYARI."""
    stub, bib = _proje(tmp_path, (
        "@article{a, author={A}, title={Ilk}, journal={J}, year={2020}}\n"
        "@article{a, author={B}, title={Ikinci}, journal={J}, year={2021}}\n"))
    MainWindow._audit_references(stub)

    panel = stub._output_panel
    metinler = [panel._warn_list.item(i).text() for i in range(panel._warn_list.count())]
    assert any("Mükerrer" in m and "a" in m for m in metinler), metinler
    # Her iki satır da metinde yazılı olmalı: kullanıcı ötekini arayabilsin
    ilgili = [m for m in metinler if "Mükerrer" in m][0]
    assert "1" in ilgili and "2" in ilgili, ilgili


def test_mukerrer_ilk_tanima_tiklanabiliyor(qapp, tmp_path):
    stub, bib = _proje(tmp_path, (
        "@article{a, author={A}, title={T}, journal={J}, year={2020}}\n"
        "@article{a, author={B}, title={T}, journal={J}, year={2021}}\n"))
    MainWindow._audit_references(stub)
    panel = stub._output_panel
    for i in range(panel._warn_list.count()):
        it = panel._warn_list.item(i)
        if "Mükerrer" in it.text():
            assert it.data(Qt.ItemDataRole.UserRole) == (str(bib), 1)
            return
    raise AssertionError("mükerrer bulgusu yok")


def test_eksik_zorunlu_alan_oneri_olarak_cikiyor(qapp, tmp_path):
    """Derleme durmuyor, kaynakça eksik basılıyor: uyarı değil öneri."""
    stub, bib = _proje(tmp_path, "@article{a, title={T}}\n")
    MainWindow._audit_references(stub)

    panel = stub._output_panel
    metinler = [panel._suggest_list.item(i).text()
                for i in range(panel._suggest_list.count())]
    ilgili = [m for m in metinler if "Eksik zorunlu alan" in m]
    assert ilgili, metinler
    assert "author" in ilgili[0] and "journal" in ilgili[0] and "year" in ilgili[0]


def test_tam_bib_temiz_cikiyor(qapp, tmp_path):
    """Kural gürültü üretmemeli: tam girdide iki denetim de susmalı."""
    stub, _bib = _proje(
        tmp_path,
        "@article{a, author={A}, title={T}, journal={J}, year={2020}}\n")
    MainWindow._audit_references(stub)
    panel = stub._output_panel
    hepsi = ([panel._warn_list.item(i).text() for i in range(panel._warn_list.count())]
             + [panel._suggest_list.item(i).text()
                for i in range(panel._suggest_list.count())])
    assert not [m for m in hepsi if "Mükerrer" in m or "Eksik zorunlu" in m], hepsi


def test_misc_girdisi_eksik_saymiyor(qapp, tmp_path):
    """@misc'in zorunlu alanı yok; uydurma bulgu üretilmemeli."""
    stub, _bib = _proje(tmp_path, "@misc{a, note={N}}\n")
    MainWindow._audit_references(stub)
    panel = stub._output_panel
    metinler = [panel._suggest_list.item(i).text()
                for i in range(panel._suggest_list.count())]
    assert not [m for m in metinler if "Eksik zorunlu" in m], metinler


def test_bib_yoksa_cokmuyor(qapp, tmp_path):
    """\\bibliography yoksa denetim boş dönmeli, hata vermemeli."""
    main = tmp_path / "m.tex"
    main.write_text("\\label{a}\n\\ref{a}\n", encoding="utf-8")
    ed = EditorWidget()
    ed._file_path = str(main)
    ed.setText(main.read_text(encoding="utf-8"))
    MainWindow._audit_references(_StubMain(ed))   # istisna atmamalı


def test_ozet_sifirlari_atliyor(qapp, tmp_path):
    """Altı kategori her seferinde sıralanınca gerçek bulgu kayboluyordu."""
    stub, _bib = _proje(tmp_path, (
        "@article{a, author={A}, title={T}, journal={J}, year={2020}}\n"
        "@article{a, author={B}, title={T}, journal={J}, year={2021}}\n"))
    MainWindow._audit_references(stub)
    msg = stub._status.msg
    assert "mükerrer" in msg.lower(), msg
    assert "tanımsız ref" not in msg, msg
    assert "kullanılmayan label" not in msg, msg


# --- Kaynakça sekmesi: yapılandırılmış görünüm ---
#
# .bib'i editörde açmak zaten mümkün; bu sekmenin varlık sebebi girdileri
# SÜTUNLARA ayırıp sıralayabilmek ve süzebilmek. Ölçülen en büyük gerçek
# .bib 118 girdi taşıyor, panel ise 200 piksel: süzgeç olmadan kaydırmaktan
# ibaret kalırdı.


def _bib_projesi(tmp_path, bib_icerik: str, tex: str = None):
    bib = tmp_path / "refs.bib"
    bib.write_text(bib_icerik, encoding="utf-8")
    main = tmp_path / "m.tex"
    main.write_text(tex if tex is not None else "\\bibliography{refs}\n",
                    encoding="utf-8")
    ed = EditorWidget()
    ed._file_path = str(main)
    ed.setText(main.read_text(encoding="utf-8"))
    return _StubMain(ed), bib


IKI_GIRDI = (
    "@article{Kaya2018, author={Kaya, Aydın and Can, Ahmet},"
    " title={Akciğer nodülü}, journal={Gazi}, year={2018}}\n"
    "@inproceedings{He2016, author={He, Kaiming}, title={Deep Residual},"
    " booktitle={CVPR}, year={2016}}\n"
)


def test_girdiler_sutunlara_ayriliyor(qapp, tmp_path):
    stub, bib = _bib_projesi(tmp_path, IKI_GIRDI)
    MainWindow._show_bibliography(stub)

    tablo = stub._output_panel._bib_table
    assert tablo.rowCount() == 2
    satirlar = {tablo.item(r, 0).text(): [tablo.item(r, c).text() for c in range(5)]
                for r in range(2)}
    assert satirlar["Kaya2018"] == [
        "Kaya2018", "article", "Kaya vd.", "2018", "Akciğer nodülü"]
    assert satirlar["He2016"][1] == "inproceedings"
    assert satirlar["He2016"][2] == "He"          # tek yazar, "vd." yok


def test_satira_tiklayinca_bib_satirina_gidiyor(qapp, tmp_path):
    stub, bib = _bib_projesi(tmp_path, IKI_GIRDI)
    MainWindow._show_bibliography(stub)

    panel = stub._output_panel
    atlamalar = []
    panel.error_clicked.connect(lambda p, l: atlamalar.append((p, l)))
    tablo = panel._bib_table
    # İkinci girdi dosyanın 2. satırında
    hedef = [r for r in range(2) if tablo.item(r, 0).text() == "He2016"][0]
    panel._on_bib_click(tablo.item(hedef, 4))     # BAŞLIK sütununa tıkla
    assert atlamalar == [(str(bib), 2)], atlamalar


def test_tiklama_hangi_sutundan_gelirse_gelsin_calisiyor(qapp, tmp_path):
    """Yol/satır yalnız ilk sütunda; tıklama satırın her yerinden okumalı."""
    stub, bib = _bib_projesi(tmp_path, IKI_GIRDI)
    MainWindow._show_bibliography(stub)
    panel = stub._output_panel
    for sutun in range(5):
        atlamalar = []
        baglanti = panel.error_clicked.connect(
            lambda p, l: atlamalar.append((p, l)))
        panel._on_bib_click(panel._bib_table.item(0, sutun))
        panel.error_clicked.disconnect(baglanti)
        assert len(atlamalar) == 1, sutun


def test_suzgec_anahtar_yazar_basliga_bakiyor(qapp, tmp_path):
    stub, _bib = _bib_projesi(tmp_path, IKI_GIRDI)
    MainWindow._show_bibliography(stub)
    panel = stub._output_panel
    tablo = panel._bib_table

    def gorunen():
        return [tablo.item(r, 0).text() for r in range(tablo.rowCount())
                if not tablo.isRowHidden(r)]

    panel._bib_filter.setText("kaya")          # yazar
    assert gorunen() == ["Kaya2018"]
    panel._bib_filter.setText("residual")      # başlık
    assert gorunen() == ["He2016"]
    panel._bib_filter.setText("He2016")        # anahtar
    assert gorunen() == ["He2016"]
    panel._bib_filter.setText("")
    assert len(gorunen()) == 2


def test_suzgec_turkce_harf_duyarsiz(qapp, tmp_path):
    """Projede ara ile aynı katlama: 'ciger' araması 'Akciğer'i bulmalı."""
    stub, _bib = _bib_projesi(tmp_path, IKI_GIRDI)
    MainWindow._show_bibliography(stub)
    panel = stub._output_panel
    panel._bib_filter.setText("AKCİĞER")
    gorunen = [panel._bib_table.item(r, 0).text()
               for r in range(panel._bib_table.rowCount())
               if not panel._bib_table.isRowHidden(r)]
    assert gorunen == ["Kaya2018"], gorunen


def test_suzgec_yila_bakmiyor(qapp, tmp_path):
    """Yıl sütunu SIRALAMA için, süzgeç için değil.

    Anahtar yılı İÇERDİĞİ için (Kaya2018 gibi, ki olağan biçim budur) bunu
    ayırt eden sahne anahtarında yıl GEÇMEYEN bir girdi gerektiriyor.
    """
    stub, _bib = _bib_projesi(tmp_path, (
        "@article{kaya, author={Kaya, A}, title={Nodül},"
        " journal={J}, year={2018}}\n"))
    MainWindow._show_bibliography(stub)
    panel = stub._output_panel
    panel._bib_filter.setText("2018")
    gorunen = [r for r in range(panel._bib_table.rowCount())
               if not panel._bib_table.isRowHidden(r)]
    assert gorunen == [], "yıl süzgece giriyor"

    # Kapının kendisi: aynı sahnede yazar araması BULMALI, yoksa yukarıdaki
    # boş sonuç "süzgeç hiç çalışmıyor" yüzünden de geliyor olabilirdi.
    panel._bib_filter.setText("kaya")
    assert [r for r in range(panel._bib_table.rowCount())
            if not panel._bib_table.isRowHidden(r)] == [0]


def test_tablo_salt_okunur(qapp, tmp_path):
    """Girdi düzenleme bilinçli olarak kapsam dışı."""
    stub, _bib = _bib_projesi(tmp_path, IKI_GIRDI)
    MainWindow._show_bibliography(stub)
    from PyQt6.QtWidgets import QAbstractItemView
    assert (stub._output_panel._bib_table.editTriggers()
            == QAbstractItemView.EditTrigger.NoEditTriggers)


def test_siralama_acik(qapp, tmp_path):
    stub, _bib = _bib_projesi(tmp_path, IKI_GIRDI)
    MainWindow._show_bibliography(stub)
    assert stub._output_panel._bib_table.isSortingEnabled()


def test_bibliography_yoksa_nedeni_soyleniyor(qapp, tmp_path):
    """'Boş' ile '\\bibliography satırı yok' ayrı şeyler."""
    stub, _bib = _bib_projesi(tmp_path, IKI_GIRDI, tex="merhaba\n")
    MainWindow._show_bibliography(stub)
    panel = stub._output_panel
    assert panel._bib_table.rowCount() == 0
    assert "bibliography" in panel._bib_status.text().lower()


def test_dosya_acik_degilse_uyariyor(qapp):
    stub = _StubMain(EditorWidget())
    MainWindow._show_bibliography(stub)
    assert ".tex" in stub._output_panel._bib_status.text()


def test_bos_bib_dosyasi(qapp, tmp_path):
    stub, _bib = _bib_projesi(tmp_path, "% yalnız yorum\n")
    MainWindow._show_bibliography(stub)
    panel = stub._output_panel
    assert panel._bib_table.rowCount() == 0
    assert panel._bib_status.text()


def test_cp1254_bib_okunabiliyor(qapp, tmp_path):
    """Türkçe .bib dosyaları cp1254 ile kaydedilmiş olabilir."""
    bib = tmp_path / "refs.bib"
    bib.write_bytes(
        "@article{k, author={Öz, Ali}, title={Şekil}, journal={J}, year={2020}}\n"
        .encode("cp1254"))
    main = tmp_path / "m.tex"
    main.write_text("\\bibliography{refs}\n", encoding="utf-8")
    ed = EditorWidget()
    ed._file_path = str(main)
    ed.setText(main.read_text(encoding="utf-8"))
    stub = _StubMain(ed)
    MainWindow._show_bibliography(stub)
    tablo = stub._output_panel._bib_table
    assert tablo.rowCount() == 1
    assert tablo.item(0, 2).text() == "Öz"
    assert tablo.item(0, 4).text() == "Şekil"


def test_yeniden_doldurma_eski_satirlari_birakmiyor(qapp, tmp_path):
    stub, bib = _bib_projesi(tmp_path, IKI_GIRDI)
    MainWindow._show_bibliography(stub)
    assert stub._output_panel._bib_table.rowCount() == 2

    bib.write_text("@book{tek, author={A}, title={T}, publisher={P}, year={2020}}\n",
                   encoding="utf-8")
    MainWindow._show_bibliography(stub)
    assert stub._output_panel._bib_table.rowCount() == 1


def test_sekmeye_gecince_doldurma_isteniyor(qapp):
    """Boş sekmeye tıklayıp boş tablo görmek çıkmaz sokak."""
    panel = OutputPanel(theme=THEMES["dark"])
    istekler = []
    panel.bibliography_requested.connect(lambda: istekler.append(1))
    panel._tabs.setCurrentIndex(panel._bib_tab_index)
    assert istekler == [1]


def test_dolu_sekmeye_gecince_tekrar_istenmiyor(qapp):
    panel = OutputPanel(theme=THEMES["dark"])
    panel.show_bibliography([(("k", "article", "A", "2020", "T"), 1)], "/tmp/r.bib")
    istekler = []
    panel.bibliography_requested.connect(lambda: istekler.append(1))
    panel._tabs.setCurrentIndex(0)
    panel._tabs.setCurrentIndex(panel._bib_tab_index)
    assert istekler == []


def test_clear_bibliography_bosaltiyor(qapp):
    """Kök değişince eski projenin girdileri kalmamalı."""
    panel = OutputPanel(theme=THEMES["dark"])
    panel.show_bibliography([(("k", "article", "A", "2020", "T"), 1)], "/tmp/r.bib")
    panel._bib_filter.setText("k")
    panel.clear_bibliography()
    assert panel._bib_table.rowCount() == 0
    assert panel._bib_filter.text() == ""


# --- Kaynakça listelenemiyorsa NEDENİ söylenmeli ---
#
# Dört ayrı durum vardı, üçü aynı mesajı alıyordu ve ikisi YANLIŞTI:
#   - elle kaynakça yazana "kaynakçan yok" deniyordu (13 şablon böyle)
#   - dosyası eksik olana da aynısı deniyordu, oysa \bibliography satırı
#     belgede DURUYOR; kullanıcı zaten orada olan komutu aramaya gidiyordu


def test_bildirim_var_dosya_yoksa_dosya_adi_soyleniyor(qapp, tmp_path):
    main = tmp_path / "m.tex"
    main.write_text("\\bibliography{olmayan}\n", encoding="utf-8")
    ed = EditorWidget()
    ed._file_path = str(main)
    ed.setText(main.read_text(encoding="utf-8"))
    stub = _StubMain(ed)
    MainWindow._show_bibliography(stub)
    not_ = stub._output_panel._bib_status.text()
    assert "olmayan.bib" in not_, not_
    assert "bibliography" not in not_.lower(), "bildirim yok sanıldı: " + not_


def test_elle_kaynakca_ayirt_ediliyor(qapp, tmp_path):
    """\\begin{thebibliography} kullanan belgenin kaynakçası VAR."""
    main = tmp_path / "m.tex"
    main.write_text(
        "\\begin{thebibliography}{9}\n\\bibitem{a} A. Yazar, 2020.\n"
        "\\end{thebibliography}\n", encoding="utf-8")
    ed = EditorWidget()
    ed._file_path = str(main)
    ed.setText(main.read_text(encoding="utf-8"))
    stub = _StubMain(ed)
    MainWindow._show_bibliography(stub)
    not_ = stub._output_panel._bib_status.text()
    assert "elle" in not_.lower(), not_


def test_hic_kaynakca_yoksa_bildirim_yok_deniyor(qapp, tmp_path):
    main = tmp_path / "m.tex"
    main.write_text("Sadece metin.\n", encoding="utf-8")
    ed = EditorWidget()
    ed._file_path = str(main)
    ed.setText(main.read_text(encoding="utf-8"))
    stub = _StubMain(ed)
    MainWindow._show_bibliography(stub)
    not_ = stub._output_panel._bib_status.text()
    assert "bibliography" in not_.lower(), not_
    assert "elle" not in not_.lower(), not_


def test_uc_neden_birbirinden_FARKLI(qapp, tmp_path):
    """Kapının kendisi: üçü aynı metne dönerse yukarıdakiler boşa düşer."""
    mesajlar = set()
    for ad, icerik in (
        ("yok", "Sadece metin.\n"),
        ("eksik", "\\bibliography{olmayan}\n"),
        ("elle", "\\begin{thebibliography}{9}\n\\bibitem{a} X\n"
                 "\\end{thebibliography}\n"),
    ):
        p = tmp_path / (ad + ".tex")
        p.write_text(icerik, encoding="utf-8")
        mesajlar.add(EditOpsMixin._bib_yok_nedeni(icerik, str(p)))
    assert len(mesajlar) == 3, mesajlar


# --- Çıktı paneli yüksekliği ---
#
# Tavan 200'dü ve panel ayırıcıdan sürüklense bile orada takılıyordu
# (ölçüldü: 300/450/600 istendi, üçünde de 200). Kaynakça sekmesi 118
# satırlık tabloyu o alana sığdıramıyor.


def test_panel_tavani_iki_kat(qapp):
    panel = OutputPanel(theme=THEMES["dark"])
    assert panel.maximumHeight() == 400


def test_panel_kuculme_siniri_DEGISMEDI(qapp):
    """İstenen buydu: büyüyebilsin ama eskisi kadar da küçülebilsin.

    Açık bir minimumHeight konmamalı; taban widget'ın kendi
    minimumSizeHint'i (ölçüldü: 116 px).
    """
    panel = OutputPanel(theme=THEMES["dark"])
    assert panel.minimumHeight() == 0
    assert panel.minimumSizeHint().height() <= 200


def test_pencere_buyuyunce_panel_buyumuyor(qapp):
    """Fazla alanı ÜST bölme almalı; panel sürüklendiği yerde kalmalı.

    Tavan 200'ken fark edilmiyordu; 400'e çıkınca uzun pencerede panel
    kendiliğinden 400'e şişip editörü eziyordu (1600x2000'de 181 -> 400).
    """
    from PyQt6.QtWidgets import QSplitter, QWidget
    from PyQt6.QtCore import Qt

    s = QSplitter(Qt.Orientation.Vertical)
    ust = QWidget()
    panel = OutputPanel(theme=THEMES["dark"])
    s.addWidget(ust)
    s.addWidget(panel)
    s.setSizes([700, 200])
    s.setStretchFactor(0, 1)
    s.setStretchFactor(1, 0)
    s.resize(1200, 900)
    s.show()
    QApplication.processEvents()
    once = panel.height()

    s.resize(1200, 1800)
    QApplication.processEvents()
    assert panel.height() <= once + 5, (once, panel.height())
    s.close()


def test_main_window_esneme_carpanlarini_kuruyor():
    """Yukarıdaki mekanizma GERÇEKTEN bağlanmış mı."""
    kok = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(kok, "desktop", "gui", "main_window.py"),
              encoding="utf-8") as f:
        k = f.read()
    assert "self._main_splitter.setStretchFactor(0, 1)" in k
    assert "self._main_splitter.setStretchFactor(1, 0)" in k

"""FileTree._collect_files — snapshot/refresh yürüyüşünün atlama kuralları.

Ağaç çizimi _SKIP_DIRS/_MAX_DEPTH uyguluyordu; snapshot yürüyüşü de aynı
kuralları uygulamalı (her FS olayında koşar, WSL'de pahalı).
"""

import os

import pytest

try:
    from PyQt6.QtWidgets import QApplication
    from gui.file_tree import FileTree
    from gui.theme import THEMES
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / gui modülleri gerekli", allow_module_level=True)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_collect_files_skip_ve_derinlik_kurallari(qapp, tmp_path):
    (tmp_path / "ana.tex").write_text("x", encoding="utf-8")
    sub = tmp_path / "bolum"
    sub.mkdir()
    (sub / "giris.tex").write_text("x", encoding="utf-8")
    for skip in ("node_modules", "venv", "__pycache__"):
        d = tmp_path / skip
        d.mkdir()
        (d / f"{skip}.tex").write_text("x", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "gizli.tex").write_text("x", encoding="utf-8")

    # _MAX_DEPTH = 5: kök düzey 0; 6 seviye derindeki dosya taranmamalı
    deep = tmp_path
    for i in range(6):
        deep = deep / f"d{i}"
        deep.mkdir()
    (deep / "cok_derin.tex").write_text("x", encoding="utf-8")

    tree = FileTree(theme=THEMES["dark"])
    files = tree._collect_files(str(tmp_path))

    got = {os.path.relpath(f, str(tmp_path)).replace(os.sep, "/") for f in files}
    assert got == {"ana.tex", "bolum/giris.tex"}


def test_input_ref_ok_tek_okumayla_iki_denetim(qapp, tmp_path, monkeypatch):
    """Bağlantılı dosya denetimi dosyayı TEK kez açmalı (can_compile +
    detect_root ayrı ayrı okuyordu); kök yönlendirmesi de çalışmalı."""
    from gui.file_tree import FileTree

    root = tmp_path / "main.tex"
    root.write_text("\\begin{document}\\input{bolum}\\end{document}\n", encoding="utf-8")
    child = tmp_path / "bolum.tex"
    child.write_text("% !TEX root = main.tex\nparca\n", encoding="utf-8")

    tree = FileTree(theme=THEMES["dark"])
    acilis = {"n": 0}
    gercek_open = open

    def sayan_open(file, *a, **k):
        if str(file).endswith("bolum.tex"):
            acilis["n"] += 1
        return gercek_open(file, *a, **k)

    import builtins
    monkeypatch.setattr(builtins, "open", sayan_open)

    assert tree._input_ref_ok(str(child)) is True      # kök yönlendirmesi
    assert acilis["n"] == 1, "dosya tek kez açılmalı"

    plain = tmp_path / "bagimsiz.tex"
    plain.write_text("\\begin{document}tam belge\\end{document}\n", encoding="utf-8")
    assert tree._input_ref_ok(str(plain)) is True      # doğrudan derlenebilir
    parcacik = tmp_path / "parca2.tex"
    parcacik.write_text("yalnızca parça\n", encoding="utf-8")
    assert tree._input_ref_ok(str(parcacik)) is False


def test_input_ref_ok_BUYUK_HARFLI_uzantiyi_da_goruyor(qapp, tmp_path):
    """`.TEX` de `.tex` kadar gecerli bir LaTeX dosyasi.

    Gercek sablonda var: `template34-tez` (Istanbul Universitesi Fen
    Bilimleri tez sablonu) kok dosyasini `iufenbil_tez_sablonu.TEX` diye
    tasiyor. Windows dosya sistemi harf duyarsiz ama karsilastirma
    duyarliydi; o dosya "derlenemez" sayilip agacta oyle isaretleniyordu.

    2026-09-04'te MiKTeX olcumu sirasinda bulundu.
    """
    from gui.file_tree import FileTree

    buyuk = tmp_path / "BELGE.TEX"
    buyuk.write_text("\\begin{document}tam belge\\end{document}\n",
                     encoding="utf-8")
    tree = FileTree(theme=THEMES["dark"])
    assert tree._input_ref_ok(str(buyuk)) is True


# ---------------------------------------------------------------------------
# Bağlam menüsü işlemleri: yeni dosya / yeni klasör / yeniden adlandır
#
# Menüde yalnız "Derle / Düzenle / Klasörde Aç / Sil" vardı. Silme varken
# yeniden adlandırmanın olmaması göze batıyordu; klasöre sağ tıklamak ise
# HİÇBİR menü açmıyordu (`_on_context_menu` dosya değilse hemen dönüyordu).
# ---------------------------------------------------------------------------

from PyQt6.QtCore import QPoint, Qt  # noqa: E402
from PyQt6.QtWidgets import (  # noqa: E402
    QInputDialog, QMenu, QMessageBox, QTreeWidgetItem,
)
from core import fs_ops  # noqa: E402


def _agac(qapp, kok):
    t = FileTree(theme=THEMES["dark"])
    t.set_root(str(kok))
    return t


def _oge_bul(tree, ad: str):
    """Ağaçta metnine göre öğe bul (ikon öneki yok sayılır)."""
    kok = tree._tree.invisibleRootItem()
    yigin = [kok.child(i) for i in range(kok.childCount())]
    while yigin:
        oge = yigin.pop()
        if oge.text(0).split(" ", 1)[-1] == ad:
            return oge
        yigin.extend(oge.child(i) for i in range(oge.childCount()))
    return None


def _menu_actionlari(tree, oge, monkeypatch):
    """Bağlam menüsünü aç, eylem metinlerini topla, menüyü iptal et."""
    toplanan = []

    def sahte_exec(menu_self, *_a, **_k):
        toplanan.extend(act.text() for act in menu_self.actions() if act.text())
        return None

    monkeypatch.setattr(QMenu, "exec", sahte_exec)
    monkeypatch.setattr(type(tree._tree), "itemAt", lambda *_a: oge)
    monkeypatch.setattr(type(tree._tree), "mapToGlobal", lambda _s, p: p)
    tree._on_context_menu(QPoint(0, 0))
    return toplanan


class TestBaglamMenusu:
    def test_klasore_sag_tik_menu_aciyor(self, qapp, tmp_path, monkeypatch):
        """Eskiden klasörde menü HİÇ açılmıyordu (dosya değil diye dönülüyordu)."""
        alt = tmp_path / "bolumler"
        alt.mkdir()
        (alt / "giris.tex").write_text("x", encoding="utf-8")
        tree = _agac(qapp, tmp_path)

        oge = _oge_bul(tree, "bolumler")
        assert oge is not None, "klasör ağaçta yok"
        metinler = _menu_actionlari(tree, oge, monkeypatch)

        assert any("Yeni Dosya" in m for m in metinler), metinler
        assert any("Yeni Klasör" in m for m in metinler), metinler
        assert any("Yeniden Adlandır" in m for m in metinler), metinler

    def test_klasor_ogesi_yolunu_tasiyor(self, qapp, tmp_path):
        """Menünün hangi klasörde çalışacağını bu veriden öğreniyor."""
        alt = tmp_path / "bolumler"
        alt.mkdir()
        (alt / "a.tex").write_text("x", encoding="utf-8")
        tree = _agac(qapp, tmp_path)
        oge = _oge_bul(tree, "bolumler")
        assert oge.data(0, Qt.ItemDataRole.UserRole) == str(alt)

    def test_dosyada_yeniden_adlandir_var(self, qapp, tmp_path, monkeypatch):
        (tmp_path / "ana.tex").write_text("x", encoding="utf-8")
        tree = _agac(qapp, tmp_path)
        metinler = _menu_actionlari(tree, _oge_bul(tree, "ana.tex"), monkeypatch)
        assert any("Yeniden Adlandır" in m for m in metinler), metinler
        assert any("Sil" in m for m in metinler), metinler

    def test_bos_alanda_kokte_yeni_oge(self, qapp, tmp_path, monkeypatch):
        """Ağaç boşken de dosya yaratılabilmeli; tıklanacak öğe yok."""
        tree = _agac(qapp, tmp_path)
        metinler = _menu_actionlari(tree, None, monkeypatch)
        assert any("Yeni Dosya" in m for m in metinler), metinler
        # Kökün kendisi silinemez/adlandırılamaz
        assert not any("Yeniden Adlandır" in m for m in metinler), metinler
        assert not any("Sil" in m for m in metinler), metinler

    def test_kok_klasor_silinemez(self, qapp, tmp_path, monkeypatch):
        """Kök ağacın dayanağı: menüden silinirse ağaç ortada kalırdı."""
        (tmp_path / "a.tex").write_text("x", encoding="utf-8")
        tree = _agac(qapp, tmp_path)
        # Kökü gösteren sahte öğe: itemAt kök yolunu döndürsün
        sahte = QTreeWidgetItem(["kok"])
        sahte.setData(0, Qt.ItemDataRole.UserRole, str(tmp_path))
        metinler = _menu_actionlari(tree, sahte, monkeypatch)
        assert not any("Sil" in m for m in metinler), metinler


class TestPdfGorunurlugu:
    r"""`.pdf` çift anlamlı: derleme çıktısı da olabilir, ŞEKİL de.

    Tek kural ikisini ayırt etmiyordu, hepsi gizliydi. Tez yazarı kendi
    `Figures/` klasörünü boş görüyordu. Üstelik uygulama ağaçtan editöre
    sürükle-bırakta `.pdf` için `\includegraphics` bloğu üretiyor, yani
    özellik yazılmış ama kullanılamıyordu.

    39 şablonda ölçüldü, 84 dosyanın 84'ü doğru tarafta:
      kökte 61 (hepsi main_pdflatex.pdf gibi çıktı),
      alt klasörde 23 (hepsi Figures/logo/figs/Definitions içinde).
    """

    def test_ayni_adli_tex_varsa_cikti_sayiliyor(self, qapp, tmp_path):
        (tmp_path / "ana.tex").write_text("x", encoding="utf-8")
        (tmp_path / "ana.pdf").write_bytes(b"%PDF-1.4\n")
        tree = _agac(qapp, tmp_path)
        assert _oge_bul(tree, "ana.pdf") is None

    def test_kokteki_esi_olmayan_pdf_de_gizli(self, qapp, tmp_path):
        """main_pdflatex.pdf gibi: adı .tex'e uymuyor ama yine de çıktı."""
        (tmp_path / "main.tex").write_text("x", encoding="utf-8")
        (tmp_path / "main_pdflatex.pdf").write_bytes(b"%PDF-1.4\n")
        tree = _agac(qapp, tmp_path)
        assert _oge_bul(tree, "main_pdflatex.pdf") is None

    def test_alt_klasordeki_pdf_gorunuyor(self, qapp, tmp_path):
        (tmp_path / "ana.tex").write_text("x", encoding="utf-8")
        fig = tmp_path / "Figures"
        fig.mkdir()
        (fig / "Sample.pdf").write_bytes(b"%PDF-1.4\n")
        tree = _agac(qapp, tmp_path)
        assert _oge_bul(tree, "Sample.pdf") is not None

    def test_alt_klasorde_de_esi_varsa_gizli(self, qapp, tmp_path):
        """bolum1.tex ile bolum1.pdf yan yanaysa, alt klasörde bile çıktıdır."""
        (tmp_path / "ana.tex").write_text("x", encoding="utf-8")
        alt = tmp_path / "bolumler"
        alt.mkdir()
        (alt / "bolum1.tex").write_text("x", encoding="utf-8")
        (alt / "bolum1.pdf").write_bytes(b"%PDF-1.4\n")
        (alt / "sekil.pdf").write_bytes(b"%PDF-1.4\n")
        tree = _agac(qapp, tmp_path)
        assert _oge_bul(tree, "bolum1.pdf") is None
        assert _oge_bul(tree, "sekil.pdf") is not None

    def test_diger_artiklar_her_yerde_gizli(self, qapp, tmp_path):
        """.aux/.log/.toc'un tek kaynağı derleme; kural onlara dokunmadı."""
        (tmp_path / "ana.tex").write_text("x", encoding="utf-8")
        alt = tmp_path / "bolumler"
        alt.mkdir()
        for ad in ("ana.aux", "ana.log", "ana.toc", "ana.bbl", "ana.synctex.gz"):
            (alt / ad).write_text("x", encoding="utf-8")
        (alt / "gercek.tex").write_text("x", encoding="utf-8")
        tree = _agac(qapp, tmp_path)
        for ad in ("ana.aux", "ana.log", "ana.toc", "ana.bbl", "ana.synctex.gz"):
            assert _oge_bul(tree, ad) is None, ad
        assert _oge_bul(tree, "gercek.tex") is not None

    def test_gorunur_pdf_duzenlenebilir_degil(self, qapp, tmp_path):
        """Çift tıklayınca editörde açılmamalı; sürüklenebilir olması yeter."""
        (tmp_path / "ana.tex").write_text("x", encoding="utf-8")
        fig = tmp_path / "Figures"
        fig.mkdir()
        (fig / "Sample.pdf").write_bytes(b"%PDF-1.4\n")
        tree = _agac(qapp, tmp_path)
        oge = _oge_bul(tree, "Sample.pdf")
        assert oge.data(0, Qt.ItemDataRole.UserRole + 1) is False

    def test_anlik_goruntu_agacla_ayni_kurali_kullaniyor(self, qapp, tmp_path):
        """_collect_files ile ağaç ayrışırsa yeni şekil kendiliğinden düşmez.

        Ters yön de önemli: kökteki PDF anlık görüntüye girseydi her derleme
        ağacı baştan taratırdı.
        """
        (tmp_path / "ana.tex").write_text("x", encoding="utf-8")
        (tmp_path / "ana.pdf").write_bytes(b"%PDF-1.4\n")
        fig = tmp_path / "Figures"
        fig.mkdir()
        (fig / "Sample.pdf").write_bytes(b"%PDF-1.4\n")
        tree = _agac(qapp, tmp_path)

        toplanan = {os.path.basename(p) for p in tree._collect_files(str(tmp_path))}
        assert "Sample.pdf" in toplanan
        assert "ana.pdf" not in toplanan


class TestKlasorGorunurlugu:
    """Her klasör ağaçta görünmeli.

    Kural eskiden "görünür dosyası olmayan klasörü gizle" idi ve iki şeyi
    birden bozuyordu:

    - Menüden yaratılan klasör HİÇ görünmüyordu (boş olduğu için). Görünmeyen
      klasörün içine dosya da eklenemiyor: kullanıcı Explorer'a gitmek
      zorundaydı. KULLANICI BİLDİRDİ (2026-09-01).
    - 39 şablonda ölçüldü: gizlenen 7 klasörün beşi `Figures` / `logo` gibi
      KAYNAK klasörleri. İçlerindeki dosyalar .pdf olduğu ve .pdf
      _HIDDEN_EXT'te bulunduğu için klasör "dosyasız" sayılıyordu.
    """

    def test_bos_klasor_gorunuyor(self, qapp, tmp_path):
        (tmp_path / "ana.tex").write_text("x", encoding="utf-8")
        (tmp_path / "yeni_bos").mkdir()
        tree = _agac(qapp, tmp_path)
        assert _oge_bul(tree, "yeni_bos") is not None

    def test_yalniz_gizli_uzantili_klasor_gorunuyor(self, qapp, tmp_path):
        """Figures/ içinde yalnız .pdf varsa bile klasör görünmeli."""
        (tmp_path / "ana.tex").write_text("x", encoding="utf-8")
        fig = tmp_path / "Figures"
        fig.mkdir()
        (fig / "Electron.pdf").write_bytes(b"%PDF-1.4\n")
        tree = _agac(qapp, tmp_path)
        assert _oge_bul(tree, "Figures") is not None

    def test_yaratilan_klasor_hemen_agacta(self, qapp, tmp_path, monkeypatch):
        """Menüden yarat -> refresh -> ağaçta görünmeli (uçtan uca)."""
        (tmp_path / "ana.tex").write_text("x", encoding="utf-8")
        tree = _agac(qapp, tmp_path)
        monkeypatch.setattr(QInputDialog, "getText",
                            lambda *a, **k: ("gorseller", True))
        tree._yeni_oge(str(tmp_path), klasor=True)
        assert _oge_bul(tree, "gorseller") is not None, \
            "klasör diskte yaratıldı ama ağaçta yok"

    def test_atlanan_klasorler_hala_gizli(self, qapp, tmp_path):
        """Kural gevşedi ama _SKIP_DIRS ve nokta klasörleri kapsam dışı."""
        (tmp_path / "ana.tex").write_text("x", encoding="utf-8")
        for ad in ("node_modules", "__pycache__", ".git"):
            (tmp_path / ad).mkdir()
        tree = _agac(qapp, tmp_path)
        for ad in ("node_modules", "__pycache__", ".git"):
            assert _oge_bul(tree, ad) is None, ad


class TestYeniOge:
    def test_dosya_yaratiliyor_ve_aciliyor(self, qapp, tmp_path, monkeypatch):
        tree = _agac(qapp, tmp_path)
        monkeypatch.setattr(QInputDialog, "getText",
                            lambda *a, **k: ("bolum2.tex", True))
        acilan = []
        tree.file_open_requested.connect(acilan.append)

        tree._yeni_oge(str(tmp_path), klasor=False)

        assert (tmp_path / "bolum2.tex").is_file()
        assert acilan == [str(tmp_path / "bolum2.tex")], acilan

    def test_duzenlenemez_uzanti_acilmiyor(self, qapp, tmp_path, monkeypatch):
        """.txt editörde açılamıyor; yaratılıyor ama sekme açılmıyor."""
        tree = _agac(qapp, tmp_path)
        monkeypatch.setattr(QInputDialog, "getText",
                            lambda *a, **k: ("notlar.txt", True))
        acilan = []
        tree.file_open_requested.connect(acilan.append)
        tree._yeni_oge(str(tmp_path), klasor=False)
        assert (tmp_path / "notlar.txt").is_file()
        assert acilan == []

    def test_klasor_yaratiliyor(self, qapp, tmp_path, monkeypatch):
        tree = _agac(qapp, tmp_path)
        monkeypatch.setattr(QInputDialog, "getText",
                            lambda *a, **k: ("gorseller", True))
        tree._yeni_oge(str(tmp_path), klasor=True)
        assert (tmp_path / "gorseller").is_dir()

    def test_iptal_hicbir_sey_yaratmiyor(self, qapp, tmp_path, monkeypatch):
        tree = _agac(qapp, tmp_path)
        monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("x.tex", False))
        tree._yeni_oge(str(tmp_path), klasor=False)
        assert not (tmp_path / "x.tex").exists()

    def test_var_olan_ad_uyariyor_uzerine_YAZMIYOR(self, qapp, tmp_path, monkeypatch):
        p = tmp_path / "dolu.tex"
        p.write_text("degerli", encoding="utf-8")
        tree = _agac(qapp, tmp_path)
        monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("dolu.tex", True))
        uyarilar = []
        monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: uyarilar.append(a))
        tree._yeni_oge(str(tmp_path), klasor=False)
        assert uyarilar, "var olan ad sessizce geçti"
        assert p.read_text(encoding="utf-8") == "degerli"


class TestAdDenetimiArayuzde:
    def test_gecersiz_ad_uyariyor_ve_tekrar_soruyor(self, qapp, tmp_path, monkeypatch):
        """Önce yasak karakterli ad, sonra geçerli: kutu ikinci kez açılmalı."""
        tree = _agac(qapp, tmp_path)
        cevaplar = [("a<b.tex", True), ("ab.tex", True)]
        monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: cevaplar.pop(0))
        uyarilar = []
        monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: uyarilar.append(a))

        tree._yeni_oge(str(tmp_path), klasor=False)

        assert len(uyarilar) == 1, "geçersiz ad için uyarı çıkmadı"
        assert (tmp_path / "ab.tex").is_file()

    def test_bastaki_sondaki_bosluk_kirpiliyor(self, qapp, tmp_path, monkeypatch):
        """Görünmez karakter yüzünden hata vermek anlamsız."""
        tree = _agac(qapp, tmp_path)
        monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("  a.tex  ", True))
        monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
        tree._yeni_oge(str(tmp_path), klasor=False)
        assert (tmp_path / "a.tex").is_file()

    def test_her_gerekce_kodunun_metni_var(self, qapp):
        """Yeni bir gerekçe eklenip metni unutulursa kullanıcı 'Ad geçersiz.' görür."""
        kodlar = [v for k, v in vars(fs_ops).items()
                  if k.isupper() and isinstance(v, str) and not k.startswith("_")]
        assert len(kodlar) >= 6, kodlar
        for kod in kodlar:
            metin = FileTree._ad_hata_metni(kod)
            assert metin and metin != "Ad geçersiz.", kod


class TestYenidenAdlandir:
    def test_dosya_adlandiriliyor_ve_sinyal_gidiyor(self, qapp, tmp_path, monkeypatch):
        p = tmp_path / "eski.tex"
        p.write_text("icerik", encoding="utf-8")
        tree = _agac(qapp, tmp_path)
        monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("yeni.tex", True))
        sinyaller = []
        tree.file_renamed.connect(lambda a, b: sinyaller.append((a, b)))

        tree._yeniden_adlandir(str(p))

        assert (tmp_path / "yeni.tex").read_text(encoding="utf-8") == "icerik"
        assert not p.exists()
        assert sinyaller == [(str(p), str(tmp_path / "yeni.tex"))], sinyaller

    def test_ayni_ad_hicbir_sey_yapmiyor(self, qapp, tmp_path, monkeypatch):
        p = tmp_path / "a.tex"
        p.write_text("x", encoding="utf-8")
        tree = _agac(qapp, tmp_path)
        monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("a.tex", True))
        sinyaller = []
        tree.file_renamed.connect(lambda a, b: sinyaller.append((a, b)))
        tree._yeniden_adlandir(str(p))
        assert sinyaller == []

    def test_var_olanin_uzerine_yazmiyor(self, qapp, tmp_path, monkeypatch):
        a = tmp_path / "taslak.tex"
        b = tmp_path / "ana.tex"
        a.write_text("taslak", encoding="utf-8")
        b.write_text("DEGERLI", encoding="utf-8")
        tree = _agac(qapp, tmp_path)
        monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("ana.tex", True))
        uyarilar = []
        monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: uyarilar.append(a))
        sinyaller = []
        tree.file_renamed.connect(lambda x, y: sinyaller.append((x, y)))

        tree._yeniden_adlandir(str(a))

        assert uyarilar, "çarpışma sessiz geçti"
        assert b.read_text(encoding="utf-8") == "DEGERLI"
        assert sinyaller == [], "başarısız işlem sinyal yaydı"

    def test_klasor_adlandiriliyor(self, qapp, tmp_path, monkeypatch):
        d = tmp_path / "eski"
        d.mkdir()
        (d / "ic.tex").write_text("x", encoding="utf-8")
        tree = _agac(qapp, tmp_path)
        monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("yeni", True))
        tree._yeniden_adlandir(str(d))
        assert (tmp_path / "yeni" / "ic.tex").is_file()


def test_input_agaci_BUYUK_HARFLI_uzantida_da_gosteriliyor(qapp, tmp_path):
    r"""`.TEX` kök dosyada `\input` bağımlılık ağacı gizlenmemeli.

    Uzantı süzgeci harf duyarlıydı: `.TEX` dosyası açılınca panel tamamen
    gizleniyordu. Sahada gerçek dosya var (template34-tez). Aynı sınıf
    `63173f9`'da bu dosyanın 254. satırı için düzeltilmiş, burası
    atlanmıştı.
    """
    (tmp_path / "bolum1.tex").write_text("x", encoding="utf-8")
    icerik = "\\documentclass{article}\n\\input{bolum1}\n"

    gizli = {}
    for uz in (".tex", ".TEX", ".Tex"):
        tree = FileTree(theme=THEMES["dark"])
        tree.update_input_tree(str(tmp_path / ("TEZ" + uz)), icerik)
        gizli[uz] = tree._input_tree.isHidden()

    assert gizli == {".tex": False, ".TEX": False, ".Tex": False}


def test_input_agaci_TEX_OLMAYAN_dosyada_gizli_kaliyor(qapp, tmp_path):
    """Karşı durum: .bib gibi dosyalarda ağaç hâlâ gizlenmeli."""
    tree = FileTree(theme=THEMES["dark"])
    tree.update_input_tree(str(tmp_path / "refs.bib"),
                           "\\documentclass{article}\n\\input{bolum1}\n")
    assert tree._input_tree.isHidden()

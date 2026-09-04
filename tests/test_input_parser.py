"""input_parser modülü testleri."""

import os

from core.input_parser import parse_inputs, group_by_directory
from core.latex_utils import strip_comments as _strip_comments


# --- strip_comments ---


class TestStripComments:
    def test_no_comments(self):
        assert _strip_comments("hello world") == "hello world"

    def test_full_line_comment(self):
        result = _strip_comments("% yorum\nhello")
        assert result == "\nhello"

    def test_inline_comment(self):
        result = _strip_comments("kod % yorum")
        assert result == "kod "

    def test_escaped_percent(self):
        result = _strip_comments(r"\% yüzde")
        assert r"\%" in result

    def test_empty_string(self):
        assert _strip_comments("") == ""

    def test_backslash_before_percent(self):
        result = _strip_comments(r"\\% yorum")
        assert "%" not in result


# --- parse_inputs ---


class TestParseInputs:
    def test_empty_content(self):
        assert parse_inputs("", "/tmp") == []

    def test_single_input(self, tmp_path):
        chapter = tmp_path / "chapter1.tex"
        chapter.write_text("content", encoding="utf-8")
        result = parse_inputs("\\input{chapter1}", str(tmp_path))
        assert len(result) == 1
        assert result[0]["name"] == "chapter1.tex"

    def test_single_include(self, tmp_path):
        chapter = tmp_path / "chapter1.tex"
        chapter.write_text("content", encoding="utf-8")
        result = parse_inputs("\\include{chapter1}", str(tmp_path))
        assert len(result) == 1

    def test_missing_extension(self, tmp_path):
        chapter = tmp_path / "chapter1.tex"
        chapter.write_text("content", encoding="utf-8")
        result = parse_inputs("\\input{chapter1}", str(tmp_path))
        assert result[0]["name"] == "chapter1.tex"

    def test_explicit_extension(self, tmp_path):
        chapter = tmp_path / "chapter1.tex"
        chapter.write_text("content", encoding="utf-8")
        result = parse_inputs("\\input{chapter1.tex}", str(tmp_path))
        assert len(result) == 1

    def test_empty_ref_skipped(self, tmp_path):
        result = parse_inputs("\\input{}", str(tmp_path))
        assert result == []

    def test_nested_input(self, tmp_path):
        c = tmp_path / "c.tex"
        c.write_text("leaf content", encoding="utf-8")
        b = tmp_path / "b.tex"
        b.write_text("\\input{c}", encoding="utf-8")
        result = parse_inputs("\\input{b}", str(tmp_path))
        assert len(result) == 1
        assert result[0]["name"] == "b.tex"
        assert len(result[0]["children"]) == 1
        assert result[0]["children"][0]["name"] == "c.tex"

    def test_circular_reference(self, tmp_path):
        a = tmp_path / "a.tex"
        b = tmp_path / "b.tex"
        a.write_text("\\input{b}", encoding="utf-8")
        b.write_text("\\input{a}", encoding="utf-8")
        result = parse_inputs("\\input{a}", str(tmp_path))
        assert len(result) == 1
        assert result[0]["name"] == "a.tex"
        # b -> a cycle prevented
        assert len(result[0]["children"]) == 1

    def test_path_traversal_blocked(self, tmp_path):
        result = parse_inputs("\\input{../../etc/passwd}", str(tmp_path))
        assert result == []

    def test_nonexistent_file_skipped(self, tmp_path):
        result = parse_inputs("\\input{nonexistent}", str(tmp_path))
        assert result == []

    def test_multiple_inputs(self, tmp_path):
        for name in ("ch1.tex", "ch2.tex", "ch3.tex"):
            (tmp_path / name).write_text("content", encoding="utf-8")
        result = parse_inputs(
            "\\input{ch1}\n\\input{ch2}\n\\input{ch3}", str(tmp_path)
        )
        assert len(result) == 3

    def test_comment_input_ignored(self, tmp_path):
        chapter = tmp_path / "chapter1.tex"
        chapter.write_text("content", encoding="utf-8")
        result = parse_inputs("% \\input{chapter1}", str(tmp_path))
        assert result == []

    def test_space_before_brace(self, tmp_path):
        chapter = tmp_path / "chapter1.tex"
        chapter.write_text("content", encoding="utf-8")
        result = parse_inputs("\\input {chapter1}", str(tmp_path))
        assert len(result) == 1
        assert result[0]["name"] == "chapter1.tex"


# --- group_by_directory ---


class TestGroupByDirectory:
    def test_empty_list(self):
        assert group_by_directory([], "/tmp") == []

    def test_all_in_root(self, tmp_path):
        refs = [
            {"name": "a.tex", "path": str(tmp_path / "a.tex")},
            {"name": "b.tex", "path": str(tmp_path / "b.tex")},
        ]
        result = group_by_directory(refs, str(tmp_path))
        assert len(result) == 2
        assert all(not r.get("is_dir") for r in result)

    def test_subdirectory_grouped(self, tmp_path):
        sub = tmp_path / "chapters"
        refs = [
            {"name": "ch1.tex", "path": str(sub / "ch1.tex")},
        ]
        result = group_by_directory(refs, str(tmp_path))
        assert len(result) == 1
        assert result[0].get("is_dir") is True
        assert result[0]["name"] == "chapters"

    def test_mixed_root_and_subdir(self, tmp_path):
        sub = tmp_path / "chapters"
        refs = [
            {"name": "main.tex", "path": str(tmp_path / "main.tex")},
            {"name": "ch1.tex", "path": str(sub / "ch1.tex")},
        ]
        result = group_by_directory(refs, str(tmp_path))
        # root file first, then dir group
        assert len(result) == 2
        assert not result[0].get("is_dir")
        assert result[1].get("is_dir") is True

    def test_nested_children(self, tmp_path):
        sub = tmp_path / "chapters"
        refs = [
            {
                "name": "ch1.tex",
                "path": str(sub / "ch1.tex"),
                "children": [
                    {"name": "sec1.tex", "path": str(sub / "sec1.tex")},
                ],
            },
        ]
        result = group_by_directory(refs, str(tmp_path))
        assert result[0]["is_dir"] is True
        # children within the dir group
        assert len(result[0]["children"]) == 1


class TestAltDizinZinciri:
    r"""İç içe \input LaTeX gibi KÖK dizine göre çözülmeli (A2026-08-30, A4).

    Özyinelemede base_dir olarak çocuğun dizini geçiliyordu; LaTeX ise yolları
    derleme dizinine (ana dosyanın dizini) göre çözer. Alt dizinli tez/kitap
    projelerinde torun dosyalar hiç bulunamıyor, dosya ağacında görünmüyor ve
    \label'ları Referans Denetimi'ne gelmiyordu.
    """

    def test_torun_koke_gore_bulunuyor(self, tmp_path):
        (tmp_path / "bolumler").mkdir()
        (tmp_path / "main.tex").write_text(
            "\\input{bolumler/bolum1}\n", encoding="utf-8")
        # LaTeX uzlaşımı: çocuk da yolu KÖKE göre yazar
        (tmp_path / "bolumler" / "bolum1.tex").write_text(
            "\\input{bolumler/bolum2}\n", encoding="utf-8")
        (tmp_path / "bolumler" / "bolum2.tex").write_text("son\n", encoding="utf-8")

        refs = parse_inputs("\\input{bolumler/bolum1}\n", str(tmp_path))
        assert len(refs) == 1
        assert refs[0]["name"] == "bolum1.tex"
        cocuklar = refs[0].get("children") or []
        assert [c["name"] for c in cocuklar] == ["bolum2.tex"]

    def test_cocuk_goreli_yazim_geri_donuk_calisiyor(self, tmp_path):
        """Bölümü kendi dizinine göre yazan projeler de desteklenmeli."""
        (tmp_path / "bol").mkdir()
        (tmp_path / "main.tex").write_text("\\input{bol/b1}\n", encoding="utf-8")
        (tmp_path / "bol" / "b1.tex").write_text("\\input{b2}\n", encoding="utf-8")
        (tmp_path / "bol" / "b2.tex").write_text("son\n", encoding="utf-8")

        refs = parse_inputs("\\input{bol/b1}\n", str(tmp_path))
        cocuklar = refs[0].get("children") or []
        assert [c["name"] for c in cocuklar] == ["b2.tex"]

    def test_kok_disina_cikis_hala_engelleniyor(self, tmp_path):
        """Traversal koruması kökle yapılmalı; dışarısı yine yasak."""
        kok = tmp_path / "proje"
        kok.mkdir()
        (tmp_path / "gizli.tex").write_text("sir\n", encoding="utf-8")
        refs = parse_inputs("\\input{../gizli}\n", str(kok))
        assert refs == []


class TestGruplamaKokeGore:
    r"""Gruplama da KÖKE göre olmalı; yoksa ağaca ``..`` adlı klasör giriyor.

    ``parse_inputs`` yolları ana belgenin dizinine göre çözüyor (LaTeX
    uzlaşımı). ``group_by_directory`` ise çocukları üst DOSYANIN kendi
    dizinine göre grupluyordu. Alt dizindeki bir bölüm başka bir dizine
    ``\input`` edince ``relpath`` ``..`` ile başlıyor ve dosya ağacında
    ``📁 ..`` diye var olmayan bir klasör beliriyordu (file_tree.py
    ``_populate_input_tree`` her ``is_dir`` düğümünü klasör olarak çiziyor).
    """

    @staticmethod
    def _kur(kok, dosyalar):
        for ad, icerik in dosyalar.items():
            yol = kok / ad
            yol.parent.mkdir(parents=True, exist_ok=True)
            yol.write_text(icerik, encoding="utf-8")
        icerik = (kok / "main.tex").read_text(encoding="utf-8")
        return group_by_directory(parse_inputs(icerik, str(kok)), str(kok))

    @staticmethod
    def _adlar(agac):
        out = []
        for r in agac:
            out.append(r["name"])
            out += TestGruplamaKokeGore._adlar(r.get("children", []))
        return out

    def test_kardes_dizine_input_eden_bolum(self, tmp_path):
        agac = self._kur(tmp_path, {
            "main.tex": "\\input{bolumler/b1}\n",
            "bolumler/b1.tex": "\\input{ekler/ek1}\n",
            "ekler/ek1.tex": "ek\n",
        })
        # önkoşul: torun gerçekten bulunmuş olmalı, yoksa test boşa döner
        assert "ek1.tex" in self._adlar(agac), agac
        assert ".." not in self._adlar(agac), agac
        assert self._adlar(agac) == ["bolumler", "b1.tex", "ekler", "ek1.tex"]

    def test_kokteki_ortak_makroyu_input_eden_bolum(self, tmp_path):
        agac = self._kur(tmp_path, {
            "main.tex": "\\input{bolumler/b1}\n",
            "bolumler/b1.tex": "\\input{makrolar}\n",
            "makrolar.tex": "\\newcommand{\\x}{y}\n",
        })
        assert "makrolar.tex" in self._adlar(agac), agac
        assert ".." not in self._adlar(agac), agac

    def test_uc_seviye_zincir(self, tmp_path):
        agac = self._kur(tmp_path, {
            "main.tex": "\\input{bir/b}\n",
            "bir/b.tex": "\\input{iki/c}\n",
            "iki/c.tex": "\\input{uc/d}\n",
            "uc/d.tex": "son\n",
        })
        assert self._adlar(agac) == \
            ["bir", "b.tex", "iki", "c.tex", "uc", "d.tex"], agac

    def test_hicbir_dugum_kok_disina_isaret_etmiyor(self, tmp_path):
        r"""Asıl değişmez: her düğümün yolu kökün ALTINDA kalmalı.

        ``..`` düğümünün yolu ``<kök>/bolumler/..`` idi; normalize edilince
        kökün kendisi çıkıyor, yani ağaç kendi kökünü çocuk gösteriyordu.
        """
        agac = self._kur(tmp_path, {
            "main.tex": "\\input{bolumler/b1}\n",
            "bolumler/b1.tex": "\\input{ekler/ek1}\n",
            "ekler/ek1.tex": "ek\n",
        })
        kok = os.path.normpath(str(tmp_path))

        def gez(rs):
            for r in rs:
                yol = os.path.normpath(r["path"])
                assert yol != kok, "düğüm kökün kendisini gösteriyor: %r" % r
                assert yol.startswith(kok + os.sep), \
                    "düğüm kök dışına çıkıyor: %r" % r
                assert ".." not in yol.split(os.sep), \
                    "normalize edilmemiş yol: %r" % r
                gez(r.get("children", []))

        gez(agac)

    # --- karşı durumlar: eskiden doğru olan davranış aynen sürmeli

    def test_tek_seviye_alt_dizin_degismedi(self, tmp_path):
        """En yaygın şablon yapısı; depodaki 59 şablonun tamamı böyle."""
        agac = self._kur(tmp_path, {
            "main.tex": "\\input{bolumler/b1}\n\\input{bolumler/b2}\n",
            "bolumler/b1.tex": "", "bolumler/b2.tex": "",
        })
        assert self._adlar(agac) == ["bolumler", "b1.tex", "b2.tex"]

    def test_ayni_dizinde_torun_degismedi(self, tmp_path):
        agac = self._kur(tmp_path, {
            "main.tex": "\\input{bolumler/b1}\n",
            "bolumler/b1.tex": "\\input{bolumler/b2}\n",
            "bolumler/b2.tex": "",
        })
        assert self._adlar(agac) == ["bolumler", "b1.tex", "bolumler", "b2.tex"]

    def test_root_dir_ucuncu_arguman_istege_bagli(self, tmp_path):
        """İki argümanlı eski çağrı bozulmadı (file_tree ve web onu kullanıyor)."""
        refs = [{"name": "a.tex", "path": str(tmp_path / "a.tex"),
                 "children": []}]
        assert group_by_directory(refs, str(tmp_path)) == \
            group_by_directory(refs, str(tmp_path), str(tmp_path))

"""_latex_wordcount testleri — matematik içeriği kelime sayımını şişirmemeli.

tab_ops._latex_wordcount eskiden `$...$` / `$$...$$` matematik bölgelerini
temizlemiyordu (_RE_MATH_ENV tanımlıydı ama kullanılmıyordu — dead code). Sonuç:
matematik ağırlıklı belgelerde kelime sayısı şişiyordu (ör. "$x^2 + y^2$" →
3 kelime sayılıyordu).
"""

import pytest

# desktop/ path'e ekle (gui/syntax için); core pytest'in rootdir'inden gelir

try:
    from gui.mixins.tab_ops import _latex_wordcount
except ImportError:  # pragma: no cover
    pytest.skip("gui.mixins.tab_ops import edilemiyor (PyQt6/desktop gerekli)",
                allow_module_level=True)


def words(text: str) -> int:
    return _latex_wordcount(text)[0]


# --- Matematik sayılmamalı (bug teyidi) ---


def test_inline_math_excluded():
    """$...$ satır içi matematik içeriği kelime olarak sayılmamalı."""
    assert words("$x^2 + y^2$ hello") == 1


def test_display_math_excluded():
    """$$...$$ görüntü matematik sayılmamalı.

    Regression: $$ alternatifinin $...$'tan ÖNCE denenmesi gerekir, yoksa
    `$$a$$` boş satır içi math olarak yanlış eşlenir.
    """
    assert words("$$a + b$$ hello") == 1


def test_math_environment_content_excluded():
    r"""\\begin{equation}...\\end{equation} içeriği (tag'ler değil) sayılmamalı."""
    assert words("\\begin{equation}x + y\\end{equation} hello") == 1


def test_math_environment_starred_excluded():
    r"""\\begin{align*} gibi yıldızlı ortamlar da sayılmamalı."""
    assert words("\\begin{align*}a \\\\ b\\end{align*} done") == 1


def test_bracket_math_excluded():
    r"""\\[...\\] ve \\(...\\) matematik gösterimleri de sayılmamalı."""
    assert words("\\[a + b\\] metin") == 1
    assert words("\\(a + b\\) metin") == 1


def test_math_with_commands_excluded():
    r"""Math içindeki \\komutlar dahil tüm matematik bloğu sayılmamalı."""
    assert words("$\\alpha + \\beta$ metin") == 1


def test_multiline_display_math_excluded():
    """Birden çok satıra yayılan görüntü matematik sayılmamalı."""
    text = "$$\na^2 + b^2\n= c^2\n$$\nsonuc"
    assert words(text) == 1


# --- Mevcut doğru davranış korunmalı (regresyon) ---


def test_plain_text_counted():
    assert words("bir iki üç dört") == 4


def test_command_arg_counted():
    r"""Komut argümanı görünür metin olarak sayılmalı (ör. \\section başlığı)."""
    assert words("\\section{Baslik} ve yazi") == 3


def test_comment_excluded():
    """Yorumlar (% sonrası) sayılmamalı."""
    assert words("kelime % $x$ yorum") == 1


# --- Bileşik gerçekçi belge ---


def test_mixed_document():
    """Matematik + komut + düz metin karışımı gerçekçi belge."""
    text = (
        "\\section{Giris}\n"
        "Bu bir denklemdir $E = mc^2$ ve onemli.\n"
        "\\begin{equation}\n"
        "a^2 + b^2 = c^2\n"
        "\\end{equation}\n"
        "Sonuc budur.\n"
    )
    # Görünür kelimeler: Giris Bu bir denklemdir ve onemli. Sonuc budur. = 8
    assert words(text) == 8


# =====================================================================
# Sayacın sistematik olarak yanıldığı yedi durum (2026-08-30 denetimi).
# Gerçekçi bir tez belgesinde toplam sapma +%25'ti; hatalar iki yönlüydü
# (kaçış yutması eksiltiyor, ayraç/önsöz şişiriyordu) ve kısmen birbirini
# götürdüğü için fark edilmemişti.
# =====================================================================


def test_kacisli_yuzde_yorum_sanilmiyor():
    r"""`\%` yorum başlangıcı değil: satırın geri kalanı silinmemeli."""
    assert words(r"Oran \%50 artti bu yil.") == 5
    # Gerçek yorum hâlâ silinmeli: görünen "Oran %50 artti"
    assert words(r"Oran \%50 artti % bu yorum") == 3


def test_kacisli_dolar_matematik_sanilmiyor():
    r"""`\$100 ... \$200` arası matematik bölgesi sanılıp yutulmamalı."""
    assert words(r"Fiyat \$100 ile \$200 arasi") == 5
    # Gerçek matematik hâlâ elenmeli: görünen "Deger kadar"
    assert words(r"Deger $x + y$ kadar") == 2


def test_satir_sonu_kelime_degil():
    r"""`\\` satır sonu ve `\\[2mm]` kelime sayılmamalı."""
    assert words(r"birinci satir \\ ikinci satir") == 4
    assert words(r"birinci satir \\[2mm] ikinci satir") == 4


def test_tablo_ayraci_kelime_degil():
    r"""Tablo `&` ayracı kelime sayılmamalı; kaçışlı `\&` sayılmalı."""
    assert words(r"elma & armut \\ kiraz & incir") == 4
    assert words(r"Ahmet \& Mehmet geldi") == 4


def test_onsoz_sayilmiyor_baslik_sayiliyor():
    r"""Önsöz elenmeli ama \title/\author \maketitle ile basıldığı için sayılmalı."""
    text = (
        "\\documentclass[12pt]{article}\n"
        "\\usepackage[utf8]{inputenc}\n"
        "\\title{Yapay Ogrenme}\n"
        "\\author{Serkan Balli}\n"
        "\\begin{document}\n"
        "\\maketitle\n"
        "Tek satir metin\n"
        "\\end{document}\n"
    )
    # Yapay Ogrenme (2) + Serkan Balli (2) + Tek satir metin (3) = 7
    assert words(text) == 7


def test_bolum_dosyasinda_tum_metin_sayilir():
    r"""\input ile çağrılan bölümde \begin{document} yoktur: hepsi sayılır."""
    assert words("Bu bir bolum dosyasi metnidir") == 5


def test_gorunmez_komut_argumani_sayilmiyor():
    r"""\includegraphics/\usepackage argümanı kelime değil; \section başlığı kelime."""
    assert words(r"Sekil \includegraphics{resim.png} burada") == 2
    assert words(r"Sekil \includegraphics[width=0.8\textwidth]{a/b.png} burada") == 2
    assert words(r"\section{Giris Bolumu} ve yazi") == 4


def test_kod_ortami_sayilmiyor():
    """verbatim/lstlisting içeriği düzyazı değil, sayılmamalı."""
    text = ("Metin\n\\begin{verbatim}\nfor i in range(10):\n"
            "\\end{verbatim}\nSon")
    assert words(text) == 2
    text2 = ("Metin\n\\begin{lstlisting}\nx = %100\n\\end{lstlisting}\nSon")
    assert words(text2) == 2


def test_karakter_sayisi_ic_bosluklari_saymiyor():
    """chars görünür metnin karakteri olmalı: iç boşluk/satır sonu şişirmesin."""
    assert _latex_wordcount("Merhaba dunya")[1] == len("Merhaba dunya")
    # Komut silindikten sonra kalan çoklu boşluk teke iner
    assert _latex_wordcount(r"Bu \textbf{kalin} yazi")[1] == len("Bu kalin yazi")
    # Satır sonu tek boşluk sayılır
    assert _latex_wordcount("birinci\nikinci")[1] == len("birinci ikinci")


def test_gercekci_belge_tam_isabet():
    """Uçtan uca: önsöz + tablo + matematik + şekil + kaçışlar."""
    text = (
        "\\documentclass{article}\n"
        "\\usepackage{booktabs}\n"
        "\\title{Sonuclar}\n"
        "\\begin{document}\n"
        "\\maketitle\n"
        "\\section{Giris}\n"
        "Dogruluk orani \\%92 oldu.\n"
        "\\begin{tabular}{lr}\n"
        "Yontem & Skor \\\\\n"
        "Agac & 0.87 \\\\\n"
        "\\end{tabular}\n"
        "Maliyet $J(x)$ dusuktur.\n"
        "\\end{document}\n"
    )
    # Sonuclar(1) Giris(1) Dogruluk orani %92 oldu.(4)
    # Yontem Skor Agac 0.87 (4) Maliyet dusuktur.(2) = 12
    assert words(text) == 12


# --- Kod bloğu içindeki \end{document} gövdeyi kesmemeli ---
#
# Gövde `_RE_BODY` ile çıkarılıyor ve desen NON-GREEDY: ilk `\end{document}`te
# duruyor. Kod ortamları eskiden gövdeden SONRA atıldığı için, iskeleti
# verbatim içinde gösteren belgelerde gövde blok içinde kesiliyor ve blok
# sonrasındaki bütün metin sayımdan düşüyordu. ÖLÇÜLDÜ: aynı görünür metin
# 27 kelime yerine 4 sayılıyordu, %85 kayıp.
#
# LaTeX kılavuzları, sınıf/paket belgeleri ve şablonlar iskeleti tam olarak
# böyle gösteriyor; `lstlisting` ve `minted` de aynı desende.

_KOD_ICERIGI = ("\\documentclass{article}\n"
                "\\begin{document}\n"
                "merhaba\n"
                "\\end{document}\n")


def _belge(blok: str) -> str:
    return ("\\documentclass{article}\n"
            "\\begin{document}\n"
            "Giris paragrafi burada.\n"
            + blok +
            "Bundan sonra gelen metin de sayilmali.\n"
            "\\end{document}\n")


@pytest.mark.parametrize(
    "ortam", ["verbatim", "lstlisting", "minted", "Verbatim", "alltt"])
def test_kod_blogundaki_end_document_govdeyi_KESMIYOR(ortam):
    """Blok sonrasındaki metin sayıma girmeli."""
    blok = ("\\begin{%s}\n" % ortam) + _KOD_ICERIGI + ("\\end{%s}\n" % ortam)
    # Kod bloğu olmayan aynı belge: görünür metin aynı, doğru sayı bu.
    assert words(_belge(blok)) == words(_belge(""))


def test_kod_blogunun_ICERIGI_yine_sayilmiyor():
    """Düzeltme "bloğu hiç atma" yönüne kaymamalı.

    Blok artık daha erken atılıyor; atılmayıp sayılmaya başlasaydı bu test
    düşer. İçerik bilerek çok kelimeli seçildi.
    """
    blok = ("\\begin{verbatim}\n"
            "alfa beta gama delta epsilon zeta eta teta iota kappa\n"
            "\\end{verbatim}\n")
    assert words(_belge(blok)) == words(_belge(""))


def test_govdesiz_parca_dosyada_da_kod_blogu_atiliyor():
    r"""`\input` ile çağrılan bölüm dosyasında `\begin{document}` yok.

    O yolda metnin tamamı sayılıyor; kod bloğu yine elenmeli.
    """
    parca = ("Bir iki uc.\n"
             "\\begin{lstlisting}\n"
             "alfa beta gama delta\n"
             "\\end{lstlisting}\n"
             "Dort bes alti.\n")
    assert words(parca) == 6

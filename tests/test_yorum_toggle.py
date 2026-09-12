# -*- coding: utf-8 -*-
"""Yorum toggle (Ctrl+/): yorum OLMAYAN metne dokunulmamalı.

`_toggle_comment` yön kararını yalnız İLK satıra bakarak veriyor ve o kararı
bütün seçime uyguluyor. Bu doğru toggle davranışı, ama yorum kaldırırken
satırdaki ilk `%`'yi körü körüne siliyordu; yorum işareti mi kaçış mı ayırt
etmiyordu. Karışık bir seçimde belge sessizce bozuluyordu (ölçüldü):

    `Kâr oranı \\%15 arttı`  ->  `\\15`  tanımsız kontrol dizisi, DERLENMİYOR
    `x = 5 % açıklama`       ->  `x = 5  açıklama`, yorum canlı metne dönüyor

Ayrı bir kusur: seçim sonraki satırın 0. sütununda bittiğinde o satır da
kapsama giriyordu, oysa oradan hiçbir karakter seçili değil.

GERÇEK QsciScintilla kullanılıyor: metot `SendScintilla`, `setSelection` ve
`removeSelectedText` çağırıyor; taklitle sınamak sadakatsiz olurdu. Sahipsiz
editörleri conftest'teki fixture topluyor.
"""

import pytest

try:
    from PyQt6.QtWidgets import QApplication
    from gui.editor import EditorWidget
    from gui.mixins.edit_ops import EditOpsMixin
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / gui import edilemiyor", allow_module_level=True)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class _Pencere(EditOpsMixin):
    """Mixin'in tek ihtiyacı `_current_editor()`."""

    def __init__(self, ed):
        self._ed = ed

    def _current_editor(self):
        return self._ed


def _toggle(metin, secim=None, imlec=None):
    """Metni kur, seçimi/imleci ayarla, toggle'ı çalıştır, sonucu döndür."""
    ed = EditorWidget()
    ed.setText(metin)
    if secim is not None:
        ed.setSelection(*secim)
    else:
        ed.setCursorPosition(*(imlec or (0, 0)))
    _Pencere(ed)._toggle_comment()
    return ed.text()


# --- Yorum kaldırma yorum OLMAYAN satıra dokunmamalı ---


def test_yorum_acarken_YUZDE_KACISI_silinmiyor(qapp):
    """`\\%` kaçışındaki yüzde silinirse geriye tanımsız kontrol dizisi kalır.

    Yorum açarken satırdaki İLK `%` değil, GİRİNTİDEKİ `%` kaldırılmalı.
    Eskiden `text.find('%')` kullanılıyordu ve bu satırda `\\%15`in yüzdesi
    siliniyor, belge derlenemez hâle geliyordu.

    Seçim BİLEREK tekdüze (iki satır da yorumlu): yön kararı artık "boş
    olmayan satırların hepsi yorumlu mu" sorusuna bakıyor, karışık bir
    seçim bu dala hiç girmiyor.
    """
    sonuc = _toggle("% Bu bolum eski\n% Kar orani \\%15 artti.\n",
                    secim=(0, 0, 1, 22))
    assert sonuc == " Bu bolum eski\n Kar orani \\%15 artti.\n"
    assert "\\%15" in sonuc


def test_yorum_acarken_SATIR_ICI_yorum_silinmiyor(qapp):
    """Satır içi yorum işareti silinirse açıklama canlı metne dönüp derlenir."""
    sonuc = _toggle("% ust yorum\n% x = 5 % aciklama\n", secim=(0, 0, 1, 18))
    assert sonuc == " ust yorum\n x = 5 % aciklama\n"


def test_BOS_satirla_baslayan_secimde_IKINCI_BASIS_yorumu_ACIYOR(qapp):
    """Ctrl+/ toggle olmalı: ilk satır boş diye yön hep "yorumla" kalmasın.

    Yön kararı yalnız ilk satırın ham başlangıcına bakıyordu;
    `"".lstrip().startswith('%')` False olduğu için boş satırla başlayan her
    seçimde karar "yorumla" çıkıyor, ikinci basış bir `%` DAHA ekliyordu.

    ÖLÇÜLDÜ (2026-09-12, gerçek editör, 39 şablondan alınan tekdüze
    seçimler): ilk satırı boş 200 seçimin 200'ü de iki basıştan sonra `%%`
    ile kalıyordu. Paragrafın üstündeki boş satırdan sürüklemeye başlamak
    olağan bir seçim biçimi.
    """
    metin = "\n\\section{Giris}\nBir cumle.\n"
    bir = _toggle(metin, secim=(0, 0, 2, 10))
    assert bir == "\n%\\section{Giris}\n%Bir cumle.\n"
    assert _toggle(bir, secim=(0, 0, 2, 11)) == metin


def test_AYRAC_satiriyla_baslayan_secim_ikinci_basista_GERI_YORUMLANIYOR(qapp):
    """`%%%%%` ayracı yüzünden yön "aç"ta takılıp kod CANLI kalmamalı.

    Yorum açıldıktan sonra ayraç hâlâ `%` ile başlıyor. Eski kural ilk
    satıra baktığı için ikinci basış yine "aç" diyor, ayraçtan bir `%` daha
    yontuyor ve yorumdaki LaTeX satırları AÇIK kalıyordu; ölçümde bu,
    `% \\let\\oldbibitem\\bibitem` gibi satırların canlı koda dönmesi demekti
    (template33-tez).

    İkinci basıştaki ` %` kayması bilinen ve zararsız: yorum açma
    girintideki `%`yi alıyor, yorumlama girintiden sonra yazıyor; satır
    yorum olarak kalıyor.
    """
    metin = "%%%%%\n% \\let\\a\\b\n"
    bir = _toggle(metin, secim=(0, 0, 1, 10))
    assert bir == "%%%%\n \\let\\a\\b\n"
    assert _toggle(bir, secim=(0, 0, 1, 10)) == "%%%%%\n %\\let\\a\\b\n"


def test_girintili_yorum_yine_acilabiliyor(qapp):
    """Asıl yol bozulmamalı: girintiden sonraki `%` kaldırılıp girinti kalmalı.

    Düzeltme "hiçbir şeyi silme"ye kaçarsa bu test yakalar.
    """
    assert _toggle("    % girintili\n    % ikinci\n", secim=(0, 0, 1, 12)) \
        == "     girintili\n     ikinci\n"


# --- Seçim sınırı ---


def test_secim_SIFIRINCI_SUTUNDA_bitince_son_satir_kapsam_disi(qapp):
    """Aşağı sürükleyip bırakınca imleç sonraki satırın başında kalıyor.

    O satırdan hiçbir karakter seçili değil; yorumlanması kullanıcının
    ekranda görmediği bir değişiklik oluyordu.
    """
    assert _toggle("bir\niki\nuc\n", secim=(0, 0, 2, 0)) == "%bir\n%iki\nuc\n"


def test_secim_sifirinci_sutunda_BITMIYORSA_satir_kapsamda(qapp):
    """Karşı durum: düzeltme fazla iş yapıp meşru satırı düşürmemeli."""
    assert _toggle("bir\niki\nuc\n", secim=(0, 0, 2, 1)) == "%bir\n%iki\n%uc\n"


def test_TEK_SATIRLIK_secim_yorumlaniyor(qapp):
    """Seçim tek satırda başlayıp bitiyorsa o satır yorumlanmalı.

    DİKKAT, bu test `line_to > line_from` korumasını SINAMIYOR ve sınayamaz:
    boş olmayan bir seçim 0. sütunda bitiyorsa en az iki satıra yayılmış
    olmak zorundadır, yani o koşul bu daldan ulaşılamıyor (ölçüldü: koşul
    kaldırılınca hiçbir test düşmüyor). Burada sınanan, seçimli dalın
    tek satırda da doğru çalıştığı.
    """
    assert _toggle("bir\niki\nuc\n", secim=(1, 0, 1, 3)) == "bir\n%iki\nuc\n"

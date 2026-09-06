"""LaTeX yardımcı fonksiyonları: yorum temizleme, etiket anahtarı."""

import re

# Etiket anahtarında GÜVENLİ sayılan karakterler. Harf/rakamın yanında
# `_ - . :` duruyor; `fig:sonuc_grafik` LaTeX'te yaygın ve doğru bir anahtar.
_ETIKET_GUVENSIZ = re.compile(r"[^A-Za-z0-9_\-.:]+")


def strip_comments(text: str) -> str:
    """Yorum satırlarını ve satır içi yorumları kaldır.

    \\% kaçırılmış yüzde işaretlerini korur.
    Satır yapısını (girintiler dahil) korur, sadece yorum kısmını kaldırır.
    """
    result = []
    for line in text.split('\n'):
        # Hız yolu: '%' içermeyen satır değişmez (aşağıdaki döngü bu satırı
        # birebir kopyalayarak aynı sonucu verir). C-hızlı 'in' denetimi,
        # karakter-karakter Python döngüsünü yorumlu azınlık satırlara indirger.
        if '%' not in line:
            result.append(line)
            continue
        clean = []
        i = 0
        while i < len(line):
            if line[i] == '\\' and i + 1 < len(line):
                clean.append(line[i:i + 2])
                i += 2
            elif line[i] == '%':
                break
            else:
                clean.append(line[i])
                i += 1
        result.append(''.join(clean))
    return '\n'.join(result)


def label_key(text: str) -> str:
    r"""Serbest metinden kullanılabilir bir `\label` anahtarı üret.

    Dosya adından etiket türetilirken gerekiyor. İki ayrı sorun var ve
    ikisi de ÖLÇÜLDÜ (2026-09-06, pdflatex, `\label{...}` tek başına):

      %   -> "! File ended while scanning use of \label."  DERLEME KIRILIR
      #   -> "! Illegal parameter number in definition of \reserved@a."

    `_ & $ ^` ise etiket içinde sorunsuz derleniyor; anahtar TİPOGRAFİK
    metin değil, `\label` argümanını dizmiyor. O yüzden burada kaçış
    (`\_`) YANLIŞ olurdu: anahtarı değiştirir, kullanıcının `\ref` ile
    yazacağı ad tutmaz ve deponun `\label{...}` tarayıcıları (anahat,
    F2 yeniden adlandırma, referans denetimi) başka bir dize görür.

    Bu yüzden kaçırmak yerine SADELEŞTİRİLİYOR: güvenli olmayan her öbek
    tek bir `-` oluyor. `&` ve `$` derlense de elle yazılması zor bir
    anahtar üretiyorlar, onlar da sadeleşiyor.
    """
    return _ETIKET_GUVENSIZ.sub("-", text).strip("-") or "etiket"

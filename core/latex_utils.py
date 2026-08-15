"""LaTeX yardımcı fonksiyonları — yorum temizleme."""


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

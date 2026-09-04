"""minted tespiti: shell-escape gerekiyor mu, Qt'süz saf katman.

NEDEN SORULUYOR: `-shell-escape` belgeye KEYFİ KOMUT çalıştırma izni veriyor
(`\\write18`). `derle.sh` bunu minted görünce kendiliğinden açıyordu ve bu
ölçülmüş bir riskti: proje klasöründe minted geçen KULLANILMAYAN tek bir
dosya bile, ana belgedeki `\\write18`i çalıştırmaya yetiyordu (2026-09-02,
zararsız kanıtla doğrulandı). İnternetten indirilen bir şablonu açıp
derlemek yeterliydi.

Karar artık kullanıcının: uygulama ilk seferinde soruyor, cevabı proje
klasörü başına hatırlıyor ve `derle.sh`e açıkça bildiriyor.

Tespit `derle.sh:minted_kontrol` ile AYNI ölçütü kullanıyor; ayrışırsa
kullanıcıya sorulmadan bayrak açılabilir ya da minted sessizce çalışmaz.
"""

import os
import re

# derle.sh'teki desenin aynısı: paket iki yoldan yüklenebiliyor (bir .sty
# içinden \RequirePackage ile de) ve ortam doğrudan da kullanılabiliyor.
_RE_MINTED = re.compile(
    r"(usepackage|RequirePackage)[^\n]*\{minted\}|\\begin\{minted")

# derle.sh `grep -r --include` ile tarıyor; aynı uzantı kümesi.
_UZANTILAR = (".tex", ".cls", ".sty")

# ATLANAN DİZİNLER: yalnızca LaTeX KAYNAĞI BARINDIRAMAYACAK olanlar.
#
# Eskiden `project_search.SKIP_DIRS` kullanılıyordu ve orada `build` ile
# `dist` de var; oysa üretilen `.tex` oraya konabiliyor. Ayrıca 5 seviye
# derinlik ve 4 MB dosya sınırı vardı. Üçü birden bu modülün docstring'inde
# ilan edilen "derle.sh ile AYNI ölçüt" değişmezini bozuyordu. ÖLÇÜLDÜ,
# Python "minted yok" derken derle.sh buluyordu:
#
#   6 seviye derinde .tex    build/ içinde       5 MB'lik dosya
#   8 seviye derinde .tex    dist/ içinde
#
# Bunların her birinde GUI bayrak göndermiyor ve derle.sh `-shell-escape`i
# KULLANICIYA SORMADAN açıyor (derle.sh: "bayrak verilmezse eski davranış
# sürüyor") — yani özelliğin engellemek için yazıldığı senaryonun kendisi.
#
# MALİYET KABACA AYNI (ölçüldü, gerçek uygulamayla önce/sonra): gerçek
# şablonda 84 -> 96 ms, tüm şablonlarda 1018 -> 1085 ms, 19 bin dosyalık
# kökte 1094 -> 975 ms. Yani daha geniş tarama bedelsiz geliyor; sınırların
# koruduğu şey zaten `duz_dosya_mi`nin stat çağrıları kadar bile değildi.
_ATLANAN_DIZINLER = frozenset({
    ".git", ".svn", ".hg", "node_modules", "__pycache__",
    ".venv", "venv", ".env", ".mypy_cache", ".pytest_cache", ".tox",
})

# Derinlik sınırı KALDIRILDI: `os.walk` symlink izlemiyor, döngü riski yok.
# Boyut sınırı 4 MB'den 64 MB'ye çıkarıldı; bu ölçekte bir `.tex` kaynağı
# gerçekçi değil ama 4 MB gerçekçiydi (birleştirilmiş tez, üretilmiş tablo).
_MAX_DOSYA_BAYT = 64 * 1024 * 1024


def minted_kullaniliyor(kok: str) -> bool:
    """Proje klasöründe minted geçen bir kaynak dosya var mı.

    YANLIŞ "hayır" GÜVENLİK AÇIĞIDIR: çağıran o durumda derle.sh'e hiçbir
    bayrak göndermiyor ve derle.sh kendi (sınırsız) taramasıyla minted'i
    bulup `-shell-escape`i sormadan açıyor. Bu yüzden tarama derle.sh'ten
    DAR olmamalı; bkz. _ATLANAN_DIZINLER.
    """
    from core.project_search import duz_dosya_mi

    if not kok or not os.path.isdir(kok):
        return False
    for dizin, altlar, dosyalar in os.walk(kok):
        # NOKTA DİZİNLERİ DE TARANIYOR. `.git`, `.venv` gibi gerçekten büyük
        # olanlar zaten ADLA eleniyor; geriye kalan nokta dizinleri
        # kullanıcının kendi klasörleri ve minted taşıyabilirler (derle.sh'in
        # grep'i de onları tarıyor). ÖLÇÜLDÜ, gerçek bir .git deposu olan
        # gerçek bir şablonda fark 7.6 -> 8.1 ms, yani yok sayılır.
        altlar[:] = [a for a in altlar if a not in _ATLANAN_DIZINLER]
        for ad in dosyalar:
            if not ad.lower().endswith(_UZANTILAR):
                continue
            yol = os.path.join(dizin, ad)
            # FIFO'yu okumak sonsuza dek bloklardi ve derleme karari orada
            # asilirdi (bkz. project_search.duz_dosya_mi).
            if not duz_dosya_mi(yol):
                continue
            try:
                if os.path.getsize(yol) > _MAX_DOSYA_BAYT:
                    continue
                with open(yol, "rb") as f:
                    ham = f.read()
            except OSError:
                continue
            # Kodlamayı çözmeye gerek yok: aranan desen saf ASCII ve
            # cp1254/utf-8 farkı bu baytları değiştirmiyor.
            if _RE_MINTED.search(ham.decode("latin-1", "replace")):
                return True
    return False

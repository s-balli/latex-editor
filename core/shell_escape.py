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

# Taramanın sınırları: derleme öncesi her seferinde koşuyor, arayüzü
# bekletmemeli. project_search'ün SKIP_DIRS'i tek kaynaktan geliyor.
_MAX_DOSYA_BAYT = 4 * 1024 * 1024
_MAX_DERINLIK = 5


def minted_kullaniliyor(kok: str) -> bool:
    """Proje klasöründe minted geçen bir kaynak dosya var mı."""
    from core.project_search import SKIP_DIRS

    if not kok or not os.path.isdir(kok):
        return False
    for dizin, altlar, dosyalar in os.walk(kok):
        altlar[:] = [a for a in altlar
                     if a not in SKIP_DIRS and not a.startswith(".")]
        if dizin[len(kok):].count(os.sep) >= _MAX_DERINLIK:
            altlar[:] = []
        for ad in dosyalar:
            if not ad.lower().endswith(_UZANTILAR):
                continue
            yol = os.path.join(dizin, ad)
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

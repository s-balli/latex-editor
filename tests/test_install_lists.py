"""Kurulum listesi tutarlılık testi.

TeX Live kurulum komutu dört yüzeyde elle yaşar: README (TR/EN),
yayın notu şablonu (scripts/release_notes.sh) ve landing page
(docs/index.html). v1.0.12'de
python3-pygments README'lere eklenmiş ama diğer kopyalar sürüklenmişti;
release sayfası eski listeyle yayınlandı. Bu test sapmayı CI'da yakalar:
'tam kurulum' bloklarının (texlive-latex-extra içerenler; minimum kurulum
bilinçli olarak eksiktir) standart paket kümesinin tamamını taşıdığını
her yüzeyde doğrular.
"""

import os
import re

import pytest

_ROOT = os.path.join(os.path.dirname(__file__), "..")

# Standart tam kurulum paketleri. Bu küme testin doğruluk kaynağıdır: listeye
# yeni paket eklenirse önce buraya, sonra dört yüzeye eklenir; biri unutulursa
# test kırmızı olur. (libxcb-cursor0 bilinçli olarak yok: Linux'a özgü ek.)
FULL_PKGS = {
    "texlive-base", "texlive-binaries", "texlive-latex-base",
    "texlive-latex-extra", "texlive-latex-recommended",
    "texlive-lang-european", "texlive-luatex", "texlive-xetex",
    "texlive-fonts-extra", "texlive-science", "texlive-bibtex-extra",
    "texlive-font-utils", "texlive-extra-utils", "biber",
    "texlive-publishers", "texlive-humanities", "texlive-pstricks",
    "python3-pygments", "pandoc",
}

# Satır sonu '\\' devamı: README/HTML'de '\', release.yml echo'sunda '\\"'
_CONT = re.compile(r'\\\s*"?\s*$')

_SURFACES = {
    "README.tr.md": "README.tr.md",
    "README.md": "README.md",
    # release.yml'in gömülü ~100 satırlık notu scripts/release_notes.sh'e
    # taşındı (iki job'da kopyaydı). Yüzey artık o betik.
    "release_notes.sh": os.path.join("scripts", "release_notes.sh"),
    "landing page": os.path.join("docs", "index.html"),
}


def _install_commands(text: str) -> list[set[str]]:
    """Metindeki tüm 'sudo apt-get install ...' komutlarını paket kümesi olarak
    döndürür. Satır-sonu '\\' devam satırları (README/HTML'de '\', yml echo
    satırlarında '\\' + tırnak) birleştirilir."""
    lines = text.splitlines()
    cmds = []
    i = 0
    while i < len(lines):
        if "sudo apt-get install" not in lines[i]:
            i += 1
            continue
        parts = [lines[i]]
        while _CONT.search(parts[-1]) and i + 1 < len(lines):
            i += 1
            parts.append(lines[i])
        joined = " ".join(
            p.rstrip().rstrip("\\").strip().strip('"').strip() for p in parts)
        # HTML yüzeyinde son paket etikete yapışır ('pandoc</code></pre>...')
        toks = {t.strip("`'\"").split("<")[0] for t in joined.split()}
        toks -= {"sudo", "apt-get", "install", "&&", "update", ""}
        cmds.append(toks)
        i += 1
    return cmds


@pytest.mark.parametrize("name", sorted(_SURFACES))
def test_tam_kurulum_listesi_tutarli(name):
    path = os.path.join(_ROOT, _SURFACES[name])
    with open(path, encoding="utf-8") as f:
        cmds = _install_commands(f.read())

    # 'tam kurulum' bloğu: texlive-latex-extra içerir (minimum kurulum
    # bilinçli olarak kısa; tablo satırları install komutu değildir)
    full = [c for c in cmds if "texlive-latex-extra" in c]
    assert full, f"{name}: tam kurulum bloğu hiç ayıklanamadı (parser bozulmuş olabilir)"

    for c in full:
        missing = FULL_PKGS - c
        assert not missing, (
            f"{name}: tam kurulum listesinde eksik paketler: {sorted(missing)} "
            "(README/landing/yayın notu kopyalarından biri sürüklendi; dört "
            "yüzeyi de güncelle)"
        )


def test_ayiklayici_devam_satirlarini_birlestirir():
    """Parser güvenliği: çok satırlı komut tek küme olarak gelmeli."""
    text = ("sudo apt-get install a-pkg b-pkg \\\n"
            "  c-pkg d-pkg\n"
            "sudo apt-get install x-pkg\n")
    cmds = _install_commands(text)
    assert cmds[0] == {"a-pkg", "b-pkg", "c-pkg", "d-pkg"}
    assert cmds[1] == {"x-pkg"}

#!/bin/bash
# SYNCTEX SYMLINK SUPHESI: /var mi /private/var mi.
#
# `synctex` CLI hem `-d` ile hem onsuz sorunsuz calisti, yani kusur
# CLI'de degil. Kalan fark testin kostugu YER: macOS'ta
# `tempfile.mkdtemp()` `/var/folders/...` veriyor ve `/var` aslinda
# `/private/var`a sembolik bag.
#
# Derleyici belgeyi bir yol bicimiyle gorur, `synctex view -i` oteki
# bicimle sorarsa ad eslesmez ve sonuc BOS doner. Iki kol karsilastiriliyor.
#
# Ayri dosyada, cunku YAML blogu icine ters bolu iceren LaTeX gomunce
# icerik bozuluyor (bu oturumda birkac kez yasandi).
set -euo pipefail

KOK="$(cd "$(dirname "$0")/../.." && pwd)"
d="$(mktemp -d)"
gercek="$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$d")"

echo "mktemp -d  : $d"
echo "realpath   : $gercek"
if [ "$d" = "$gercek" ]; then
    echo "NOT: iki yol AYNI, symlink suphesi bu kosucuda gecerli degil"
fi

cat > "$d/s.tex" <<'TEX'
\documentclass{article}
\begin{document}
birinci satir

ikinci satir
\end{document}
TEX

/bin/bash "$KOK/core/derle.sh" "$d/s.tex" > /dev/null 2>&1 || true
ls "$d" | sed 's/^/   uretilen: /'

say() {
    # $1 baslik, $2 dizin
    local n
    n="$(synctex view -i "5:1:$2/s.tex" -o "$2/s.pdf" 2>&1 | grep -c '^Page:' || true)"
    printf '%-38s Page satiri: %s\n' "$1" "$n"
}

say "KOL A: yol OLDUGU GIBI (/var/...)" "$d"
say "KOL B: realpath ile (/private/var/...)" "$gercek"

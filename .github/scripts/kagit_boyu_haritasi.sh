#!/bin/bash
# OLCUM: kagit boyunu belge mi belirliyor, dagitim mi.
#
# NEDEN. Ayni kaynak macOS'ta US Letter, Linux'ta A4 cikti (olculdu
# 2026-09-19, ayni motor pdflatex). Debian/Ubuntu TeX Live'i A4'e,
# MacTeX/BasicTeX ise US Letter'a ayarli. Soru, belgenin KENDI beyaninin
# bunu ezip ezmedigi; cevap yazim bicimine gore degisiyor.
#
# Bes belge, artan guclulukte:
#   1  secenek yok, geometry yok
#   2  [a4paper], geometry YOK
#   3  [a4paper] + \usepackage{geometry} + yalniz kenar bosluklari
#      (template36-ders'in bicimi: gercek bir ders notu boyle yaziyor)
#   4  [letterpaper] + geometry, yalniz kenar bosluklari
#   5  \usepackage[a4paper]{geometry}
#
# Cikti her platformda ayni betikten alinip karsilastirilabilsin diye
# yalin: dosya adi ve olculen kagit.
set -uo pipefail
KOK="$(cd "$(dirname "$0")/../.." && pwd)"
D="${1:-$(mktemp -d)}"
mkdir -p "$D"
# `:-` yerine `-`: BOS ikinci arguman "varsayilan motor" (lualatex) demek,
# `:-` onu da ezip pdflatex yapiyordu ve iki kol ayni sonucu yaziyordu.
MOTOR="${2--pdflatex}"

yaz() {
    local ad="$1" sinif="$2" geo="$3"
    {
        echo "\\documentclass[$sinif]{article}"
        [ -n "$geo" ] && echo "$geo"
        echo '\begin{document}'
        echo 'Kagit boyu olcumu.'
        echo '\end{document}'
    } > "$D/$ad.tex"
}

yaz k1 "11pt" ""
yaz k2 "a4paper,11pt" ""
yaz k3 "a4paper,11pt" '\usepackage{geometry}
\geometry{top=2.0cm, bottom=2.0cm, left=2.5cm, right=2.5cm}'
yaz k4 "letterpaper,11pt" '\usepackage{geometry}
\geometry{top=2.0cm, bottom=2.0cm, left=2.5cm, right=2.5cm}'
yaz k5 "11pt" '\usepackage[a4paper]{geometry}'

echo "platform: $(uname -s)   motor: $MOTOR"
for ad in k1 k2 k3 k4 k5; do
    bash "$KOK/core/derle.sh" "$D/$ad.tex" $MOTOR > /dev/null 2>&1
done

PY="$(command -v python3 || command -v python)"
for ad in k1 k2 k3 k4 k5; do
    if [ -f "$D/$ad.pdf" ]; then
        "$PY" "$KOK/.github/scripts/kagit_boyu_yaz.py" "$D/$ad.pdf" "$ad"
    else
        echo "  $ad: PDF URETILMEDI"
    fi
done

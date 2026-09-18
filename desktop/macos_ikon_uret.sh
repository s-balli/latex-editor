#!/bin/bash
# macOS paket ikonu (.icns) uretir.
#
# IKON DEPODA IKILI OLARAK DURMUYOR, kaynak PNG'den uretiliyor. Gerekce
# bu depoda pahaliya ogrenilmis olan sinif: ayni bilgi iki yerde durunca
# ayrisiyor ve ayrisma sessiz kaliyor. `.icns` ayri bir ikili olsaydi
# `latex-editor.png` degisince onunla birlikte degismesi hicbir seyin
# guvencesinde olmazdi.
#
# `sips` ve `iconutil` macOS ile birlikte geliyor, ayrica kurulum yok.
#
# Kullanim: bash desktop/macos_ikon_uret.sh [cikti.icns]
set -euo pipefail

KOK="$(cd "$(dirname "$0")" && pwd)"
KAYNAK="$KOK/linux/latex-editor.png"
CIKTI="${1:-$KOK/linux/latex-editor.icns}"

if [ "$(uname -s)" != "Darwin" ]; then
    echo "[hata] bu betik macOS'ta kosar (sips/iconutil gerekiyor)" >&2
    exit 1
fi
if [ ! -f "$KAYNAK" ]; then
    echo "[hata] kaynak ikon yok: $KAYNAK" >&2
    exit 1
fi

GECICI="$(mktemp -d)/latex-editor.iconset"
mkdir -p "$GECICI"
trap 'rm -rf "$(dirname "$GECICI")"' EXIT

# Kaynak 256x256. 512 uretmek 2x buyutme demek; macOS'un kendi
# olceklemesinden daha iyi sonuc veriyor ve iconutil 512'yi istiyor.
# 1024 UREITLMIYOR: 4x buyutme bulanik cikiyor, macOS 512'den olcekliyor.
for boy in 16 32 64 128 256 512; do
    sips -z "$boy" "$boy" "$KAYNAK" \
        --out "$GECICI/icon_${boy}x${boy}.png" >/dev/null
done
# @2x adlari: iconutil kucuk boylarin retina karsiligini boyle ariyor.
cp "$GECICI/icon_32x32.png"   "$GECICI/icon_16x16@2x.png"
cp "$GECICI/icon_64x64.png"   "$GECICI/icon_32x32@2x.png"
cp "$GECICI/icon_256x256.png" "$GECICI/icon_128x128@2x.png"
cp "$GECICI/icon_512x512.png" "$GECICI/icon_256x256@2x.png"
rm -f "$GECICI/icon_64x64.png"

iconutil -c icns "$GECICI" -o "$CIKTI"
echo "[tamam] $CIKTI ($(du -h "$CIKTI" | cut -f1))"

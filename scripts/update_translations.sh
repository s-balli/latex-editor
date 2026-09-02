#!/bin/bash
# Çeviri dosyalarını güncelle ve derle
# Kullanım: bash scripts/update_translations.sh
# Yeni dil eklemek için LANGS değişkenini düzenle

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

# pylupdate6 — venv'den veya sistemden bul
PYLUPDATE6=$(find . -name pylupdate6 -path "*/bin/*" 2>/dev/null | head -1)
if [ -z "$PYLUPDATE6" ]; then
    PYLUPDATE6=$(which pylupdate6 2>/dev/null)
fi
if [ -z "$PYLUPDATE6" ]; then
    echo "HATA: pylupdate6 bulunamadı. PyQt6 kurulu mu?"
    exit 1
fi

# Diller — yeni dil eklemek için buraya ekle
LANGS="tr en"

TS_DIR="desktop/translations"
mkdir -p "$TS_DIR"

# pylupdate6 lambda ile _() çağrılarını göremez; geçici kopyalarda
# _() → QCoreApplication.translate() dönüşümü yapılır.
#
# Bu iş eskiden tek satırlık bir regex'le yapılıyordu ve ÇOK SATIRLI _()
# çağrılarını (örtük dizge birleştirme) hiç görmüyordu: o dizgeler katalogdan
# type="vanished" olarak düşüyor, uygulama İngilizceye alınsa bile Türkçe
# kalıyorlardı. CI yalnız "unfinished" saydığı için sessizce kaçıyordu.
# Dönüşüm artık AST tabanlı: scripts/extract_tr.py (gerekçesi orada).
TMPDIR=$(mktemp -d)
trap "rm -rf $TMPDIR" EXIT

echo "=== Kaynak dosyalar hazırlanıyor ==="
for src in $(find desktop/gui desktop/gui/mixins desktop/gui/pdf_viewer_mixins -name "*.py" -not -path "*__pycache__*") desktop/main.py; do
    tmp="$TMPDIR/$src"
    mkdir -p "$(dirname "$tmp")"
    python3 "$SCRIPT_DIR/extract_tr.py" "$src" "$tmp"
done

echo "=== Çeviri dosyaları güncelleniyor ==="
echo "Diller: $LANGS"
echo ""

SRC_FILES=$(find "$TMPDIR/desktop/gui" "$TMPDIR/desktop/gui/mixins" "$TMPDIR/desktop/gui/pdf_viewer_mixins" -name "*.py" -not -path "*__pycache__*" 2>/dev/null)
SRC_FILES="$SRC_FILES $TMPDIR/desktop/main.py"

for lang in $LANGS; do
    TS_FILE="$TS_DIR/latexeditor_${lang}.ts"
    echo "  $lang → $TS_FILE"
    "$PYLUPDATE6" $SRC_FILES --ts "$TS_FILE"
done

echo ""

# Türkçe kaynak dil: unfinished çevirileri kaynak metinle doldur
TR_TS="$TS_DIR/latexeditor_tr.ts"
if [ -f "$TR_TS" ]; then
    echo "=== Türkçe kaynak çevirileri dolduruluyor ==="
    TR_TS_PATH="$TR_TS" python3 -c "
import re, os
ts_file = os.environ['TR_TS_PATH']
with open(ts_file, 'r', encoding='utf-8') as f:
    content = f.read()
def repl(m):
    src = m.group(1)
    return '<source>' + src + '</source>\n        <translation>' + src + '</translation>'
content = re.sub(r'<source>([^<]*)</source>\n\s*<translation type=\"unfinished\" />', repl, content)
content = re.sub(r'<source>([^<]*)</source>\n\s*<translation type=\"unfinished\">[^<]*</translation>', repl, content)
with open(ts_file, 'w', encoding='utf-8') as f:
    f.write(content)
"
    echo "  Tamamlandı"
    echo ""
fi

# .qm dosyalarını derle
# lrelease dağıtımlarda PATH'e konmuyor (Debian/Ubuntu /usr/lib/qt6/bin).
# Sadece `command -v` bakılınca .qm derlemesi SESSİZCE atlanıyor ve git'te
# izlenen .qm dosyaları .ts'lerin gerisinde kalıyordu: uygulama İngilizceye
# alınsa bile yeni dizgeler Türkçe görünüyor.
# `|| true`: set -e açık; lrelease yoksa atamanın kendisi hata döner
# ve betik burada sessizce ölürdü.
LRELEASE=$(command -v lrelease 2>/dev/null || true)
for cand in /usr/lib/qt6/bin/lrelease /usr/lib/x86_64-linux-gnu/qt6/bin/lrelease; do
    [ -n "$LRELEASE" ] && break
    [ -x "$cand" ] && LRELEASE="$cand"
done
if [ -n "$LRELEASE" ]; then
    echo "=== .qm dosyaları derleniyor ==="
    for lang in $LANGS; do
        TS_FILE="$TS_DIR/latexeditor_${lang}.ts"
        if [ -f "$TS_FILE" ]; then
            echo "  $lang → ${TS_FILE%.ts}.qm"
            "$LRELEASE" "$TS_FILE" 2>/dev/null
        fi
    done
else
    echo "UYARI: lrelease bulunamadı. .qm dosyaları derlenmedi."
    echo "  sudo apt install qt6-l10n-tools"
fi

echo ""
echo "Tamamlandı. Çevirileri düzenlemek için:"
echo "  - .ts dosyalarını herhangi bir metin düzenleyicide açın (XML formatı)"
echo "  - Veya Qt Linguist kullanın"

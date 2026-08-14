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

# pylupdate6 lambda ile _() çağrılarını göremez.
# Geçici dosyalarda _() → QCoreApplication.translate() dönüştürmesi yap
TMPDIR=$(mktemp -d)
trap "rm -rf $TMPDIR" EXIT

echo "=== Kaynak dosyalar hazırlanıyor ==="
for src in $(find desktop/gui desktop/gui/mixins desktop/gui/pdf_viewer_mixins -name "*.py" -not -path "*__pycache__*") desktop/main.py; do
    tmp="$TMPDIR/$src"
    mkdir -p "$(dirname "$tmp")"
    # _ = lambda s: QCoreApplication.translate("Ctx", s) → bağlamı çıkar
    # _("text") → QCoreApplication.translate("Ctx", "text") dönüştür
    ctx=$(grep '_ = lambda s: QCoreApplication.translate(' "$src" 2>/dev/null | head -1 | sed 's/.*translate("//;s/".*//')
    if [ -n "$ctx" ]; then
        # _("[text]") → QCoreApplication.translate("Ctx", "[text]")
        # _('[text]') → QCoreApplication.translate('Ctx', '[text]')
        # Bağlam tırnakları argüman tırnaklarıyla eşleşir: f-string içindeki
        # _('...') çağrısına çift tırnaklı bağlam koymak geçici dosyada
        # sözdizimi bozuyor (pylupdate6 "Invalid syntax" veriyordu).
        python3 - "$src" "$tmp" "$ctx" <<'PYEOF'
import re
import sys

src_path, dst_path, ctx = sys.argv[1], sys.argv[2], sys.argv[3]
text = open(src_path, encoding="utf-8").read()
text = re.sub(r'_\("((?:[^"\\]|\\.)*)"\)',
              lambda m: f'QCoreApplication.translate("{ctx}", "{m.group(1)}")', text)
text = re.sub(r"_\('((?:[^'\\]|\\.)*)'\)",
              lambda m: f"QCoreApplication.translate('{ctx}', '{m.group(1)}')", text)
open(dst_path, "w", encoding="utf-8").write(text)
PYEOF
    else
        cp "$src" "$tmp"
    fi
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
if command -v lrelease &>/dev/null; then
    echo "=== .qm dosyaları derleniyor ==="
    for lang in $LANGS; do
        TS_FILE="$TS_DIR/latexeditor_${lang}.ts"
        if [ -f "$TS_FILE" ]; then
            echo "  $lang → ${TS_FILE%.ts}.qm"
            lrelease "$TS_FILE" 2>/dev/null
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

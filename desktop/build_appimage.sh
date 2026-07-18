#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Versiyonu çek
VER=$(grep 'VERSION' ../core/version.py | cut -d'"' -f2)
APP_NAME="latex-editor-${VER}"
APPDIR="dist/${APP_NAME}.AppDir"

echo "=== LaTeX Editor v${VER} — AppImage Build ==="
echo ""

# Virtual environment
VENV_DIR=".venv-build"
if [ ! -d "$VENV_DIR" ]; then
    echo "Virtual environment oluşturuluyor..."
    python3 -m venv "$VENV_DIR"
fi
source "$VENV_DIR/bin/activate"

# Bağımlılıkları kur
echo "Bağımlılıklar kontrol ediliyor..."
pip install -q -r requirements.txt -r requirements-build.txt

# 1. PyInstaller ile derle (onedir mod)
echo "[1/5] PyInstaller derlemesi..."
python -m PyInstaller latex-editor-linux.spec --clean --noconfirm

if [ ! -d "dist/latex-editor" ]; then
    echo "HATA: PyInstaller derlemesi başarısız!"
    exit 1
fi

# derle.sh — PyInstaller'ın toplamadığı veri dosyası
mkdir -p dist/latex-editor/_internal/core
cp ../core/derle.sh dist/latex-editor/_internal/core/derle.sh
chmod +x dist/latex-editor/_internal/core/derle.sh

# 2. AppDir yapısını oluştur
echo "[2/5] AppDir yapısı oluşturuluyor..."
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin"
mkdir -p "$APPDIR/usr/share/icons/hicolor/256x256/apps"
mkdir -p "$APPDIR/usr/share/applications"

# PyInstaller çıktısını kopyala
cp -r dist/latex-editor/* "$APPDIR/usr/bin/"

# 3. AppImage dosyalarını yerleştir
echo "[3/5] Desktop dosyası ve ikon yerleştiriliyor..."
cp linux/AppRun "$APPDIR/AppRun"
chmod +x "$APPDIR/AppRun"

cp linux/latex-editor.desktop "$APPDIR/latex-editor.desktop"
cp linux/latex-editor.desktop "$APPDIR/usr/share/applications/latex-editor.desktop"

# İkon: SVG -> PNG (inkscape ile, metin sigmasi icin genis viewBox)
if command -v inkscape &>/dev/null; then
    ICON_SVG="linux/latex-editor.svg"
    ICON_PNG="linux/latex-editor.png"
    TMP_SVG=$(mktemp /tmp/icon_XXXXXX.svg)
    sed 's/viewBox="0 0 256 256"/viewBox="-32 0 320 256"/' "$ICON_SVG" > "$TMP_SVG"
    inkscape -w 640 -h 512 "$TMP_SVG" -o /tmp/icon_render.png 2>/dev/null
    python3 -c "
from PIL import Image
img = Image.open('/tmp/icon_render.png')
left = (img.width - img.height) // 2
square = img.crop((left, 0, left + img.height, img.height)).resize((256, 256), Image.LANCZOS)
square.save('$ICON_PNG')
"
    rm -f "$TMP_SVG" /tmp/icon_render.png
    echo "  İkon SVG->PNG dönüştürüldü"
fi
cp linux/latex-editor.png "$APPDIR/.DirIcon"
cp linux/latex-editor.png "$APPDIR/latex-editor.png"
cp linux/latex-editor.png "$APPDIR/usr/share/icons/hicolor/256x256/apps/latex-editor.png"

# Çeviri dosyaları
if [ -d "translations" ]; then
    cp -r translations "$APPDIR/usr/bin/translations/"
    echo "  Çeviri dosyaları kopyalandı"
fi

# 4. appimagetool ile sar
echo "[4/5] AppImage oluşturuluyor..."
ARCH=$(uname -m)
APPIMAGETOOL_EXTRACTED="appimagetool_extracted"

# appimagetool'u edin (FUSE gerektirmez)
TOOL_FILE=""
if [ -d "$APPIMAGETOOL_EXTRACTED" ]; then
    echo "  appimagetool (önceden çıkarılmış) kullanılıyor..."
else
    if [ ! -f "./appimagetool" ] && [ ! -f "./appimagetool-${ARCH}.AppImage" ]; then
        echo "  appimagetool indiriliyor..."
        wget -q "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-${ARCH}.AppImage" -O appimagetool
    fi
    TOOL_FILE=$(ls "$SCRIPT_DIR"/appimagetool* 2>/dev/null | head -1)
    chmod +x "$TOOL_FILE"
    echo "  appimagetool çıkarılıyor (FUSE gerektirmez)..."
    cd "$SCRIPT_DIR"
    "$(realpath "$TOOL_FILE")" --appimage-extract
    mv "$SCRIPT_DIR/squashfs-root" "$SCRIPT_DIR/$APPIMAGETOOL_EXTRACTED"
fi

APPIMAGETOOL_BIN="${APPIMAGETOOL_EXTRACTED}/AppRun"
# -u: AppImageUpdate için güncelleme bilgisi (gh-releases-zsync). Bu olmadan
# delta güncelleme ve AppImageHub/zsync otomatik algılama çalışmaz.
UPDATE_INFO="gh-releases-zsync|s-balli|latex-editor|latest|latex-editor-*-x86_64.AppImage.zsync"
ARCH=x86_64 "$(realpath "$APPIMAGETOOL_BIN")" -u "$UPDATE_INFO" "$APPDIR" "dist/${APP_NAME}-x86_64.AppImage"

# appimagetool kalıntılarını temizle
rm -rf "$SCRIPT_DIR/$APPIMAGETOOL_EXTRACTED"
rm -f "$SCRIPT_DIR"/appimagetool*

# 5. Sonuç
echo ""
echo "[5/5] Tamamlandı!"
if [ -f "dist/${APP_NAME}-x86_64.AppImage" ]; then
    SIZE=$(du -h "dist/${APP_NAME}-x86_64.AppImage" | cut -f1)
    echo "Başarılı! Dosya: dist/${APP_NAME}-x86_64.AppImage (${SIZE})"
    echo ""
    echo "Çalıştırmak için:"
    echo "  chmod +x dist/${APP_NAME}-x86_64.AppImage"
    echo "  ./dist/${APP_NAME}-x86_64.AppImage"
else
    echo "HATA: AppImage dosyası oluşturulamadı!"
    exit 1
fi

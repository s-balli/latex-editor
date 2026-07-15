#!/bin/bash
# LaTeX Derleme Betiği — tek seferlik + watch modu
# Kullanim:
#   bash derle-new.sh dosya.tex [--pdflatex] [--watch] [--shell-escape]
#   bash derle-new.sh *.tex [--pdflatex]
#   bash derle-new.sh /klasor/ [--pdflatex]

set -euo pipefail

# Renk kodlari
KIRMIZI='\033[0;31m'
YESIL='\033[0;32m'
SARI='\033[0;33m'
MAVI='\033[0;34m'
SIFIRLA='\033[0m'
MAVI2='\033[1;36m'

# Eksik dosya → paket eşleme tablosu
declare -A PAKET_HARITASI=(
    # texlive-humanities
    ["phonrule.sty"]="texlive-humanities"
    # texlive-publishers
    ["IEEEtran.bst"]="texlive-publishers"
    ["IEEEtran.cls"]="texlive-publishers"
    ["elsarticle.cls"]="texlive-publishers"
    ["revtex4-2.cls"]="texlive-publishers"
    ["revtex4-1.cls"]="texlive-publishers"
    ["revtex4.cls"]="texlive-publishers"
    ["emulateapj.cls"]="texlive-publishers"
    ["aastex.cls"]="texlive-publishers"
    ["aguplus.cls"]="texlive-publishers"
    ["agu2018.bst"]="texlive-publishers"
    # texlive-science
    ["algorithm.sty"]="texlive-science"
    ["algorithmic.sty"]="texlive-science"
    ["algorithm2e.sty"]="texlive-science"
    ["chemformula.sty"]="texlive-science"
    ["chemmacros.sty"]="texlive-science"
    ["siunitx.sty"]="texlive-science"
    ["units.sty"]="texlive-science"
    ["nicefrac.sty"]="texlive-science"
    ["cancel.sty"]="texlive-science"
    # texlive-pstricks
    ["pstricks.sty"]="texlive-pstricks"
    ["pst-node.sty"]="texlive-pstricks"
    ["pst-text.sty"]="texlive-pstricks"
    ["pst-3d.sty"]="texlive-pstricks"
    # texlive-fonts-extra
    ["ifsym.sty"]="texlive-fonts-extra"
    ["fontawesome.sty"]="texlive-fonts-extra"
    ["fontawesome5.sty"]="texlive-fonts-extra"
    ["dingbat.sty"]="texlive-fonts-extra"
    ["pifont.sty"]="texlive-fonts-extra"
    # texlive-bibtex-extra
    ["plainurl.bst"]="texlive-bibtex-extra"
    ["apacite.bst"]="texlive-bibtex-extra"
    ["apacite.sty"]="texlive-bibtex-extra"
    ["chicago.sty"]="texlive-bibtex-extra"
    # texlive-lang-japanese
    ["ascmac.sty"]="texlive-lang-japanese"
    ["okumacro.sty"]="texlive-lang-japanese"
    ["bxjscls.cls"]="texlive-lang-japanese"
    # python3-pygments (minted gereksinimi)
    ["minted.sty"]="texlive-latex-extra + python3-pygments + -shell-escape"
)

# Babel dil → paket eşleme tablosu
declare -A BABEL_HARITASI=(
    ["brazil"]="texlive-lang-portuguese"
    ["portuguese"]="texlive-lang-portuguese"
    ["spanish"]="texlive-lang-spanish"
    ["french"]="texlive-lang-french"
    ["german"]="texlive-lang-german"
    ["italian"]="texlive-lang-italian"
    ["dutch"]="texlive-lang-dutch"
    ["polish"]="texlive-lang-polish"
    ["czech"]="texlive-lang-czechslovak"
    ["slovak"]="texlive-lang-czechslovak"
    ["russian"]="texlive-lang-cyrillic"
    ["ukrainian"]="texlive-lang-cyrillic"
    ["greek"]="texlive-lang-greek"
    ["chinese"]="texlive-lang-chinese"
    ["korean"]="texlive-lang-korean"
    ["arabic"]="texlive-lang-arabic"
    ["finnish"]="texlive-lang-finnish"
    ["swedish"]="texlive-lang-swedish"
    ["norwegian"]="texlive-lang-norwegian"
    ["danish"]="texlive-lang-danish"
)

# Eksik paket tespiti
eksik_paket_goster() {
    local CIKTI="$1"

    # 1) Eksik .sty/.cls/.bst dosyaları
    local EKSIKLER
    EKSIKLER=$(echo "$CIKTI" | grep 'File `' | cut -d'`' -f2 | cut -d"'" -f1 | sort -u) || true
    if [ -n "$EKSIKLER" ]; then
        echo "$EKSIKLER" | while IFS= read -r dosya; do
            [ -z "$dosya" ] && continue
            local paket="${PAKET_HARITASI[$dosya]:-}"
            [ -z "$paket" ] && continue
            printf "${MAVI2}==> Eksik paket: %s \(%s\)${SIFIRLA}\n" "$paket" "$dosya"
            printf "${MAVI2}    sudo apt-get install %s${SIFIRLA}\n" "$paket"
        done
    fi

    # 2) Babel dil desteği eksik
    local DILLER
    DILLER=$(echo "$CIKTI" | grep "babel Error:" | sed -n "s/.*Unknown option '\([^']*\)'.*/\1/p; s/.*language '\([^']*\)'.*/\1/p" | sort -u) || true
    if [ -n "$DILLER" ]; then
        echo "$DILLER" | while IFS= read -r dil; do
            [ -z "$dil" ] && continue
            local paket="${BABEL_HARITASI[$dil]:-}"
            [ -z "$paket" ] && continue
            printf "${MAVI2}==> Eksik dil paketi: %s \(%s\)${SIFIRLA}\n" "$paket" "$dil"
            printf "${MAVI2}    sudo apt-get install %s${SIFIRLA}\n" "$paket"
        done
    fi
}

# Argüman kontrolü
if [ $# -lt 1 ]; then
    echo -e "${KIRMIZI}[hata] Kullanim: bash derle-new.sh dosya.tex [--pdflatex] [--watch] [--shell-escape]${SIFIRLA}"
    echo -e "${KIRMIZI}        bash derle-new.sh *.tex [--pdflatex]${SIFIRLA}"
    echo -e "${KIRMIZI}        bash derle-new.sh /klasor/ [--pdflatex]${SIFIRLA}"
    exit 1
fi

USE_PDFLATEX=false
USE_WATCH=false
FORCE_SHELL_ESCAPE=false
DOSYALAR=()

for arg in "$@"; do
    case $arg in
        --pdflatex) USE_PDFLATEX=true ;;
        --watch) USE_WATCH=true ;;
        --shell-escape) FORCE_SHELL_ESCAPE=true ;;
        *) DOSYALAR+=("$arg") ;;
    esac
done

# Watch modda sadece tek dosya
if [ "$USE_WATCH" = true ] && [ ${#DOSYALAR[@]} -gt 1 ]; then
    echo -e "${KIRMIZI}[hata] Watch modda yalnizca tek dosya verilebilir${SIFIRLA}"
    exit 1
fi

# Klasör argümanı ise .tex dosyalarını bul
GENISLETILMIS=()
for arg in "${DOSYALAR[@]}"; do
    if [ -d "$arg" ]; then
        while IFS= read -r -d '' f; do
            GENISLETILMIS+=("$f")
        done < <(find "$arg" -maxdepth 1 -name "*.tex" -type f -print0)
    else
        GENISLETILMIS+=("$arg")
    fi
done
DOSYALAR=("${GENISLETILMIS[@]}")

if [ ${#DOSYALAR[@]} -eq 0 ]; then
    echo -e "${KIRMIZI}[hata] Derlenecek .tex dosyasi bulunamadi${SIFIRLA}"
    exit 1
fi

# Watch modda dosya varlık kontrolü
if [ "$USE_WATCH" = true ] && [ ! -f "${DOSYALAR[0]}" ]; then
    echo -e "${KIRMIZI}[hata] Dosya bulunamadi: ${DOSYALAR[0]}${SIFIRLA}"
    exit 1
fi

# minted paketi kullanılıyor mu kontrol et
minted_kontrol() {
    local KLASOR="$1"
    grep -rl 'usepackage.*{minted}' "$KLASOR" --include='*.tex' --include='*.cls' --include='*.sty' 2>/dev/null | head -1 | grep -q .
}

# Tek dosya derleme fonksiyonu
derle_dosya() {
    local DOSYA_YOLU="$1"
    local KLASOR
    KLASOR=$(dirname "$(realpath "$DOSYA_YOLU")")
    local DOSYA_ADI
    DOSYA_ADI=$(basename "$DOSYA_YOLU")
    # Büyük harf uzantıyı küçült (.TEX → .tex)
    local EXT="${DOSYA_ADI##*.}"
    local ISIM="${DOSYA_ADI%.*}"
    if [ "${EXT,,}" != "tex" ]; then
        ISIM="$DOSYA_ADI"
    fi

    local MOTOR CIKTI_ISIM
    if [ "$USE_PDFLATEX" = true ]; then
        MOTOR="pdflatex"
        CIKTI_ISIM="$ISIM"
    else
        MOTOR="lualatex"
        CIKTI_ISIM="$ISIM"
    fi

    # -shell-escape: yalnızca minted tespit edildiğinde veya zorlandığında
    local SHELL_ESCAPE_FLAG=""
    if [ "$FORCE_SHELL_ESCAPE" = true ] || minted_kontrol "$KLASOR"; then
        SHELL_ESCAPE_FLAG="-shell-escape"
    fi

    # SyncTeX: PDF ↔ kaynak eşleştirme
    local SYNCTEX_FLAG="-synctex=1"

    # Arama yolları: kaynak klasör + alt klasörlerdeki .cls/.sty/.bst dizinleri
    # // kullanilmaz — \graphicspath ile çakışır
    local TEX_PATHS="$KLASOR:"
    for resfile in "$KLASOR"/*/*.cls "$KLASOR"/*/*.sty "$KLASOR"/*/*.bst "$KLASOR"/*/*/*.cls "$KLASOR"/*/*/*.sty "$KLASOR"/*/*/*.bst; do
        [ -f "$resfile" ] && TEX_PATHS+="$(dirname "$resfile"):"
    done
    export TEXINPUTS="$TEX_PATHS"
    export BSTINPUTS="$TEX_PATHS"
    export BIBINPUTS="$TEX_PATHS"

    # Geçici dizin — kaynak klasörün alt dizin yapısını oluştur (\include .aux yazımı için)
    local TMPDIR
    if [ -n "${WATCH_TMPDIR:-}" ]; then
        TMPDIR="$WATCH_TMPDIR"
    else
        TMPDIR=$(mktemp -d)
        cd "$KLASOR" && find . -mindepth 1 -type d 2>/dev/null | while read -r SUBDIR; do
            mkdir -p "$TMPDIR/$SUBDIR"
        done
    fi

    # Derleme
    if [ "$USE_WATCH" = true ]; then
        echo -e "${SARI}[derleniyor] $(date +%H:%M:%S) — $DOSYA_ADI ($MOTOR)${SIFIRLA}"
    else
        echo -e "${SARI}[derleniyor] $DOSYA_ADI ($MOTOR) ...${SIFIRLA}"
    fi

    local BASLANGIC
    if [ "$USE_WATCH" = true ]; then
        BASLANGIC=$(date +%s)
    fi

    local DERLEME_CIKTI DERLEME_HATA=0 HATA_OLDU=0
    DERLEME_CIKTI=$(cd "$KLASOR" && "$MOTOR" -interaction=nonstopmode $SHELL_ESCAPE_FLAG $SYNCTEX_FLAG -output-directory="$TMPDIR" -- "$DOSYA_ADI" 2>&1) || DERLEME_HATA=$?

    if [ $DERLEME_HATA -ne 0 ]; then
        local HATALAR
        HATALAR=$(echo "$DERLEME_CIKTI" | grep -E '^!|^\s*l\.[0-9]+' | head -40)
        if [ "$USE_WATCH" = true ]; then
            echo -e "${KIRMIZI}[hata] $(date +%H:%M:%S) — Derleme basarisiz:${SIFIRLA}"
        else
            echo -e "${KIRMIZI}[hata] $DOSYA_ADI derleme basarisiz:${SIFIRLA}"
        fi
        echo "$HATALAR" | while read -r line; do
            printf "${KIRMIZI}  %s${SIFIRLA}\n" "$line"
        done
        eksik_paket_goster "$DERLEME_CIKTI"
        cp "$TMPDIR/${ISIM}.log" "$KLASOR/" 2>/dev/null || true
        # nonstop modda PDF üretilmiş olabilir — devam et, PDF kopyalansın
        HATA_OLDU=1
    fi

    # Kaynakça — biber (biblatex) veya bibtex (geleneksel)
    if [ -f "$TMPDIR/${ISIM}.bcf" ] && command -v biber &>/dev/null; then
        local BIB_CIKTI
        BIB_CIKTI=$(cd "$TMPDIR" && biber "${ISIM}" 2>&1) || true
        local BIB_HATALAR
        BIB_HATALAR=$(echo "$BIB_CIKTI" | grep -iE "error|warn" || true)
        if [ -n "$BIB_HATALAR" ]; then
            if [ "$USE_WATCH" = true ]; then
                echo -e "${SARI}[biber] $(date +%H:%M:%S) — biber uyarilari:${SIFIRLA}"
            else
                echo -e "${SARI}[biber] $DOSYA_ADI — biber uyarilari:${SIFIRLA}"
            fi
            echo "$BIB_HATALAR" | while read -r line; do
                printf "${SARI}  %s${SIFIRLA}\n" "$line"
            done
        fi
    elif [ -f "$TMPDIR/${ISIM}.aux" ] && grep -rl '\\bibdata' "$TMPDIR/"*.aux &>/dev/null; then
        if command -v bibtex &>/dev/null; then
            local BIB_CIKTI
            BIB_CIKTI=$(cd "$TMPDIR" && bibtex "${ISIM}" 2>&1) || true
            local BIB_HATALAR
            BIB_HATALAR=$(echo "$BIB_CIKTI" | grep -i "error\|warning" || true)
            if [ -n "$BIB_HATALAR" ]; then
                if [ "$USE_WATCH" = true ]; then
                    echo -e "${SARI}[bibtex] $(date +%H:%M:%S) — bibtex uyarilari:${SIFIRLA}"
                else
                    echo -e "${SARI}[bibtex] $DOSYA_ADI — bibtex uyarilari:${SIFIRLA}"
                fi
                echo "$BIB_HATALAR" | while read -r line; do
                    printf "${SARI}  %s${SIFIRLA}\n" "$line"
                done
            fi
        fi
    fi

    # İndeks — makeindex (.idx → .ind)
    if [ -f "$TMPDIR/${ISIM}.idx" ] && command -v makeindex &>/dev/null; then
        local IDX_CIKTI
        IDX_CIKTI=$(cd "$TMPDIR" && makeindex "${ISIM}" 2>&1) || true
        local IDX_HATALAR
        IDX_HATALAR=$(echo "$IDX_CIKTI" | grep -iE "error|warn" || true)
        if [ -n "$IDX_HATALAR" ]; then
            if [ "$USE_WATCH" = true ]; then
                echo -e "${SARI}[makeindex] $(date +%H:%M:%S) — makeindex uyarilari:${SIFIRLA}"
            else
                echo -e "${SARI}[makeindex] $DOSYA_ADI — makeindex uyarilari:${SIFIRLA}"
            fi
            echo "$IDX_HATALAR" | while read -r line; do
                printf "${SARI}  %s${SIFIRLA}\n" "$line"
            done
        fi
    fi

    # İkinci derleme — sadece yardımcı dosyalar oluştuysa gerekli
    local SON_CIKTI="$DERLEME_CIKTI"
    local IKINCI_DERLEME=false
    for ext in toc bbl bcf lof lot idx glo nls; do
        if [ -f "$TMPDIR/${ISIM}.${ext}" ]; then
            IKINCI_DERLEME=true
            break
        fi
    done
    # İlk derleme çıktısında rerun gerektiren mesaj varsa
    if echo "$DERLEME_CIKTI" | grep -q "Rerun to get\|Label(s) may have changed"; then
        IKINCI_DERLEME=true
    fi

    if [ "$IKINCI_DERLEME" = true ]; then
        local IKINCI_CIKTI
        IKINCI_CIKTI=$(cd "$KLASOR" && "$MOTOR" -interaction=nonstopmode $SHELL_ESCAPE_FLAG $SYNCTEX_FLAG -output-directory="$TMPDIR" -- "$DOSYA_ADI" 2>&1) || true
        SON_CIKTI="$IKINCI_CIKTI"
        # Referanslar hala değişiyorsa üçüncü derleme
        if echo "$IKINCI_CIKTI" | grep -q "Rerun to get\|Label(s) may have changed"; then
            local UCUNCU_CIKTI
            UCUNCU_CIKTI=$(cd "$KLASOR" && "$MOTOR" -interaction=nonstopmode $SHELL_ESCAPE_FLAG $SYNCTEX_FLAG -output-directory="$TMPDIR" -- "$DOSYA_ADI" 2>&1) || true
            SON_CIKTI="$UCUNCU_CIKTI"
        fi
    fi

    # Hata var mı? (exit kodu VEYA çıktıda ^! hataları). PDF mesajından ÖNCE
    # belirlenmeli ki çelişkili "[basarili]" + "[hata]" çıktısı oluşmasın.
    local HATA_SATIRLARI
    HATA_SATIRLARI=$(echo "$SON_CIKTI" | grep -E '^!|^\s*l\.[0-9]+' || true)
    if [ "$DERLEME_HATA" -ne 0 ] || [ -n "$HATA_SATIRLARI" ]; then
        HATA_OLDU=1
    fi

    # PDF'i kaynak klasöre kopyala
    if [ -f "$TMPDIR/${ISIM}.pdf" ]; then
        mv -f "$TMPDIR/${ISIM}.pdf" "$KLASOR/${CIKTI_ISIM}.pdf" 2>/dev/null || cp -f "$TMPDIR/${ISIM}.pdf" "$KLASOR/${CIKTI_ISIM}.pdf"
        # SyncTeX eşleştirme dosyasını kaynak klasöre kopyala
        cp -f "$TMPDIR/${ISIM}.synctex.gz" "$KLASOR/${CIKTI_ISIM}.synctex.gz" 2>/dev/null || true
        if [ "$HATA_OLDU" = 1 ]; then
            # PDF üretildi (nonstopmode kurtardı) ama derleme hatalı — preview için kopyalandı
            if [ "$USE_WATCH" = true ]; then
                local BITIS
                BITIS=$(date +%s)
                local SURE=$((BITIS - BASLANGIC))
                echo -e "${SARI}[uyari] $(date +%H:%M:%S) — PDF güncellendi ama hata var (${SURE}s)${SIFIRLA}"
            else
                echo -e "${SARI}[uyari] ${CIKTI_ISIM}.pdf üretildi (kısmi) — derleme hataları var${SIFIRLA}"
            fi
        elif [ "$USE_WATCH" = true ]; then
            local BITIS
            BITIS=$(date +%s)
            local SURE=$((BITIS - BASLANGIC))
            echo -e "${YESIL}[basarili] $(date +%H:%M:%S) — PDF güncellendi (${SURE}s)${SIFIRLA}"
        else
            echo -e "${YESIL}[basarili] ${CIKTI_ISIM}.pdf → $KLASOR/${SIFIRLA}"
        fi
    else
        if [ "$USE_WATCH" = true ]; then
            echo -e "${KIRMIZI}[hata] $(date +%H:%M:%S) — PDF olusmadi${SIFIRLA}"
        else
            echo -e "${KIRMIZI}[hata] $DOSYA_ADI — PDF olusmadi${SIFIRLA}"
        fi
        local HATALAR
        HATALAR=$(echo "$DERLEME_CIKTI" | grep -E '^!|^\s*l\.[0-9]+' | head -40)
        if [ -n "$HATALAR" ]; then
            echo "$HATALAR" | while read -r line; do
                printf "${KIRMIZI}  %s${SIFIRLA}\n" "$line"
            done
        else
            echo -e "${KIRMIZI}  (hata satiri bulunamadi, son 30 satir:)${SIFIRLA}"
            echo "$DERLEME_CIKTI" | tail -30 | while read -r line; do
                printf "${KIRMIZI}  %s${SIFIRLA}\n" "$line"
            done
        fi
        eksik_paket_goster "$DERLEME_CIKTI"
        cp "$TMPDIR/${ISIM}.log" "$KLASOR/" 2>/dev/null || true
        if [ -z "${WATCH_TMPDIR:-}" ]; then rm -rf "$TMPDIR"; fi
        return 1
    fi

    # Hataları göster (HATA_SATIRLARI yukarda hesaplandı)
    if [ -n "$HATA_SATIRLARI" ]; then
        if [ "$USE_WATCH" = true ]; then
            echo -e "${KIRMIZI}[hata] $(date +%H:%M:%S) — derleme hatalari:${SIFIRLA}"
        else
            echo -e "${KIRMIZI}[hata] $DOSYA_ADI — derleme hatalari:${SIFIRLA}"
        fi
        echo "$HATA_SATIRLARI" | head -40 | while read -r line; do
            printf "${KIRMIZI}  %s${SIFIRLA}\n" "$line"
        done
        eksik_paket_goster "$SON_CIKTI"
    fi

    # Uyarıları göster
    local UYARI_SATIRLARI
    UYARI_SATIRLARI=$(echo "$SON_CIKTI" | grep "^LaTeX Warning\|^Package.*Warning\|^Overfull\|^Underfull" || true)
    local UYARI_SAYISI
    UYARI_SAYISI=$(echo "$UYARI_SATIRLARI" | grep -c . || true)
    if [ "$UYARI_SAYISI" -gt 0 ]; then
        if [ "$USE_WATCH" = true ]; then
            echo -e "${SARI}[uyari] $(date +%H:%M:%S) — $UYARI_SAYISI adet uyari${SIFIRLA}"
        else
            echo -e "${SARI}[uyari] $DOSYA_ADI — $UYARI_SAYISI adet uyari${SIFIRLA}"
        fi
        echo "$UYARI_SATIRLARI" | while read -r line; do
            printf "${SARI}  %s${SIFIRLA}\n" "$line"
        done
    fi

    # Temizlik (watch modunda kalıcı TMPDIR silinmez)
    if [ -z "${WATCH_TMPDIR:-}" ]; then rm -rf "$TMPDIR"; fi

    # Hata varsa başarısız sinyalle (PDF kopyalanmış olsa bile).
    # 95e83ba PDF üretildiğinde return 1'i kaldırmıştı; bu exit kodunu yanıltıcı
    # şekilde 0 yapıyordu (false success). PDF kopyalamayı koruyup başarısızlığı
    # burada sinyal ediyoruz — böylece derleyici/GUI/CI doğru exit kodu alıyor.
    if [ "$HATA_OLDU" = 1 ]; then
        return 1
    fi
    return 0
}

# ────────────────────────────────────────────
# Normal mod: tek seferlik derleme
# ────────────────────────────────────────────
if [ "$USE_WATCH" = false ]; then
    # Motor bilgisi
    if [ "$USE_PDFLATEX" = true ]; then
        echo -e "${MAVI}[bilgi] pdflatex modu${SIFIRLA}"
    else
        echo -e "${MAVI}[bilgi] lualatex modu${SIFIRLA}"
    fi

    BASARILI=0
    BASARISIZ=0
    TOPLAM=${#DOSYALAR[@]}

    if [ "$TOPLAM" -gt 1 ]; then
        echo -e "${MAVI}[bilgi] $TOPLAM dosya derlenecek${SIFIRLA}"
        echo ""
    fi

    for dosya in "${DOSYALAR[@]}"; do
        if [ ! -f "$dosya" ]; then
            echo -e "${KIRMIZI}[hata] Dosya bulunamadi: $dosya${SIFIRLA}"
            ((BASARISIZ++)) || true
            continue
        fi

        if derle_dosya "$dosya"; then
            ((BASARILI++)) || true
        else
            ((BASARISIZ++)) || true
        fi

        if [ "$TOPLAM" -gt 1 ]; then
            echo ""
        fi
    done

    # Özet
    if [ "$TOPLAM" -gt 1 ]; then
        echo -e "${MAVI}═══════════════════════════════════════${SIFIRLA}"
        echo -e "${MAVI} Toplam: $TOPLAM | ${YESIL}Basarili: $BASARILI${SIFIRLA} | ${KIRMIZI}Basarisiz: $BASARISIZ${SIFIRLA}"
        echo -e "${MAVI}═══════════════════════════════════════${SIFIRLA}"
    fi

    if [ "$BASARISIZ" -gt 0 ]; then
        exit 1
    fi

    exit 0
fi

# ────────────────────────────────────────────
# Watch modu: dosya değişince otomatik derle
# ────────────────────────────────────────────
DOSYA_YOLU="${DOSYALAR[0]}"
DOSYA_ADI=$(basename "$DOSYA_YOLU")
WATCH_KLASOR=$(dirname "$(realpath "$DOSYA_YOLU")")

if [ "$USE_PDFLATEX" = true ]; then
    MOTOR="pdflatex"
else
    MOTOR="lualatex"
fi

# Kalıcı geçici dizin — derlemeler arasında yeniden kullanılır
WATCH_TMPDIR=$(mktemp -d)
(cd "$WATCH_KLASOR" && find . -mindepth 1 -type d 2>/dev/null) | while read -r SUBDIR; do
    mkdir -p "$WATCH_TMPDIR/$SUBDIR"
done

echo -e "${MAVI}[izleniyor] $DOSYA_ADI — kaydetmek derlemeyi tetikler${SIFIRLA}"
echo -e "${MAVI}         Motor: $MOTOR | Ctrl+C ile durdurun${SIFIRLA}"
echo ""

# Ctrl+C ile çıkış — geçici dizini temizle
trap 'rm -rf "$WATCH_TMPDIR" 2>/dev/null; echo -e "\n${MAVI}[durduruldu] Watch mode sonlandirildi${SIFIRLA}"; exit 0' INT

# İlk derleme
derle_dosya "$DOSYA_YOLU"

# mtime takibi
SON_MOD=$(stat -c %Y "$DOSYA_YOLU" 2>/dev/null || echo "0")

while true; do
    sleep 2
    YENI_MOD=$(stat -c %Y "$DOSYA_YOLU" 2>/dev/null || echo "$SON_MOD")

    if [ "$YENI_MOD" != "$SON_MOD" ]; then
        SON_MOD="$YENI_MOD"
        echo -e "${SARI}[derleniyor] $(date +%H:%M:%S) — $DOSYA_ADI degisti${SIFIRLA}"
        derle_dosya "$DOSYA_YOLU"
    fi
done

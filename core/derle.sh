#!/bin/bash
# LaTeX Derleme Betiği — tek seferlik + watch modu
# Kullanim:
#   bash derle-new.sh dosya.tex [--pdflatex | --xelatex] [--watch] [--shell-escape]
#   bash derle-new.sh *.tex [--pdflatex]
#   bash derle-new.sh /klasor/ [--xelatex]

set -euo pipefail

# AppImage ortamı LD_LIBRARY_PATH ile gömülü (eski) kütüphanelerini sızdırır;
# sistem ikilileri (xelatex/biber/...) gömülü libstdc++'yi bulunca
# "GLIBCXX_3.4.32 not found" ile düşer. Derleme zinciri sistem araçlarıyla
# çalıştığından yol baştan temizlenir.
unset LD_LIBRARY_PATH LD_PRELOAD

# TeX günlüğü varsayılan olarak 79 sütunda SARIYOR. Açılan dosyanın adı da
# sarıyor ve ikiye bölünüyor; uygulama hangi dosyada olduğunu günlükteki
# `(dosya ... )` yığınından çıkardığı için bölünen ad yığına hiç girmiyor ve
# hata YANLIŞ DOSYAYA yazılıyor.
#
# ÖLÇÜLDÜ (2026-09-13, hatayı bilerek belli bir satıra koyup): 70 karakteri
# aşan bir yol altındaki bölüm dosyasındaki hata ana belgeye atfediliyordu,
# yani kullanıcı hataya tıklayınca ana dosyanın sağlam bir satırına
# gidiyordu. `max_print_line=1000` ile ad tek parça kalıyor ve hata kendi
# dosyasına düşüyor. latexmk de aynı değişkeni aynı gerekçeyle ayarlıyor.
export max_print_line=1000

# Hata satırı deseni. TEK KAYNAK: üç ayrı yerde kullanılıyor ve motora
# `-file-line-error` verildiği için İKİ biçim birden geçerli.
#
# `-file-line-error` olmadan TeX yalnız "! Undefined control sequence."
# yazıyor; hangi dosyada olduğu günlüğün `(dosya ... )` iç içe
# parantezlerinde duruyor ve bu betik kullanıcıya YALNIZ hata bloklarını
# bastığı için o bilgi GUI'ye HİÇ ulaşmıyordu. Sonuç: `\input` ile bölünmüş
# bir belgede her hata ANA DOSYAYA atfediliyor, kullanıcı hataya tıklayınca
# ana belgenin sağlam bir satırına gidiyordu (ölçüldü 2026-09-13, hata
# bilerek belli bir dosyanın belli bir satırına konarak: yedi kurgunun
# yedisinde de dosya ana belge çıkıyordu).
#
# `-file-line-error` ile hatanın başına "./bolum/ch1.tex:3: " geliyor, yani
# bağlamı MOTORUN KENDİSİ taşıyor ve yeniden kurmaya gerek kalmıyor.
#
# Ada BOŞLUK serbest (`./bolum/ch bir.tex:3: ...`); ayırt edici olan
# `.<uzanti>:<sayi>: ` üçlüsü. Boşluksuz yazılınca boşluklu dosya adı olan
# projelerde hata satırı hiç basılmıyordu (ölçüldü).
HATA_DESENI='^!|^[^ ].*\.[A-Za-z0-9]+:[0-9]+: '

# Uyarı satırı deseni. TEK KAYNAK ve ayrıştırıcının (core/log_parser.py)
# tanıdığı sınıflarla AYNI olmak zorunda: burada süzülen bir uyarı GUI'ye
# hiç ulaşmıyor, çünkü panelin gördüğü tek şey bu betiğin çıktısı.
#
# ÖLÇÜLDÜ (2026-09-13, her sınıf için küçük bir belge üretilip hem ham
# günlük hem bu betiğin çıktısı ayrıştırılarak): "Missing character"
# sınıfı süzgeçte YOKTU, yani ayrıştırıcının o sınıf için özel olarak
# yazdığı toplama kolu ve `error_hints`teki ipucu HİÇ görünemiyordu.
# Bu sınıf Türkçe için önemli: harf PDF'e hiç basılmıyor, derleme
# BAŞARILI bitiyor ve kullanıcı ancak okurken fark ediyor.
UYARI_DESENI='^LaTeX Warning|^Package.*Warning|^Overfull|^Underfull|^(pdfTeX|LuaTeX|XeTeX) warning|^Font .* not loadable'

# TEKRARLAYAN uyarı sınıfları: aynı satır belge boyunca onlarca, yüzlerce
# kez geçtiği için BENZERSİZLEŞTİRİLİYOR. Yukarıdaki desende olmamaları
# şart, yoksa iki koldan birden basılırlar.
#
# `Missing character:` bu koldaki ilk sınıftı: aynı karakter belge boyunca
# yüzlerce kez geçiyor (bir şablonda 8226 satır) ve hepsini listelemek
# Uyarılar sekmesini kullanılmaz yapıyordu. Her (karakter, yazı tipi)
# ikilisi bir kez bildiriliyor, hacim alfabeyle sınırlı kalıyor.
#
# ÖLÇÜLDÜ (2026-09-14, 39 şablonun 55 ana belgesi kendi motoruyla derlenip
# süzgecin ÖNÜNE gelen metinle panele ULAŞAN metin karşılaştırılarak).
# İçinde "Warning" geçen 810 satırın 568'ini ne bu süzgeç ne de
# `core/log_parser.py` tanıyordu; ikisi tek sınıfta toplanıyor:
#
#   LaTeX Font Warning: ...   199 satır, 55 belgenin 18'inde
#     Yazı tipi biçimi yoksa LaTeX sessizce BAŞKASINI koyuyor ve derleme
#     başarılı bitiyor; kullanıcı ancak PDF'e bakınca fark ediyor.
#     `^LaTeX Warning` bu satıra UYMUYOR ("LaTeX Font Warning").
#
#   warning  (pdf backend): ...   358 satır, 55 belgenin 17'sinde
#     LuaTeX kendi adını yazmıyor, o yüzden `^(pdfTeX|LuaTeX|XeTeX) warning`
#     kolu boşa düşüyordu. Aynı kusurun pdfTeX'teki karşılığı ("pdfTeX
#     warning (ext4): destination with the same identifier ...") panele
#     ULAŞIYOR. Yani çift etiket uyarısı pdflatex'te görünüyor,
#     uygulamanın VARSAYILAN motoru lualatex'te hiç görünmüyordu.
#
# Sınıf sınıf tasarlanmış belgelerle yapılan önceki ölçüm bunları
# bulamamıştı: yalnızca akla gelen sınıfları sınıyordu.
TEKRARLAYAN_UYARI='^Missing character:|^LaTeX Font Warning:|^warning +\('

# Renk kodlari
KIRMIZI='\033[0;31m'
YESIL='\033[0;32m'
SARI='\033[0;33m'
MAVI='\033[0;34m'
SIFIRLA='\033[0m'
MAVI2='\033[1;36m'

# Eksik dosya → paket eşleme tablosu
#
# DOĞRULANDI (2026-09-13, Ubuntu/TeX Live): her dosya `kpsewhich` ile
# bulunup sahibi `dpkg -S` ile soruldu. 32 denetlenebilir girdinin 5'i YANLIŞ
# pakete gönderiyordu (kullanıcı komutu çalıştırıp yine aynı hatayı alırdı):
#
#   cancel.sty      texlive-science     -> texlive-latex-extra
#   nicefrac.sty    texlive-science     -> texlive-latex-extra
#   units.sty       texlive-science     -> texlive-latex-extra
#   emulateapj.cls  texlive-publishers  -> texlive-latex-extra
#   pifont.sty      texlive-fonts-extra -> texlive-latex-base
#
# Kalan 5 girdi bu kurulumda yüklü olmadığı için denetlenemedi; paket
# ADLARININ apt'de var olduğu ayrıca doğrulandı.
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
    # texlive-latex-extra (dpkg ile doğrulandı; üçü de science sanılıyordu)
    ["units.sty"]="texlive-latex-extra"
    ["nicefrac.sty"]="texlive-latex-extra"
    ["cancel.sty"]="texlive-latex-extra"
    ["emulateapj.cls"]="texlive-latex-extra"
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
    # texlive-latex-base (pifont temel kurulumda; dpkg ile doğrulandı)
    ["pifont.sty"]="texlive-latex-base"
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
#
# DOĞRULANDI (2026-09-13, Ubuntu): beş girdi apt'de HİÇ OLMAYAN paket adları
# veriyordu, yani kullanıcı komutu çalıştırınca "Unable to locate package"
# alıyordu. Debian bu dilleri tek pakette topluyor:
#
#   danish, dutch, finnish, norwegian, swedish  ->  texlive-lang-european
#
# Tablodaki 27 paket adının tamamı `apt-cache policy` ile denetlendi;
# yalnız bu beşi yoktu.
declare -A BABEL_HARITASI=(
    ["brazil"]="texlive-lang-portuguese"
    ["portuguese"]="texlive-lang-portuguese"
    ["spanish"]="texlive-lang-spanish"
    ["french"]="texlive-lang-french"
    ["german"]="texlive-lang-german"
    ["italian"]="texlive-lang-italian"
    ["dutch"]="texlive-lang-european"
    ["polish"]="texlive-lang-polish"
    ["czech"]="texlive-lang-czechslovak"
    ["slovak"]="texlive-lang-czechslovak"
    ["russian"]="texlive-lang-cyrillic"
    ["ukrainian"]="texlive-lang-cyrillic"
    ["greek"]="texlive-lang-greek"
    ["chinese"]="texlive-lang-chinese"
    ["korean"]="texlive-lang-korean"
    ["arabic"]="texlive-lang-arabic"
    ["finnish"]="texlive-lang-european"
    ["swedish"]="texlive-lang-european"
    ["norwegian"]="texlive-lang-european"
    ["danish"]="texlive-lang-european"
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

    # 3) Pygments eksik: minted.sty kurulu ama pygmentize yok. minted'in bu
    #    durumdaki kesin hata işareti "Missing Pygments output"tur; minted.sty
    #    kendisi eksikse 1. kol yakalar (haritada python3-pygments geçiyor).
    if echo "$CIKTI" | grep -q "Missing Pygments"; then
        printf "${MAVI2}==> Eksik paket: python3-pygments \(%s\)${SIFIRLA}\n" "pygmentize"
        printf "${MAVI2}    sudo apt-get install python3-pygments${SIFIRLA}\n"
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
USE_XELATEX=false
USE_WATCH=false
FORCE_SHELL_ESCAPE=false
DENY_SHELL_ESCAPE=false
DOSYALAR=()

for arg in "$@"; do
    case $arg in
        --pdflatex) USE_PDFLATEX=true ;;
        --xelatex) USE_XELATEX=true ;;
        --watch) USE_WATCH=true ;;
        --shell-escape) FORCE_SHELL_ESCAPE=true ;;
        # Kararı ÇAĞIRAN veriyor: GUI kullanıcıya sorup burayı açıkça
        # bildiriyor. Bayrak verilmezse eski davranış (minted görülünce
        # kendiliğinden aç) sürüyor; komut satırından derleyenler
        # etkilenmesin diye.
        --no-shell-escape) DENY_SHELL_ESCAPE=true ;;
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
    # İki sinyal: (1) \usepackage{minted} / \RequirePackage{minted} ile yükleme
    # (paket bir .sty içinde RequirePackage ile yüklenebilir; webdiller.sty örneği),
    # (2) \begin{minted} ortamının doğrudan kullanımı. Eskiden yalnızca küçük harfli
    # 'usepackage' deseni aranıyordu; RequirePackage kullanan stiller kaçırılıyordu.
    grep -rlEq '(usepackage|RequirePackage).*\{minted\}|\\begin\{minted' \
        "$KLASOR" --include='*.tex' --include='*.cls' --include='*.sty' 2>/dev/null
}

# minted + -output-directory uyumsuzluğu (minted 2.x): minted vurgulanacak kodu
# \openout ile TMPDIR'e (ISIM.pyg) yazar ama pygmentize'a cwd'den okutur;
# shell-escape açılsa bile "Missing Pygments output" ile düşer. Kaynak klasörde
# kurulan geçici sembolik bağ iki tarafı aynı dosyada buluşturur. minted kod
# dosyasını geçiş içinde sildiğinden her derleme geçişinden önce yenilenir.
minted_pyg_bagla() {
    local KLASOR="$1" GECICI="$2" ISIM="$3"
    rm -f "$KLASOR/${ISIM}.pyg"
    ln -s "$GECICI/${ISIM}.pyg" "$KLASOR/${ISIM}.pyg" 2>/dev/null || true
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
    elif [ "$USE_XELATEX" = true ]; then
        MOTOR="xelatex"
    else
        MOTOR="lualatex"
    fi
    CIKTI_ISIM="$ISIM"

    # Motor kurulu mu? — biber/bibtex deseninde öneriyle bildir (GUI Öneriler
    # sekmesi bu çıktıyı parse eder).
    # Paket adları: motor KOMUTUNU (sembolik bağı) hangi paket getiriyorsa o.
    #
    # DOĞRULANDI (2026-09-13, `dpkg -S /usr/bin/<motor>`):
    #   /usr/bin/pdflatex  -> texlive-latex-base
    #   /usr/bin/lualatex  -> texlive-latex-base
    #   /usr/bin/xelatex   -> texlive-xetex
    #
    # `lualatex` için `texlive-luatex` YAZIYORDU ve yanlıştı: o paketin
    # içinde `lualatex` diye bir komut yok (`dpkg -L`: checkcites,
    # luaotfload-tool, optex, texfindpkg) ve `texlive-latex-base`e de
    # bağımlı değil. Yani TeX'siz bir makinede önerilen komut çalıştıktan
    # sonra `lualatex` yine bulunamıyordu.
    #
    # Aynı eşlem `core/env_check.py`deki APT_HINTS'te de duruyor; ikisinin
    # ayrışmadığını `tests/test_motor_paketi.py` sabitliyor.
    local MOTOR_PAKET
    case "$MOTOR" in
        lualatex) MOTOR_PAKET="texlive-latex-base" ;;
        pdflatex) MOTOR_PAKET="texlive-latex-base" ;;
        xelatex)  MOTOR_PAKET="texlive-xetex" ;;
    esac
    if ! command -v "$MOTOR" &>/dev/null; then
        echo -e "${KIRMIZI}[hata] $MOTOR kurulu değil — derlenemedi${SIFIRLA}"
        printf "${MAVI2}==> Eksik paket: %s (%s)${SIFIRLA}\n" "$MOTOR_PAKET" "$MOTOR"
        printf "${MAVI2}    sudo apt-get install %s${SIFIRLA}\n" "$MOTOR_PAKET"
        return 1
    fi

    # -shell-escape: yalnızca minted tespit edildiğinde veya zorlandığında
    local SHELL_ESCAPE_FLAG=""
    local MINTED_VAR=false
    if minted_kontrol "$KLASOR"; then
        MINTED_VAR=true
    fi
    # -shell-escape .tex'e KEYFİ KOMUT çalıştırma izni veriyor. Kendiliğinden
    # açılması ölçülmüş bir risk: proje klasöründe minted geçen kullanılmayan
    # tek bir dosya bile ana belgedeki \write18'i çalıştırıyordu (2026-09-02,
    # zararsız kanıtla doğrulandı). GUI artık kullanıcıya soruyor ve kararı
    # --shell-escape / --no-shell-escape ile bildiriyor.
    if [ "${DENY_SHELL_ESCAPE:-false}" = true ]; then
        SHELL_ESCAPE_FLAG=""
    elif [ "$FORCE_SHELL_ESCAPE" = true ] || [ "$MINTED_VAR" = true ]; then
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

    # minted: kod dosyası köprüsü (bkz. minted_pyg_bagla) — TMPDIR hazır olduktan
    # sonra, ilk derleme geçişinden önce
    if [ "$MINTED_VAR" = true ]; then
        minted_pyg_bagla "$KLASOR" "$TMPDIR" "$ISIM"
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
    DERLEME_CIKTI=$(cd "$KLASOR" && "$MOTOR" -interaction=nonstopmode -file-line-error $SHELL_ESCAPE_FLAG $SYNCTEX_FLAG -output-directory="$TMPDIR" -- "$DOSYA_ADI" 2>&1) || DERLEME_HATA=$?

    if [ $DERLEME_HATA -ne 0 ]; then
        local HATALAR
        HATALAR=$(echo "$DERLEME_CIKTI" | grep -A4 -E "$HATA_DESENI" | grep -v '^--$' | head -60)
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
    if [ -f "$TMPDIR/${ISIM}.bcf" ]; then
        if command -v biber &>/dev/null; then
            local BIB_CIKTI
            BIB_CIKTI=$(cd "$TMPDIR" && biber "${ISIM}" 2>&1) || true
            local BIB_HATALAR
            BIB_HATALAR=$(echo "$BIB_CIKTI" | grep -iE "error|warn" || true)
            if [ -n "$BIB_HATALAR" ]; then
                if [ "$USE_WATCH" = true ]; then
                    echo -e "${SARI}[biber] $(date +%H:%M:%S): biber uyarilari:${SIFIRLA}"
                else
                    echo -e "${SARI}[biber] $DOSYA_ADI: biber uyarilari:${SIFIRLA}"
                fi
                echo "$BIB_HATALAR" | while read -r line; do
                    printf "${SARI}  %s${SIFIRLA}\n" "$line"
                done
            fi
        else
            # biblatex .bcf üretti ama biber kurulu değil → atıflar çözülemeyecek
            echo -e "${SARI}[uyari] Kaynakça (biblatex) için biber gerekli ama kurulu değil, atıflar çözülemeyecek.${SIFIRLA}"
            printf "${MAVI2}==> Eksik paket: biber (biblatex kaynakça aracı)${SIFIRLA}\n"
            printf "${MAVI2}    sudo apt-get install biber${SIFIRLA}\n"
        fi
    elif [ -f "$TMPDIR/${ISIM}.aux" ] && grep -rl '\\bibdata' "$TMPDIR/"*.aux &>/dev/null; then
        if command -v bibtex &>/dev/null; then
            # BibTeX `\bibdata` içeren HER `.aux` için ayrı koşuyor, yalnız
            # ana dosya için değil. Koşul zaten bütün `.aux`lara bakıyordu;
            # çalıştırma tek dosyada kalmıştı.
            #
            # Belge `multibib` ile `\newcites{ek}{Başlık}` yazınca İKİNCİ bir
            # kaynakça ve ona ait ayrı bir yardımcı dosya (`ek.aux`) açılıyor.
            # `bibtex ek` koşmazsa `ek.bbl` hiç oluşmuyor ve ikinci kaynakça
            # belgede BOŞ çıkıyor: başlık basılıyor, altında hiçbir girdi yok.
            #
            # ÖLÇÜLDÜ (2026-09-13, template11 uygulamayla birlikte gelen bir
            # şablon; kehanet üretilen PDF'in metni): "Kaynaklar" başlığının
            # altında 0 karakter vardı, dört girdinin dördü de eksikti. Her
            # `.aux` için bibtex koşunca 2375 karakter ve dördü de yerinde;
            # sayfa sayısı 32'den 33'e çıkıyor.
            local BIB_CIKTI="" BIB_AUX
            while IFS= read -r BIB_AUX; do
                [ -n "$BIB_AUX" ] || continue
                BIB_AUX=$(basename "$BIB_AUX" .aux)
                BIB_CIKTI+=$(cd "$TMPDIR" && bibtex "$BIB_AUX" 2>&1 || true)
                BIB_CIKTI+=$'\n'
            done < <(grep -l '\\bibdata' "$TMPDIR/"*.aux 2>/dev/null || true)
            local BIB_HATALAR
            BIB_HATALAR=$(echo "$BIB_CIKTI" | grep -i "error\|warning" || true)
            if [ -n "$BIB_HATALAR" ]; then
                if [ "$USE_WATCH" = true ]; then
                    echo -e "${SARI}[bibtex] $(date +%H:%M:%S): bibtex uyarilari:${SIFIRLA}"
                else
                    echo -e "${SARI}[bibtex] $DOSYA_ADI: bibtex uyarilari:${SIFIRLA}"
                fi
                echo "$BIB_HATALAR" | while read -r line; do
                    printf "${SARI}  %s${SIFIRLA}\n" "$line"
                done
            fi
        else
            echo -e "${SARI}[uyari] Kaynakça için bibtex gerekli ama kurulu değil, atıflar çözülemeyecek.${SIFIRLA}"
            printf "${MAVI2}==> Eksik paket: bibtex${SIFIRLA}\n"
            printf "${MAVI2}    sudo apt-get install texlive-bibtex-extra${SIFIRLA}\n"
        fi
    fi

    # İndeks — makeindex (.idx → .ind)
    #
    # HER `.idx` için koşuyor, yalnız ana dosya için değil. `imakeidx` ile
    # `\makeindex[name=kisi]` yazan belge ikinci bir dizin açıyor ve onu
    # `kisi.idx` dosyasına yazıyor; o işlenmezse ikinci dizin BOŞ çıkıyor.
    # Kaynakçadaki (`\newcites`) ve sözlükteki kusurun aynısı: üretilen
    # yardımcı dosyalardan yalnız birine bakılıyordu.
    #
    # ÖLÇÜLDÜ (2026-09-13, kehanet üretilen PDF'in metni): iki dizinli
    # belgede ana dizin basılıyor, ikinci dizinin girdisi PDF'te hiç yok;
    # her `.idx` işlenince ikisi de yerinde. Tek dizinli klasik biçim aynı
    # ölçümde KONTROL olarak durdu ve o zaten çalışıyordu.
    if command -v makeindex &>/dev/null; then
        local IDX_CIKTI="" IDX_DOSYA
        for IDX_DOSYA in "$TMPDIR"/*.idx; do
            # Eşleşme yoksa kabuk deseni OLDUĞU GİBİ bırakıyor. Bugün bu
            # koruma GÖZLENEBİLİR bir şey değiştirmiyor (ölçüldü: korumasız
            # sürümün çıktısı da birebir aynı, çünkü makeindex'in "dosya
            # yok" iletisi aşağıdaki uyarı süzgecine takılmıyor); yine de
            # var olmayan bir dosyayı araca vermiyoruz.
            [ -f "$IDX_DOSYA" ] || continue
            IDX_CIKTI+=$(cd "$TMPDIR" \
                && makeindex "$(basename "$IDX_DOSYA" .idx)" 2>&1 || true)
            IDX_CIKTI+=$'\n'
        done
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

    # Sözlük/kısaltmalar (glossaries) ve simge listesi (nomencl).
    #
    # İkisi de kaynakça ve dizinle AYNI iki aşamalı düzende çalışıyor: LaTeX
    # girdileri bir yardımcı dosyaya yazıyor (`.glo`, `.nlo`), ayrı bir araç
    # onu sıralayıp basılacak dosyayı üretiyor (`.gls`, `.nls`), sonraki geçiş
    # onu okuyor. Araç koşmayınca başlık basılıyor, altında hiçbir şey
    # olmuyor ve HATA DA ÇIKMIYOR; kullanıcı boş bir "Kısaltmalar" sayfası
    # görüyor. Betik ek geçiş kararında `glo` ve `nls` uzantılarına zaten
    # bakıyordu, üreten adım eksikti.
    #
    # ÖLÇÜLDÜ (2026-09-13, kehanet üretilen PDF'in metni): sözlük girdisi de
    # simge girdisi de PDF'te YOKTU; araçlar koşulunca ikisi de basılıyor.
    # Dizin (makeindex) aynı ölçümde KONTROL olarak duruyordu ve o zaten
    # çalışıyordu, yani ölçüm topyekûn yanlış değildi.
    if [ -f "$TMPDIR/${ISIM}.glo" ]; then
        # `makeglossaries` Perl, `makeglossaries-lite` Lua sürümü; ikisi de
        # aynı apt paketinden geliyor (`dpkg -S` ile doğrulandı) ama bazı
        # kurulumlarda Perl olmadığı için yalnız lite sürümü çalışıyor.
        local GLO_ARAC=""
        command -v makeglossaries &>/dev/null && GLO_ARAC=makeglossaries
        [ -z "$GLO_ARAC" ] && command -v makeglossaries-lite &>/dev/null \
            && GLO_ARAC=makeglossaries-lite
        if [ -n "$GLO_ARAC" ]; then
            local GLO_CIKTI
            GLO_CIKTI=$(cd "$TMPDIR" && "$GLO_ARAC" "${ISIM}" 2>&1 || true)
            local GLO_HATALAR
            GLO_HATALAR=$(echo "$GLO_CIKTI" | grep -iE "error|warn" || true)
            if [ -n "$GLO_HATALAR" ]; then
                echo -e "${SARI}[$GLO_ARAC] $DOSYA_ADI: sozluk uyarilari:${SIFIRLA}"
                echo "$GLO_HATALAR" | while read -r line; do
                    printf "${SARI}  %s${SIFIRLA}\n" "$line"
                done
            fi
        else
            echo -e "${SARI}[uyari] Sözlük için makeglossaries gerekli ama kurulu değil, sözlük boş çıkacak.${SIFIRLA}"
            printf "${MAVI2}==> Eksik paket: makeglossaries (glossaries aracı)${SIFIRLA}\n"
            printf "${MAVI2}    sudo apt-get install texlive-latex-extra${SIFIRLA}\n"
        fi
    fi
    if [ -f "$TMPDIR/${ISIM}.nlo" ] && command -v makeindex &>/dev/null; then
        # nomencl'in kendi stil dosyası; `nomencl.sty` ile aynı pakette
        # geldiği için belge derlenebiliyorsa o da var.
        local NLO_CIKTI
        NLO_CIKTI=$(cd "$TMPDIR" && makeindex -s nomencl.ist \
            "${ISIM}.nlo" -o "${ISIM}.nls" 2>&1 || true)
        local NLO_HATALAR
        NLO_HATALAR=$(echo "$NLO_CIKTI" | grep -iE "error" || true)
        if [ -n "$NLO_HATALAR" ]; then
            echo -e "${SARI}[nomencl] $DOSYA_ADI: simge listesi uyarilari:${SIFIRLA}"
            echo "$NLO_HATALAR" | while read -r line; do
                printf "${SARI}  %s${SIFIRLA}\n" "$line"
            done
        fi
    fi

    # Ek derleme geçişleri — yardımcı dosyalar (toc/bbl/bcf/lof/lot/idx/glo/nls)
    # oluştuysa veya "rerun" mesajı varsa. Çapraz referans/TOC/cleveref için bazen
    # 3-4 geçiş gerekir; bu yüzden sabit 3 yerine rerun bitene (MAX_GECIS'e kadar) döner.
    local SON_CIKTI="$DERLEME_CIKTI"
    local MAX_GECIS=5
    local GECIS=1
    local YARDIMCI_DOSYA=false
    for ext in toc bbl bcf lof lot idx glo nls; do
        if [ -f "$TMPDIR/${ISIM}.${ext}" ]; then
            YARDIMCI_DOSYA=true
            break
        fi
    done
    # 2. geçiş: yardımcı dosya varsa VEYA ilk çıktıda rerun mesajı varsa.
    if [ "$YARDIMCI_DOSYA" = true ] || echo "$SON_CIKTI" | grep -q "Rerun to get\|Label(s) may have changed"; then
        # Sonraki geçişler yalnızca "rerun" mesajı kalırsa; toplam MAX_GECIS geçişle sınırlı.
        while [ "$GECIS" -lt "$MAX_GECIS" ]; do
            [ "$MINTED_VAR" = true ] && minted_pyg_bagla "$KLASOR" "$TMPDIR" "$ISIM"
            local EK_CIKTI
            EK_CIKTI=$(cd "$KLASOR" && "$MOTOR" -interaction=nonstopmode -file-line-error $SHELL_ESCAPE_FLAG $SYNCTEX_FLAG -output-directory="$TMPDIR" -- "$DOSYA_ADI" 2>&1) || true
            SON_CIKTI="$EK_CIKTI"
            GECIS=$((GECIS + 1))
            echo "$SON_CIKTI" | grep -q "Rerun to get\|Label(s) may have changed" || break
        done
    fi

    # Hata var mı? (exit kodu VEYA çıktıda ^! hataları). PDF mesajından ÖNCE
    # belirlenmeli ki çelişkili "[basarili]" + "[hata]" çıktısı oluşmasın.
    local HATA_SATIRLARI
    HATA_SATIRLARI=$(echo "$SON_CIKTI" | grep -A1 -E "$HATA_DESENI" | grep -v '^--$' || true)
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
        HATALAR=$(echo "$DERLEME_CIKTI" | grep -A4 -E "$HATA_DESENI" | grep -v '^--$' | head -60)
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
        [ "$MINTED_VAR" = true ] && rm -f "$KLASOR/${ISIM}.pyg" "$KLASOR/${ISIM}.w18"
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
    UYARI_SATIRLARI=$(
        {
            echo "$SON_CIKTI" | grep -E "$UYARI_DESENI" || true
            # TEKRAR SAYISI KORUNUYOR. Burada yalnizca `sort -u` vardi ve
            # ayristiricinin "yazi tipi basina kac kez gectigini yaz" kolu
            # bu yuzden HIC gercek sayiyi gormuyordu: sayilacak satirlar
            # buraya gelmeden tekillesiyordu. OLCULDU (2026-09-15, 140
            # dusen Turkce harf iceren belge, gercek derleme): motorun
            # gunlugunde 280 satir, bu boruda 4 satir, panelde "toplam 4
            # karakter". Kullanici PDF'inden 140 harf dusmusken 4 saniyordu.
            #
            # Satir BASI degismiyor, sayi SONA ekleniyor: uc sinifin da
            # ayristirici desenleri satir basina capali (`^Missing
            # character:`, `^LaTeX Font Warning:`, `^warning +\(`) ve
            # onlerine sayi konsa hicbiri eslesmezdi.
            echo "$SON_CIKTI" | grep -E "$TEKRARLAYAN_UYARI" | sort | uniq -c \
                | sed -E 's/^ *1 (.*)$/\1/; s/^ *([0-9]+) (.*)$/\2 (x\1)/' \
                || true
        } | grep -v '^[[:space:]]*$' || true)
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
    [ "$MINTED_VAR" = true ] && rm -f "$KLASOR/${ISIM}.pyg" "$KLASOR/${ISIM}.w18"
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
    elif [ "$USE_XELATEX" = true ]; then
        echo -e "${MAVI}[bilgi] xelatex modu${SIFIRLA}"
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
elif [ "$USE_XELATEX" = true ]; then
    MOTOR="xelatex"
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

# İlk derleme. derle_dosya hata durumunda 1 döner; koşulsuz çağrı set -e
# altında betiği öldürürdü. Watch modunun varlık sebebi hatalardan sonra da
# dinlemeye devam etmek olduğundan hatayı yutup döngüde kalıyoruz.
derle_dosya "$DOSYA_YOLU" || true

# mtime takibi
SON_MOD=$(stat -c %Y "$DOSYA_YOLU" 2>/dev/null || echo "0")

while true; do
    sleep 2
    YENI_MOD=$(stat -c %Y "$DOSYA_YOLU" 2>/dev/null || echo "$SON_MOD")

    if [ "$YENI_MOD" != "$SON_MOD" ]; then
        SON_MOD="$YENI_MOD"
        echo -e "${SARI}[derleniyor] $(date +%H:%M:%S) — $DOSYA_ADI degisti${SIFIRLA}"
        # Aynı gerekçe: hatalı derleme watch döngüsünü öldürmemeli.
        derle_dosya "$DOSYA_YOLU" || true
    fi
done

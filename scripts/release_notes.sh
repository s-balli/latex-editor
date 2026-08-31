#!/usr/bin/env bash
# GitHub Release notu üretir. STDIN: tag mesajı (ham). $1: sürüm (ör. 1.0.17).
#
# Bu dosya release.yml'in build-windows ve build-linux job'larında AYNI notu
# basan ~100 satırlık echo bloğunun tek kaynağa indirilmiş hâli. İki kopya
# birebir aynıydı ve öyle kalması hiçbir şeyle güvence altında değildi;
# kurulum listesi zaten bir kez sürüklenmişti (bkz. tests/test_install_lists.py,
# artık bu dosyayı da yüzey olarak sayıyor).
#
# Kullanım:
#   git tag -l --format='%(contents)' "$TAG" | bash scripts/release_notes.sh "$V"
set -euo pipefail

V="${1:?sürüm gerekli (ör. 1.0.17)}"

# Tag mesajı Release gövdesine HTML olarak giriyor: <, > ve & kaçırılmazsa
# mesajdaki "<3" gibi bir şey etiket sanılıp yutulur.
TAG_MSG="$(cat)"
TAG_MSG="$(printf '%s' "$TAG_MSG" | sed 's/&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g')"

printf "## What's Changed\n\n"
printf '%s\n' "$TAG_MSG"

# Gövde sabit; yalnız sürüm yer tutucusu doldurulur. Tırnaklı heredoc:
# içerideki `backtick`, $ ve \ kabuk tarafından yorumlanmaz.
sed "s/__V__/${V}/g" <<'GOVDE'

---

## Installation

> Warning: The app only includes the GUI. The LaTeX compiler (`lualatex`/`pdflatex`/`xelatex`) must be installed separately via **TeX Live**.

### Windows
1. **Install WSL** (PowerShell, as administrator):
   ```
   wsl --install
   ```
2. **Install TeX Live in WSL:**
   ```
   sudo apt-get update
   sudo apt-get install texlive-base texlive-binaries texlive-latex-base \
     texlive-latex-extra texlive-latex-recommended texlive-lang-european \
     texlive-luatex texlive-xetex texlive-fonts-extra texlive-science texlive-bibtex-extra \
     texlive-font-utils texlive-extra-utils biber texlive-publishers \
     texlive-humanities texlive-pstricks python3-pygments pandoc
   ```
3. Download `LaTeX_Editor_v__V___Windows.exe` and run.

### Linux
**Install TeX Live:**
   ```
   sudo apt-get update
   sudo apt-get install texlive-base texlive-binaries texlive-latex-base \
     texlive-latex-extra texlive-latex-recommended texlive-lang-european \
     texlive-luatex texlive-xetex texlive-fonts-extra texlive-science texlive-bibtex-extra \
     texlive-font-utils texlive-extra-utils biber texlive-publishers \
     texlive-humanities texlive-pstricks libxcb-cursor0 python3-pygments pandoc
   ```
Download `LaTeX_Editor_v__V___Linux_x86_64.AppImage`, `chmod +x` and run.

### Minimum installation (basic compilation only)
   ```
   sudo apt-get update
   sudo apt-get install texlive-base texlive-binaries texlive-latex-base \
     texlive-latex-recommended texlive-luatex texlive-xetex libxcb-cursor0
   ```

---

## Kurulum

> Önemli: Uygulama yalnızca GUI'yi içerir. LaTeX derleyicisi (`lualatex`/`pdflatex`/`xelatex`) ayrıca **TeX Live** ile kurulmalıdır.

### Windows
1. **WSL kur** (PowerShell, yönetici olarak):
   ```
   wsl --install
   ```
2. **WSL içinde TeX Live kur:**
   ```
   sudo apt-get update
   sudo apt-get install texlive-base texlive-binaries texlive-latex-base \
     texlive-latex-extra texlive-latex-recommended texlive-lang-european \
     texlive-luatex texlive-xetex texlive-fonts-extra texlive-science texlive-bibtex-extra \
     texlive-font-utils texlive-extra-utils biber texlive-publishers \
     texlive-humanities texlive-pstricks python3-pygments pandoc
   ```
3. `LaTeX_Editor_v__V___Windows.exe`'yi indir ve çalıştır.

### Linux
**TeX Live kur:**
   ```
   sudo apt-get update
   sudo apt-get install texlive-base texlive-binaries texlive-latex-base \
     texlive-latex-extra texlive-latex-recommended texlive-lang-european \
     texlive-luatex texlive-xetex texlive-fonts-extra texlive-science texlive-bibtex-extra \
     texlive-font-utils texlive-extra-utils biber texlive-publishers \
     texlive-humanities texlive-pstricks libxcb-cursor0 python3-pygments pandoc
   ```
`LaTeX_Editor_v__V___Linux_x86_64.AppImage`'i indir, `chmod +x` yapip calistir.

### Minimum kurulum (sadece temel derleme)
   ```
   sudo apt-get update
   sudo apt-get install texlive-base texlive-binaries texlive-latex-base \
     texlive-latex-recommended texlive-luatex texlive-xetex libxcb-cursor0
   ```

---

For detailed usage see [README](https://github.com/s-balli/latex-editor#readme).
Detaylı kullanım için [README.tr.md](https://github.com/s-balli/latex-editor/blob/main/README.tr.md).
GOVDE

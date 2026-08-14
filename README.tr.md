# LaTeX Editor

[![CI](https://img.shields.io/github/actions/workflow/status/s-balli/latex-editor/ci.yml?branch=main&label=CI)](https://github.com/s-balli/latex-editor/actions)
[![License](https://img.shields.io/badge/license-GPL--3.0-blue.svg)](LICENSE)
[![Version](https://img.shields.io/github/v/release/s-balli/latex-editor?label=version&color=green)](https://github.com/s-balli/latex-editor/releases)
[![Downloads](https://img.shields.io/github/downloads/s-balli/latex-editor/total)](https://github.com/s-balli/latex-editor/releases)

> 🌐 **Tanıtım sayfası:** https://s-balli.github.io/latex-editor/

> **English:** [README.md](README.md) | **Türkçe:** README.tr.md (şu an buradasınız)

PyQt6 tabanlı LaTeX editörü ve derleyici. Notepad++ tarzı düzenlemeyi gömülü PDF önizleme, sözdizimi renklendirme, SyncTeX, çoklu tema ve dil desteği ile birleştirir. Windows (TeX Live için WSL) ve Linux (AppImage). GPL-3.0 lisanslı. Pasif/deneysel bir web sürümü (FastAPI + React/Monaco) `web/` altında bulunur ancak **dağıtılmaz**.

---

 ## Ekran görüntüsü

![Ana pencere](./docs/assets/01.png)

### SyncTeX canlı

Editörde bir satıra Ctrl+Click → PDF o konuma, sayfalar arası bile zıplar. PDF'e Ctrl+Click → editör o kaynak satıra geri döner.

![SyncTeX: kaynak satıra tıkla ↔ PDF'e geç](./docs/assets/ss1.gif)

---

## İndirme / Download

| Platform | Dosya | Gereksinim |
|----------|-------|------------|
| **Windows** | `LaTeX_Editor_v*_Windows.exe` (portable) | [WSL](https://learn.microsoft.com/en-us/windows/wsl/install) + TeX Live |
| **Linux** | `LaTeX_Editor_v*_Linux_x86_64.AppImage` | TeX Live |

➜ **[Download (Releases) sayfası](https://github.com/s-balli/latex-editor/releases)**

> ⚠️ **Önemli:** Uygulama yalnızca GUI'yi içerir. LaTeX derleyicisi (`lualatex`/`pdflatex`) ayrıca **TeX Live** ile kurulmalıdır — Windows'ta **WSL** üzerinden, Linux'ta `apt` ile. Detaylar için [Gereksinimler](#gereksinimler) bölümüne bakın.

---

## Sürüm Geçmişi

### Unreleased
- **Motor**: XeLaTeX desteği: araç çubuğunda üçüncü motor, `derle.sh`'de `--xelatex` bayrağı, magic comment ve paket bazlı algılama (`mathspec`, `xeCJK`, `xltxtra`, `requires XeLaTeX`), motor eksikse `sudo apt-get install texlive-xetex` önerisi
- **Editör**: `\input{` / `\include{` tamamlaması: projedeki `.tex` dosyalarını önerir (göreli yol, uzantısız), alt dizinler dahil
- **Editör**: `\includegraphics{` tamamlaması: projedeki resim dosyalarını (`png/jpg/jpeg/pdf/eps`) önerir; resim yapıştırma/sürükle-bırak ile aynı yol kuralı (ana dosyaya göre, uzantılı); `[width=...]` argümanlı kullanımı da tanır
- **Editör**: referans denetimi (Düzenle > Referansları Denetle): tanımsız `\ref`/`\cite` anahtarları ve kullanılmayan `.bib` girdileri, derlemeden bağımsız lokal analiz; çok dosyalı (`\input`) farkında, yorumları ve `\nocite{*}` gözeten; bulgular tıklanabilir (kullanım satırına ya da `.bib` girdisine atlar)

### v1.0.5 — Tanıma Git, Hata İşaretleri ve Editör İyileştirmeleri
- **Editör**: doküman-farkında tamamlama: `\ref`/`\eqref`/`\pageref` ve `\cite`/`\citep`/`\citet` (ve benzerleri) için dokümandaki (ve `\input` zincirindeki) `\label` anahtarları ile `.bib` giriş anahtarlarını önerir; `\cite{key1,key2}` çoklu anahtar destekli
- **Editör**: panodan resim yapıştırma (Ctrl+V): resmi `media/`'a kaydeder ve `\begin{figure}` bloğu ekler (sürükle-bırak diyaloğunu paylaşır)
- **Editör**: derleme hataları gutter'da işaretlenir; F4 / Shift+F4 ile hatalar arasında dolaşılır (çok dosyalı belgeleri destekler)
- **Editör**: `\ref`/`\cite` üzerine Alt basılı tıkla → tanıma git (`\label`, `.bib` veya `\bibitem` girişi); `.bib` girdisine tıkla → makalede `\cite` edildiği yere. Çok dosyalı `\input` ve çok anahtarlı `\cite` destekli
- **Editör performansı**: büyük belgelerde daha hızlı yazım (sözdizimi lexer'ı ve `\begin`/`\end` vurgu sıcak yolları optimize edildi)
- **Hata düzeltme**: çok satırlı `verbatim` / `\[...\]` bloğu içinde düzenleyince artık renklendirme bozulmuyor
- **549 birim testi**

### v1.0.4 — Editör ve Dışa Aktarma İyileştirmeleri
- **Editör**: `\[...\]` / `\(...\)` math renklendirme, Ctrl+Space + ortam adı tamamlama, eşleşen `\begin`/`\end` vurgulama, akıllı girintileme, yorum/verbatim algılayan tamamlama, dinamik satır numarası margin
- **Dosya güvenliği**: atomik kayıt (çökmede truncation yok) ve UTF-8 / eski-Türkçe kodlama tespiti (sessiz bozulma yok)
- **Dışa aktarma**: abstract ve başlık artık tüm formatlarda; kaynakça HTML/DOCX/TXT/Markdown'da çözülüyor; Plain Text artık gerçek plain text; docx Word uyumluluk düzeltmeleri
- **480+ unit test**

### v1.0.3 — Uyumluluk Düzeltmesi
- **PDF yer imleri**: pypdfium2 outline API değişimine uyum (`PdfBookmark` → `PdfOutlineItem`)
- **Linux paketleme**: AppImage `.zsync` delta güncelleme dosyası ve adlandırma düzeltmeleri

### v1.0.2 — Dağıtım Altyapısı
- **Bağımlılıklar**: tekrarlanabilir derlemeler için sürüm sabitleme
- **Linux paketleme**: AppImage kurala uygun adlandırma + delta güncellemeler için `updateinformation`
- **Dokümanlar**: dinamik sürüm rozetleri, sürümden bağımsız referanslar

### v1.0.1 — Motor ve Derleme İyileştirmeleri
- **Motor seçimi**: `% !TEX program` magic comment desteği (örn. `% !TEX program = pdflatex`)
- **Derleme watchdog**: 120s zaman aşımı, takılı kalan derlemeler iptal edilir
- **Rerun döngüsü**: çapraz referanslar çözülene kadar yeniden derler (maks. 5 geçiş)
- **Kaynakça**: `biber`/`bibtex` eksikse kurulum komutu önerilir
- **Hata düzeltme**: uyarı bağlamlı `l.NNN` satırları artık derleme hatası sayılmıyor

### v1.0.0 — İlk Public Sürüm
- **Public lansman**: İlk halka açık sürüm
- **Lisans**: GPL-3.0 (PyQt6 GPL uyumlu)
- **Dağıtım**: GitHub Releases — Windows portable `.exe` + Linux `.AppImage` (GitHub Actions ile otomatik derleme)
- **Otomatik güncelleme kontrolü**: Yardım menüsünden veya açılışta GitHub Releases API ile sürüm kontrolü
- **480+ unit test**: engine_detector, input_parser, log_parser, paths, latex_utils, exporter, derle_sh, i18n, imports, autopair, latex_lexer, pdf_indicator, wordcount, updater
- **Özellikler**: Sözdizimi renklendirme, PDF önizleme, SyncTeX, 7 tema, çoklu dil (TR/EN), otomatik parantezleme, PDF yer imleri/arama/seçme, sunum modu, çift sayfa, akıllı motor algılama, görsel sürükle-bırak

---

## Özellikler

- **LaTeX sözdizimi renklendirme** — komutlar, yorumlar, matematik, ortamlar
- **PDF önizleme** — yan panelde anlık PDF görüntüleme, yakınlaştırma
- **Otomatik derleme** — Ctrl+S ile kaydet ve derle
- **Üçlü motor desteği** — lualatex (varsayılan), pdflatex ve xelatex
- **Proje yönetimi** — klasör açma, dosya ağacı, çoklu dosya sekmeleri
- **Hata görüntüleme** — derleme hataları ve uyarıları ayrı sekmelerde
- **7 tema** — Koyu, Açık, Solarized Light, Dracula, Monokai, Nord, Gruvbox
- **Çoklu dil** — Türkçe ve İngilizce arayüz, yeni dil eklemek için sadece .ts dosyası çevirmek yeterli
- **PDF yer imleri** — bölüm/başlık yapısını yan panelde gösterme
- **PDF arama** — Ctrl+F ile metin arama, vurgulama, navigasyon
- **PDF metin seçme** — sürükleyerek seçme, Ctrl+C ile kopyalama
- **Sayfaya sığdır** — genişliğe veya tam sayfaya otomatik zoom
- **Çift sayfa görünümü** — yan yana iki sayfa

---

## Masaüstü Uygulaması

### Gereksinimler

#### Windows

- **Python 3.12+** — [python.org](https://www.python.org/downloads/)
- **pip** paket yöneticisi (Python ile birlikte gelir)

#### WSL (LaTeX derleme için)

```bash
sudo apt-get update
sudo apt-get install texlive-base texlive-binaries texlive-latex-base \
  texlive-latex-extra texlive-latex-recommended texlive-lang-european texlive-luatex texlive-xetex \
  texlive-fonts-extra texlive-science texlive-bibtex-extra texlive-font-utils \
  texlive-extra-utils biber texlive-publishers texlive-humanities texlive-pstricks pandoc
```

### Kurulum

#### Yöntem 1: Exe (Tavsiye Edilen)

Python kurulumu gerektirmez. `dist/` klasöründen `LaTeX Editor.exe` dosyasını istediğiniz klasöre kopyalayın ve çift tıklayarak çalıştırın. `derle.sh` betiği exe'nin içine gömülüdür, ayrıca kopyalamaya gerek yok.

**Boyut:** ~63 MB (PyQt6, pypdfium2, send2trash dahil)

**Exe'yi oluşturmak için:**

`desktop/Exe Olustur.bat` dosyasına çift tıklayın. `dist/LaTeX Editor.exe` oluşur.

Veya PowerShell'den (tek satır, Anaconda kullanıyorsanız standalone Python yolunu belirtin):
```powershell
cd desktop
& "C:\Users\<kullanici>\AppData\Local\Programs\Python\Python312\python.exe" -m PyInstaller --onefile --windowed --name "LaTeX Editor" --add-data "..\core;core" --add-data "gui;gui" --add-data "syntax;syntax" main.py
```

**UPX ile sıkıştırılmış exe (daha küçük boyut):**

`desktop/Sikistirilmis Exe Olustur.bat` dosyasına çift tıklayın. UPX, exe dosyasını sıkıştırarak boyutunu küçültür.

UPX kurulumu:
1. [UPX Releases](https://github.com/upx/upx/releases) sayfasından en son sürümü indirin
2. `upx/` klasörünü `desktop/upx/` altına çıkarın (`desktop/upx/upx.exe` olacak şekilde)
3. `Sikistirilmis Exe Olustur.bat`'ı çalıştırın

UPX yoksa bat dosyası sıkıştırma olmadan normal exe oluşturur.

Sonuç: `dist/LaTeX Editor.exe` (Windows) veya `dist/LaTeX Editor` (Linux/macOS)

#### Yöntem 2: Kaynak Koddan

**Python paketlerini yükle:**

```bash
pip install PyQt6 PyQt6-QScintilla pypdfium2 send2trash
```

Dışa aktarma: `sudo apt-get install pandoc` (WSL/Linux) veya [pandoc.org](https://pandoc.org/installing.html) (Windows)

> **Not:** Anaconda kullanıyorsanız standalone Python kullanmanız gerekir:
> ```
> C:\Users\<kullanici>\AppData\Local\Programs\Python\Python312\python.exe -m pip install PyQt6 PyQt6-QScintilla pypdfium2 send2trash
> ```

**Uygulamayı başlat:**

`desktop/LaTeX Editor.bat` dosyasına çift tıklayın. Veya PowerShell'den:
```
cd desktop
& "C:\Users\<kullanici>\AppData\Local\Programs\Python\Python312\python.exe" main.py
```

### Başka Bilgisayarda Dağıtım

Başka bir bilgisayarda çalıştırmak için:

| Gereken | Açıklama |
|---------|----------|
| `LaTeX Editor.exe` | Tek dosya, Python gerektirmez |
| **WSL** | Windows 10/11'de WSL aktif olmalı |
| **TeX Live** | WSL içinde: `sudo apt-get update && sudo apt-get install texlive-base texlive-binaries texlive-latex-base texlive-latex-extra texlive-latex-recommended texlive-lang-european texlive-luatex texlive-xetex texlive-fonts-extra texlive-science texlive-bibtex-extra texlive-font-utils texlive-extra-utils biber texlive-publishers texlive-humanities texlive-pstricks pandoc` |
| **pandoc** | Dışa aktarma için: WSL içinde `sudo apt-get install pandoc` |

Kurulum adımları:
1. WSL'i etkinleştir: `wsl --install` (PowerShell, yönetici olarak)
2. Ubuntu uygulamasını aç (veya PowerShell'de `wsl` yaz) ve yukarıdaki komutu çalıştırarak TeX Live'ı kur
3. `LaTeX Editor.exe`'yi masaüstüne kopyala, çift tıkla

### Linux

#### Yöntem 1: AppImage (Tavsiye Edilen)

Python veya bağımlılık kurulumu gerektirmez.

**1. AppImage dosyasını indir:**
```bash
chmod +x LaTeX_Editor_v*_Linux_x86_64.AppImage
./LaTeX_Editor_v*_Linux_x86_64.AppImage
```

**2. TeX Live kur (derleme için):**

```bash
sudo apt-get update
sudo apt-get install texlive-base texlive-binaries texlive-latex-base \
  texlive-latex-extra texlive-latex-recommended texlive-lang-european \
  texlive-luatex texlive-xetex texlive-fonts-extra texlive-science texlive-bibtex-extra \
  texlive-font-utils texlive-extra-utils biber texlive-publishers \
  texlive-humanities texlive-pstricks libxcb-cursor0 pandoc
```

> **Not:** `texlive-full` (~7 GB) yerine sadece gerekli paketler kurulur (~1.5 GB). Daha az paket kurmak isterseniz ihtiyacınıza göre kaldırabilirsiniz:

| Paket | Boyut | Ne için gerekli |
|-------|-------|----------------|
| `texlive-base` | ~50 MB | Temel LaTeX (zorunlu) |
| `texlive-binaries` | ~30 MB | lualatex, pdflatex (zorunlu) |
| `texlive-latex-base` | ~20 MB | Temel paketler (zorunlu) |
| `texlive-latex-recommended` | ~40 MB | Sık kullanılan paketler |
| `texlive-latex-extra` | ~200 MB | Ek paketler (tcolorbox, minted vb.) |
| `texlive-luatex` | ~30 MB | LuaLaTeX desteği |
| `texlive-xetex` | ~20 MB | XeLaTeX desteği |
| `texlive-fonts-extra` | ~300 MB | Ek fontlar |
| `texlive-science` | ~50 MB | algorithm, siunitx vb. |
| `texlive-bibtex-extra` + `biber` | ~30 MB | Kaynakça |
| `texlive-publishers` | ~40 MB | IEEE, Elsevier şablonları |
| `texlive-humanities` | ~10 MB | phonrule vb. |
| `texlive-pstricks` | ~30 MB | PSTricks grafik |
| `texlive-lang-european` | ~20 MB | Türkçe dahil Avrupa dilleri |
| `texlive-font-utils` | ~5 MB | Font dönüştürme araçları |
| `texlive-extra-utils` | ~5 MB | Ek araçlar |
| `libxcb-cursor0` | ~1 MB | PyQt6 fare imleci desteği |

**Minimum kurulum** (sadece temel derleme):
```bash
sudo apt-get update
sudo apt-get install texlive-base texlive-binaries texlive-latex-base \
  texlive-latex-recommended texlive-luatex texlive-xetex libxcb-cursor0
```

**AppImage oluşturmak için:**
```bash
cd desktop
./build_appimage.sh
```

Sonuç: `dist/LaTeX_Editor_v*_Linux_x86_64.AppImage`

#### Yöntem 2: Kaynak Koddan

Python ve TeX Live kur:
```bash
sudo apt-get install python3 python3-pip texlive-base texlive-binaries texlive-latex-base \
  texlive-latex-extra texlive-latex-recommended texlive-lang-european texlive-luatex texlive-xetex \
  texlive-fonts-extra texlive-science texlive-bibtex-extra texlive-font-utils \
  texlive-extra-utils biber texlive-publishers texlive-humanities texlive-pstricks libxcb-cursor0 pandoc

pip install PyQt6 PyQt6-QScintilla pypdfium2 send2trash
```

Çalıştır:
```bash
cd desktop
python3 main.py
```

### macOS

Python ve MacTeX kur:
```bash
brew install python
brew install --cask mactex
pip3 install PyQt6 PyQt6-QScintilla pypdfium2 send2trash
```

Çalıştır:
```bash
cd desktop
python3 main.py
```

---

## Web Uygulaması (Deneysel — Dağıtılmıyor)

> ⚠️ **Web sürümü deneysel/pasiftir.** ~14 sürüm geride, dağıtılmaz ve GitHub Releases'e dahil edilmez. Kaynak kodu `web/` altında referans için tutulur. Aktif geliştirme yalnızca masaüstü (`desktop/`) üzerinedir.

Tarayıcı tabanlı LaTeX editörü. FastAPI backend + React/Monaco frontend.

### Backend

```bash
pip install fastapi uvicorn
python -m web.backend.run
```

Backend `http://localhost:8000` adresinde çalışır.

### Frontend

```bash
cd web/frontend
npm install
npm run dev
```

Frontend `http://localhost:5173` adresinde çalışır.

### Özellikler

- Monaco editor ile LaTeX sözdizimi renklendirme (Monarch tokenizer)
- 162 komut autocompletion (`\` yazınca tetiklenir)
- WebSocket ile gerçek zamanlı derleme çıktısı
- PDF.js ile PDF önizleme, yakınlaştırma
- Otomatik motor algılama (fontspec→lualatex, inputenc→pdflatex)
- Tab bazlı dosya yönetimi, session kalıcılığı (localStorage)
- VS Code tarzı koyu tema, menü bar, durum çubuğu
- Uyarı tıklama ile ilgili dosyaya/satıra gitme

---

## Kullanım

### Temel İş Akışı

1. **Klasör Aç** butonuna bas veya `Ctrl+O` → .tex dosyalarının olduğu klasörü seç
2. Dosya ağacından `.tex` dosyasına **çift tıkla** → editörde açılır
3. **Ctrl+S** ile kaydet → otomatik derleme başlar
4. Sağ panelde **PDF** güncellenir

### Klavye Kısayolları

| Kısayol | İşlev |
|---------|-------|
| `Ctrl+S` | Kaydet + Otomatik Derle |
| `Ctrl+B` | Derle |
| `Ctrl+N` | Yeni Dosya |
| `Ctrl+O` | Klasör Aç |
| `Ctrl+Shift+O` | Dosya Aç (Masaüstü) |
| `Ctrl+Shift+S` | Farklı Kaydet (Masaüstü) |
| `Ctrl+W` | Sekmeyi Kapat (Web) |
| `Ctrl+Z` | Geri Al |
| `Ctrl+Y` | Yinele |
| `Ctrl+F` | Bul (Editör veya PDF) |
| `Ctrl+H` | Bul ve Değiştir |
| `Ctrl+C` | Kopyala (PDF'te metin seçiliyse) |
| `Ctrl+/` | Yorum Toggle |
| `Ctrl+G` | Satıra Git |
| `Esc` | Derlemeyi Durdur / Sunum Modundan Çık |
| `F5` | Sunum Modu (PDF) |
| `Ctrl+Q` | Çıkış (Masaüstü) |
| `Ctrl+Fare Tekerleği` | PDF Yakınlaştır |
| `Ctrl+Tıklama (Editör)` | SyncTeX: PDF'te konumu göster |
| `Ctrl+Tıklama (PDF)` | SyncTeX: Kaynak koda git |

### Motor Seçimi

Araç çubuğundaki açılır menüden motor seçilir:

| Motor | Kullanım |
|-------|----------|
| **lualatex** (varsayılan) | Makaleler, genel belgeler. Yüksek font kalitesi, Overleaf uyumlu |
| **pdflatex** | ASYU/IEEE şablonları, Beamer sunumları |

#### Ne Zaman pdflatex Kullanmalı?

- **ASYU, IEEE, IEEEtran gibi şablonlar**: Bu şablonlar `ptm` (Times) gibi Type 1 fontlar kullanır. `lualatex` ile Türkçe karakterler görünmez.
- **Beamer sunumları**: Türkçe içerik ASCII olarak yazıldığı için `pdflatex` yeterlidir.
- `pdflatex` ile font ve renk kalitesi daha düşük olur. Overleaf makaleleri için `lualatex` tercih edin.

#### Lokal vs Overleaf Sayfa Farkı

Lokal derleme ile Overleaf arasında 1 sayfa fark olabilir. Nedeni: farklı TeX Live sürümleri (lokal: 2023, Overleaf: 2025). Font metric hesaplamalarındaki küçük farklar sayfa sonlarını farklı yerlere taşır. İçerik tamamen aynıdır.

### PDF Önizleme

- **+/-** butonları veya **Ctrl+Mouse Tekerleği** ile yakınlaştır
- **Genişliğe/Sayfaya sığdır** butonları ile otomatik zoom
- **Çift sayfa** toggle ile yan yana iki sayfa görünümü
- Sayfa gezinme: **< >** butonları
- **Yer imleri** paneli ile bölüm/başlık navigasyonu
- **Ctrl+F** ile PDF içinde metin arama, sonuçları vurgulama
- Fareyle metin seçme, **Ctrl+C** ile kopyalama, çift tıklama ile kelime seçme
- **Invert** butonu ile PDF renklerini ters çevir (koyu temada okuma)
- **F5** ile sunum modu — tam ekran, sayfa sayfa gezinti
- Varsayılan yakınlaştırma: %75

### Otomatik Derleme

Araç çubuğunda **● Otomatik** yazısına tıklayarak otomatik derlemeyi açıp kapatabilirsiniz. Otomatik modda Ctrl+S hem kaydeder hem derler. Manuel modda sadece kaydeder, derleme için Ctrl+B gerekir.

---

## Test

480+ unit test. PyQt6 bağımlılığı yok, saf pytest.

```bash
# pytest yükle (ilk sefer)
pip install pytest

# Tüm testleri çalıştır
python3 -m pytest tests/ -v

# Tek dosya
python3 -m pytest tests/test_log_parser.py -v

# Kısa özet
python3 -m pytest tests/ -q
```

Kapsam:

| Modül | Test sayısı | Kapsanan fonksiyonlar |
|-------|------------|----------------------|
| `engine_detector` | 47 | motor algılama, compilable kontrolü, yorum temizleme, .cls tespiti |
| `input_parser` | 24 | \input/\include çözümleme, path traversal koruması, döngüsel referans, dizin gruplama |
| `log_parser` | 26 | hata/uyarı/öneri parse, satır numarası, motor önerisi, dosya referansı |
| `paths` | 20 | Windows/WSL yol dönüşümleri, roundtrip |
| `latex_utils` | 18 | Yorum temizleme, strip_comments |
| `exporter` | 32 | Pandoc dışa aktarma, hata senaryoları |
| `derle.sh` | 23 | derle.sh entegrasyon testleri (lualatex/pdflatex) |
| `i18n` | 25 | Çeviri altyapısı, import güvenlik, başlatma akışı |
| `imports` | 3 | Modül import testleri (parametrized, syntax doğrulama) |
| `autopair` | 12 | Otomatik parantezleme, \begin/\end kapanışı |
| `latex_lexer` | 5 | Sözdizimi renklendirme |
| `pdf_indicator` | 9 | Eski PDF göstergesi, tazelik kontrolü |
| `wordcount` | 11 | Kelime sayımı, matematik dışında tutma |
| `updater` | 24 | Sürüm karşılaştırma, GitHub API, cache, ağ hatası |
| `log` | 6 | Logger başlatma, dosya handler, multi-logger |
| `compiler` | 11 | derle.sh yol bulma, frozen mod, motor ayarı |

---

## Terminal Kullanımı

`derle.sh` uygulamadan bağımsız olarak terminalden de kullanılabilir. VS Code, Vim, nano gibi herhangi bir editörle birlikte çalışır.

### Temel Kullanım

```bash
# Tek dosya derle (lualatex)
bash derle.sh dosya.tex

# pdflatex ile derle
bash derle.sh dosya.tex --pdflatex

# Klasördeki tüm .tex dosyalarını derle
bash derle.sh *.tex

# Klasör argümanı
bash derle.sh /proje/klasoru/
```

### Watch Modu

Dosya kaydedildiğinde otomatik yeniden derler. Başka bir editörle (VS Code, Vim vb.) çalışırken kullanışlıdır.

```bash
# Dosya değişince otomatik derle
bash derle.sh dosya.tex --watch

# Watch + pdflatex kombinasyonu
bash derle.sh dosya.tex --watch --pdflatex
```

Watch modunda `Ctrl+C` ile durdurulur. Her derlemede süre bilgisi gösterilir.

### Parametreler

| Parametre | Açıklama |
|-----------|----------|
| `--pdflatex` | LuaLaTeX yerine pdfLaTeX kullanır |
| `--watch` | Dosya değişikliğini izler, otomatik yeniden derler (tek dosya) |
| `--shell-escape` | `-shell-escape` bayrağını zorlar (minted paketi otomatik algılanır) |

### Derleme Özellikleri

- Kaynakça: BibTeX ve BibLaTeX (biber) otomatik algılanır
- İndeks: `makeindex` `.idx` dosyası varsa otomatik çalışır
- Çoklu pass: İçindekiler tablosu, referanslar değişiyorsa 2. ve 3. derleme otomatik tetiklenir
- Eksik paket tespiti: Derleme hatasında eksik TeX paketini ve `apt-get` komutunu gösterir

### Terminal + Harici Editör İş Akışı

Uygulama yerine terminalden çalışırken:
1. **WSL terminalinde** watch'ı başlat: `bash derle.sh dosya.tex --watch`
2. **Notepad++ veya VS Code** ile `.tex` dosyasını düzenle ve kaydet
3. **SumatraPDF** ile PDF açık — dosya değişince otomatik yenilenir

> SumatraPDF PDF'i kilitlemez ve değişiklikleri otomatik gösterir. Adobe Acrobat ve Edge PDF dosyayı kilitler.

## Teknik Detaylar

### Derleme Akışı

1. Python GUI (Windows) → `wsl bash derle.sh dosya.tex` çağırır
2. `derle.sh` → `mktemp -d`'de derler, kaynakça/indeks işler, çoklu pass yapar, PDF'i kaynak klasöre kopyalar
3. GUI → PDF'yi `pypdfium2` ile render eder, sağ panelde gösterir

### Neden WSL

WSL'de TeX Live kurulu olduğundan derleme WSL tarafında yapılır. GUI Windows'ta çalışır, derleme için `wsl.exe` üzerinden betik çağırılır. Bu sayede ayrı bir Windows TeX Live kurulumu gerekmez.

### Uyumluluk

Proje **TeX Live 2023** (Ubuntu 24.04 LTS depo sürümü) ile geliştirilmiş ve test edilmiştir. Tüm template'ler bu sürümle uyumludur. Overleaf güncel TeX Live kullandığı için lokal derleme ile 1 sayfa farkı olabilir (içerik aynıdır).

### Neden İkinci Derleme Gerekli Olabilir

İlk derlemede içindekiler tablosu (.toc) ve çapraz referans dosyaları oluşur. Bu dosyalar varsa ikinci derleme yapılır ve tablo/referanslar doldurulur. Yardımcı dosya oluşmamışsa ikinci derleme atlanır.

## Derleme Öncesi Hazırlık

Overleaf'ten indirilen dosyalarda aşağıdaki değişikliklerin yapılması gerekir.

### 1. iftex Bloğu (Türkçe Karakter Desteği)

**Eski:**
```latex
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
```

**Yeni:**
```latex
\usepackage{iftex}
\ifluatex
  \usepackage{fontspec}
\else
  \usepackage[utf8]{inputenc}
  \usepackage[T1]{fontenc}
\fi
```

### 2. Filigran Düzeltmesi

`everypage` paketi `tcolorbox` breakable kutularıyla sayfa atlıyor. `eso-pic` ile her sayfada garantili çalışır.

**Eski (`everypage`):**
```latex
\usepackage{everypage}
\AddEverypageHook{...}
```

**Yeni (`eso-pic`):**
```latex
\usepackage{eso-pic}
\AddToShipoutPictureFG{...}
```

### Otomatik Düzeltme Betiği

Birden fazla `.tex` dosyanız varsa, aşağıdaki betik hepsine iftex + eso-pic değişikliklerini otomatik uygular:

```bash
#!/bin/bash
# Kullanim: bash duzelt.sh /mnt/c/Users/secho/Desktop/abc/

KLASOR="$1"

for dosya in "$KLASOR"/*.tex; do
    echo "Isleniyor: $dosya"

    # fontspec + iftex degisikligi
    sed -i '/\\usepackage\[utf8\]{inputenc}/{
        s/\\usepackage\[utf8\]{inputenc}/\\usepackage{iftex}\n\\ifluatex\n  \\usepackage{fontspec}\n\\else\n  \\usepackage[utf8]{inputenc}/
    }' "$dosya"

    sed -i '/\\usepackage\[T1\]{fontenc}/a\\\\fi' "$dosya"

    # Filigran: everypage -> eso-pic
    sed -i 's/\\usepackage{everypage}/\\usepackage{eso-pic}/' "$dosya"
    sed -i 's/\\AddEverypageHook{/\\AddToShipoutPictureFG{/' "$dosya"

    echo "Tamam: $dosya"
done
```

> Betik çalıştırmadan önce dosyalarınızı yedekleyin.

## Sık Karşılaşılan Sorunlar

### "Python çalışmayı durdurdu" hatası

Anaconda Python ile PyQt6 uyumsuzluğu. Standalone Python kullanın:
```
cd desktop
"C:\Users\<kullanici>\AppData\Local\Programs\Python\Python312\python.exe" main.py
```

### Derleme başarısız oluyor

WSL'de TeX Live kurulu olduğundan emin olun:
```bash
wsl which lualatex
```

### PDF görünmüyor

Derleme başarılı olduktan sonra PDF otomatik gösterilir. Dosya ağacında `.pdf` dosyası oluşmuş mu kontrol edin.

## Bağımlılıklar

### Masaüstü

| Paket | Sürüm | Açıklama |
|-------|-------|----------|
| PyQt6 | >=6.6 | GUI framework |
| PyQt6-QScintilla | >=2.14 | Kod editörü bileşeni |
| pypdfium2 | >=4.20 | PDF render (PDFium tabanlı) |
| send2trash | >=1.8 | Dosyaları çöpe taşıma |

### Web

| Paket | Açıklama |
|-------|----------|
| FastAPI | Backend framework |
| uvicorn | ASGI server |
| React | Frontend framework |
| Monaco Editor | Kod editörü |
| Zustand | State management |
| PDF.js | PDF render |

## Proje Yapısı

```
latex-editor/
├── .github/workflows/        # CI + Release (GitHub Actions)
│   ├── ci.yml               # Her push'ta pytest
│   └── release.yml          # tag v* → exe + AppImage
├── core/                     # Ortak (desktop + web)
│   ├── derle.sh             # Ortak LaTeX derleme betiği
│   ├── compiler.py          # Desktop derleme motoru
│   ├── log_parser.py        # Hata/uyarı ayrıştırma
│   ├── engine_detector.py   # Motor algılama + derlenebilirlik kontrolü
│   ├── input_parser.py      # \input/\include bağımlılık çözümleyici
│   ├── exporter.py          # Pandoc dışa aktarma
│   ├── latex_utils.py       # Ortak LaTeX yardımcı fonksiyonları
│   ├── paths.py             # Platform path dönüşümleri (Windows/WSL)
│   ├── log.py               # Merkezi logging (platform-aware, rotating)
│   ├── i18n.py              # Uluslararasılaştırma (desktop + web ortak)
│   ├── updater.py           # GitHub Releases API güncelleme kontrolü
│   └── version.py           # Merkezi versiyon kaynağı
├── desktop/                  # Masaüstü uygulama (PyQt6)
│   ├── main.py              # Giriş noktası
│   ├── requirements.txt     # pip bağımlılıkları
│   ├── build_appimage.sh    # Linux AppImage build betiği
│   ├── LaTeX Editor.spec    # PyInstaller Windows spec
│   ├── latex-editor-linux.spec  # PyInstaller Linux spec
│   ├── gui/
│   │   ├── main_window.py   # Ana pencere — layout, tema, event filter, state
│   │   ├── stylesheet.py    # Tema CSS üretici (statik fonksiyon)
│   │   ├── editor.py        # QScintilla LaTeX editörü
│   │   ├── pdf_viewer.py    # PDF görüntüleyici (kompozisyon + mixin'ler)
│   │   ├── pdf_render.py    # Saf render fonksiyonu (pypdfium2 → QPixmap)
│   │   ├── pdf_links.py     # Saf link çözümleme (ctypes soyutlama)
│   │   ├── file_tree.py     # Proje dosya ağacı
│   │   ├── output_panel.py  # Derleme çıktıları
│   │   ├── outline.py       # Belge anahattı (\section hiyerarşisi)
│   │   ├── find_replace.py  # Bul/değiştir paneli
│   │   ├── synctex.py       # SyncTeX forward/reverse arama
│   │   ├── theme.py         # Merkezi tema tanımları (7 tema)
│   │   ├── mixins/          # MainWindow sorumluluk ayrımı (mixin pattern)
│   │   │   ├── file_ops.py    # Dosya aç/kaydet/yeni, recent files, motor algılama
│   │   │   ├── file_watch.py  # Açık dosyaların diskte değişmesini algıla
│   │   │   ├── tab_ops.py     # Sekme yönetimi, wordcount, outline güncelleme
│   │   │   ├── edit_ops.py    # Geri al, yinele, bul, değiştir, yorum, satıra git
│   │   │   ├── compile_ops.py # Derleme, durdurma, otomatik derleme
│   │   │   ├── image_ops.py   # Görsel ekleme, şablon tespiti, snippet üretimi
│   │   │   └── synctex_ops.py # SyncTeX forward/reverse arama
│   │   └── pdf_viewer_mixins/  # PdfViewer sorumluluk ayrımı (mixin pattern)
│   │       ├── _render.py       # PDF yükleme, sayfa render, placeholder, çift sayfa
│   │       ├── _ui_setup.py     # Araç çubuğu, tema, kaydetme, fit butonları
│   │       ├── _navigation.py   # Sayfa geçişi, zoom, sayfaya sığdır
│   │       ├── _presentation.py # Sunum modu (tam ekran)
│   │       ├── _events.py       # Event filter + link tıklama + metin seçme
│   │       ├── _synctex.py      # SyncTeX koordinat dönüşümü
│   │       ├── _highlight.py    # Vurgulama
│   │       ├── _bookmarks.py    # PDF yer imleri (TOC)
│   │       ├── _search.py       # PDF metin arama
│   │       └── _selection.py    # PDF metin seçme/kopyalama
│   ├── syntax/
│   │   └── latex_lexer.py   # LaTeX sözdizimi renklendirme
│   ├── translations/        # .ts (kaynak) + .qm (derlenmiş) çeviri dosyaları
│   ├── linux/               # AppRun, .desktop, ikonlar
│   └── *.bat                # Windows build/launcher betikleri
├── scripts/
│   └── update_translations.sh  # .ts üret + .qm derle betiği
├── web/                      # Web uygulama — deneysel/pasif (FastAPI + React)
│   ├── backend/
│   │   ├── services/
│   │   │   ├── compiler.py   # WebSocket tabanlı derleme servisi
│   │   │   └── file_system.py # Dosya sistemi işlemleri
│   │   └── run.py            # Backend giriş noktası
│   └── frontend/
│       └── src/
│           ├── components/   # React bileşenleri
│           ├── hooks/        # Custom hooks
│           ├── store/        # Zustand state management
│           └── utils/        # LaTeX komut listesi, yardımcılar
├── tests/                    # Unit testler (pytest, 326 test)
├── .github/ISSUE_TEMPLATE/  # Hata bildirim & özellik isteği şablonları
├── LICENSE                   # GPL-3.0
├── CONTRIBUTING.md           # Katkı rehberi
└── README.md
```

---

## Lisans

GPL-3.0 — bkz. [LICENSE](LICENSE).

PyQt6 ve PyQt6-QScintilla GPL-3.0 lisanslıdır; bu nedenle uygulama GPL-3.0 ile lisanslanmıştır.

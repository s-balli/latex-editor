"""LaTeX dışa aktarma — pandoc ile format dönüşümü."""

import os
import re
import shlex
import shutil
import subprocess
import sys

from core.log import get_logger
from core.paths import clean_child_env

_logger = get_logger("exporter")

FORMATS = {
    "DOCX":     ".docx",
    "HTML":     ".html",
    "Markdown": ".md",
    "Plain Text": ".txt",
}

PLATFORM = sys.platform


def pandoc_available() -> bool:
    """Dışa aktarma GERÇEKTEN çalışabilir mi.

    Windows'ta export() her zaman _export_wsl kullanıyor (pandoc WSL'de
    çağrılıyor), dolayısıyla Windows'a kurulmuş NATIVE pandoc işe yaramıyor.
    Eskiden burada "native VEYA wsl" deniyordu: pandoc'u Windows'a kurmuş ama
    WSL'e kurmamış kullanıcıda menü açık kalıyor, hiçbir uyarı çıkmıyor ve
    dışa aktarma sessizce başarısız oluyordu. Kullanılabilirlik, kullanılan
    yolla aynı olmalı.
    """
    if PLATFORM == "win32":
        return _wsl_pandoc_available()
    return shutil.which("pandoc") is not None


def _wsl_pandoc_available() -> bool:
    try:
        r = subprocess.run(
            ["wsl", "-e", "which", "pandoc"],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=5,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        return r.returncode == 0
    except Exception:
        return False


def export(tex_path: str, dest_path: str) -> tuple[bool, str]:
    """pandoc ile .tex → hedef format.

    Dönüş: (başarılı_mı, hata_mesajı)
    """
    if not os.path.exists(tex_path):
        return False, "Kaynak dosya bulunamadı"

    # Önişle: elsarticle frontmatter'ını soy, abstract/title'ı gövdeye taşı.
    # Bibliography (.bib) tespit et ki referanslar çözülsün.
    bib = _find_bibliography(tex_path)
    tmp_tex = _preprocess_tex(tex_path)
    ok, err = False, ""
    try:
        if PLATFORM == "win32":
            ok, err = _export_wsl(tmp_tex, dest_path, bib)
        else:
            ok, err = _export_native(tmp_tex, dest_path, bib)
        if ok and dest_path.endswith(".md"):
            _fix_md_image_paths(tex_path, dest_path)
            if bib:
                # tmp_tex citeproc referans üretimi için lazım; silinmeden önce çağır.
                _resolve_md_citations(dest_path, tmp_tex, bib)
        elif ok and dest_path.endswith(".docx"):
            _fix_docx_compat(dest_path)
    except Exception as e:
        # export() asla istisna fırlatmamalı: çağıran arka plan thread'i
        # (file_ops._ExportRunner) sonucu sinyalle bekliyor; istisna sinyali
        # düşürür, _export_busy sonsuza dek True kalırdı.
        _logger.error("Dışa aktarma beklenmedik hata: %s → %s",
                      tex_path, dest_path, exc_info=True)
        ok, err = False, f"Dışa aktarma sırasında beklenmedik hata: {e}"
    finally:
        if tmp_tex != tex_path:
            try:
                os.unlink(tmp_tex)
            except OSError:
                pass

    return ok, err


def _pandoc_run(args, input_text=None, timeout=40):
    """Platform-aware pandoc çağrısı; stdout döndürür. args pandoc argümanlarıdır.

    Windows'ta pandoc WSL'dedir; 'wsl -e pandoc' ile çalıştırır. Çıktı her zaman
    UTF-8 çözülür (Windows cp1254 çökmesini önler).
    """
    try:
        if PLATFORM == "win32":
            cmd = ["wsl", "-e", "pandoc"] + args
            kw = dict(creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        else:
            cmd = ["pandoc"] + args
            # AppImage gömülü kütüphane yolları sızmasın (bkz. clean_child_env)
            kw = {"env": clean_child_env()}
        r = subprocess.run(
            cmd, input=input_text, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout, **kw,
        )
        if r.returncode != 0:
            # error seviyesi + tam stderr: eskiden 120 karakterlik uyarı
            # loglanıp "" dönülüyordu; kullanıcı 'başarılı ama boş sonuç'
            # alırdı ve teşhis için logda bir şey kalmazdı
            _logger.error("pandoc başarısız (rc=%s): %s", r.returncode,
                          (r.stderr or "").strip()[:300])
            return ""
        return r.stdout
    except Exception as e:
        _logger.error("pandoc çağrısı başarısız: %s", e, exc_info=True)
        return ""


def _pandoc_csljson(bib_path: str) -> str:
    """bib -> csljson metni (inline citation çözümü için)."""
    if PLATFORM == "win32":
        from core.paths import windows_to_wsl
        return _pandoc_run([windows_to_wsl(bib_path), "-t", "csljson"])
    return _pandoc_run([bib_path, "-t", "csljson"])


def _extract_refs_div(html: str) -> str:
    """citeproc HTML'indeki <div id="refs">...</div> bloğunu döndürür."""
    start = html.find('<div id="refs"')
    if start == -1:
        return ""
    depth, i = 0, start
    while i < len(html):
        if html[i:i + 4] == "<div":
            depth += 1
            i += 4
        elif html[i:i + 6] == "</div>":
            depth -= 1
            i += 6
            if depth == 0:
                break
        else:
            i += 1
    return html[start:i]


def _resolve_md_citations(md_path: str, tex_path: str, bib_path: str):
    r"""Markdown'daki [@key] citation'larını çöz ve referans listesi ekle.

    pandoc'un markdown writer'ı citeproc'u atladığı için (markdown doğal citation
    sözdizimine sahiptir) MD'de [@key] çözülmeden kalır ve referans listesi eklenmez.

    1) Inline [@key] -> (Yazar Yıl): .bib -> csljson ile her anahtar için kısa form.
    2) Referans listesi: pandoc citeproc HTML'indeki <div id="refs"> bloğu -> plain
       text. Bu, HTML/DOCX/TXT çıktısıyla aynı TAM referansları (tüm yazarlar, dergi,
       DOI) üretir — elle kurulan basit format yerine.
    """
    import json

    # --- 1) inline çözüm için csljson ---
    csljson = _pandoc_csljson(bib_path)
    by_id = {}
    if csljson:
        try:
            by_id = {e.get("id"): e for e in json.loads(csljson) if e.get("id")}
        except Exception:
            by_id = {}

    def _year(e):
        dp = (e.get("issued") or {}).get("date-parts") or []
        return str(dp[0][0]) if dp and dp[0] and dp[0][0] is not None else ""

    def _short(e):
        fams = [a.get("family", "") for a in (e.get("author") or []) if a.get("family")]
        if not fams:
            who = "Anon"
        elif len(fams) == 1:
            who = fams[0]
        elif len(fams) == 2:
            who = f"{fams[0]} and {fams[1]}"
        else:
            who = f"{fams[0]} et al."
        y = _year(e)
        return f"{who}{(' ' + y) if y else ''}"

    try:
        with open(md_path, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return

    def repl(m):
        inside = m.group(1)
        keys = re.findall(r"@([A-Za-z0-9_:+-]+)", inside)
        if not keys:
            return m.group(0)
        # Sadece @key(ler) ve ;/boşluk varsa değiştir; prefix/suffix varsa dokunma.
        stripped = re.sub(r"@[A-Za-z0-9_:+-]+", "", inside).replace(";", "").strip()
        if stripped:
            return m.group(0)
        shorts = []
        for k in keys:
            e = by_id.get(k)
            if e is None:
                return m.group(0)           # bilinmeyen anahtar → olduğu gibi bırak
            shorts.append(_short(e))
        return "(" + "; ".join(shorts) + ")"

    content = re.sub(r"\[([^\]]*@[^]]+)\]", repl, content)

    # --- 2) referans listesi: citeproc HTML -> refs div -> plain ---
    if PLATFORM == "win32":
        from core.paths import windows_to_wsl
        tex_arg = windows_to_wsl(tex_path)
        bib_arg = windows_to_wsl(bib_path)
    else:
        tex_arg, bib_arg = tex_path, bib_path
    html = _pandoc_run([tex_arg, "--bibliography=" + bib_arg, "--citeproc", "-t", "html"])
    refs_plain = ""
    if html:
        refs_div = _extract_refs_div(html)
        if refs_div:
            refs_plain = _pandoc_run(["-f", "html", "-t", "plain"], input_text=refs_div).strip()

    if refs_plain:
        content += "\n\n## References\n\n" + refs_plain + "\n"

    try:
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(content)
    except OSError as e:
        _logger.warning("MD citation çözme başarısız: %s", e)


def _rewrite_docx_member(docx_path: str, member: str, new_bytes: bytes):
    """docx zip'inde bir üyenin içeriğini değiştir (atomik rewrite)."""
    import zipfile
    tmp = docx_path + ".tmp"
    with zipfile.ZipFile(docx_path, 'r') as zin, \
         zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = new_bytes if item.filename == member else zin.read(item.filename)
            zout.writestr(item, data)
    os.replace(tmp, docx_path)


def _fix_docx_compat(docx_path: str):
    r"""Word'ün açamadığı docx sorunlarını düzelt:

    1) Boş-anchor hyperlink'leri (eksik figure `\ref'leri) sade metne çevirir.
    2) Tanımsız tablo stili referanslarını (pandoc 3.1.3 FigureTable bug'ı) tanımlı
       `Table' stiline yönlendirir. Word tanımsız stili reddedip dosyayı açamaz.
    """
    import zipfile
    try:
        with zipfile.ZipFile(docx_path) as z:
            names = z.namelist()
            if 'word/document.xml' not in names:
                return
            doc = z.read('word/document.xml').decode('utf-8')
            styles = z.read('word/styles.xml').decode('utf-8') if 'word/styles.xml' in names else ''
    except Exception:
        _logger.warning("docx uyumluluk düzeltmesi atlandı (zip okunamadı): %s",
                        docx_path, exc_info=True)
        return

    defined = set(re.findall(r'<w:style[^>]*w:styleId="([^"]+)"', styles))
    changed = False

    # 1) boş-anchor hyperlink'lerini sade metne çevir
    bookmarks = set(re.findall(r'<w:bookmarkStart[^>]*w:name="([^"]+)"', doc))

    def fix_hyperlink(m):
        nonlocal changed
        attrs, inner = m.group(1), m.group(2)
        am = re.search(r'w:anchor="([^"]+)"', attrs)
        if am and am.group(1) not in bookmarks:
            changed = True
            return inner
        return m.group(0)

    doc = re.sub(r'<w:hyperlink\b([^>]*)>(.*?)</w:hyperlink>', fix_hyperlink, doc, flags=re.DOTALL)

    # 2) tanımsız tablo stili -> tanımlı bir tablo stiline (tercihen "Table")
    table_styles = set(re.findall(r'<w:style[^>]*w:type="table"[^>]*w:styleId="([^"]+)"', styles))
    fallback = "Table" if "Table" in table_styles else (next(iter(table_styles)) if table_styles else None)

    def fix_tblstyle(m):
        nonlocal changed
        val = m.group(1)
        if val in defined:
            return m.group(0)
        changed = True
        return f'<w:tblStyle w:val="{fallback}" />' if fallback else ''

    doc = re.sub(r'<w:tblStyle\s+w:val="([^"]+)"\s*/>', fix_tblstyle, doc)

    if changed:
        try:
            _rewrite_docx_member(docx_path, 'word/document.xml', doc.encode('utf-8'))
        except Exception as e:
            _logger.warning("docx uyumluluk düzeltme başarısız: %s", e)


def _preprocess_tex(tex_path: str) -> str:
    r"""pandoc'un düşürdüğü abstract/title'ı gövdeye taşıyacak şekilde önişle.

    pandoc `\begin{abstract}'ı metadata'ya koyar (gövdeye değil) ve elsarticle'ın
    `\begin{frontmatter}' sarmalayıcısını bilmediği için içindeki `\title'/`\author'
    dahil her şeyi düşürür. Bu yüzden:
      - `\begin{frontmatter}'/`\end{frontmatter}' soyulur
      - `\title{X}' (ve `\title[short]{X}') → `\section*{X}'
      - `\begin{abstract}' → `\section*{Abstract}', `\end{abstract}' silinir
    Değişiklik yoksa orijinal dosyayı döndürür; varsa aynı dizinde geçici dosyaya
    yazar ve onun yolunu döndürür.
    """
    try:
        with open(tex_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except OSError:
        return tex_path

    original = content
    content = content.replace("\\begin{frontmatter}", "")
    content = content.replace("\\end{frontmatter}", "")
    content = re.sub(r'\\begin\s*\{abstract\}', r'\\section*{Abstract}', content)
    content = re.sub(r'\\end\s*\{abstract\}', '', content)
    # \title{X} veya \title[short]{X} -> \section*{X} (gövdeye başlık olarak)
    content = re.sub(r'\\title(?:\[[^\]]*\])?\{', lambda m: '\\section*{', content)

    if content == original:
        return tex_path

    # Mutlak yol: pandoc farklı cwd'de çalışabilir, göreli yol bulunamaz.
    tmp = os.path.abspath(tex_path) + ".export_tmp.tex"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(content)
        return tmp
    except OSError:
        return tex_path


def _find_bibliography(tex_path: str) -> str:
    r"""\bibliography{X} veya \addbibresource{X.bib} için .bib dosya yolunu döndür.

    Bulunamazsa veya .bib yoksa boş dize. pandoc'a --bibliography + --citeproc
    geçirilince citations çözülür ve referans listesi üretilir.
    """
    tex_dir = os.path.dirname(os.path.abspath(tex_path))
    try:
        with open(tex_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except OSError:
        return ""
    for pat in (r'\\addbibresource\s*\{([^}]+\.bib)\}', r'\\bibliography\s*\{([^}]+)\}'):
        m = re.search(pat, content)
        if not m:
            continue
        name = m.group(1).strip()
        if not name.endswith(".bib"):
            name += ".bib"
        cand = os.path.join(tex_dir, name)
        if os.path.isfile(cand):
            return cand
    return ""


def _fix_md_image_paths(tex_path: str, md_path: str):
    r"""Markdown'daki göreceli resim yollarını .tex dizinine göre mutlak yap.

    \graphicspath{{media/Bolum1/}} gibi LaTeX yol tanımlarını da hesaba katar.
    """
    tex_dir = os.path.dirname(os.path.abspath(tex_path))
    graphics_paths = _extract_graphics_paths(tex_path)

    try:
        with open(md_path, "r", encoding="utf-8") as f:
            content = f.read()

        import re

        def _replace(m):
            alt = m.group(1)
            path = m.group(2)
            if os.path.isabs(path) or path.startswith(("http://", "https://")):
                return f"![{alt}]({path})"
            # Adayları SIRAYLA dene ve diskte var olanı seç. Eskiden koşulsuz
            # graphics_paths[0] ekleniyordu: ikinci \graphicspath dizini hiç
            # denenmiyor, tam yol yazılmış görsel de 'media/media/logo.png'
            # oluyordu. Sonuç sessizce kırık bağlantıydı — yanlış yol istisna
            # üretmediği için aşağıdaki except da yakalamıyordu.
            adaylar = [gp + path for gp in graphics_paths] + [path]
            for aday in adaylar:
                for ek in ("", ".png", ".pdf", ".jpg", ".jpeg", ".eps"):
                    tam = os.path.normpath(os.path.join(tex_dir, aday + ek))
                    if os.path.isfile(tam):
                        return f"![{alt}]({tam.replace(os.sep, '/')})"
            # Hiçbiri diskte yok: eski davranışa düş (pandoc uzantısız yol
            # üretebiliyor; mutlaklaştırmak yine de bağıldan iyi).
            rel = (graphics_paths[0] + path) if graphics_paths else path
            abs_path = os.path.normpath(os.path.join(tex_dir, rel)).replace(os.sep, '/')
            return f"![{alt}]({abs_path})"

        # pandoc'un görsel niteliğini yalnız GÖRSEL sözdizimine bağlıyken
        # kaldır. Eski desen belge genelinde 'width' geçen her küme parantezli
        # bloğu siliyordu (metin içindeki {image width: 5cm} gibi örnekler dahil).
        content = re.sub(
            r'(!\[[^\]]*\]\([^)]+\))\s*\{[^}]*width[^}]*\}', r'\1', content)
        content = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', _replace, content)

        with open(md_path, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception as e:
        _logger.warning("MD resim yolu düzeltme başarısız: %s", e)


def _extract_graphics_paths(tex_path: str) -> list[str]:
    r"""\graphicspath{{dir1/}{dir2/}} içindeki yolları çıkar."""
    import re
    try:
        with open(tex_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        paths = []
        for m in re.finditer(r'\\graphicspath\s*\{(.+)\}', content):
            for inner in re.finditer(r'\{([^}]+)\}', m.group(1)):
                paths.append(inner.group(1))
        return paths
    except Exception:
        _logger.warning("graphicspath okunamadı: %s", tex_path, exc_info=True)
        return []


def _pandoc_args(tex_path: str, dest_path: str, bib: str = "") -> list[str]:
    """Format'a göre pandoc argümanlarını oluştur."""
    work_dir = os.path.dirname(os.path.abspath(tex_path))
    args = ["pandoc", tex_path, "-o", dest_path, f"--resource-path={work_dir}"]
    ext = os.path.splitext(dest_path)[1].lower()
    if ext == ".html":
        args += ["--standalone", "--embed-resources"]
    elif ext == ".txt":
        # pandoc .txt'yi varsayılan olarak markdown işler; gerçek plain text iste
        # (ayrıca plain text citation-aware olmadığından citeproc burada çözülür)
        args += ["-t", "plain"]
    if bib:
        args += ["--bibliography=" + bib, "--citeproc"]
    return args


def _export_native(tex_path: str, dest_path: str, bib: str = "") -> tuple[bool, str]:
    work_dir = os.path.dirname(os.path.abspath(tex_path))
    try:
        r = subprocess.run(
            _pandoc_args(tex_path, dest_path, bib),
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=30,
            cwd=work_dir, env=clean_child_env(),
        )
        if r.returncode != 0:
            _logger.warning("Export başarısız (native): %s → %s — %s", tex_path, dest_path, r.stderr)
            return False, r.stderr.strip() or "Dışa aktarma başarısız"
        return True, ""
    except subprocess.TimeoutExpired:
        return False, "İşlem zaman aşımına uğradı"
    except FileNotFoundError:
        return False, "pandoc bulunamadı — lütfen kurun (apt install pandoc)"
    except Exception as e:
        return False, str(e)


def _export_wsl(tex_path: str, dest_path: str, bib: str = "") -> tuple[bool, str]:
    from core.paths import windows_to_wsl

    wsl_tex = windows_to_wsl(tex_path)
    wsl_dir = os.path.dirname(wsl_tex)
    # pid eki: aynı hedef adına art arda/çakışan çağrılar WSL'de birbirinin
    # ara çıktısını ezmesin. ntpath: dest_path Windows yoludur; posix basename
    # ters bölüleri ayırmaz.
    import ntpath
    tmp_dest = f"/tmp/export_{os.getpid()}_{ntpath.basename(dest_path)}"

    # pandoc argümanlarını oluştur
    pandoc_cmd = ["pandoc", wsl_tex, "-o", tmp_dest, f"--resource-path={wsl_dir}"]
    ext = os.path.splitext(dest_path)[1].lower()
    if ext == ".html":
        pandoc_cmd += ["--standalone", "--embed-resources"]
    elif ext == ".txt":
        pandoc_cmd += ["-t", "plain"]
    if bib:
        pandoc_cmd += ["--bibliography=" + windows_to_wsl(bib), "--citeproc"]

    try:
        quoted = " ".join(shlex.quote(a) for a in pandoc_cmd)
        r = subprocess.run(
            ["wsl", "-e", "bash", "-c",
             f"cd {shlex.quote(wsl_dir)} && {quoted}"],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=30,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        if r.returncode != 0:
            _logger.warning("Export başarısız (WSL): %s → %s — %s", tex_path, dest_path, r.stderr)
            return False, r.stderr.strip() or "Dışa aktarma başarısız"

        # Çıktıyı WSL'den Windows'a kopyala
        r2 = subprocess.run(
            ["wsl", "-e", "cp", tmp_dest, windows_to_wsl(dest_path)],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=10,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        if r2.returncode != 0:
            # cp başarısız — WSL'den okuyup Python ile yaz
            r3 = subprocess.run(
                ["wsl", "-e", "cat", tmp_dest],
                capture_output=True, timeout=10,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
            )
            if r3.returncode == 0:
                with open(dest_path, "wb") as f:
                    f.write(r3.stdout)
            else:
                return False, "Çıktı dosyası kopyalanamadı"

        return True, ""
    except subprocess.TimeoutExpired:
        return False, "İşlem zaman aşımına uğradı"
    except Exception as e:
        return False, str(e)
    finally:
        subprocess.run(
            ["wsl", "-e", "rm", "-f", tmp_dest],
            capture_output=True, timeout=5,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )

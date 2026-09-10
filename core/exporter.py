"""LaTeX dışa aktarma — pandoc ile format dönüşümü."""

import os
import re
import shlex
import shutil
import subprocess
import sys

from core.log import get_logger
from core.paths import clean_child_env, windows_to_wsl
from core.latex_refs import bildirimleri_ara, find_bib_paths
# Çözücü zinciri (utf-8 -> cp1254 -> iso-8859-9) `core.fs_ops`ta; buradaki
# ad `project_search`ten alınıyor çünkü modülün dışa açık yüzeyi orası.
# Modül düzeyinde alınıyor: üç ayrı yerde gerekiyor ve zincir yalnız
# stdlib'e dayanıyor, döngü ya da açılış maliyeti yok.
from core.project_search import coz

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
    bibs = _find_bibliography(tex_path)
    tmp_tex = _preprocess_tex(tex_path)
    # Uzantı KÜÇÜK HARFE çevrilerek karşılaştırılır, `_pandoc_args` zaten
    # öyle yapıyordu; burada `endswith(".md")` deniyordu ve aynı dosyada iki
    # ayrı kural vardı. Kullanıcı hedefi 'rapor.MD' diye yazınca (uzantı
    # Windows'ta harf duyarsız) pandoc dosyayı markdown üretiyor ama son
    # işlemler ATLANIYORDU. Ölçüldü, .MD çıktısında: resim yolları göreli
    # kalıyor (bağlantılar kırık), `[@anahtar]` çözülmüyor ve References
    # bölümü hiç eklenmiyor.
    hedef_ext = os.path.splitext(dest_path)[1].lower()
    ok, err = False, ""
    try:
        if PLATFORM == "win32":
            ok, err = _export_wsl(tmp_tex, dest_path, bibs)
        else:
            ok, err = _export_native(tmp_tex, dest_path, bibs)
        if ok and hedef_ext == ".md":
            _fix_md_image_paths(tex_path, dest_path)
            if bibs:
                # tmp_tex citeproc referans üretimi için lazım; silinmeden önce çağır.
                _resolve_md_citations(dest_path, tmp_tex, bibs)
        elif ok and hedef_ext == ".docx":
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

    return ok, _hata_mesaji_duzelt(err, tex_path, tmp_tex)


def _hata_mesaji_duzelt(mesaj: str, tex_path: str, tmp_tex: str) -> str:
    r"""pandoc hatasını kullanıcının GERÇEKTEN okuyabileceği tek satıra indir.

    Mesaj durum çubuğuna basılıyor (file_ops._on_export_done) ve çubuk tek
    satırlık. ÖLÇÜLDÜ (2026-09-09, 39 gerçek şablonun 7'si pandoc'un LaTeX
    ayrıştırıcısını aşıyor): mesajların 6'sı hem `main.tex.export_tmp.tex`
    diye bir dosya adı hem `/mnt/c/...` WSL yolu taşıyor ve 2-4 satır uzun.

      Error at "/mnt/c/Users/.../main.tex.export_tmp.tex" (line 7, column 17):
      unexpected ()
      \begin{document}\sloppy
                      ^

    O dosya bizim ara ürünümüz, `export`un `finally` bloğunda siliniyor:
    kullanıcı adını arayıp bulamıyor. Çubuğa da yalnız baştaki yol sığıyor,
    yani işe yarayan kısım (satır/sütun ve hatalı yapı) hiç görünmüyordu.

    Sonrası: `Error at "main.tex" (line 7, column 17): unexpected ()
    \begin{document}\sloppy`

    Tam metin log'da duruyor (`_export_wsl`/`_export_native` uyarısı).
    """
    if not mesaj:
        return mesaj
    ad = os.path.basename(tex_path)
    adaylar = {tex_path, os.path.abspath(tex_path)}
    if tmp_tex and tmp_tex != tex_path:
        adaylar |= {tmp_tex, os.path.abspath(tmp_tex)}
    for yol in list(adaylar):
        adaylar.add(yol.replace("\\", "/"))
        adaylar.add(windows_to_wsl(yol))
    # UZUN olan ÖNCE: `.../main.tex` önce değiştirilirse geriye
    # `main.tex.export_tmp.tex` kalır, yani asıl kafa karıştıran ad durur.
    for yol in sorted(adaylar, key=len, reverse=True):
        if yol:
            mesaj = mesaj.replace(yol, ad)
    # Yalnız `^` işaretinden oluşan satır tek satıra indirilince anlamsız.
    satirlar = [s for s in mesaj.splitlines() if s.strip().strip("^").strip()]
    return " ".join(" ".join(satirlar).split())


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


def _pandoc_csljson(bibs) -> str:
    r"""bib dosyaları -> csljson metni (inline citation çözümü için).

    pandoc birden çok girdiyi birleştiriyor, yani `\bibliography{a,b}`
    yazan belgede iki dosyanın kayıtları da tek csljson'da geliyor.
    """
    bibs = _bib_listesi(bibs)
    if not bibs:
        return ""
    if PLATFORM == "win32":
        yollar = [windows_to_wsl(b) for b in bibs]
    else:
        yollar = list(bibs)
    return _pandoc_run(yollar + ["-t", "csljson"])


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


_REFS_BASLIK = {"tr_TR": "Kaynakça", "en_US": "References"}


def _refs_basligi(tex_path: str) -> str:
    """Markdown'a eklenen kaynakça başlığı, BELGENİN dilinde.

    Bu başlık pandoc'tan GELMİYOR, kodun kendisi ekliyor: markdown writer'ı
    citeproc'u atladığı için referans listesini `_resolve_md_citations`
    kuruyor ve başlıksız bir liste okunmaz olurdu. Öteki biçimlerde
    (HTML/DOCX/TXT) citeproc listeyi kendisi üretiyor ve başlık EKLEMİYOR;
    yani bu, çıktıdaki tek "bizim yazdığımız" metin.

    Sabit `## References` yazılıydı. ÖLÇÜLDÜ (2026-09-08, gerçek pandoc ile),
    `\\usepackage[turkish]{babel}` bildiren bir belgeyi .md'ye aktarınca:
    baştan sona Türkçe metnin ortasına İngilizce `## References` düşüyor.

    Dil belgeden okunuyor (`core.yazim.belgeden_dil`: `% !TEX spellcheck`,
    ana dil bildirimi, babel; babel'de SON seçenek ana dil). Belge dilini
    bildirmiyorsa `References` kalıyor: bugünkü davranış korunuyor ve
    uydurma bir dil seçilmiyor.
    """
    try:
        with open(tex_path, "r", encoding="utf-8", errors="replace") as f:
            kaynak = f.read()
    except OSError:
        return "References"
    from core.yazim import belgeden_dil
    return _REFS_BASLIK.get(belgeden_dil(kaynak) or "", "References")


def _resolve_md_citations(md_path: str, tex_path: str, bibs=()):
    r"""Markdown'daki [@key] citation'larını çöz ve referans listesi ekle.

    pandoc'un markdown writer'ı citeproc'u atladığı için (markdown doğal citation
    sözdizimine sahiptir) MD'de [@key] çözülmeden kalır ve referans listesi eklenmez.

    1) Inline [@key] -> (Yazar Yıl): .bib -> csljson ile her anahtar için kısa form.
    2) Referans listesi: pandoc citeproc HTML'indeki <div id="refs"> bloğu -> plain
       text. Bu, HTML/DOCX/TXT çıktısıyla aynı TAM referansları (tüm yazarlar, dergi,
       DOI) üretir — elle kurulan basit format yerine.
    """
    import json

    bibs = _bib_listesi(bibs)
    # --- 1) inline çözüm için csljson ---
    csljson = _pandoc_csljson(bibs)
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

    # Grubun İÇİNDE `[` YASAK: en İÇTEKİ köşeli parantezle eşleşelim.
    # `[^\]]*` açılış köşeliyi de yutuyordu, yani Markdown resim
    # başlığındaki atıf `![... [@key].](yol)` biçiminde eşleşince grup
    # `... [@key` oluyor, önek varmış gibi görünüyor ve yukarıdaki
    # `stripped` dalı atıfa DOKUNMUYORDU. ÖLÇÜLDÜ (2026-09-10, atıf ve
    # .bib içeren 15 gerçek şablon uçtan uca pandoc'a verildi):
    # çözülemeyen sekiz gruptan yedisi BİLEREK öyle (dördü .bib'de
    # olmayan anahtar, üçü önek/sonek taşıyor: `[e.g. @k]`,
    # `[@k 162]`), sekizincisi tam bu iç içe durum ve `.md` çıktısında
    # şekil başlığında ham `[@PFGPlots]` görünüyordu.
    #
    # Daralttığı için önek/sonek kolunu BOZMUYOR: o gruplarda `[` yok.
    content = re.sub(r"\[([^\[\]]*@[^\[\]]+)\]", repl, content)

    # --- 2) referans listesi: citeproc HTML -> refs div -> plain ---
    if PLATFORM == "win32":
        tex_arg = windows_to_wsl(tex_path)
        bib_args = [windows_to_wsl(b) for b in bibs]
    else:
        tex_arg, bib_args = tex_path, list(bibs)
    html = _pandoc_run([tex_arg] + ["--bibliography=" + b for b in bib_args]
                       + ["--citeproc", "-t", "html"])
    refs_plain = ""
    if html:
        refs_div = _extract_refs_div(html)
        if refs_div:
            refs_plain = _pandoc_run(["-f", "html", "-t", "plain"], input_text=refs_div).strip()

    if refs_plain:
        content += ("\n\n## " + _refs_basligi(tex_path) + "\n\n"
                    + refs_plain + "\n")

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


# Stil etiketini bir kez yakala, nitelikleri ETİKETİN İÇİNDE ara: OOXML
# nitelik SIRASINI garanti etmiyor.
_RE_STIL_ETIKETI = re.compile(r'<w:style\b[^>]*>')
_RE_STIL_KIMLIGI = re.compile(r'w:styleId="([^"]+)"')
_RE_STIL_TURU = re.compile(r'w:type="([^"]+)"')


def _tablo_stilleri(styles_xml: str) -> set:
    """`styles.xml`de TABLO türünde tanımlı stil kimlikleri.

    Burada iki ayrı desen vardı ve biri sıraya bağlıydı:

        r'<w:style[^>]*w:type="table"[^>]*w:styleId="([^"]+)"'   tablo
        r'<w:style[^>]*w:styleId="([^"]+)"'                      hepsi

    İlki `w:type`ı `w:styleId`den ÖNCE bekliyor. GERÇEK pandoc 3.1.3
    çıktısı tersini yazıyor (ölçüldü 2026-09-10):

        <w:style w:default="1" w:styleId="Table" w:type="table">

    Yani tablo kümesi HER ZAMAN boş, ikinci desen ise doğru çalışıyordu:
    aynı bilgi iki desende, biri bozuk. Tek geçiş, tek kaynak.
    """
    tablo = set()
    for m in _RE_STIL_ETIKETI.finditer(styles_xml):
        etiket = m.group(0)
        km = _RE_STIL_KIMLIGI.search(etiket)
        tm = _RE_STIL_TURU.search(etiket)
        if km and tm and tm.group(1) == "table":
            tablo.add(km.group(1))
    return tablo


def _fix_docx_compat(docx_path: str):
    r"""Word'ün açamadığı docx sorunlarını düzelt:

    1) Boş-anchor hyperlink'leri (eksik figure `\ref'leri) sade metne çevirir.
    2) Tanımsız tablo stili referanslarını (pandoc 3.1.3 FigureTable bug'ı) tanımlı
       `Table' stiline yönlendirir. Word tanımsız stili reddedip dosyayı açamaz.

    İKİNCİSİ HİÇ ÇALIŞMIYORDU. Tanımlı tablo stillerini bulan desen sıraya
    bağlıydı (bkz. `_tablo_stilleri`), küme her zaman boş kalıyor ve
    `fallback` her zaman None oluyordu; tanımsız stil YÖNLENDİRİLMİYOR,
    SİLİNİYORDU. ÖLÇÜLDÜ (2026-09-10): gerçek bir çıktıya pandoc'un
    hatası taklit edilip `FigureTable` sokuldu, düzeltmeden sonra belgede
    HİÇ `<w:tblStyle>` kalmadı (0 etiket), oysa `Table`a dönmesi
    gerekiyordu. Sonuç sessiz: tablo biçimini kaybediyor ama Word dosyayı
    açtığı için kimse fark etmiyor.

    Geçerlilik denetimi de TABLO türüne bakıyor artık, "herhangi bir stil
    tanımlı mı"ya değil: `w:tblStyle` yalnız tablo stiline işaret
    edebilir, paragraf stili adına işaret eden bir referansı Word yine
    reddederdi. Gerçek veride davranış DEĞİŞMİYOR (49 çıktının 34'ünde tek
    kullanılan stil `Table`, o da tablo türünde).
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

    table_styles = _tablo_stilleri(styles)
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
    # `sorted`, `next(iter(...))` değil: küme sırası koşudan koşuya
    # değişiyor, aynı belgeden iki farklı çıktı üretirdi.
    fallback = "Table" if "Table" in table_styles else (
        sorted(table_styles)[0] if table_styles else None)

    def fix_tblstyle(m):
        nonlocal changed
        val = m.group(1)
        if val in table_styles:
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
    # KODLAMAYI ÇÖZ, `errors="replace"` ile okuma. Burası dosyayı yeniden
    # YAZAN tek yer: cp1254/iso-8859-9 bir .tex `replace` ile okununca her
    # Türkçe harf U+FFFD oluyor ve o hâliyle geçici dosyaya yazılıyordu.
    # Ölçüldü: başlıklı bir cp1254 belgede dışa aktarma BAŞARILI dönüyor
    # ama çıktıda 28 değiştirme karakteri var ve 'Öztürk' hiç yok. Önişleme
    # tetiklenmeyen belgelerde bozulma yoktu, yani kusuru üreten tam da
    # çıktıyı iyileştirmek için yapılan bu adımdı.
    try:
        with open(tex_path, "rb") as f:
            content = coz(f.read())
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


def _find_bibliography(tex_path: str) -> list[str]:
    r"""\bibliography{X} veya \addbibresource{X.bib} için .bib yollarını döndür.

    Bulunamazsa boş liste. pandoc'a her dosya için ayrı --bibliography ve
    --citeproc geçirilince citations çözülür ve referans listesi üretilir.

    LİSTE, tek yol değil: `\bibliography{kaynaklar,ek}` yazmak LaTeX'te
    geçerli ve yaygın. Eskiden dönüş tek dizeydi, virgüllü ad `kaynaklar,ek.bib`
    diye aranıyor, diskte bulunamıyor ve "" dönüyordu. ÖLÇÜLDÜ (2026-09-06,
    gerçek pandoc 3.1.3 ile uçtan uca): dışa aktarma BAŞARILI dönüyor ama
    çıktıda kaynakça HİÇ YOK; `<div id="refs">` de üretilmiyor.

    ARAMANIN KENDİSİ core.latex_refs'te, burada KOPYASI YOK. Burada kendi
    uygulaması vardı ve iki taraf birbirinin dersini taşımıyordu; ÖLÇÜLDÜ
    (2026-09-09, 39 gerçek şablon): buradaki uygulama `\input` zincirini ve
    sınıf dosyasını taramadığı için iki tez şablonunda (template33-tez,
    template4) kaynakça HİÇ bulunamıyor, DOCX/HTML kaynakçasız çıkıyordu.
    Ters yönde de eksik vardı: virgüllü listeyi yalnız burası biliyordu.
    """
    # Çözücü zinciri: cp1254 bir .tex'te Türkçe adlı bir .bib
    # (`\bibliography{kaynakça}`) `replace` okumasıyla bozuluyor, dosya
    # diskte bulunamıyor ve "" dönüyordu. Sonuç: kaynakça HİÇ çözülmüyor,
    # referans listesi üretilmiyor (ölçüldü). Yorumların ayıklanması ve
    # zincir/sınıf taraması `find_bib_paths` içinde.
    try:
        with open(tex_path, "rb") as f:
            content = coz(f.read())
    except OSError:
        return []
    return find_bib_paths(content, tex_path)


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


# `\graphicspath{{a/}{b/}}`. Gövde YALNIZ süslü gruplardan (ve boşluktan)
# oluşuyor; `\graphicspath` söz dizimi tam bu. Eskiden dış desen `(.+)`
# ile yazılıydı, yani SATIR SONUNU GEÇMİYORDU: birden çok dizini alt alta
# yazan biçim (gerçek şablonda var, template1) hiç okunmuyordu.
#
#     \graphicspath{
#         {./Figures/}
#         {./logo/}
#     }
#
# `re.S` ve `\s*` ile ikisi de okunuyor; girintideki bölünmez boşluk
# (U+00A0, o dosyada birebir bu var) `\s`ye giriyor.
_RE_GRAPHICSPATH = re.compile(
    r'\\graphicspath\s*\{((?:\s*\{[^{}]*\})+)\s*\}', re.S)


def _graphicspath_bildirimleri(metin: str, _bdir: str) -> list[str]:
    r"""Metindeki `\graphicspath` dizinleri. `bildirimleri_ara` imzası.

    Yoruma alınmış bir `\graphicspath` dizin değil örnektir; yorumları
    çağıran soyuyor (`bildirimleri_ara` ve zincir/sınıf kolları
    `strip_comments`ten geçiriyor). ÖLÇÜLDÜ (2026-09-06):
    `% \graphicspath{{eski/}}` satırı listeye 'eski/' ekliyordu ve
    `_fix_md_image_paths` adayları SIRAYLA denediği için o dizin gerçek
    olandan ÖNCE deneniyordu.
    """
    paths = []
    for m in _RE_GRAPHICSPATH.finditer(metin):
        for inner in re.finditer(r'\{([^{}]*)\}', m.group(1)):
            if inner.group(1):
                paths.append(inner.group(1))
    return paths


def _extract_graphics_paths(tex_path: str) -> list[str]:
    r"""\graphicspath{{dir1/}{dir2/}} içindeki yolları çıkar.

    ARAMA ÜÇ DÜZEYLİ (`latex_refs.bildirimleri_ara`): belge, `\input`
    zinciri, sonra `.cls`/`.sty`. Burada yalnız belgeye bakılıyordu ve
    ÖLÇÜLDÜ (2026-09-10, 59 gerçek ana .tex dosyası uçtan uca pandoc'a
    verildi): template28-book1'de bildirim `LegrandOrangeBook.cls` içinde,
    görseller `Images/` altında ve dışa aktarılan Markdown'da ÜÇ görselin
    bağı kırık çıkıyordu. Dışa aktarma "başarılı" dönüyor, kusur ancak
    dosya açılınca görünüyor.

    `.bib` araması aynı üç düzeyi 2026-09-09'da öğrenmişti; aynı dosyada,
    bir işlev ötede duran bu arama öğrenmemiş.
    """
    try:
        # Çözücü zinciri: `\graphicspath{{şekiller/}}` cp1254 bir belgede
        # `replace` okumasıyla bozuluyor ve o dizindeki hiçbir görsel
        # bulunamıyordu (ölçüldü: 'şekiller/' yerine '�ekiller/').
        with open(tex_path, "rb") as f:
            content = coz(f.read())
        return bildirimleri_ara(content, tex_path,
                                _graphicspath_bildirimleri)
    except Exception:
        _logger.warning("graphicspath okunamadı: %s", tex_path, exc_info=True)
        return []


def _bib_listesi(bibs) -> list[str]:
    """`bibs` her zaman liste olsun.

    Dize de ITERE EDİLEBİLİR: `for b in bibs` tek bir yol verildiğinde onu
    KARAKTERLERE bölüp `--bibliography=/`, `--bibliography=x` ... üretirdi.
    pandoc bunlara "dosya yok" demeden devam ettiği için hata sessiz kalır,
    yalnız kaynakça kaybolurdu. Ölçüldü: `_find_bibliography` liste dönmeye
    başlayınca eski imzayla yazılmış üç test tam bu şekilde düştü.
    """
    if isinstance(bibs, str):
        return [bibs] if bibs else []
    return list(bibs)


def _bicim_argumanlari(dest_path: str, bibs=()) -> list[str]:
    """Hedef biçimine göre pandoc seçenekleri. BU KURALIN TEK KAYNAĞI.

    Yollar iki yolda farklı (native Windows/Linux yolu kullanıyor, WSL yolu
    `/mnt/...` istiyor) ama BİÇİM kuralı aynı ve iki yerde kopyalanmıştı:
    `_pandoc_args` ile `_export_wsl` aynı üç dalı ayrı ayrı yazıyordu. Bu
    depo yinelenen paketleme/uzantı tanımından birkaç kez yandı; burada
    henüz ayrışmamışken tek kaynağa alındı.
    """
    bibs = _bib_listesi(bibs)
    args = []
    ext = os.path.splitext(dest_path)[1].lower()
    if ext == ".html":
        args += ["--standalone", "--embed-resources"]
    elif ext == ".txt":
        # pandoc .txt'yi varsayılan olarak markdown işler; gerçek plain text iste
        # (ayrıca plain text citation-aware olmadığından citeproc burada çözülür)
        args += ["-t", "plain"]
    for b in bibs:
        args += ["--bibliography=" + b]
    if bibs:
        args += ["--citeproc"]
    return args


def _pandoc_args(tex_path: str, dest_path: str, bibs=()) -> list[str]:
    """Format'a göre pandoc argümanlarını oluştur."""
    work_dir = os.path.dirname(os.path.abspath(tex_path))
    return (["pandoc", tex_path, "-o", dest_path, f"--resource-path={work_dir}"]
            + _bicim_argumanlari(dest_path, bibs))


def _export_native(tex_path: str, dest_path: str, bibs=()) -> tuple[bool, str]:
    work_dir = os.path.dirname(os.path.abspath(tex_path))
    try:
        r = subprocess.run(
            _pandoc_args(tex_path, dest_path, bibs),
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=30,
            cwd=work_dir, env=clean_child_env(),
        )
        if r.returncode != 0:
            _logger.warning("Export başarısız (native): %s → %s (%s)", tex_path, dest_path, r.stderr)
            return False, r.stderr.strip() or "Dışa aktarma başarısız"
        return True, ""
    except subprocess.TimeoutExpired:
        return False, "İşlem zaman aşımına uğradı"
    except FileNotFoundError:
        return False, "pandoc bulunamadı, lütfen kurun (apt install pandoc)"
    except Exception as e:
        return False, str(e)


def _export_wsl(tex_path: str, dest_path: str, bibs=()) -> tuple[bool, str]:
    wsl_tex = windows_to_wsl(tex_path)
    wsl_dir = os.path.dirname(wsl_tex)
    # pid eki: aynı hedef adına art arda/çakışan çağrılar WSL'de birbirinin
    # ara çıktısını ezmesin. ntpath: dest_path Windows yoludur; posix basename
    # ters bölüleri ayırmaz.
    import ntpath
    tmp_dest = f"/tmp/export_{os.getpid()}_{ntpath.basename(dest_path)}"

    # Biçim kuralı `_bicim_argumanlari`de; burada yalnız YOLLAR farklı.
    pandoc_cmd = (["pandoc", wsl_tex, "-o", tmp_dest,
                   f"--resource-path={wsl_dir}"]
                  + _bicim_argumanlari(dest_path,
                                       [windows_to_wsl(b) for b in bibs]))

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
            _logger.warning("Export başarısız (WSL): %s → %s (%s)", tex_path, dest_path, r.stderr)
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

"""LaTeX derleme çıktısını parse etme — hatalar ve uyarıları ayıklama."""

import os
import re
from dataclasses import dataclass, field

from core.engine_detector import MOTOR_TAKMA_ADLARI


@dataclass
class LatexError:
    line_number: int = 0
    message: str = ""
    context: str = ""
    file_path: str = ""


@dataclass
class LatexWarning:
    line_number: int = 0
    message: str = ""
    warning_type: str = ""
    file_path: str = ""


@dataclass
class LatexSuggestion:
    message: str = ""
    install_command: str = ""


@dataclass
class CompileResult:
    success: bool = False
    pdf_path: str = ""
    errors: list[LatexError] = field(default_factory=list)
    warnings: list[LatexWarning] = field(default_factory=list)
    suggestions: list[LatexSuggestion] = field(default_factory=list)
    raw_output: str = ""
    duration: float = 0.0


# Hata satırı: "! Undefined control sequence." vb.
_RE_ERROR = re.compile(r'^\s*! (.+)')
# `-file-line-error` biçimi: "./bolum/ch1.tex:3: Undefined control sequence."
# Dosya adı BOŞLUK taşıyabiliyor, o yüzden ada boşluk serbest; ayırt edici
# olan `:<sayı>: ` üçlüsü. Uzantı zorunlu tutuluyor ki "Package foo: 3: ..."
# gibi düz yazı hata sanılmasın.
_RE_FILE_LINE_ERROR = re.compile(
    r'^\s*(\S[^:]*\.[A-Za-z0-9]+):(\d+): (.+)')
# Paket hatası: "! Package babel Error: ..."
_RE_PKG_ERROR = re.compile(r'^\s*! Package (\S+) Error: (.+)')
# Satır numarası bağlamı: "l.42 \badcommand"
_RE_LINE_CTX = re.compile(r'^\s*l\.(\d+)')
# Uyarı satır numarası: "on input line 42" veya "on lines 5--10"
_RE_WARN_LINE = re.compile(r'(?:on|at) (?:input )?lines? (\d+)')
# LaTeX uyarısı. `LaTeX Font Warning:` AYRI bir başlık ve desene girmiyordu:
# yazı tipi biçimi yokken LaTeX sessizce başkasını koyuyor, derleme başarılı
# bitiyor ve kullanıcı ancak PDF'e bakınca fark ediyor. ÖLÇÜLDÜ (2026-09-14):
# 55 gerçek belgenin 18'inde toplam 199 satır, hepsi görünmezdi.
#
# Devam satırı (`(Font)    using ... instead on input line 9.`) BİLEREK
# dışarıda: `(natbib)` gibi paket devam satırları da öteden beri panele
# çıkmıyor, tek satırlık kural korunuyor.
_RE_LATEX_WARN = re.compile(r'^\s*LaTeX( Font)? Warning: (.+)')
# Paket uyarısı
_RE_PKG_WARN = re.compile(r'^\s*Package (\S+) Warning: (.+)')
# Motor uyarısı: "pdfTeX warning (ext4): destination ... duplicate ignored" vb.
# Çift \label tespiti (error_hints duplicate_label ipucu) bu satırdan gelir.
#
# LuaTeX KENDİ ADINI YAZMIYOR: "warning  (pdf backend): ignoring duplicate
# destination with the name 'figure.9'". Motor adı zorunluyken bu biçim hiç
# eşleşmiyordu, yani aynı kusur pdflatex'te uyarı üretiyor, uygulamanın
# VARSAYILAN motoru lualatex'te hiç üretmiyordu. ÖLÇÜLDÜ (2026-09-14): 55
# belgenin 17'sinde 358 satır; panele ulaşan sayısı sıfırdı.
_RE_ENGINE_WARN = re.compile(
    r'^\s*(?:(pdfTeX|LuaTeX|XeTeX) warning|warning\s+\([^)]*\))[^:]*:\s*(.+)',
    re.IGNORECASE)
# Overfull/Underfull
_RE_BOX_WARN = re.compile(r'^\s*(Overfull|Underfull) \\\w+ .+')
# Font uyarısı
_RE_FONT_WARN = re.compile(r'^\s*Font .+ not loadable')
# "Missing character: There is no ş (U+015F) in font ec-lmr10!"
#
# XeLaTeX/LuaLaTeX + [T1]{fontenc} birleşiminde Türkçeye özgü harfler PDF'e
# yazılmadan atlanıyor ve derleme BAŞARILI bitiyor. Kullanıcı okuyana kadar
# fark etmiyor, o yüzden panele çıkması gerek (ipucu error_hints'te).
#
# TEK TEK EKLENMEZ: belge başına yüzlerce, binlerce satır geliyor. Ölçüldü:
# demo belgemizde 149, template36-ders'te 8226. Hepsini listelemek Uyarılar
# sekmesini kullanılmaz yapardı. Yazı tipi başına TEK uyarı üretilip kaç kez
# geçtiği yazılıyor; mesaj ilk gerçek satırı koruyor ki error_hints'teki
# desen yazı tipi adını çıkarabilsin.
_RE_MISSING_GLYPH = re.compile(
    r'^\s*Missing character: There is no .+? in font ([^\s!]+)')
# derle.sh TEKRARLAYAN uyarı sınıflarını tekilleştirip tekrar sayısını
# satırın SONUNA `(x149)` diye yazıyor (satır başı değişmiyor, çünkü üç
# sınıfın da deseni satır başına çapalı). Sayı olmayan satır bir kez geçmiş
# demektir.
_RE_TEKRAR_SAYISI = re.compile(r'\s*\(x(\d+)\)\s*$')


def _tekrar_ayir(satir: str) -> tuple[str, int]:
    """`... (x149)` -> (`...`, 149); eki yoksa (satır, 1)."""
    m = _RE_TEKRAR_SAYISI.search(satir)
    if not m:
        return satir, 1
    return satir[:m.start()], int(m.group(1))
# Öneri: ==> Eksik paketi: ... veya ==> Eksik dil paketi: ...
_RE_SUGGESTION = re.compile(r'^==>\s*(Eksik (?:dil )?paket[ie]?): (.+)')
# Kurulum komutu: "    sudo apt-get install ..." (Linux/WSL) ya da macOS
# karşılıkları. Komut BÜTÜN olarak yakalanıp aynen taşınıyor; eskiden
# `apt-get install` soyulup yeniden KURULUYORDU, o yüzden başka bir
# paket yöneticisinin komutu buradan geçemezdi.
#
# Windows davranışı DEĞİŞMİYOR: orada derle.sh WSL'in içinde koşuyor ve
# satır yine `sudo apt-get install ...` geliyor, yakalanan da o.
_RE_INSTALL = re.compile(
    r'^\s+((?:sudo )?(?:apt-get|tlmgr|brew|pip3) (?:install|search) .+)')
# Motor gereksinimi: hata mesajında "requires LuaLaTeX" vb.
# Alternatifler EŞLEMİN ANAHTARLARINDAN kuruluyor, elle YAZILMIYOR: ikisi ayrı
# yazıldığında desen `pdfTeX`i yakalıyor ama eşlem tanımıyordu ve kullanıcıya
# gereksinimin tersi söyleniyordu (gerekçe ve ölçüm engine_detector'da).
# Uzundan kısaya: alternatiflerden biri diğerinin önekiyse kısası önce
# eşleşmesin.
#
# "requires EITHER X or Y" biçimi de tanınıyor. fontspec'in kendi hatası tam
# olarak bu ("The fontspec package requires either XeTeX or LuaTeX.") ve
# desen motor adını `requires`ın HEMEN ardında beklediği için hiç
# eşleşmiyordu. ÖLÇÜLDÜ (2026-09-23, gerçek derle.sh, pdflatex): fontspec
# yükleyen belgede öneri sayısı 0'dı; önerinin var olma sebebi tam bu durum.
_MOTOR_ADI = '(' + '|'.join(sorted(MOTOR_TAKMA_ADLARI, key=len,
                                    reverse=True)) + ')'
_RE_ENGINE_REQ = re.compile(
    r'requires\s+(?:either\s+)?' + _MOTOR_ADI + r'(?:\s+or\s+' + _MOTOR_ADI
    + r')?', re.IGNORECASE)
# derle.sh'nin KENDİ hataları: "[hata] lualatex kurulu değil — derlenemedi".
# Bunlar LaTeX log'u değil betik çıktısı, o yüzden yukarıdaki '! ' desenleri
# hiçbirini görmüyordu: motor kurulu değilken, dosya bulunamazken veya PDF hiç
# oluşmazken panel "Başarısız — 0 hata" diyor, ayrıştırıcı success=True
# döndürüyordu — kullanıcıya sebebi söyleyen tek satır kayıptı.
_RE_SCRIPT_ERROR = re.compile(r'^\s*\[hata\]\s*(.+?)\s*$')

# Kaynakça aracının (bibtex/biber) KENDİ satırları. Bunlar LaTeX günlüğü
# değil, derle.sh'nin bastığı ayrı bir blok ve yukarıdaki desenlerin
# hiçbiri onları görmüyordu: kaynakça çökse bile panelde tek satır
# çıkmıyor, derleme 0 ile bitiyor ve PDF'te kaynakça BOŞ kalıyordu.
#
# ÖLÇÜLDÜ (2026-09-15, gerçek bibtex, dört bozuk kurulum: stil dosyası yok,
# .bib yok, .bib sözdizimi bozuk, anahtar yok): dördünde de PDF üretildi ve
# kaynakça boştu; `.bib` sözdizimi bozuk olanda panele HİÇ satır ulaşmadı
# (0 hata, 0 uyarı).
#
# Desenler bibtex/biber'e özgü: LaTeX günlüğünde `Warning--` (çift tire),
# `I couldn't open`, `(There were N error messages)` biçimleri geçmiyor.
_RE_BIB_ARAC = re.compile(
    r"^\s*(?:I couldn't open |I found no |Illegal |Repeated entry"
    r"|Sorry|Warning--|\(There (?:was|were) \d+ error messages?\)"
    r"|(?:ERROR|WARN) - )")

# TeX log'u SABİT GENİŞLİKTE sarıyor (`max_print_line`, ölçüldü: 59 gerçek
# şablon logunda 70426 satırın 4147'si tam 79 sütun). Uyarılar da sarıyor ve
# devam satırı hiçbir desene uymadığı için düşüyordu:
#
#   Package natbib Warning: Citation `Abramowitz_1972' on page 7 undefined on input
#    line 241.
#
# Sonuç: mesaj cümle ortasında kesiliyor, "on input line 241" kaybolduğu için
# satır numarası 0 kalıyor (Uyarılar sekmesinde tıklanamıyor) ve error_hints
# deseni eksik metinde eşleşmediği için ipucu da gitmiş oluyor. ÖLÇÜLDÜ:
# 1084 uyarının 344'ü (%31.7) sarıyor, 135'i satır numarasını kaybediyor.
_SARMA = 79
_RE_UYARI_BAS = re.compile(
    r'^\s*(?:LaTeX(?: Font)?|Package \S+) Warning: ')
# Birleştirme YALNIZ uyarılar için. Her 79 sütunluk satırı körlemesine
# birleştirmek GÜVENSİZ: ölçüldü, 4147 tam-79 satırın 395'inin (%9.5)
# ardından gerçek bir yapı satırı geliyor (çoğu `l.NN` hata bağlamı) ve onları
# yutardık.
# Yeni tanınan iki sınıf BURAYA DA girmek zorunda: bu liste "bu satır bir
# yapı başlangıcıdır, önceki sarmış satıra yapıştırma" diyor. ÖLÇÜLDÜ
# (2026-09-14, gerçek korpus): `LaTeX Font Warning` panele ulaşır ulaşmaz,
# ondan önce gelen tam 79 sütunluk bir uyarı onu YUTUYORDU (template3'te
# `Package lineno Warning: ...` satırı panelde iki boşluk girintisiyle tam
# 79 sütun oluyor). İki ayrı uyarı tek satırda birleşip biri kayboluyordu.
# Başındaki isteğe bağlı `dosya.tex: ` derle.sh'nin uyarı önekidir (bkz.
# _RE_UYARI_DOSYASI): önekli bir uyarı da yapı başlangıcı, yoksa 79
# sütunluk bir uyarının ardından gelince ona yapışırdı.
_RE_YAPI_BAS = re.compile(
    r'^\s*(?:\S[^:]*?\.tex: )?'
    r'(?:!|l\.\d+|LaTeX(?: Font)? Warning:|Package \S+ Warning:|'
    r'(?:pdfTeX|LuaTeX|XeTeX) warning|warning\s+\(|Overfull|Underfull|==>|'
    r'Missing character:)', re.IGNORECASE)

# derle.sh ANA BELGE DIŞINDAN gelen uyarının dosyasını öne yazıyor:
#
#     ./bolum/ch1.tex: LaTeX Warning: Reference `x' ... on input line 9.
#
# Uyarılar için TeX'te `-file-line-error` karşılığı yok ve derle.sh GUI'ye
# günlüğün `(dosya ... )` parantezlerini hiç basmıyor, yani dosyayı
# yalnız o biliyor (gerekçe derle.sh'deki `uyari_dosyasi_ekle`de). Önek
# YALNIZ o satırı bağlıyor: sonraki öneksiz satır yığına döner.
#
# Ardından bir uyarı başlığı gelmek ZORUNDA: önek biçimi başka bir satırda
# tesadüfen tutarsa o satır olduğu gibi kalsın. Hata biçimiyle
# (`dosya.tex:3: `) karışmıyor, çünkü orada `.tex`i `:<sayı>` izliyor.
_RE_UYARI_DOSYASI = re.compile(
    r'^(\s*)(\S[^:]*?\.tex): (?=(?:LaTeX|Package|Overfull|Underfull|'
    r'pdfTeX|LuaTeX|XeTeX|Font) )', re.IGNORECASE)


# Hata satırı da sarıyor ama BAŞKA BİÇİMDE: 79 sütun değil, LaTeX'in kendi
# hata biçimlendirmesi cümleyi kelime sınırında ikinci satıra taşıyor:
#
#     ! LaTeX Error: Unicode character ★ (U+2605)
#     not set up for use with LaTeX.
#
# Ayrıştırıcı yalnız ilk satırı alıyordu, yani mesaj cümle ortasında
# kesiliyor ve `error_hints`in TAM BU HATA İÇİN yazılmış deseni
# ("Unicode character .+ not set up") hiç eşleşmiyordu: kullanıcı kırpık
# bir cümle görüyor, ipucu hiç çıkmıyordu. Word'den yapıştırılmış tırnak,
# uzun tire ya da derece işareti pdflatex'te bu hatayı veriyor.
#
# ÖLÇÜT NOKTA: cümle noktayla bitmiyorsa yarım kalmıştır. ÖLÇÜLDÜ
# (2026-09-13, on iki gerçekçi bozuk belge, gerçek derleme):
#
#     nokta ile biten hata satırı      17   (10'unun ardından `<inserted
#                                            text>`, `<read *>` gibi TeX
#                                            BAĞLAM satırı var: onları
#                                            birleştirmek mesajı kirletirdi)
#     noktasız biten                    1   (Unicode hatası; ardındaki satır
#                                            gerçekten cümlenin devamı)
#
# Yani kural bu örneklemde 1/1 doğru birleştiriyor, 17/17 yanlış
# birleştirmeden kaçınıyor.
_RE_HATA_BAS = re.compile(r'^\s*! ')
_CUMLE_SONU = (".", "?", "!")
# Paket hatasının DEVAM satırı `(fontspec)   ...` önekiyle başlıyor (LaTeX'in
# `\PackageError` biçimi). Birleştirirken atılıyor, yoksa cümlenin ortasına
# "(fontspec)" ve bir sıra boşluk giriyordu. Dosya açılışları `(./a.tex`
# gibi yol taşıdığı için desene uymuyor.
_RE_PAKET_DEVAM = re.compile(r'^\([A-Za-z][\w-]*\)\s+')


def _mantiksal_satirlar(ham: list[str]) -> list[str]:
    """Sarmış UYARI ve HATA satırlarını devamlarıyla birleştir."""
    out: list[str] = []
    i, n = 0, len(ham)
    while i < n:
        s = ham[i]
        if _RE_UYARI_BAS.match(s):
            son = s
            while (len(son) == _SARMA and i + 1 < n
                   and ham[i + 1].strip()
                   and not _RE_YAPI_BAS.match(ham[i + 1])):
                son = ham[i + 1]
                s += son
                i += 1
        elif _RE_HATA_BAS.match(s) or _RE_FILE_LINE_ERROR.match(s):
            # Uyarı kolundan farklı olarak BOŞLUKLA ekleniyor: kırılma
            # kelime sınırında, 79. sütunda değil.
            #
            # `-file-line-error` biçimi (`yol:satır: ...`) de burada. Kural
            # yalnız `! ` ile başlayan satırı tanıyordu ve derle.sh motora
            # `-file-line-error` verdiği için hata o biçimde geliyor: kural
            # GERÇEK boru hattında hiç çalışmıyordu. ÖLÇÜLDÜ (2026-09-23,
            # gerçek derle.sh): yukarıda anlatılan Unicode hatası yine
            # "(U+2605)"de kesiliyor ve ipucu çıkmıyordu; fontspec hatası
            # "requires either XeTeX or"da. Aynı biçimdeki bir sonraki hata
            # satırı da birleştirmeyi durduruyor, iki hata birbirine yapışmasın.
            while (not s.rstrip().endswith(_CUMLE_SONU) and i + 1 < n
                   and ham[i + 1].strip()
                   and not _RE_YAPI_BAS.match(ham[i + 1])
                   and not _RE_FILE_LINE_ERROR.match(ham[i + 1])):
                s = (s.rstrip() + " "
                     + _RE_PAKET_DEVAM.sub("", ham[i + 1].strip()))
                i += 1
        out.append(s)
        i += 1
    return out


# Dosya açılışı `(ad.uzanti`, kapanışı `)`. Her açılış yığına giriyor
# (kapanışlar dengelensin diye), ama rapor edilen yalnız kullanıcının
# .tex kaynağı: `.cls`/`.sty` yüklemeleri ebeveynin adını taşıyor.
#
# Ad BOŞLUK taşıyabiliyor: TeX `(./bolum/ch bir.tex` diye yazıyor ve
# boşluksuz desen adı `./bolum/ch` diye kesip eşleşmiyordu, yani dosya
# yığına hiç girmiyor ve içindeki hata ANA BELGEYE atfediliyordu (ölçüldü
# 2026-09-13, hata bilerek belli bir satıra konarak).
#
# Boşluğa izin vermenin bedeli düz yazıyı dosya sanmak. Bu yüzden boşluklu
# aday yalnız DİSKTE VARSA kabul ediliyor (bkz. `_dosya_adayi`); boşluksuz
# adaylarda davranış birebir eskisi gibi kalıyor.
_RE_PAREN = re.compile(r'\((?:\./)?([^()]*?\.[A-Za-z0-9]+)(?=[\s()]|$)|(\))')


def _dosya_adayi(ad: str, base_dir: str) -> bool:
    """Parantez içindeki aday GERÇEKTEN bir dosya mı.

    Yalnız boşluklu adlar için soruluyor; boşluksuzlar eski davranışta
    kalsın diye. Kehanet dosya sisteminin kendisi: TeX ancak var olan bir
    dosyayı açar.
    """
    if " " not in ad:
        return True
    if not base_dir:
        return False
    return os.path.isfile(os.path.join(base_dir, ad))


def _tekille(hatalar: list[LatexError]) -> list[LatexError]:
    """Aynı hatanın İKİNCİ listelenişini ele.

    derle.sh hataları İKİ kez basıyor ve ikisi de aynı derlemeden geliyor:

        [hata] ... derleme basarisiz:   grep -A4  (bağlam satırları DAHİL)
        [hata] ... derleme hatalari:    grep -A1  (bağlam KESİK)

    Panelde her hata İKİ satır oluyordu (ölçüldü 2026-09-14, gerçek
    derleme: tek hatalı belgede 2 satır, üç hatalı belgede 6). Bağlam
    okunur hâle gelince bu daha da kötüleşirdi: aynı hata bir kez komut
    adıyla, bir kez adsız görünürdü.

    Bağlamsız kopya ELENİYOR, bağlamlı olan KALIYOR. Aynı satırda İKİ ayrı
    tanımsız komut varsa ikisi de duruyor, çünkü bağlam satırları farklı
    (TeX kırılma noktasını hatanın olduğu yerde koyuyor).
    """
    sonuc: list[LatexError] = []
    tam: set[tuple] = set()
    baglamli: set[tuple] = set()
    for h in hatalar:
        kimlik = (h.file_path, h.line_number, h.message)
        if (kimlik + (h.context,)) in tam:
            continue
        if not h.context and kimlik in baglamli:
            continue
        tam.add(kimlik + (h.context,))
        if h.context:
            baglamli.add(kimlik)
        sonuc.append(h)
    return sonuc


def parse_output(raw: str, source_file: str = "") -> CompileResult:
    """derle.sh çıktısını parse eder."""
    result = CompileResult()
    result.raw_output = raw
    current_file = source_file
    # Dosya yığını: '(' ile GİR, ')' ile ÇIK. Eskiden yalnız giriş vardı ve
    # çocuk dosya kapandıktan sonraki hatalar hâlâ ona atfediliyordu; F4 ile
    # hata satırına gitmek kullanıcıyı YANLIŞ DOSYAYA götürüyordu (ölçüldü:
    # main.tex:5'teki hata, 3 satırlık bolumler/b1.tex'in 5. satırı diye
    # gösteriliyordu). pdflatex'in `-file-line-error` çıktısına karşı
    # doğrulandı: 59 şablonun 230 hatasında doğruluk %97.4'ten %98.7'ye
    # çıkıyor, gerileme yok.
    dosya_yigini: list[str] = [source_file]
    kaynak_dizin = os.path.dirname(os.path.abspath(source_file)) \
        if source_file else ""

    lines = _mantiksal_satirlar(raw.split('\n'))
    current_error: LatexError | None = None
    # yazı tipi -> [ilk ham satır, kaç kez]. Döngü sonunda tek uyarıya iner.
    eksik_glif: dict[str, list] = {}

    for line in lines:
        # derle.sh'nin uyarı öneki: dosyayı bu satır için sakla, öneki at
        # ki aşağıdaki desenler satırı eskisi gibi tanısın.
        satir_dosyasi = ""
        m = _RE_UYARI_DOSYASI.match(line)
        if m:
            satir_dosyasi = m.group(2)
            line = m.group(1) + line[m.end():]

        # Kaynakça aracının (bibtex/biber) kendi satırı. EN BAŞTA, çünkü
        # `(There were 2 error messages)` satırındaki kapanış parantezi
        # aşağıdaki dosya yığınından bir dosya düşürürdü.
        m = _RE_BIB_ARAC.match(line)
        if m:
            result.warnings.append(LatexWarning(
                message=line.strip(),
                warning_type="BibTeX",
                file_path=source_file,
            ))
            continue

        # Dosya takibi: yalnız kullanıcının .tex kaynağı raporlanır.
        # .cls/.sty/.bib yüklemeleri de yığına girer ki `)` sayısı tutsun, ama
        # ebeveynin adını taşırlar; yoksa hatalar epstopdf-base.sty gibi
        # paketlere atfedilip editörde işaretlenmezdi.
        for pm in _RE_PAREN.finditer(line):
            if pm.group(1):
                ad = pm.group(1)
                if not _dosya_adayi(ad, kaynak_dizin):
                    continue
                kullanilabilir = (ad.endswith(".tex")
                                  and not os.path.isabs(ad))
                dosya_yigini.append(ad if kullanilabilir else dosya_yigini[-1])
            elif len(dosya_yigini) > 1:
                dosya_yigini.pop()
        current_file = satir_dosyasi or dosya_yigini[-1]

        # derle.sh'nin kendi hata satırı
        m = _RE_SCRIPT_ERROR.match(line)
        if m:
            mesaj = m.group(1)
            # İki nokta ile biten satırlar BAŞLIK ("— derleme hatalari:"),
            # ardından gerçek ayrıntılar geliyor; onları hata saymak listeyi
            # ikizlerdi.
            if not mesaj.endswith(":"):
                if current_error:
                    result.errors.append(current_error)
                    current_error = None
                result.errors.append(LatexError(message=mesaj, file_path=current_file))
            continue

        # Paket hatası (daha spesifik, önce kontrol edilmeli)
        m = _RE_PKG_ERROR.match(line)
        if m:
            if current_error:
                result.errors.append(current_error)
            current_error = LatexError(
                message=f"[{m.group(1)}] {m.group(2)}",
                file_path=current_file,
            )
            continue

        # `-file-line-error` biçimi: "./bolum/ch1.tex:3: Undefined ..."
        # Dosyayı ve satırı MOTORUN KENDİSİ söylüyor; parantez yığınından
        # çıkarmaya gerek yok ve zaten derle.sh yalnız hata bloklarını
        # bastığı için yığın oradan hiç beslenmiyordu (bkz. derle.sh'deki
        # HATA_DESENI gerekçesi).
        m = _RE_FILE_LINE_ERROR.match(line)
        if m:
            if current_error:
                result.errors.append(current_error)
            current_error = LatexError(message=m.group(3).strip(),
                                       file_path=m.group(1),
                                       line_number=int(m.group(2)))
            continue

        # Genel hata
        m = _RE_ERROR.match(line)
        if m:
            if current_error:
                result.errors.append(current_error)
            current_error = LatexError(message=m.group(1), file_path=current_file)
            continue

        # Hata bağlamı: "l.42 Kume $\mathbb" satırı. Hem satır numarasını
        # hem de hatanın geçtiği KAYNAK PARÇASINI taşıyor.
        #
        # Bu dal `line_number == 0` koşuluna bağlıydı ve o koşul artık HİÇ
        # sağlanmıyor: derle.sh motora `-file-line-error` veriyor, yani her
        # hata "./d.tex:3: ..." önekiyle geliyor ve satır numarası ZATEN
        # dolu oluyor. Sonuç: `context` her zaman boş kalıyordu ve
        # `error_hints`in tanımsız komudu bağlamdan çıkarmak için yazılmış
        # kolu (135330 komut geçişinde ölçülüp "SON komut alınır" diye
        # ayarlanmıştı) gerçek boru hattında HİÇ çalışmıyordu. Kullanıcı
        # "Tanımsız komut: yazım hatası olabilir..." görüyor, HANGİ komut
        # olduğunu hiç öğrenmiyordu (ölçüldü 2026-09-14, beş belge, gerçek
        # derleme: bağlam taşıyan hata 0/6).
        if current_error:
            m = _RE_LINE_CTX.match(line)
            if m:
                if current_error.line_number == 0:
                    current_error.line_number = int(m.group(1))
                current_error.context = line
                continue

        # LaTeX uyarısı
        m = _RE_LATEX_WARN.match(line)
        if m:
            warn_line = 0
            lm = _RE_WARN_LINE.search(m.group(2))
            if lm:
                warn_line = int(lm.group(1))
            result.warnings.append(LatexWarning(
                message=m.group(2),
                warning_type="Font" if m.group(1) else "LaTeX",
                file_path=current_file,
                line_number=warn_line,
            ))
            continue

        # Motor uyarısı (pdfTeX/LuaTeX): çift \label buradan gelir
        m = _RE_ENGINE_WARN.match(line)
        if m:
            result.warnings.append(LatexWarning(
                message=m.group(2),
                # Adsız biçimi yalnız LuaTeX'in pdf arka ucu yazıyor.
                warning_type=m.group(1) or "LuaTeX",
                file_path=current_file,
            ))
            continue

        # Paket uyarısı
        m = _RE_PKG_WARN.match(line)
        if m:
            warn_line = 0
            lm = _RE_WARN_LINE.search(m.group(2))
            if lm:
                warn_line = int(lm.group(1))
            result.warnings.append(LatexWarning(
                message=m.group(2),
                warning_type=m.group(1),
                file_path=current_file,
                line_number=warn_line,
            ))
            continue

        # Box uyarısı
        m = _RE_BOX_WARN.match(line)
        if m:
            warn_line = 0
            lm = _RE_WARN_LINE.search(line)
            if lm:
                warn_line = int(lm.group(1))
            result.warnings.append(LatexWarning(
                message=line.strip(),
                warning_type=m.group(1),
                file_path=current_file,
                line_number=warn_line,
            ))
            continue

        # Font uyarısı
        m = _RE_FONT_WARN.match(line)
        if m:
            result.warnings.append(LatexWarning(
                message=line.strip(),
                warning_type="Font",
                file_path=current_file,
            ))
            continue

        # Eksik glif: biriktir, döngü sonunda yazı tipi başına tek uyarı
        m = _RE_MISSING_GLYPH.match(line)
        if m:
            duz, tekrar = _tekrar_ayir(line.strip())
            kayit = eksik_glif.setdefault(m.group(1), [duz, 0, 0])
            kayit[1] += tekrar   # PDF'e yazılmayan karakter sayısı
            kayit[2] += 1        # kaç FARKLI karakter (satır)
            continue

        # Öneri: eksik paketi / dil paketi
        m = _RE_SUGGESTION.match(line)
        if m:
            result.suggestions.append(LatexSuggestion(
                message=f"{m.group(1)}: {m.group(2)}",
            ))
            continue

        # Kurulum komutu (öneriye eşlik eden)
        m = _RE_INSTALL.match(line)
        if m and result.suggestions:
            result.suggestions[-1].install_command = m.group(1)
            continue

    if current_error:
        result.errors.append(current_error)

    result.errors = _tekille(result.errors)

    # Eksik glifler: yazı tipi başına tek uyarı. Mesaj ilk GERÇEK log satırını
    # koruyor (error_hints deseni yazı tipi adını oradan çıkarıyor); sayılar
    # sonuna ekleniyor.
    #
    # FARKLI HARF SAYISI DA YAZILIYOR, çünkü satır tek bir örneği gösteriyor:
    # `ş`, `ı`, `İ`, `ğ` düşen bir belgede mesaj yalnız birini adlandırıyor ve
    # okuyan "140 tane ğ mi eksik" diye düşünüyordu.
    for _font, (ilk_satir, adet, farkli) in eksik_glif.items():
        if adet <= 1:
            mesaj = ilk_satir
        elif farkli > 1:
            mesaj = (f"{ilk_satir} (toplam {adet} karakter, "
                     f"{farkli} farklı harf)")
        else:
            mesaj = f"{ilk_satir} (toplam {adet} karakter)"
        result.warnings.append(LatexWarning(
            message=mesaj,
            warning_type="Font",
            file_path=source_file,
        ))

    # Hata mesajlarında motor gereksinimi tespiti
    for err in result.errors:
        m = _RE_ENGINE_REQ.search(err.message)
        if m:
            # İki seçenek varsa ve biri lualatex'se o öneriliyor: uygulamanın
            # varsayılanı ve `engine_detector`ın fontspec için seçtiği motor.
            secenekler = [MOTOR_TAKMA_ADLARI[g.lower()] for g in m.groups() if g]
            required = ("lualatex" if "lualatex" in secenekler
                        else secenekler[0])
            result.suggestions.append(LatexSuggestion(
                message=f"Bu belge {required} gerektiriyor. Derleme motorunu {required} olarak değiştirin.",
            ))
            break

    result.success = len(result.errors) == 0
    return result


def resolve_error_path(file_path: str, base_dir: str) -> str:
    """Hata kaynağı olan dosya yolunu ana dosya dizinine göre çözümle.

    Parser çok dosyalı belgelerde çocuk dosyalar (\\input) için bare filename
    (örn. 'bolum1.tex'), ana dosya için tam yol döndürür. UI katmanı bunu
    base_dir (ana dosyanın dizini) ile birleştirip gerçek yola çevirir; böylece
    F4 ile hata satırına ve gutter işaretine doğru dosyada ulaşılabilir.

    Çözümlenen dosya diskte yoksa (parser yanlış yakalamış olabilir) yolu
    olduğu gibi geri döndürür — çağıran yine de deneyebilir.
    """
    if not file_path:
        return file_path
    if os.path.isabs(file_path) and os.path.isfile(file_path):
        return file_path
    cand = os.path.normpath(os.path.join(base_dir, file_path))
    return cand if os.path.isfile(cand) else file_path

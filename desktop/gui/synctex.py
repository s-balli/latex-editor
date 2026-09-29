"""SyncTeX bridge — ileri/geri arama via synctex CLI."""

import os
import subprocess
import sys
import time
from dataclasses import dataclass

from core.log import get_logger
from core.paths import clean_child_env, windows_to_wsl, wsl_to_windows

_logger = get_logger("synctex")

_PLATFORM = sys.platform

# synctex çağrılarının zaman aşımı. 3 sn'ydi ve DAR bir bütçeydi: sıcak WSL'de
# tüm çağrı ~85 ms sürüyor (ölçüldü — 181 sayfalık belgede de aynı, maliyetin
# tamamı `wsl -e` süreç açılışı, synctex ayrıştırması ihmal edilebilir), yani
# 3 sn aslında SOĞUK WSL başlangıcı için ayrılmış bir bütçe. Bu makinedeki
# dağıtım systemd + snapd + unattended-upgrades ile açılıyor; soğuk başlangıç
# saniyeler sürebiliyor ve bütçeyi aşarsa ileri-arama sessizce düşüyor
# (yalnız log'a warning). Kullanıcının SyncTeX'i ilk denediği an ise tam da
# bilgisayarı yeni açtığı andır — hatanın en olası olduğu yer en görünür yer.
# Uzatmanın bedeli yok: bu çağrılar SyncTexWorker thread'inde koşuyor, UI
# beklemiyor; 15 sn yalnızca gerçekten asılmış bir sürecin warning'ini geciktirir.
_ZAMAN_ASIMI = 15

# Windows'ta konsol penceresi açılmasını engelle
_SUBPROCESS_FLAGS = 0
_SI = None
if _PLATFORM == "win32":
    _SUBPROCESS_FLAGS = subprocess.CREATE_NO_WINDOW
    _SI = subprocess.STARTUPINFO()
    _SI.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    _SI.wShowWindow = 0  # SW_HIDE


class _AracYok:
    """`synctex` ÇALIŞTIRILAMADI işareti; `None` "koştu, eşleşme yok" demek.

    Üç durum vardı ve üçü de `None` dönüyordu, yani kullanıcı üçünde de
    "SyncTeX: Eşleşme bulunamadı" görüyordu. ÖLÇÜLDÜ (2026-09-06):

        synctex kurulu değil (native)   FileNotFoundError
        WSL var, TeX Live yok           çıkış 127, stderr "command not found"
        koştu, o noktada eşleşme yok    çıkış 255, stdout'ta sürüm başlığı

    İlk ikisinde kullanıcı konumu yanlış sanıp aynı yeri tekrar deniyordu;
    yapması gereken TeX Live kurmaktı. Aynı ders `.synctex.gz` denetiminde
    bir kez alınmıştı (bkz. `synctex_ops._on_reverse_search` yorumu).

    FALSY: `if result:` yazan çağıranlar bugünkü davranışı sürdürsün,
    ayrımı isteyen `result is ARAC_YOK` diye sorsun. Böylece işaret bir yerde
    unutulursa sessizce "eşleşme var" sanılmıyor.
    """

    __slots__ = ()

    def __bool__(self) -> bool:
        return False

    def __repr__(self) -> str:                       # pragma: no cover
        return "ARAC_YOK"


ARAC_YOK = _AracYok()

# `wsl -e <komut>` komutu bulamazsa kabuk 127 döndürüyor (ölçüldü). synctex'in
# kendi "eşleşme yok" çıkışı 255; ikisi karışmıyor.
_KOMUT_YOK = 127


@dataclass
class ForwardResult:
    page: int
    x: float
    y: float
    left: float = 0.0   # h alanı — satır sol kenarı
    width: float = 0.0   # W alanı — satır genişliği
    height: float = 0.0  # H alanı — metin yüksekliği


@dataclass
class ReverseResult:
    file_path: str
    line: int
    col: int = 0


def _parse_forward(output: str) -> ForwardResult | None:
    # Birden fazla sonuç var — ilkini al (en yakın eşleşme)
    page = x = y = left = width = height = None
    for ln in output.split('\n'):
        ln = ln.strip()
        if ln.startswith("Page:"):
            if page is not None and x is not None and y is not None:
                break  # İlk sonuç tamam, döngüden çık
            page = int(ln.split(":")[1].strip())
        elif ln.startswith("x:"):
            x = float(ln.split(":")[1].strip())
        elif ln.startswith("y:"):
            y = float(ln.split(":")[1].strip())
        elif ln.startswith("h:"):
            left = float(ln.split(":")[1].strip())
        elif ln.startswith("W:"):
            width = float(ln.split(":")[1].strip())
        elif ln.startswith("H:"):
            height = float(ln.split(":")[1].strip())
    if page is not None and x is not None and y is not None:
        return ForwardResult(page=page, x=x, y=y,
                             left=left or 0.0, width=width or 0.0, height=height or 0.0)
    return None


def _parse_reverse(output: str) -> ReverseResult | None:
    # İLK sonuç alınır, tıpkı `_parse_forward`da olduğu gibi. Döngü eskiden
    # kırılmıyordu, yani SONUNCU kayıt kazanıyordu ve bunun bir gerekçesi de
    # yazılı değildi.
    #
    # ÖLÇÜLDÜ (2026-09-12, 30 gerçek `.synctex.gz`, 143 nokta; her nokta
    # gerçek bir kaynak satırından ileri arama ile üretildi): synctex 18
    # noktada BİRDEN ÇOK kayıt döndürüyor ve 18'inde de ilk ile son farklı.
    # Son kayıt dağılıyor: `egpaper_final.tex` (458 satır) için 19213,
    # `article.tex` (268 satır) için 14722. İkisi de AYNI dosyayı gösteriyor,
    # yani satır numarası doğrudan uydurma. Kullanıcı PDF'te tıklıyor ve
    # editör var olmayan bir satıra atlıyordu.
    #
    # İstenen satırdan sapma, 143 noktanın tamamında:
    #
    #   son kayıt (eski)  ortanca 0, ortalama 245.1, en büyük 19114
    #   ilk kayıt (yeni)  ortanca 0, ortalama   6.6, en büyük   283
    #
    # Dosyada OLMAYAN satıra gönderen nokta: eskiden 2, şimdi 0. İlk kayıt
    # her zaman TAM isabet demek değil (yukarıdaki 283), ama hep aynı
    # dosyanın gerçek bir satırı.
    input_file = line = col = None
    for ln in output.split('\n'):
        ln = ln.strip()
        if ln.startswith("Input:"):
            if input_file is not None and line is not None:
                break                     # ilk sonuç tamam
            input_file = ln.split(":", 1)[1].strip()
        elif ln.startswith("Line:"):
            line = int(ln.split(":")[1].strip())
        elif ln.startswith("Column:"):
            c = ln.split(":")[1].strip()
            col = int(c) if c != "-1" else 0
    if input_file and line is not None:
        return ReverseResult(file_path=input_file, line=line, col=col or 0)
    return None


def forward_search(tex_path: str, line: int, col: int, pdf_path: str,
                   synctex_dir: str = "") -> ForwardResult | None:
    if _PLATFORM == "win32":
        return _forward_wsl(tex_path, line, col, pdf_path, synctex_dir)
    return _forward_native(tex_path, line, col, pdf_path, synctex_dir)


# Ters aramada komşu noktalar (punto): sonuç şüpheliyse (bkz. `_supheli`)
# sırayla bunlara bakılıyor. İlk dördü sözcük ölçeğinde. Sola büyüyen adımlar
# satır sonu boşluğu için: LuaTeX'te boşluğun tamamı gönderilme konumunu
# verebiliyor ve o satırın metni hep solda kalıyor.
_KOMSULAR = (-8, 8, -16, 16, -32, -64, -128, -256, -384)

# Ek sorguların (köşe ve komşular) süre bütçesi. Sıcak WSL'de sorgu ~85 ms,
# yerlide ~10 ms. İlk sorgu bundan uzun sürdüyse (soğuk WSL, asılı süreç)
# ek sorgu yapılmıyor: tek tıklama altı kez zaman aşımı beklemesin.
_EK_SORGU_BUTCESI = 1.5


def reverse_search(page: int, x: float, y: float, pdf_path: str,
                   synctex_dir: str = "") -> ReverseResult | None:
    """PDF noktasının kaynak dosyası ve satırı.

    LuaTeX sayfayı gönderirken oluşan bazı düğümlere O ANKİ giriş konumunu
    yazıyor: paragrafların içinde sayfanın gönderildiği satırı (çoğu zaman
    sonraki bölümün dosyası) gösteren kayıtlar var, o noktaya tıklamak
    başka bir dosyaya atlıyordu. ÖLÇÜLDÜ (2026-09-27, gerçek derleme, üç
    bölüm dosyalı beş sayfalık tez, her cümle kendi satırında, karakterlerin
    üstüne 464-467 tıklama, doğru satır):

        motor                   eskiden   şimdi
        lualatex (varsayılan)   406       460
        lualatex + fontspec     410       463
        pdflatex                464       464
        xelatex                 465       465

    Başka dosya ya da sonuçsuz: LuaTeX'te 38 ve 34'ten 3'e. Sayfanın gönderilme
    konumunu köşe sorgusu veriyor (sayfanın dış kutusu). Sonuç şüpheliyse
    (bkz. `_supheli`) yandaki noktalara bakılıyor, sonuç ancak komşu şüpheli
    olmayan bir konum verirse değişiyor. Maliyet tıklama başına bir köşe
    sorgusu; komşulara yalnız şüpheli sonuçta bakılıyor.

    SATIR SONU BOŞLUĞU VE YANLIŞ DOSYA ADI (ölçüldü 2026-09-29, article ve
    report sınıfı iki belge, bölüm dosyaları `\\input` ile; kehanet
    `pdftotext -bbox-layout`: sözcüğün doğru hedefi sözcüğün kaynak satırı,
    satır sonu boşluğununki o görsel satırdaki sözcüklerin satırları).
    LuaTeX'te satır sonundaki boşluğun tamamı gönderilme konumunu
    verebiliyor ve ±16 pt komşular da o boşlukta kalıyordu:

        motor      tık      doğru satır (eski / yeni)   başka dosya ya da boş
        lualatex   boşluk   75 / 103 (111)              28 / 0
        lualatex   sözcük   127 / 134 (139)             7 / 0
        xelatex    boşluk   105 / 106 (111)             1 / 0
        xelatex    sözcük   132 / 134 (139)             2 / 0
        pdflatex   ikisi    değişmedi                   0 / 0

    Kalan yanlışların hepsi aynı dosyada bir yan satır; aynısı pdflatex'te
    de var (SyncTeX'in kendi çözünürlüğü). Satırların en sol ucuna da tıklayan
    canlı kapıda (tests/test_synctex_live.py, bölüm sonu sayfası, 54 tık)
    başka dosyaya giden: lualatex 15'ten 0'a, pdflatex 2'den 0'a.
    """
    if _PLATFORM == "win32":
        return _reverse_search_wsl(page, x, y, pdf_path, synctex_dir)
    tek = _reverse_native
    t0 = time.monotonic()
    sonuc = tek(page, x, y, pdf_path, synctex_dir)
    if sonuc is ARAC_YOK or time.monotonic() - t0 > _EK_SORGU_BUTCESI:
        return sonuc
    bitis = time.monotonic() + _EK_SORGU_BUTCESI
    gonderilme = tek(page, 1.0, 1.0, pdf_path, synctex_dir)
    kok = os.path.dirname(os.path.normcase(os.path.abspath(pdf_path)))
    if _supheli(sonuc, gonderilme, kok):
        for dx in _KOMSULAR:
            if time.monotonic() > bitis:
                break
            if x + dx < 0:
                continue
            komsu = tek(page, x + dx, y, pdf_path, synctex_dir)
            if not _supheli(komsu, gonderilme, kok):
                return komsu
    return sonuc


def _reverse_search_wsl(page: int, x: float, y: float, pdf_path: str,
                        synctex_dir: str = "") -> ReverseResult | None:
    """`reverse_search`in Windows kolu: aynı seçim, sorgular TOPLU.

    Her sorgu ayrı bir `wsl -e` süreciydi (sıcak WSL'de ~85 ms, maliyetin
    tamamı süreç açılışı) ve şüpheli sonuçta tık başına on bire kadar sorgu
    gidiyordu: kısa bir satırın sağındaki boşluğa Ctrl+tık ~1 sn sürüyordu.
    Artık iki süreç: tıklanan nokta ile köşe BİRLİKTE, gerekirse bütün
    komşular BİRLİKTE. Seçim kuralı yerli koldakiyle aynı (ilk şüpheli
    olmayan komşu, yoksa ilk sonuç).

    Süre bütçesi yok: yerli kolda ek sorgu başına ayrı zaman aşımı
    bekleniyordu, burada ilk toplu sorgu düşerse komşulara hiç gidilmiyor.
    """
    ilk = _reverse_wsl_toplu(page, [(x, y), (1.0, 1.0)], pdf_path, synctex_dir)
    if ilk is ARAC_YOK or ilk is None:
        return ilk
    sonuc, gonderilme = ilk
    kok = os.path.dirname(os.path.normcase(os.path.abspath(pdf_path)))
    if not _supheli(sonuc, gonderilme, kok):
        return sonuc
    komsular = [(x + dx, y) for dx in _KOMSULAR if x + dx >= 0]
    sonuclar = _reverse_wsl_toplu(page, komsular, pdf_path, synctex_dir)
    for komsu in sonuclar if isinstance(sonuclar, list) else ():
        if not _supheli(komsu, gonderilme, kok):
            return komsu
    return sonuc


def _supheli(sonuc, gonderilme, kok: str = "") -> bool:
    """Sonuç kullanıcının metni olamayacak bir yer mi.

    Üç durum:

    - Boş sonuç.
    - Sayfanın gönderilme konumu ya da AYNI dosyada ondan sonraki bir satır.
      Sayfa gönderilme konumunda (köşe sorgusu) gönderiliyor; sayfadaki her
      şey o konumdan ÖNCE okunmuş. Üç motorda da öyle kayıtlar var: bir
      bölüm dosyasının son paragrafını sonraki dosyanın `\\newpage`i
      kapatınca o paragrafın satır kutuları SONRAKİ dosyanın adını, kendi
      satır numaralarını taşıyor (ölçüldü 2026-09-29: `yontem.tex:9` yerine
      `sonuc.tex:9`, oysa sonuc.tex altı satır; pdflatex'te yalnız satırın
      en sol ucunda).
    - PDF'in dizininin (`kok`) dışındaki bir dosya. LuaTeX'te gönderilme
      konumunu veren bölgelerin arasında `article.cls:0` gibi tek noktalık
      kayıtlar var (ölçüldü 2026-09-29); komşu taraması onlara düşünce
      editörde TeX dağıtımının sınıf dosyası açılıyordu. Projedeki kendi
      .cls dosyası dışarıda sayılmıyor.

    Tümü şüpheliyse ilk sonuç korunuyor (bkz. `reverse_search`), yani
    yanlış alarmın bedeli yalnız ek sorgu.
    """
    if not sonuc:
        return True
    if kok and os.path.isabs(sonuc.file_path):
        # Kökle AYNI biçimde (abspath): yoksa POSIX yolu Windows'ta sürücüsüz
        # kalıp her sonucu dışarıda gösterirdi.
        yol = os.path.normcase(os.path.abspath(sonuc.file_path))
        try:
            if os.path.commonpath([yol, kok]) != kok:
                return True
        except ValueError:              # başka sürücü ya da WSL yolu
            return True
    return (bool(gonderilme) and sonuc.file_path == gonderilme.file_path
            and sonuc.line >= gonderilme.line)


# Bu dosyadaki beş subprocess.run çağrısı da encoding="utf-8" GEÇMEK ZORUNDA.
# text=True + encoding yoksa Python locale.getpreferredencoding() kullanır;
# Türkçe Windows'ta bu cp1254'tür. Proje yolu Türkçe karakter içerdiğinde
# (C:\Users\Şerif\... çok yaygın) synctex çıktısındaki yol UTF-8 gelir ve
# cp1254'te tanımsız bayta denk gelir: 'Ş' = C5 9E, cp1254'te 0x9E YOK.
# Çözme hatası OKUMA THREAD'inde oluştuğu için run() istisna FIRLATMAZ —
# r.stdout None olur, returncode 0 kalır, guard'dan geçer ve _parse_*(None)
# AttributeError verir. except kolu onu yakalamıyor; synctex_worker'ın geniş
# except'i yutuyor ve SyncTeX Türkçe yollu projede sessizce hiç çalışmıyordu.
# 'r.stdout is None' denetimi ikinci savunma hattı: encoding sorunu dışında
# bir nedenle de None gelirse sessiz AttributeError yerine düzgün None dönsün.


def _forward_wsl(tex_path: str, line: int, col: int, pdf_path: str,
                synctex_dir: str = "") -> ForwardResult | None:
    # Bağ çözme YERLİ kolda vardı, burada YOKTU. Windows'ta da gerekli:
    # dizin bağlantısı (junction) altındaki bir projede derleme gerçek yolu
    # kaydeder, sorgu ise bağ yolunu taşır ve adlar eşleşmez. Kusur macOS'ta
    # `/private/var` ile görülmüştü; aynı kusur bu kolda duruyordu ve
    # Windows'ta hiçbir canlı test koşmadığı için görünmüyordu.
    tex_path = _gercek_yol(tex_path)
    pdf_path = _gercek_yol(pdf_path)
    cmd = ["wsl", "-e", "synctex", "view",
           "-i", f"{line}:{col}:{windows_to_wsl(tex_path)}",
           "-o", windows_to_wsl(pdf_path)]
    if synctex_dir:
        cmd += ["-d", windows_to_wsl(synctex_dir)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=_ZAMAN_ASIMI,
                           startupinfo=_SI, creationflags=_SUBPROCESS_FLAGS)
        if r.returncode == _KOMUT_YOK:
            return ARAC_YOK
        if r.returncode != 0 or r.stdout is None:
            return None
        return _parse_forward(r.stdout)
    except subprocess.TimeoutExpired as e:
        _logger.warning("SyncTeX forward (WSL) zaman aşımı: %s:%d (%s)", tex_path, line, e)
        return None
    except (FileNotFoundError, OSError) as e:
        _logger.warning("SyncTeX forward (WSL) çalıştırılamadı: %s:%d (%s)", tex_path, line, e)
        return ARAC_YOK


def _gercek_yol(yol: str) -> str:
    r"""Sembolik bağları çözülmüş yol.

    macOS'ta `/tmp` ve `/var` birer sembolik bağ (`/private/...`).
    Derleyici belgeyi bir yol biçimiyle kaydediyor, `synctex` öteki
    biçimle sorulunca ADI EŞLEŞTİREMİYOR ve BOŞ dönüyor: hata yok,
    çıkış kodu 0, sonuç yok.

    ÖLÇÜLDÜ (2026-09-18, macos-15, aynı belge aynı komutla, yalnız yol
    biçimi değişerek):

        /var/folders/.../tmp.X        Page satiri: 0   (bulamiyor)
        /private/var/folders/.../X    Page satiri: 1   (buluyor)

    Linux'ta ve Windows'ta sembolik bağ yoksa işlev hiçbir şey
    değiştirmiyor; çözülemeyen yol olduğu gibi dönüyor.

    VAR OLMAYAN yola dokunulmuyor. `os.path.realpath` yolu mutlaklaştırıyor
    da: POSIX'te `C:\Users\...` GÖRECELİ sayılıp başına çalışma dizini
    ekleniyor. Üründe bu yollar her zaman var (derleme onları yeni üretti),
    ama WSL kolunu POSIX'te taklit eden birim testleri sahte Windows yolları
    veriyor ve çeviri bozuluyordu (üç test düştü). Var olmayan yolda çözecek
    bir bağ da yok, yani kısıt bedava.
    """
    try:
        if not os.path.exists(yol):
            return yol
        return os.path.realpath(yol)
    except OSError:                   # pragma: no cover
        return yol


def _kullanici_yoluna(sonuc, pdf_path: str):
    """Ters aramanın sonucunu kullanıcının PDF'e verdiği yol biçimine çevir.

    Sorgu `_gercek_yol`dan geçiyor ve TeX dosya adlarını çalışma dizininin
    GERÇEK yoluyla kaydediyor (getcwd bağları çözüyor). Proje sembolik bağ
    ya da dizin bağlantısı altındaysa sonuç bu yüzden bağsız biçimde
    geliyordu; macOS'ta `/var` ve `/tmp` de birer bağ. Proje kökü ise
    kullanıcının yolundan hesaplanıyor (`reverse_search`): her sonuç proje
    dışı sayılıp şüpheli oluyor, başka dosyaya atlama kuralı (`_supheli`)
    devre dışı kalıyor ve editör dosyayı kullanıcının açtığından başka bir
    yolla açıyordu. ÖLÇÜLDÜ (2026-09-29, macos-15, bölüm sonu sayfası):
    lualatex'te 88 tıkın 88'i `/private/var/...` ile döndü, gösterilen ilk
    altısının beşi `sonuc.tex`e atlıyordu.

    PDF'in gerçek klasörü altındaki sonuç, aynı göreli yolla kullanıcının
    klasörüne taşınıyor; dışındakine (TeX dağıtımının dosyaları) dokunulmuyor.
    """
    if not sonuc or not os.path.isabs(sonuc.file_path):
        return sonuc
    klasor = os.path.dirname(os.path.abspath(pdf_path))
    gercek = os.path.dirname(_gercek_yol(os.path.abspath(pdf_path)))
    if os.path.normcase(klasor) == os.path.normcase(gercek):
        return sonuc
    try:
        ic = os.path.relpath(sonuc.file_path, gercek)
    except ValueError:                # başka sürücü
        return sonuc
    if ic == os.pardir or ic.startswith(os.pardir + os.sep):
        return sonuc
    sonuc.file_path = os.path.join(klasor, ic)
    return sonuc


def _forward_native(tex_path: str, line: int, col: int, pdf_path: str,
                    synctex_dir: str = "") -> ForwardResult | None:
    tex_path = _gercek_yol(tex_path)
    pdf_path = _gercek_yol(pdf_path)
    cmd = ["synctex", "view",
           "-i", f"{line}:{col}:{tex_path}",
           "-o", pdf_path]
    if synctex_dir:
        cmd += ["-d", synctex_dir]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace",
                           timeout=_ZAMAN_ASIMI, env=clean_child_env())
        if r.returncode == _KOMUT_YOK:
            return ARAC_YOK
        if r.returncode != 0 or r.stdout is None:
            return None
        return _parse_forward(r.stdout)
    except subprocess.TimeoutExpired as e:
        _logger.warning("SyncTeX forward (native) zaman aşımı: %s:%d (%s)", tex_path, line, e)
        return None
    except (FileNotFoundError, OSError) as e:
        _logger.warning("SyncTeX forward (native) çalıştırılamadı: %s:%d (%s)", tex_path, line, e)
        return ARAC_YOK


# Koordinat synctex'e KESİRLİ veriliyor. `int(x)`/`int(y)` ile kırpılıyordu
# ve bunun bir gerekçesi yazılı değildi; kullanıcının tıkladığı nokta bir
# puntoya kadar kaydırılmış oluyordu. Satır yüksekliği ~9 pt, yani 1 pt
# satır sınırında cevabı değiştirebiliyor. ÖLÇÜLDÜ (2026-09-12, 142 nokta):
# kırpmak 11 noktada FARKLI satır döndürüyor; tam isabet 76'ya karşı 80,
# istenen satırdan ortalama sapma 4.7'ye karşı 4.5. Kazanç küçük ama tek
# yönlü ve bedeli yok: synctex kesirli koordinatı zaten kabul ediyor.
def _reverse_wsl(page: int, x: float, y: float, pdf_path: str,
                synctex_dir: str = "") -> ReverseResult | None:
    gercek_pdf = _gercek_yol(pdf_path)    # bkz. _forward_wsl'deki gerekçe
    wsl_pdf = windows_to_wsl(gercek_pdf)
    cmd = ["wsl", "-e", "synctex", "edit",
           "-o", f"{page}:{x:f}:{y:f}:{wsl_pdf}"]
    if synctex_dir:
        cmd += ["-d", windows_to_wsl(synctex_dir)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=_ZAMAN_ASIMI,
                           startupinfo=_SI, creationflags=_SUBPROCESS_FLAGS)
        if r.returncode == _KOMUT_YOK:
            return ARAC_YOK
        if r.returncode != 0 or r.stdout is None:
            return None
        parsed = _parse_reverse(r.stdout)
        if parsed:
            # `ornek` PDF'in Windows yolu: proje WSL'in KENDİ dosya
            # sisteminde duruyorsa dağıtım adı yalnız oradan öğrenilebiliyor
            # (gerekçe ve üretilmiş örnek core/paths.py'de).
            parsed.file_path = wsl_to_windows(parsed.file_path,
                                              ornek=gercek_pdf)
        return _kullanici_yoluna(parsed, pdf_path)
    except subprocess.TimeoutExpired as e:
        _logger.warning("SyncTeX reverse (WSL) zaman aşımı: sayfa %d (%s)", page, e)
        return None
    except (FileNotFoundError, OSError) as e:
        _logger.warning("SyncTeX reverse (WSL) çalıştırılamadı: sayfa %d (%s)", page, e)
        return ARAC_YOK


# Toplu sorguda her `synctex edit`in çıktısının sonuna düşen işaret; ardından
# o sorgunun çıkış kodu geliyor.
_TOPLU_AYRAC = "@@latex-editor-synctex@@"


def _reverse_wsl_toplu(page: int, noktalar: list, pdf_path: str,
                       synctex_dir: str = ""):
    """Birden çok noktayı TEK `wsl -e sh` sürecinde sor.

    Dönüş: nokta başına sonuç listesi (eşleşme yoksa None), synctex
    çalıştırılamadıysa ARAC_YOK, süreç düştüyse None. Argümanlar kabuğa
    konumsal parametre olarak gidiyor (`"$@"`), yol betiğe gömülmüyor:
    boşluklu ve Türkçe yollar tek sorgudaki gibi aynen geçiyor.
    """
    gercek_pdf = _gercek_yol(pdf_path)    # bkz. _forward_wsl'deki gerekçe
    wsl_pdf = windows_to_wsl(gercek_pdf)
    betik = (('d="$1"; shift; ' if synctex_dir else '')
             + 'for o in "$@"; do synctex edit -o "$o"'
             + (' -d "$d"' if synctex_dir else '')
             + '; echo "' + _TOPLU_AYRAC + ' $?"; done')
    cmd = ["wsl", "-e", "sh", "-c", betik, "sh"]
    if synctex_dir:
        cmd.append(windows_to_wsl(synctex_dir))
    cmd += [f"{page}:{nx:f}:{ny:f}:{wsl_pdf}" for nx, ny in noktalar]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=_ZAMAN_ASIMI,
                           startupinfo=_SI, creationflags=_SUBPROCESS_FLAGS)
    except subprocess.TimeoutExpired as e:
        _logger.warning("SyncTeX reverse (WSL) zaman aşımı: sayfa %d (%s)", page, e)
        return None
    except (FileNotFoundError, OSError) as e:
        _logger.warning("SyncTeX reverse (WSL) çalıştırılamadı: sayfa %d (%s)", page, e)
        return ARAC_YOK
    sonuclar, blok = [], []
    for satir in (r.stdout or "").split("\n"):
        if not satir.startswith(_TOPLU_AYRAC):
            blok.append(satir)
            continue
        kod = satir[len(_TOPLU_AYRAC):].strip()
        if kod == str(_KOMUT_YOK) and not sonuclar:
            return ARAC_YOK
        parsed = _parse_reverse("\n".join(blok)) if kod == "0" else None
        if parsed:
            # `ornek` PDF'in Windows yolu (bkz. _reverse_wsl).
            parsed.file_path = wsl_to_windows(parsed.file_path, ornek=gercek_pdf)
        sonuclar.append(_kullanici_yoluna(parsed, pdf_path))
        blok = []
    if len(sonuclar) != len(noktalar):
        # wsl.exe kabuğu hiç başlatamadı (dağıtım yok) ya da çıktı yarım.
        return ARAC_YOK if r.returncode == _KOMUT_YOK else None
    return sonuclar


def _reverse_native(page: int, x: float, y: float, pdf_path: str,
                    synctex_dir: str = "") -> ReverseResult | None:
    gercek_pdf = _gercek_yol(pdf_path)
    cmd = ["synctex", "edit",
           "-o", f"{page}:{x:f}:{y:f}:{gercek_pdf}"]
    if synctex_dir:
        cmd += ["-d", synctex_dir]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace",
                           timeout=_ZAMAN_ASIMI, env=clean_child_env())
        if r.returncode == _KOMUT_YOK:
            return ARAC_YOK
        if r.returncode != 0 or r.stdout is None:
            return None
        return _kullanici_yoluna(_parse_reverse(r.stdout), pdf_path)
    except subprocess.TimeoutExpired as e:
        _logger.warning("SyncTeX reverse (native) zaman aşımı: sayfa %d (%s)", page, e)
        return None
    except (FileNotFoundError, OSError) as e:
        _logger.warning("SyncTeX reverse (native) çalıştırılamadı: sayfa %d (%s)", page, e)
        return ARAC_YOK
